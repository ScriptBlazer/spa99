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
- **Privacy notice changed** (a line about the tracking pixel in invitation emails, date 30 October 2026). Run `docker compose exec web python manage.py backfill_site_data --dry-run`, then without `--dry-run`: it updates the "Emails" part and "Last updated" only while they still have exactly the old wording (a part you edited by hand is left; add the line yourself in Control).
- System > Emails has a new **Bounces** tab and the Dashboard a "Bounces" tile. Old bounces before this release are not in the log (only new ones).

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
