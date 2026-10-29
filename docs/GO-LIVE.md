# Go live

Do these in order. Live starts with an empty database, so it needs no backfills. Server commands run in the folder that holds `docker-compose.yml`.

**What lives on the server:** only `.env` and Caddy's certificates. The database is RDS (with its own backups), uploads are in S3, static files are inside the image, logs go to `docker compose logs`. Losing the server loses nothing but `.env`, so keep a copy of it in your private folder.

## Launch

1. **GitHub and Docker Hub**
   - Docker Hub: create a **private** repository `spa99`. Make two access tokens (Account settings > Personal access tokens): **Read & Write** for GitHub, **Read-only** for the server.
   - GitHub (repo > Settings > Secrets and variables > Actions): add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (the Read & Write token).
   - Merge `docker-live` (and anything else for launch) into `main`. Wait for the green tick.
   - Release: `git tag 1.0.0 && git push origin 1.0.0`. Actions runs the tests on Postgres and, only if green, pushes `<username>/spa99:1.0.0` and `:latest`. Check both appear on Docker Hub.

2. **AWS** (region eu-west-2, London)
   - **RDS PostgreSQL:** automatic backups **on, 7 days or more**. Security group: port 5432 from the server only. Copy the endpoint; it goes in `DATABASE_URL` (URL-encode symbols in the password).
   - **S3:** a **private** bucket (Block all public access on). The site refuses to start without it.
   - **IAM role for the server** with `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `arn:aws:s3:::<bucket>/*` and `s3:ListBucket` on `arn:aws:s3:::<bucket>`. (Add `ses:SendRawEmail` and `ses:GetAccount` only when moving to SES.)
   - **EC2** (x86_64, e.g. t3.small, Ubuntu): attach the role. Security group: **80 and 443** open to all, 22 from your IP only. Set the instance metadata **hop limit to 2** (Actions > Instance settings > Modify instance metadata options), or the containers can't use the role and S3 fails. Install Docker with the compose plugin.

3. **Postmark** (approved 2026-10-29, Basic, 10,000 a month)
   - Sender domain `spa99.uk`: add its **DKIM** and **Return-Path** records in Cloudflare (DNS only). Wait until both show green in Postmark.
   - Copy the **Server API token** (for `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`).

4. **Server `.env`**
   - Log in to Docker Hub once: `docker login -u <username>` (password: the Read-only token).
   - Copy `docker-compose.yml`, `Caddyfile` and `.env.example` to the server. Rename `.env.example` to `.env` and fill it in. Every line is explained there.
   - Required (the site will not start without them, and the error lists what's wrong): `SECRET_KEY` (new, in single quotes), `DATABASE_URL`, `AWS_STORAGE_BUCKET_NAME`, `SYSTEM_UNLOCK_CODE`, `ADMIN_PATH`, `DEFAULT_FROM_EMAIL`, the four `*_DOMAIN`s, `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` (the Postmark token).
   - Also: `IMAGE=<username>/spa99`, `APP_TAG=1.0.0`, `SENTRY_DSN`, `ANTHROPIC_API_KEY` (blank = chat off), `POSTMARK_WEBHOOK_USER` / `_PASSWORD` (step 9).
   - Leave out: `EMAIL_BACKEND` (blank = Postmark SMTP), `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (the server uses its role), `DEBUG`, `DJANGO_SETTINGS_MODULE`, `SPA99_PRIVATE_DIR`, `Q_SYNC`.
   - Save a copy of the finished `.env` in your private folder.

5. **DNS** (Cloudflare, **grey cloud / DNS only** for now): A records for `spa99.uk`, `www`, `office`, `system` and `control` pointing at the server's IP (use an Elastic IP so it never changes).

6. **Start:** `docker compose pull && docker compose up -d`. Web runs the migrations, then starts; the worker waits for it.
   - `docker compose logs web | head -30`: the startup line must say `settings=config.settings.prod`, `database=postgresql:...`, `media=s3:<bucket>/prod/`, `email=smtp:smtp.postmarkapp.com`.
   - `docker compose logs caddy`: it should say the certificates were obtained.
   - If web keeps restarting: `docker compose logs web` shows the list of missing or wrong `.env` values.

7. **First data** (once; Postmark domain must be green first, or the invites never arrive)
   - Preview: `docker compose run --rm web python manage.py setup_live --dry-run`. It lists everything and sends nothing.
   - Run: `docker compose run --rm web python manage.py setup_live`. It loads the seed, the team levels, System values (contact email, Gold CC, WhatsApp, staff alerts), and creates moishe@spa99.uk (Developer + Final approver) and barry@spa99.uk (Admin + Approver), each invited by email. It refuses to run if email doesn't work.
   - The output must end with "invite sent" for both. Open the invite and choose your password within 1 hour (expired: Forgot password on spa99.uk).

8. **Checks**
   - `https://spa99.uk/health/` answers OK.
   - Sign in at `https://system.spa99.uk/dev-login/`, unlock with the lock code. Check the opening date, the email settings, and that Memberships is still hidden.
   - Do it yourself, on a phone too: the journey and email, register and confirm, apply for Gold (the approver email arrives and "Review application" opens it in the Office).
   - Upload a picture in System > Emails: it must show (proves S3 and the role work).

9. **Postmark bounces:** in Postmark, Server > Webhooks > Add webhook, URL `https://<user>:<password>@spa99.uk/postmark/webhook/` (the two values from `.env`), tick **Bounce** and **Spam complaint** only, **Send test** for each: 200 is right (404 = the env values are missing, 401 = they differ from the URL).

10. **Cloudflare on**
    - SSL/TLS: **Full (strict)** ("Flexible" causes an endless redirect loop).
    - Turn the records **orange** (proxied). Turn on "Always use HTTPS".
    - Leave **Bot Fight Mode off**: it blocks Postmark webhooks and uptime checks.
    - Check `/health/` and a sign-in again.

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

Never edit or delete a migration that is already live.

**Rollback:** set `APP_TAG` back to the previous version, then `docker compose pull && docker compose up -d`. If a migration damaged data, restore the RDS snapshot to a new instance and point `DATABASE_URL` at it.

## After launch

- **Backups:** live uses RDS automatic backups (daily, kept 7+ days) plus a snapshot before risky releases. `scripts/backup_db.sh` is for your Mac's SQLite only.
- **HSTS:** after a week of clean HTTPS, set `SECURE_HSTS_SECONDS=31536000` in `.env` and `docker compose up -d`.
- **Uptime alert:** a free check (UptimeRobot or Better Stack) on `https://spa99.uk/health/`.
- **Stay off the server for 2 days:** urgent fixes only.
- **Tell Barry:** where the Office is and how Gold approvals arrive.
- **Before the first marketing email:** an unsubscribe link for journey leads (confirm and approval emails are transactional).
- **Legal:** solicitor's sign-off on the men-only wording and the privacy notice.
- **Moving to SES later:** in `.env` set `EMAIL_BACKEND=notifications.backends.SesBackend`, remove the `EMAIL_HOST*` lines, add the SES permissions to the role, `docker compose up -d`. Then subscribe `https://spa99.uk/ses/notifications/` to the SNS topic (set `SES_SNS_TOPIC_ARN`) and change the Postmark lines in the privacy notice back to Amazon SES.
- **Control (parked):** Cloudflare caps uploads at 100 MB, so big Control videos need `control.spa99.uk` on grey cloud.
