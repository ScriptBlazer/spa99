# Feature: Email bounces and complaints (Amazon SES via SNS)

Built 2026-10-25 (branch feature/email-signup). It is what we told AWS: bounce and complaint notifications are published to Amazon SNS and delivered to the application, which flags the address and stops all further email to it.

## How it works

- SES publishes bounce and complaint feedback to the SNS topic `spa99-ses-feedback` (eu-west-2). SNS POSTs it to `POST https://spa99.uk/ses/notifications/` (public host, no login, CSRF exempt, marked PUBLIC in `config/urls.py`).
- The endpoint is **off (404) while `SES_SNS_TOPIC_ARN` is empty**. When set, a message is accepted only if its `TopicArn` equals that value AND its signature verifies (SignatureVersion 1 and 2, `cryptography`) against a certificate downloaded only from an `https://sns.<region>.amazonaws.com/` address (exact host, no redirects, cached a day). Anything else: 403 and a log line. Body limit 256 KB. The certificate and SubscribeURL host must be `sns.<region>.amazonaws.com` for the region in the topic ARN (region-shaped, so `sns.s3.amazonaws.com` is refused). Messages with a Timestamp over an hour old are refused (no replay). A body that is not JSON gets 400.
- `SubscriptionConfirmation`: after the same checks the app fetches the `SubscribeURL` (same host rule) and logs it, so the subscription confirms itself.
- `Notification` with an SES message: permanent bounce adds each bounced address to `notifications.EmailSuppression` (reason `hard_bounce`); complaint adds each complained address (`complaint`, the stronger reason replaces a bounce). Transient bounces and deliveries are ignored. A repeat of the same SES feedback id changes nothing (SNS delivers at least once).
- **The guard:** `notifications.services.send_templated` is the only way the site sends email. It drops suppressed addresses from To and CC (case-insensitive), logs a warning (no address), and if nobody is left writes an `EmailLog` row with status `suppressed` and returns it. It never raises, so a password reset for a suppressed address gives the same page as any other.
- The address stays suppressed even if the person deletes their account (it holds only the address; sending again would harm our reputation).

## Seeing and removing (System, Developer level, behind the unlock)

`/suppressions/` ("Email suppressions"): email, reason, last seen, count, and **Remove**. Remove writes a `suppress_removed` event to the System audit log first (nothing is removed if that cannot be written). The Django admin has a read-only list with CSV export. `manage.py ses_suppressions --list` / `--remove EMAIL` also exist (not audit logged: prefer System).

## Setup Moishe must do in AWS (eu-west-2, London)

1. SNS, Topics, Create topic, type **Standard**, name `spa99-ses-feedback`. Copy the topic ARN.
2. SES, Identities, `spa99.uk`, Notifications tab, Feedback notifications, Edit: Bounce feedback and Complaint feedback each go to SNS topic `spa99-ses-feedback`; **Include original email headers: off**. Leave Delivery feedback unset.
3. Put the ARN in the live `.env` as `SES_SNS_TOPIC_ARN=arn:aws:sns:eu-west-2:...:spa99-ses-feedback`, deploy, check that a POST to `https://spa99.uk/ses/notifications/` (for example `curl -X POST -d '{}' https://spa99.uk/ses/notifications/`) answers 400 or 403, not 404 (404 means the variable is not set; a GET answers 405 either way).
4. **Only once the site is live:** SNS, the topic, Create subscription, protocol **HTTPS**, endpoint `https://spa99.uk/ses/notifications/`. It confirms itself within seconds (status Confirmed); if it stays Pending, check the app logs for "SES feedback refused".
5. SES, Configuration, Suppression list: confirm account-level suppression is on for Bounces and Complaints.
6. The IAM role of the server needs nothing extra (SNS calls us; we do not call AWS SNS).

Until the site is live the subscription cannot be confirmed (SNS cannot reach the endpoint), but the SES account-level suppression list already protects sending: SES itself refuses addresses that bounced or complained. The app list adds our own record and stops us even attempting to send.

## Tests

`notifications/tests/test_ses_feedback.py`: signature accept and reject (throwaway key and certificate, download patched), wrong topic, evil certificate and subscribe hosts, subscription confirmation, permanent and transient bounce, complaint, repeats, the guard for every account email, the same reset answer, and the System remove (audit logged, 404 below Developer). The signature tests skip themselves if `cryptography` is not installed.
