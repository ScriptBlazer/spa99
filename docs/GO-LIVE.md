# Go live

Do these in order. Live started with an empty database, so the first launch needed no backfills. Later releases may: if the release notes say so, run `backfill_site_data` (see "Every release"). Server commands run in `~/spa99` (the folder that holds `docker-compose.yml`).

## Waiting for Moishe

None of these block the launch. Each has a safe default already in place.

1. **Background jobs: no Redis.** The jobs use the database as their queue (django-q2, ORM broker), with 4 job workers in one worker container. Reason: at this size Redis would add a container, memory and a failure point without a real gain. Override: say "add Redis" and it becomes one extra container plus a settings change.
2. **Personal-data retention** (privacy notice proposals, `docs/features/legal.md`). Today these are kept forever: sign-in records, email records, journey emails with no account, change history and the System audit log. Needs your and the solicitor's yes on the periods, then clean-up jobs get built. The quick one: set `SYSTEM_AUDIT_RETENTION_DAYS=730` in `.env` and the daily housekeeping job prunes the audit log to 2 years.

**What lives on the server:** only `.env` and Caddy's certificates. The database is RDS (with its own backups), uploads are in S3, static files are inside the image, logs go to `docker compose logs`. Losing the server loses nothing but `.env`, so keep a copy of it in your private folder.

## Launch

1. **GitHub and Docker Hub**
   - Docker Hub: create a **private** repository `spa99`. Make two access tokens (Account settings > Personal access tokens): **Read & Write** for GitHub, **Read-only** for the server.
   - GitHub (repo > Settings > Secrets and variables > Actions): add `DOCKERHUB_USERNAME` (`scriptblazer`) and `DOCKERHUB_TOKEN` (the Read & Write token).
   - Merge `claude/docker-live-d1d28a` (and anything else for launch) into `main`. Wait for the green tick.
   - Release: `git tag 1.0.0 && git push origin 1.0.0`. Actions runs the tests on Postgres and, only if they pass, pushes `scriptblazer/spa99:1.0.0` and `:latest`. Check that both appear on Docker Hub.

