# Go live (first launch)

Run these in order. Live starts with an empty database, so it needs no backfills. Commands run on the server in the folder that holds `docker-compose.yml`.

## A. Day before (code)

1. Merge every open branch into `main` (now: `feature/compare-order`). Wait for the green tick on GitHub.
2. **Docker Hub:** create a **private** repository called `spa99`. Make two access tokens (Account settings > Personal access tokens): one **Read & Write** for GitHub, one **Read-only** for the server.
   In GitHub (repo > Settings > Secrets and variables > Actions) add the secrets `DOCKERHUB_USERNAME` (your Docker Hub username) and `DOCKERHUB_TOKEN` (the Read & Write token).
3. Tag the release: `git tag 1.0.0 && git push origin 1.0.0`. GitHub Actions tests it and pushes `<username>/spa99:1.0.0` to Docker Hub. Check it appears there.

## B. AWS

4. **Postgres (RDS):** create the database and turn on automatic daily backups (7 days or more). Allow connections from the server only (security group). Copy the connection string; it goes in `DATABASE_URL`. If the password has symbols, URL-encode it.
5. **S3:** create a private bucket for uploaded files. The site refuses to start without one.
6. **Server (EC2):** install Docker. In the security group, open ports 80 and 443 only.
   - Set the instance metadata hop limit to **2**. Without this, the containers can't use the server's role, so S3 and SES fail.
   - Give the server role a policy with:
     - `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` and `s3:ListBucket` on the bucket
     - `ses:SendRawEmail` and `ses:GetAccount`
7. **Email: Postmark for launch** (2026-10-27; SES is still in sandbox).
   - In Postmark, add the sending domain `spa99.uk` and put its DKIM and Return-Path records in Cloudflare. They sit alongside the SES records without clashing.
   - Copy the server token.
   - **Bounces:** make up a long random user and password (letters and digits only) and put them in the server `.env` as `POSTMARK_WEBHOOK_USER` and `POSTMARK_WEBHOOK_PASSWORD`, then `docker compose up -d`. In Postmark: Server, Webhooks, Add webhook. URL `https://<user>:<password>@spa99.uk/postmark/webhook/`. Tick **Bounce** and **Spam complaint** only. Press **Send test** next to each: it must show 200 (a 404 means the two env values are not set, 401 means they differ from the URL). Cloudflare Bot Fight Mode must stay off (see below) or it blocks Postmark.
   - Ask Postmark to approve the account. Until it does, mail only reaches addresses at spa99.uk.
   - **Switching to SES later** is a `.env` change only (and change the Postmark lines in the privacy notice, parts 6 and 7, back to Amazon SES in Control). Delete the five `EMAIL_*` lines, so the default (SES) applies again, then run `docker compose up -d`. Then do step 19 for the bounce subscription.

## C. Server

8. **Log the server in to Docker Hub** (once; it stays logged in): `docker login -u <username>`, and paste the Read-only token as the password.
9. Copy `docker-compose.yml` and `Caddyfile` to the server.
10. Create the server's `.env` from `.env.example`. Wrap `SECRET_KEY` in single quotes (it may contain `$`).

    These keys are required, and the site refuses to start without them:
    - `SECRET_KEY`: a new random key. Never reuse the one from your Mac.
    - `DATABASE_URL`: from step 4.
    - `SYSTEM_UNLOCK_CODE`: 6 to 12 digits.
    - `ADMIN_PATH`: your own value, not the example one.
    - `DEFAULT_FROM_EMAIL=Spa 99 <hello@spa99.uk>`
    - `AWS_STORAGE_BUCKET_NAME`

    Also set:
    - `DOMAIN`, `OFFICE_DOMAIN`, `SYSTEM_DOMAIN`, `CONTROL_DOMAIN`
    - Email through Postmark (both user and password are the server token):
      ```
      EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
      EMAIL_HOST=smtp.postmarkapp.com
      EMAIL_PORT=587
      EMAIL_HOST_USER=<postmark server token>
      EMAIL_HOST_PASSWORD=<postmark server token>
      ```
    - `AWS_SES_REGION_NAME=eu-west-2` and `SES_SNS_TOPIC_ARN=arn:aws:sns:eu-west-2:137808120968:spa99-ses-feedback` (harmless now, ready for SES)
    - `SENTRY_DSN`
    - `IMAGE=<username>/spa99` and `APP_TAG=1.0.0`

    Live always uses the prod settings, whatever the `.env` says. Email goes through SES unless `EMAIL_BACKEND` is set (as above for Postmark). No AWS keys: the server uses its role.
