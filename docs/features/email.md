# Feature: Email bounces and complaints (Amazon SES via SNS)

Built 2026-10-25 (branch feature/email-signup). It is what we told AWS: bounce and complaint notifications are published to Amazon SNS and delivered to the application, which flags the address and stops all further email to it.

## How it works

- SES publishes bounce and complaint feedback to the SNS topic `spa99-ses-feedback` (eu-west-2). SNS POSTs it to `POST https://spa99.uk/ses/notifications/` (public host, no login, CSRF exempt, marked PUBLIC in `config/urls.py`).
- The endpoint is **off (404) while `SES_SNS_TOPIC_ARN` is empty**. When set, a message is accepted only if its `TopicArn` equals that value AND its signature verifies (SignatureVersion 1 and 2, `cryptography`) against a certificate downloaded only from an `https://sns.<region>.amazonaws.com/` address (exact host, no redirects, cached a day). Anything else: 403 and a log line. Body limit 256 KB. The certificate and SubscribeURL host must be `sns.<region>.amazonaws.com` for the region in the topic ARN (region-shaped, so `sns.s3.amazonaws.com` is refused). Messages with a Timestamp over an hour old are refused (no replay). A body that is not JSON gets 400.
- `SubscriptionConfirmation`: after the same checks the app fetches the `SubscribeURL` (same host rule) and logs it, so the subscription confirms itself.
- `Notification` with an SES message: permanent bounce adds each bounced address to `notifications.EmailSuppression` (reason `hard_bounce`); complaint adds each complained address (`complaint`, the stronger reason replaces a bounce). Transient bounces and deliveries are ignored. A repeat of the same SES feedback id changes nothing (SNS delivers at least once).
- **The guard:** `notifications.services.send_templated` is the only way the site sends email. It drops suppressed addresses from To and CC (case-insensitive), logs a warning (no address), and if nobody is left writes an `EmailLog` row with status `suppressed` and returns it. It never raises, so a password reset for a suppressed address gives the same page as any other.
- The address stays suppressed even if the person deletes their account (it holds only the address; sending again would harm our reputation).

## Postmark bounces and complaints (2026-10-27, feature/postmark-bounces)

Launch mail goes through Postmark, so its bounces reach the same `notifications.EmailSuppression` list as SES feedback does.