2. **AWS** (region eu-west-2, London)
   - **EC2** (done): t3.medium, Ubuntu 26.04 x86_64, 30 GB gp3 encrypted, termination protection on. Security group `spa99-web`: 22 from your IP, 80 and 443 open to all. IAM role `spa99-ec2` (S3 policy for `spa99-media`, plus SSM). **Elastic IP 3.8.30.182** allocated and attached.
     - Set the instance metadata **hop limit to 2** (Actions > Instance settings > Modify instance metadata options), or the containers can't use the role and S3 fails.
   - **S3** (done): private bucket `spa99-media` (Block all public access on). The role allows `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `arn:aws:s3:::spa99-media/*` and `s3:ListBucket` on `arn:aws:s3:::spa99-media`. (Add `ses:SendRawEmail` and `ses:GetAccount` only when moving to SES.)
   - **RDS PostgreSQL:** Create database > Standard create > PostgreSQL.
     - Instance **db.t4g.small**, storage **gp3** with **storage auto scaling on**.
     - Connectivity: the **same VPC as the EC2**, **Public access: No**. New security group (e.g. `spa99-db`) with one inbound rule: PostgreSQL **5432** from the security group **`spa99-web`** (not from an IP).
     - **Additional configuration > Initial database name: `spa99`**. Without it RDS creates no database and the site can't connect.
     - Automatic backups **on, 14 days**.
     - Copy the endpoint. `DATABASE_URL=postgres://<user>:<password>@<endpoint>:5432/spa99` (URL-encode symbols in the password).

3. **Postmark** (approved 2026-10-29, Basic, 10,000 a month)
   - Sender domain `spa99.uk`: add its **DKIM** and **Return-Path** records in Cloudflare (DNS only). Wait until both show green in Postmark.
   - Copy the **Server API token** (for `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`).

4. **Server: setup script, then the files.** From your Mac, in the project folder (`ssh spa99` is the shortcut in `~/.ssh/config`):
   ```bash
   scp -r scripts/server spa99:~/server-setup
   ssh spa99 'sudo bash ~/server-setup/bootstrap.sh'
   ```
   It installs updates, automatic security updates, 2 GB swap, Docker (official repo, logs capped), fail2ban, key-only SSH with no root login, `~/spa99` and `~/scripts` (health check and Telegram alerts), and the cron jobs. Safe to run again. Details in `scripts/server/README.md`.
   Then copy the app files and log in again (so the docker group applies):
   ```bash
   scp docker-compose.yml Caddyfile .env.example spa99:spa99/
   ssh spa99
   ```
   On the server:
   ```bash
   docker compose version
   docker login -u scriptblazer
   cd ~/spa99
   cp .env.example .env && chmod 600 .env
   nano .env
   ```
   - `docker login`: paste the **Read-only** token as the password. It stays logged in.
   - **Alerts:** put the Telegram bot token and your chat id in `~/scripts/.alert.env` (the bot must have been started from that Telegram account; @userinfobot shows your id), then `~/scripts/alert.sh --test`. Fill it once the site is up, or you get "site down" until then.
   - **Every server command from here on runs in `~/spa99`.**

5. **Server `.env`** (every line is explained in the file)
   - Required (the site will not start without them, and the error lists what's wrong): `SECRET_KEY` (new, in single quotes), `DATABASE_URL`, `AWS_STORAGE_BUCKET_NAME=spa99-media`, `SYSTEM_UNLOCK_CODE`, `ADMIN_PATH`, `DEFAULT_FROM_EMAIL`, the four `*_DOMAIN`s, and `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` (the Postmark token).
   - Also: `IMAGE=scriptblazer/spa99`, `APP_TAG=1.0.0`, `SENTRY_DSN`, `ANTHROPIC_API_KEY` (blank = chat off), `POSTMARK_WEBHOOK_USER` / `_PASSWORD` (step 9).
   - Leave out: `EMAIL_BACKEND` (blank = Postmark SMTP), `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (the server uses its role), `DEBUG`, `DJANGO_SETTINGS_MODULE`, `SPA99_PRIVATE_DIR`, `Q_SYNC`.
   - Save a copy of the finished `.env` in your private folder.
   - **DNS** (done): the GoDaddy parking A record is deleted; `spa99.uk`, `www`, `office`, `system` and `control` point at **3.8.30.182**, grey cloud (DNS only) until step 10.

6. **Start:** `docker compose pull && docker compose up -d`. No manual steps: web runs the migrations and creates the cache table, then starts gunicorn (static files are already in the image); the worker waits for web to be healthy, registers the recurring jobs and starts; Caddy gets the certificates once DNS points at the server (step 5, grey cloud) and 80/443 are open.
   - `docker compose logs web | head -30`: the startup line must say `settings=config.settings.prod`, `database=postgresql:...`, `media=s3:<bucket>/prod/`, `email=smtp:smtp.postmarkapp.com`.
   - `docker compose logs caddy`: it should say the certificates were obtained.
   - If web keeps restarting: `docker compose logs web` shows the list of missing or wrong `.env` values.

7. **First data** (once; Postmark domain must be green first, or the invites never arrive)
   - Preview: `docker compose run --rm web python manage.py setup_live --dry-run`. It lists everything and sends nothing.
   - Run: `docker compose run --rm web python manage.py setup_live`. It loads the seed, the team levels, System values (contact email, Gold CC, WhatsApp, staff alerts), and creates moishe@spa99.uk (Developer + Final approver) and barry@spa99.uk (Admin + Approver), each invited by email. It refuses to run if email doesn't work.
   - The output must end with "invite sent" for both, then a "Launch state" and "Next steps" block. Open the invite and choose your password within 1 hour (expired: System > Team, resend, or Forgot password on spa99.uk).

8. **Checks**
   - `https://spa99.uk/health/` answers OK.
   - Sign in at `https://system.spa99.uk/dev-login/`, unlock with the lock code. Settings > Launch: Memberships public off, final approval as you want it, payments not opened. Defaults: payment alert address and caps. Emails: send a test to yourself.
   - Do it yourself, on a phone too: the journey and email, register and confirm, apply for Gold (the approver email arrives and "Review application" opens it in the Office).
   - Upload a picture in System > Emails: it must show (proves S3 and the role work).

9. **Postmark bounces:** in Postmark, Server > Webhooks > Add webhook, URL `https://<user>:<password>@spa99.uk/postmark/webhook/` (the two values from `.env`), tick **Bounce** and **Spam complaint** only, **Send test** for each: 200 is right (404 = the env values are missing, 401 = they differ from the URL).

10. **Cloudflare on**
    - SSL/TLS: **Full (strict)** ("Flexible" causes an endless redirect loop).
    - Turn the records **orange** (proxied). Turn on "Always use HTTPS".
    - Leave **Bot Fight Mode off**: it blocks Postmark webhooks and uptime checks.
    - Check `/health/` and a sign-in again.
    - Certificate renewal keeps working through Cloudflare (Caddy renews on its own). If it ever fails, check `docker compose logs caddy`; turning the records grey for a few minutes lets Caddy renew, then turn them orange again.

11. **Sentry:** `docker compose run --rm web python manage.py sentry_test`. The test error must appear in Sentry, tagged with the release (e.g. 1.0.0).

## Soft launch (decided)

- **Memberships stay hidden.** People get the journey and the email gate and can register.
- **Payments closed.** No card payments yet; the payment window opens later from System.
- Turn Memberships on only when prices are final.

## Every release

1. `git tag 1.0.1 && git push origin 1.0.1`. Wait for the green tick and the new tag on Docker Hub.
2. Before a release with migrations: take an RDS snapshot (RDS > Snapshots > Take snapshot).
3. On the server: set `APP_TAG=1.0.1` in `.env`, then `docker compose pull && docker compose up -d`.
4. Check `https://spa99.uk/health/` and `docker compose logs web | head`.
5. If the release notes say so, run `docker compose exec web python manage.py backfill_site_data --dry-run`, then without `--dry-run`.

**1.0.1** (Barry's Gold changes) needs that: it renames the industry question, "BML staff member", adds "Barry's status", turns Rest of London into Midlands and renames the Gold rating reason. It also has one migration (`business_willing`).
Never edit or delete a migration that is already live.

**Rollback:** set `APP_TAG` back to the previous version, then `docker compose pull && docker compose up -d`. If a migration damaged data, restore the RDS snapshot to a new instance and point `DATABASE_URL` at it.

## 1.0.2 (invite link through the questionnaire, personal links in the builder)

- **Migration `system.0021`** adds `SiteDefaults.invite_landing` (schema only, `db_default='journey'`). Take the RDS snapshot first. It runs on start.
- **No backfill.** `backfill_site_data` is unchanged.
- **After deploy**, Moishe updates his saved invite wording in System > Emails > Automatic > Invitation to register (the saved body says "link to register"; the subject is also the old one).
- **The setting** is in System > Defaults > Emails, "Invitation link goes to" (the questionnaire by default, or Register).
- **Rollback is safe:** the column has a database default, so 1.0.1 can still save Defaults without migrating back.

## 1.0.3 (WhatsApp buttons, number and message settings, Gold wording)

- **Migration `plans.0025`** adds three `SiteSettings` fields: `whatsapp_number` (empty), `whatsapp_message` ("Hi, I'd love to find out more about Spa 99.") and `whatsapp_rate_message` ("Hi, I'd like to discuss better prices for Spa 99."). Schema only; all three have a database default, so existing rows get the defaults. Take the RDS snapshot first. It runs on start.
- **After deploy, run `python manage.py backfill_site_data`** (try `--dry-run` first). It copies the digits from the old `https://wa.me/447441919990` link into the WhatsApp number (live has the old link; the number stays empty otherwise) and moves the stored Gold wording to "For BML clients: past, present and future." (exact old wording only, so anything edited by hand is kept; includes the chat FAQ "What is the Gold Card?"). Safe to run twice.
- **Check** System > Settings > "Wording, tax and WhatsApp": the number reads 447441919990, the message is "Hi, I'd love to find out more about Spa 99.", and "WhatsApp message (better prices)" is "Hi, I'd like to discuss better prices for Spa 99.". Open a better-rate button (Register, or a Memberships "Looking for a better rate?") and check WhatsApp opens with the better-prices text; the footer button opens with the general text.
- `setup_live` fills the number, message and better-prices message (empty fields only) instead of the link. The column `discount_contact_url` stays, unused.
- **Rollback is safe:** all three new columns have a database default, so 1.0.2 can still save Settings (checked: 1.0.2's code saves `SiteSettings` on the 0025 schema). The WhatsApp links on 1.0.2 use the old link, which 1.0.3 does not clear, so they keep working.

## Next release (Office additions: heard via, chats card, Invited list)

- **No migration, no backfill.**
- **After deploy**, refresh the stored figures so Analytics shows "How people heard about us" (the hourly roll-up also does it): `docker compose exec web python manage.py shell -c "from office import snapshots; snapshots.build_everything()"`.
- The Invited page (`/invited/`) is Admin and above only.
- **Invite email opens and the Bounces log:** migrations `mailings.0008` (adds nullable `Invite.email_opened_at`; rollback safe) and `notifications.0006` (new `EmailBounce` table; a rollback just leaves it unused). Take the RDS snapshot first. They run on start.
- **In Postmark**, on the webhook for the Default Transactional Stream, also tick the **Open** event (Bounce and Spam Complaint stay ticked). Open tracking is switched on per email by the site, for invite emails only; opens are known only for invites sent after this release.
- **Privacy notice changed** (a line about the tracking pixel in invitation emails, date 30 October 2026). Run `docker compose exec web python manage.py backfill_site_data --dry-run`, then without `--dry-run`: it updates the "Emails" part and "Last updated" only while they still have exactly the old wording (a part you edited by hand is left; add the line yourself in Control). Live may still hold the 27 October text (the 28 October chat line had no backfill); if the dry-run says "Nothing to change", add both the Ask us chat line and the tracking-pixel line by hand in Control.
- System > Emails has a new **Bounces** tab and the Dashboard a "Bounces" tile. Old bounces before this release are not in the log (only new ones).

## Next release (Office outreach: guide, sticky notes, Approach list, archive, next-morning email, Launch)

- **Take the RDS snapshot first.** Migrations run on start (web).
- **New migrations:** `outreach 0001` to `0003` (new tables only: notes, Approach list entries, messages, archived leads and their events, next-morning rows, note events); `plans 0026` (Gold guide file, Approach list name), `0027` (next-morning email sender, switch, time, hours), `0028` (Launch), `0029` (adds database defaults to every new `plans` column, see Rollback); `gold 0012` to `0014` (new event kinds, choices only); `system 0022` (**drops `leads_show`** from the Defaults), `0023` (Launch audit kind, choices only).
- **After deploy, in this order:**
  1. `docker compose exec web python manage.py backfill_sticky_notes --dry-run`, read the list, then without `--dry-run` (a re-run copies nothing).
  2. `docker compose exec web python manage.py rebuild_metrics` so the Leads totals follow the new rules (registered people are not leads; archived leads are left out).
  3. System > Gold: upload the Gold Card guide PDF (at most 5 MB).
  4. Optional: System > Settings, set the Approach list name.
  5. System > Emails: set the automatic emails sender (name and an address on the sending domain, for example barry@spa99.uk), check the send time (10:00) and minimum hours (8), read the "Next-morning email" wording under Automatic, and make sure Postmark accepts that From address. **Turn the switch on last.** Only leads who give their email after it is on are emailed; the worker registers the 15-minute job on start.
  6. System > Launch exists. **Do not press it until opening.**
- **Rollback.** The new `plans` columns have database defaults, so the previous image can still save Settings and its history rows. The new tables are simply ignored by the old code. The one thing the old code cannot live with is `system 0022` (the old Defaults model reads `leads_show`). So **before** setting `APP_TAG` back, with the NEW image still running, undo it: `docker compose exec web python manage.py migrate system 0021` (the reverse puts `leads_show` back with its default "all"). Then set `APP_TAG` to the previous version and `docker compose pull && docker compose up -d`. If data was damaged, restore the snapshot as in "Every release".

## Next release (WhatsApp in the Office: chat, templates, push, first name and mobile at the email step)

- **Take the RDS snapshot first.** Migrations run on start (web): `journey 0006` (three new `JourneySession` columns and their history columns, all with database defaults), `outreach 0004` (new table `PersonEdit`) and `outreach 0005` (wider `PersonEdit` columns, a new kind), `plans 0031` (only the default privacy version changes, no SQL), `whatsapp 0001` (new tables). No data is touched.
- **Copy the changed Caddyfile** (the Office host now limits uploads to 20 MB) and reload it: `scp Caddyfile spa99:spa99/` then `docker compose restart caddy`. The image build installs `pywebpush` and its pinned dependencies (one of them, `http_ece`, builds from source: the build needs no extra tools, it uses pip's own build step).
- **Server `.env`, new values** (never in git or chat; keep a copy in the private folder):
  - `TWILIO_ACCOUNT_SID` (Twilio Console home), `TWILIO_AUTH_TOKEN` (same page; **only** checks the webhook signature; if BML rotates it, change it here too).
  - `TWILIO_API_KEY_SID` and `TWILIO_API_KEY_SECRET`: make a **separate API key for Spa 99** (Console > Account > API keys and tokens > Create API key, type Standard) so it can be revoked without touching BML.
  - `TWILIO_WHATSAPP_FROM=+442045384999`.
  - `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT=mailto:hello@spa99.uk`: run `docker compose run --rm web python manage.py whatsapp_vapid_keys` once and paste the lines. Keep the pair for good: changing it drops every subscribed device.
  - Then `docker compose up -d`. The startup line shows `whatsapp=on`. Blank values leave WhatsApp "not configured": the webhooks answer 404 and nothing can be sent, which is safe.
- **After deploy, in this order:**
  1. `docker compose exec web python manage.py backfill_site_data --dry-run`, read it, then without `--dry-run`: adds the WhatsApp lines to the privacy notice and moves "Last updated" to 3 November 2026, only while the notice still has exactly the previous wording (a part edited by hand is left; add the lines yourself in Control). Do this **before** the first WhatsApp goes out.
  2. **Twilio Console, Messaging > Senders > WhatsApp senders > the Spa 99 sender (+44 20 4538 4999) only**, never account-wide: "A message comes in" = `https://spa99.uk/twilio/whatsapp/incoming/` (POST), "Status callback URL" = `https://spa99.uk/twilio/whatsapp/status/`. BML's sender and its templates stay untouched. Cloudflare Bot Fight Mode stays off (it blocks Twilio).
  3. **Balance:** the account balance is shared with BML and was low (about 16 pounds). Top up and turn on auto-recharge before launch.
  4. **Template:** in Twilio, Content Template Builder, create `spa99_lead_follow_up` (WhatsApp, language English, category Marketing, one variable `{{1}}` with a sample name): "Hi {{1}}, thanks for checking out Spa 99. For custom prices, or more information about memberships, just reply here and we'll look after you." (the wording Moishe confirms) and submit it for WhatsApp approval (minutes to a day). Moishe chose no STOP line in the text (typing STOP still opts him out). If Meta rejects the template for that, add "Reply STOP to opt out." and resubmit.
  5. **System > WhatsApp** (Developer, unlocked): press **Check Twilio** (is the Spa 99 sender online; read through the WhatsApp Senders API only, because a Standard API key cannot read the Twilio account), then **Sync templates** once Twilio shows approved: the template appears as approved. The variable is labelled "First name" by default.
  6. **Test on a staff phone:** register or add the staff mobile to a lead, open the lead, WhatsApp > Choose a template > send; reply from the phone (the message appears and the window opens), send free text, send a photo and a PDF; send STOP (the chat says he opted out) and START. Then install the Office on a phone (Add to Home Screen) and turn on notifications.
  7. **Only then**: System > Settings, change the site's **WhatsApp number** to the new number so every "WhatsApp us" button lands in the Office (Moishe does this; it is not done by the release).
  8. Launch turns the email step off once; after launch it can be switched back on in System > Settings ("Journey asks for an email").
- **What changed for staff:** Message on a lead or person and Respond on Gold are WhatsApp now; Send guide and the automatic emails are unchanged. The email templates `office_message` and `gold_respond` stay in System > Emails, unused.
- **Rollback (tested on a scratch SQLite database).** Do these in order:
  1. **Before** setting `APP_TAG` back, with the NEW image still running: `docker compose exec web python manage.py migrate whatsapp zero`. It drops every WhatsApp table (the chats in the Office are lost: export first if you need them; Twilio keeps its own message log). Why: the database holds foreign keys from the WhatsApp tables to users. The old image does not know those tables, so its `delete_user_data` (a member deleting his account, Office "Delete", Django admin) raises an IntegrityError for any user still referenced from a chat, a read marker, a push device or a preference. Tested: with the tables the delete fails, after `migrate whatsapp zero` it works.
  2. The old image's erasure does **not** clear the new journey columns, so a person erased on the old image keeps `lead_first_name` and `lead_mobile` (and in the history rows). Do not erase people on the old image; if one was done, clear it with `docker compose exec web python manage.py shell -c "from journey.models import JourneySession as J; J.objects.filter(lead_email='').exclude(lead_mobile='').update(lead_first_name='', lead_mobile=''); J.history.model.objects.filter(lead_email='').exclude(lead_mobile='').update(lead_first_name='', lead_mobile='')"`.
  3. Then `APP_TAG` back, `docker compose pull && docker compose up -d`. The new `journey`, `outreach` and `plans` changes need no undo: the new `JourneySession` columns have database defaults (the old image still saves journeys, and ignores them) and `PersonEdit` is a table the old image ignores.
  4. Other things the old image cannot do: register or save an account that holds a **non-UK mobile** (the number stays stored), and the email Message and Respond come back. WhatsApp stops working (webhooks answer 404 on the old image, Twilio retries and gives up, harmless).
- **Not verified before release (needs the real account):** that Twilio accepts the Content API and WhatsApp senders endpoints exactly as coded (they are mocked in tests), the plain-reason mapping of Twilio error codes, and the Postgres run (CI runs the tests on Postgres; nothing is Postgres-only).

## Next release (Email chat in the Office, WhatsApp round 2: replies, video, voice notes; mobile optional at the email step)

Status: built and reviewed on `feature/whatsapp`, **not released**; the review fixes of 2026-11-04 are in (docs/features/office-email-chat.md, "Review fixes"). Postmark, Twilio and a real iPhone are not tested live (see "Not verified" below).

Spec: `docs/features/office-email-chat.md` and `docs/features/whatsapp.md` (both have a "Built" section).

- **Take the RDS snapshot first.** Migrations run on start (web): `emailchat 0001` (new tables only: thread, message, attachment, read marker), `emailchat 0002` (two columns on the email message and an index for the unread counts: `incomplete` has a database default, `notified_at` is nullable with no default (existing rows read as empty); no data is touched, no backfill) and `emailchat 0003` (`to_address` on the email message, with a database default; existing rows stay blank and show the thread's address) and `whatsapp 0002` (one nullable column, `Message.reply_to`).
- **The image changes:** it now installs `ffmpeg` (apt, `--no-install-recommends`; voice notes) and `nh3` (a pinned Python wheel that cleans email HTML; manylinux wheels exist, nothing compiles). The image grows by roughly 150 to 250 MB for ffmpeg and its libraries (an estimate: Docker is not available here, so it was not built or measured. Check `docker image ls` after the first build).
- **Caddy: nothing to change.** The public host (`spa99.uk`) has no `request_body` limit, so Postmark's inbound POST (a mail of up to 35 MB arrives as about 47 MB of JSON, files in base64) passes. The app drops anything over 50 MB (`EMAILCHAT_MAX_INBOUND_BYTES`) with a 200 and a log line; Cloudflare's own upload limit (100 MB on the free plan) is above that. **Do not add a small global limit to the public host later**, or large inbound mail stops arriving. The Office host keeps its 20 MB limit (voice notes are about 1 to 3 MB, files on emails 10 MB each and 9 MB in all).
- **Email chat setup (Moishe, no code):**
  1. Postmark: the plan must include **inbound** (10K Pro or Platform, not Basic). Account > Plans & Add-ons.
  2. Cloudflare DNS: `MX`, name `reply`, value `inbound.postmarkapp.com`, priority 10, DNS only. This subdomain only, so hello@ and BML mail are untouched.
  3. Postmark > the server > **Inbound** stream > Settings: inbound domain `reply.spa99.uk` (Postmark asks you to confirm it); webhook URL `https://<user>:<password>@spa99.uk/postmark/inbound/` with a password made for this (not the bounce webhook's).
  4. Server `.env`: `EMAIL_INBOUND_DOMAIN=reply.spa99.uk`, `EMAIL_INBOUND_USER`, `EMAIL_INBOUND_PASSWORD` (the same pair as in the URL). Then `docker compose up -d`; the startup line shows `emailchat=replies-in-office`. With the domain blank it shows `replies-to-mailbox`: staff can still send, Reply-To stays hello@ and the screen says replies go to that mailbox. Domain set but user or password blank shows `inbound-webhook-not-set` (the webhook answers 404; set both).
  5. Postmark > the Default Transactional Stream webhook: also tick **Delivery** (Bounce and Spam Complaint stay ticked). A bounce marks the email bounced in the thread; Delivery adds the delivered state (without it an email stays "sent"). Matching works through our own `X-PM-Metadata-chat` header, so it needs nothing else.
  6. Test: Office > a lead > Start email > send to a staff address, reply from that mailbox (the reply lands in the thread within seconds), send a file and an image, reply with an attachment over 10 MB (it is dropped with a note). Check In-Reply-To threading in the mail app: **not verified**, because Postmark may replace the Message-ID we set (we also send In-Reply-To and References from his last mail, which does not depend on that).
- **Emails sent directly to staff (decided 2026-11-04; migration `emailchat 0005`: new columns only, all nullable or with a database default, `StaffSender.inbox_token` and `Message.direct_key` are unique and nullable, no backfill).** Settings (all optional, server `.env`): `EMAIL_INTERNAL_DOMAIN` (the BML domain: mail from it is internal and stays in Outlook; blank = none) and `EMAIL_STAFF_GROUP_ADDRESS` (`staff@spa99.uk`: mail addressed to it, to hello@ or to the group-copy address in System > Defaults is never taken in). Setup for each staff mailbox (Barry, Moishe), no code:
  1. System > Team > the person > **Email**: press Save once. The **Inbox address** field then shows `inbox+<token>@reply.spa99.uk`. Copy it. (It is a random token on purpose; keep it private.)
  2. Microsoft 365 admin centre > Users > Active users > the person > **Mail** tab > **Email forwarding** > Manage email forwarding > turn on, **Forward all emails sent to this mailbox** to that address, and tick **Deliver messages to both forwarding address and mailbox** (so Outlook keeps its copy). Save. Only these two staff mailboxes are changed; no BML mailbox and no BML policy.
  3. Microsoft blocks automatic forwarding outside the organisation by default. Without a fix the forward is refused and the sender may get a bounce with **error 5.7.520** ("Access denied, Your organization does not allow external forwarding"). Fix: Microsoft Defender portal (security.microsoft.com) > Email & collaboration > Policies & rules > Threat policies > Anti-spam policies > **Anti-spam outbound policy (Default)** is left alone; create a **new custom outbound policy** (Create policy > Outbound), apply it to only those two staff mailboxes (Users: Barry's and Moishe's), and set **Automatic forwarding rules** to **On - Forwarding is enabled**. A custom policy beats the default for the people it covers. The menu labels change from time to time: check them against Microsoft's current page "Control automatic external email forwarding in Microsoft 365" if one is not where it says. Allow a little while for it to apply.
  4. Test (unrun): from a personal address send a new email to barry@spa99.uk only. Within seconds it should be in Outlook as usual **and** a thread "Sent to Barry" should be in the Office Email tab with a push. Then check it does **not** appear for: an email to barry@ and hello@ together, an email to barry@ and staff@ together, and an email from another staff or BML address. Check the headers: if Microsoft rewrites `To` on the forward, the app reads the original To from the headers; a mail whose original To cannot be told is not stored (the log says so). Reply from the Office: it goes to the sender from the replying person's address. **Not verified against real Postmark and Microsoft:** the payloads in the tests are written from Postmark's documentation. Watch for good mail flagged as failing sender checks after forwarding (the check prefers Microsoft's own `Authentication-Results`).
- **Incomplete inbound mail:** the worker runs an hourly job `emailchat-give-up` (registered by `register_schedules` on worker start): inbound emails whose files were never finished after a day say their files could not be saved. By hand: `docker compose exec web python manage.py give_up_incomplete_emails --dry-run`.
- **Old Office emails (optional):** `docker compose exec web python manage.py backfill_email_threads --dry-run`, read it, then without `--dry-run`. It copies the old Message emails into email threads (one thread per address, subject "A message from Spa 99") so they show in the Email tab; a copied one is no longer listed twice in the timeline. Safe to run twice. Not part of a migration.
- **Voice notes:** nothing to set (`FFMPEG_BIN` is optional). The startup line shows `voice=on` when ffmpeg is found. If it shows `voice=off` the chat hides the microphone. Phone test: record a note in the chat; check on his phone that it plays as a voice note and not as an audio file (Twilio documents only OGG Opus as audio and we serve it as `audio/ogg`).
- **Microphone permission:** every response now carries `Permissions-Policy: microphone=(self)` on the Office host and `microphone=()` on the others. Nothing else was blocked before.
- **Privacy notice (decided by Moishe, 2026-11-04): no line about email chats.** "People know chats are kept." Only the words that describe the journey tick were changed so the notice matches it: email, and WhatsApp if a number is added, about opening and offers (parts 2 and 3, including the WhatsApp block in part 2). **`PRIVACY_VERSION` and the "Last updated" date were not bumped:** the project's rule (docs/features/legal.md) is to bump only when a change should make people accept again, and the notice now matches the tick of `2026-11-04` (the journey's `CONSENT_VERSION`); older ticks, including `2026-11-03` and the leads before versions, said about opening only (see `journey/copy.py` `CONSENT_TEXTS`, and Office > a lead shows the wording that person ticked). New installs get the words from the seed. If live already holds the 3 November wording, `backfill_site_data` does not carry these edits: change the four phrases by hand in Control (Privacy parts 2 and 3: "email you, and WhatsApp you if you add a number, about opening and offers"; "news about the opening and offers"; "stop emailing and WhatsApping you").
- **Rollback.** Do in order: (1) **before** setting `APP_TAG` back, with the NEW image running: `docker compose exec web python manage.py migrate emailchat zero` (drops the email chat tables, so the threads and messages are gone; the old image cannot delete a person who is still referenced from them, as with WhatsApp). **It does not touch S3:** the files on emails (his attachments and ours) stay in the bucket as orphans under `emailchat/`, and they are personal data. The bucket has **versioning on** (docs/PROJECT.md), so `aws s3 rm` alone only adds delete markers and the files stay as old versions: remove the versions too. From a machine whose credentials may delete (the EC2 role may), dry run first: (a) `aws s3 rm s3://spa99-media/prod/emailchat/ --recursive --dryrun`, then without `--dryrun` (adds the markers); (b) write what is left into two files and read them: `aws s3api list-object-versions --bucket spa99-media --prefix prod/emailchat/ --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' > versions.json` and the same with `DeleteMarkers[]` into `markers.json` (the CLI pages through the whole listing by itself; a file that says `"Objects": null` has nothing in it, skip it); (c) delete them with `aws s3api delete-objects --bucket spa99-media --delete file://versions.json`, then the same with `file://markers.json` (the file is the JSON `{"Objects": [{"Key": ..., "VersionId": ...}, ...]}`, which is what (b) writes; add `"Quiet": true` to see only failures). One call takes at most 1000 entries: if a file holds more, cut it into files of 1000 (for example with `jq '{Objects: .Objects[0:1000]}'`, then `[1000:2000]`, and so on). There is no dry-run flag for (c), so the files from (b) are the dry run. Check `list-object-versions` again: it must come back empty. (The bucket policy may need `s3:DeleteObjectVersion` for the role; if it is refused, use root or Moishe's user.) The prefix is `prod/emailchat/` because live stores media under `prod/` (`media=s3:<bucket>/prod/` in the startup line); nothing else lives under `emailchat/`. **There is no bulk export of email threads.** The exports are per person (Office > person or lead > Export, a JSON file with the emails and a listing of the files, not the file bytes), so "export first" means doing that for each person whose thread you need, and downloading any file you need from the thread page. The one bulk route is Django admin > Email chat > Messages > select all > "Export selected rows as CSV" (the rows and text, no files). The `whatsapp 0002` column is harmless and can stay; if wanted, `migrate whatsapp 0001`. (2) `APP_TAG` back, `docker compose pull && docker compose up -d`. The public email step on the old image asks for the mobile again (the new one made it optional; people who signed up without one keep a blank). Postmark inbound keeps retrying for hours then gives up; unset the inbound webhook in Postmark if you roll back for long.
- **Office email from a person (same release; spec docs/features/office-email-chat.md, "Office email from a person").**
  - **Migrations (run on start; take the RDS snapshot first):** `emailchat 0004` (new table `StaffSender`, `Message.signature_html` and `signature_text` with database defaults, `Message.group_copied_at` nullable, `Attachment.inline_ref` with a database default; no data touched, so 0001 to 0003 rollback notes are unchanged: `migrate emailchat zero` drops the new table too) and `system 0025` (`SiteDefaults.office_copy_email` and `office_copy_seeded`, history columns too, all with database defaults). Rollback of the app alone is safe: every new column has a database default or is nullable.
  - **New setting (optional):** `EMAIL_SENDING_DOMAIN` in `.env`. Blank is right on live: it uses the domain of `DEFAULT_FROM_EMAIL` (spa99.uk, the domain verified in Postmark). Only an address on that domain can be a From.
  - **Order after `docker compose up -d`:** (1) `docker compose exec web python manage.py seed_phase1 --dry-run`, read it, then without `--dry-run`: it sets System > Defaults > Emails > "Copy of replies to the Office goes to" to `staff@spa99.uk` once (a field you clear later stays clear; clear it to switch the copy off). (2) Signatures: `docs/` is not in the image, so copy the two files to the server and mount them: `scp docs/design/spa99-signature-moishe.html docs/design/spa99-signature-barry.html <server>:~/signatures/`, then `docker compose run --rm -v "$HOME/signatures:/signatures:ro" web python manage.py fill_signatures --source /signatures --dry-run`, read it, then without `--dry-run`. It fills EMPTY signatures only, matched by the email in each file's first comment. Or paste a signature in System > Team > the person > Email. (3) System > Team > Email for anyone whose login is not on spa99.uk (BML logins): set the sending address (must end @spa99.uk), or they send from hello@. (4) Check Barry and Moishe have `@spa99.uk` login addresses (their own address is the From).
  - **Pictures:** the signature logo and banner are plain files under `/static/common/img/email/`. **Never rename or delete them** (old emails point at them); a new picture gets a new file name.
  - **Postmark:** nothing new to set. The sending domain spa99.uk is already verified; the sender signature for hello@ stays. Check one Office email from Barry's address in Postmark Activity (From, Reply-To with a name, signature picture loads).
  - **Test:** Office > a lead > Start email > send to a staff address: From is `Barry, Spa 99 <barry@spa99.uk>`, the signature is under the text, no big heading, no "write to hello@" line; reply from that mailbox: the reply lands in the thread and a short "Reply in the Office" copy reaches `staff@spa99.uk` with Reply-To `staff@spa99.uk` (not the thread). **Not verified:** how Outlook for Windows draws the 600 px signature in the narrower card, Outlook dark mode, and the fold of Outlook's quote in a real browser with real Outlook mail (tests use hand-written HTML of each client; the page script was only checked by `node --check` and a stub of its walk).
- **Not verified before release:** Postmark inbound and Delivery payloads against the real account (tests use payloads written from Postmark's documentation), ffmpeg inside the Docker image, Twilio accepting the converted OGG as a voice note, and the real image size.

## What is kept, and for how long

Nothing grows without limit on disk: every container's log is capped at 5 x 10 MB (`docker-compose.yml`), and the server holds no app data.

| Data | Kept | Cleared by |
|---|---|---|
| Container logs | 50 MB per container | Docker (json-file, 5 x 10 MB) |
| Ask us chats | 90 days | `chat-prune`, daily 03:30 |
| Visitor counter hashes and salt | today only | `metrics-rollup`, hourly |
| Sessions | until they expire | `housekeeping`, daily 04:15 |
| Wrong-try counters (sign-in, unlock) | 24 hours after the last try | `housekeeping` (and on every try) |
| Background job results | last 250 successes; failures 30 days | django-q `save_limit`; `housekeeping` |
| Rate-limit cache | self-trimming (100,000 entries max) | Django's database cache |
| System audit log | forever (`SYSTEM_AUDIT_RETENTION_DAYS=0`) | `housekeeping` once the setting is above 0 (see "Waiting for Moishe") |
| Sign-in records, email records, change history, journey emails | forever for now | not yet: retention periods await the solicitor ("Waiting for Moishe") |
| WhatsApp click counts (`LinkClickDay`) | forever (counts only, no personal data) | kept on purpose |
| Email chat threads, messages and files | forever for now, erased with the person (staff delete, a member's own delete for his verified address) | retention period awaits the solicitor, like WhatsApp chats |
| Database backups | RDS automatic backups, 14 days | RDS |

## After launch

- **Backups:** live uses RDS automatic backups (daily, kept 14 days) plus a snapshot before risky releases. `scripts/backup_db.sh` is for your Mac's SQLite only.
- **HSTS:** after a week of clean HTTPS, set `SECURE_HSTS_SECONDS=31536000` in `.env` and `docker compose up -d`.
- **Uptime alert:** a free check (UptimeRobot or Better Stack) on `https://spa99.uk/health/`.
- **Stay off the server for 2 days:** urgent fixes only.
- **Tell Barry:** where the Office is and how Gold approvals arrive.
- **Before the first marketing email:** an unsubscribe link for journey leads (confirm and approval emails are transactional).
- **Legal:** solicitor's sign-off on the men-only wording and the privacy notice.
- **Moving to SES later:** in `.env` set `EMAIL_BACKEND=notifications.backends.SesBackend`, remove the `EMAIL_HOST*` lines, add the SES permissions to the role, `docker compose up -d`. Then subscribe `https://spa99.uk/ses/notifications/` to the SNS topic (set `SES_SNS_TOPIC_ARN`) and change the Postmark lines in the privacy notice back to Amazon SES.
- **Control (parked):** Cloudflare caps uploads at 100 MB, so big Control videos need `control.spa99.uk` on grey cloud.