11. **DNS, grey cloud first (DNS only):** point `spa99.uk`, `www.spa99.uk`, `office.spa99.uk`, `system.spa99.uk` and `control.spa99.uk` at the server.
12. Start it: `docker compose up -d`. Migrations run by themselves.
13. Check `docker compose logs web | head -30`: the startup line should name the prod settings, Postgres and S3. Check `docker compose logs caddy` too: it should say the certificates were obtained.

## D. First data (once only, straight after step 12)

14. `docker compose run --rm web python manage.py seed_phase1`. It loads plans, facilities and site text, and only adds rows that are missing.
15. `docker compose run --rm web python manage.py setup_roles`. It creates the team levels and approval groups.
16. `docker compose run --rm web python manage.py createsuperuser`. Use your own email and a strong password.

## E. Checks, then switch Cloudflare on

17. Open `https://spa99.uk/health/`. It should answer OK.
18. **Cloudflare:**
    - Set SSL/TLS to **Full (strict)**. "Flexible" causes an endless redirect loop.
    - Turn the records to orange (proxied).
    - Leave **Bot Fight Mode off**: it can block Amazon SNS and uptime checks.
19. **(Only once on SES.)** Run `curl -X POST -d '{}' https://spa99.uk/ses/notifications/`. It should answer 400 or 403, not 404. Then, in SNS, open the topic and create a subscription: HTTPS, endpoint `https://spa99.uk/ses/notifications/`. Its status should turn to Confirmed.
20. **System** (`system.spa99.uk`):
    - Add Barry in Team (Office level).
    - Make him Approver in Approval.
    - Check the opening date, the email settings and that Memberships is still hidden.
21. Test it yourself:
    - Do the journey and enter your email.
    - Register, then confirm the email.
    - Apply for the Gold Card. Check the approver email arrives, that "Review application" opens it in the Office, and that you can approve, decline or respond there.
22. Run `docker compose run --rm web python manage.py sentry_test` and check the test error appears in Sentry.

## F. Every deploy after launch

- Take an RDS snapshot first.
- Never edit or delete a migration that is already live.
- Tag the new version (for example `1.0.1`), wait for the green tick, set `APP_TAG` in `.env`, run `docker compose up -d`, then check `/health/`.
- If something breaks, set `APP_TAG` back to the previous version and run `docker compose up -d` again. If a migration damaged data, restore the snapshot.

## Suggestions (not blockers)

- **Soft launch:** keep Memberships hidden. People get the journey and the email gate and can register. Turn Memberships on only when prices are final.
- **Stay off the server for 2 days:** no new features or deploys for the first 48 hours. Only urgent fixes.
- **Uptime alert:** add a free check (UptimeRobot or Better Stack) on `https://spa99.uk/health/` that emails you if the site goes down.
- **Cloudflare:** turn on "Always use HTTPS". Keep Bot Fight Mode off (step 18).
- **Real phone test:** do the journey, register and apply for Gold on an iPhone and an Android, not just your Mac.
- **Tell Barry:** where the Office is and how Gold approvals arrive.
- **Before the first marketing email:** add an unsubscribe link for journey leads. It's not needed for launch, because confirm and approval emails are transactional.
- **Legal:** get the solicitor's sign-off on the men-only wording and the privacy notice.
- **Later (Control is parked):** Cloudflare caps uploads at 100 MB, so big Control videos need `control.spa99.uk` on grey cloud.