- Endpoint `POST /postmark/webhook/` (public, CSRF exempt, JSON, marked PUBLIC in `config/urls.py`, rate limited 300 a minute per IP). Code: `notifications/postmark.py`, view `postmark_webhook`.
- **Off (404) unless both `POSTMARK_WEBHOOK_USER` and `POSTMARK_WEBHOOK_PASSWORD` are set.** Then HTTP Basic is required (`hmac.compare_digest`); wrong or missing credentials: 401. Prod starts fine without them.
- `RecordType` `SpamComplaint` (or a Bounce of Type `SpamComplaint`) is stored as `complaint`. A `Bounce` of Type `HardBounce`, `BadEmailAddress` or `ManuallyDeactivated`, or any bounce with `Inactive: true` (Postmark itself stopped sending), is stored as `hard_bounce`. SoftBounce, Transient, AutoResponder and the rest are ignored.
- A bounce of Type `Unsubscribe` (the recipient asked to be removed) is stored as `complaint`. Non-string `Email`/`Type`/`RecordType` and addresses that fail `validate_email` (shared with SES, in `suppression.py`) are ignored with 200.
- **Bounce log (2026-10-30):** every Bounce and SpamComplaint record (soft ones too) is also stored in `notifications.EmailBounce` (`notifications/bouncelog.py`): email (lower), kind hard / soft / complaint / other (from Postmark's Type), Postmark type, detail (300), record id (unique when not blank, so a retry adds nothing), message id, received_at (BouncedAt, else ReceivedAt, else now). Suppression rules are unchanged; a failure to log never stops suppression. System > Emails > **Bounces** shows the latest 500 (`?kind=`), with a Suppressed badge, and the System Dashboard has a "Bounces, last 7 days" tile. `common.tasks.housekeeping` deletes rows older than 365 days. Like suppressions, the log is not erased with an account (address only, no account link).
- **Invite email opens (2026-10-30):** the Postmark `Open` event (tick it on the webhook) carries `Metadata.invite`, the invite token we set in the `X-PM-Metadata-invite` header on invite emails only (`mailings.invites.open_tracking_headers`; the same send also sets `X-PM-TrackOpens: true` and `X-PM-Tag: invite`). `mailings.invites.mark_email_opened` sets `Invite.email_opened_at` on the first open only; no or bad metadata is ignored (never matched by address); always 200. This is not the link click (`opened_at`, status OPENED). The privacy notice says invitation emails contain a tracking pixel.
- Staff: if a member says they get no reset or other email, check System > Email suppressions and remove the address (a bounce or complaint blocks every email to it, resets included).
- Valid records we ignore answer 200 (Postmark retries anything else). A body that is not a JSON object: 400.
- Same upsert as SES (`suppression.add`: lower case, first_seen / last_seen, count, invites and mailing rows marked bounced). The feedback id is the Postmark record `ID`, so a retry of the same record changes nothing; a new bounce for the same address updates `last_seen`. `EmailLog` is not touched: it stores no Postmark message id (SES does not update it either).
- Logs hold the record type and a count, never the address or the credentials.
- Setup: see `docs/GO-LIVE.md` steps 3 and 9. Tests: `notifications/tests/test_postmark_feedback.py`.

## Seeing and removing (System, Developer level, behind the unlock)

`/suppressions/` ("Email suppressions"): email, reason, last seen, count, and **Remove**. Remove writes a `suppress_removed` event to the System audit log first (nothing is removed if that cannot be written). The Django admin has a read-only list with CSV export. `manage.py ses_suppressions --list` / `--remove EMAIL` also exist (not audit logged: prefer System).

## Setup Moishe must do in AWS (eu-west-2, London)

1. SNS, Topics, Create topic, type **Standard**, name `spa99-ses-feedback`. Copy the topic ARN.
2. SES, Identities, `spa99.uk`, Notifications tab, Feedback notifications, Edit: Bounce feedback and Complaint feedback each go to SNS topic `spa99-ses-feedback`; **Include original email headers: off**. Leave Delivery feedback unset.
3. Put the ARN in the live `.env` as `SES_SNS_TOPIC_ARN=arn:aws:sns:eu-west-2:137808120968:spa99-ses-feedback` (topic created 2026-10-25), deploy, check that a POST to `https://spa99.uk/ses/notifications/` (for example `curl -X POST -d '{}' https://spa99.uk/ses/notifications/`) answers 400 or 403, not 404 (404 means the variable is not set; a GET answers 405 either way).
4. **Only once the site is live:** SNS, the topic, Create subscription, protocol **HTTPS**, endpoint `https://spa99.uk/ses/notifications/`. It confirms itself within seconds (status Confirmed); if it stays Pending, check the app logs for "SES feedback refused".
5. SES, Configuration, Suppression list: confirm account-level suppression is on for Bounces and Complaints.
6. The IAM role of the server needs nothing extra (SNS calls us; we do not call AWS SNS).

Until the site is live the subscription cannot be confirmed (SNS cannot reach the endpoint), but the SES account-level suppression list already protects sending: SES itself refuses addresses that bounced or complained. The app list adds our own record and stops us even attempting to send.

## Tests

`notifications/tests/test_ses_feedback.py`: signature accept and reject (throwaway key and certificate, download patched), wrong topic, evil certificate and subscribe hosts, subscription confirmation, permanent and transient bounce, complaint, repeats, the guard for every account email, the same reset answer, and the System remove (audit logged, 404 below Developer). The signature tests skip themselves if `cryptography` is not installed.

## Unsubscribe, List-Unsubscribe and rate (2026-10-25, feature/emails)

- News mailings and invites carry a one-click unsubscribe link `/unsubscribe/<signed token>/` (no login, no expiry) in the footer and the headers `List-Unsubscribe: <url>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058; the SES backend sends the raw message, so the headers go through). GET shows a confirm page, POST (and the one-click POST from the mail client, CSRF exempt) sets `marketing_consent` off through `member.set_marketing_consent` (history logged) or, for an address with no account, adds it to `mailings.EmailOptOut`. Service messages have no unsubscribe and say why the person receives them.
- Suppression stays the guard: group sends and invites go through `send_templated`, so a suppressed address is skipped (`suppressed` in the EmailLog, `skipped` on the recipient). A hard bounce or complaint also marks that address's invites and recent group-send rows `bounced`.
- Send rate: group sends and invites go out at `MAILING_RATE_PER_SECOND` (settings, default 10, never above SES `MaxSendRate`) from a background task in slices; none when the queue runs inline in dev.
- `send_templated(..., headers=None, body=None)`; `EmailLog.message_id` keeps the SES message id. The wording of the automatic emails is editable (`NotificationTemplate.body`, `notifications/emailbody.py`): see `docs/features/system-emails.md`.
- The SES production gate (`notifications.ses_status()`): group sends and invites only start when SES reports production access (or in development). Full detail in `docs/features/system-emails.md`.
- Password changed: after any signed-in change or completed reset (team accounts too) `users.services.password_changed` queues `password_changed` (editable, see `docs/features/system-emails.md`); a first password from an invite sends nothing.
