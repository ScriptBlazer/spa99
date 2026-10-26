# Go live (first launch)

Run these in order. Live starts with an empty database, so it needs no backfills. Commands run on the server in the folder that holds `docker-compose.yml`.

## A. Day before (code)

1. Merge every open branch into `main` (now: `feature/compare-order`). Wait for the green tick on GitHub.
2. In GitHub, go to Settings > Secrets and variables > Actions. Add the variables `REGISTRY` and `IMAGE_NAME`, and the secrets `REGISTRY_USERNAME` and `REGISTRY_PASSWORD`. Without them the image is built but never pushed.
3. Tag the release: `git tag 1.0.0 && git push origin 1.0.0`. GitHub Actions tests it and pushes the image.

## B. AWS

4. **Postgres (RDS):** create the database and turn on automatic daily backups (7 days or more). Copy the connection string; it goes in `DATABASE_URL`.
5. **S3:** create a private bucket for uploaded files. Give the server's IAM role access to it. Without the bucket, uploads stay inside the container and disappear on the next deploy.
6. **SES:** check that production access is approved. While SES is in the sandbox, confirm and reset emails reach only verified addresses.
7. **SNS:** the topic `spa99-ses-feedback` already exists. You subscribe to it in step 17.

## C. Server

8. **DNS:** point `spa99.uk`, `office.spa99.uk`, `system.spa99.uk` and `control.spa99.uk` at the server. With Cloudflare in front, use proxied (orange cloud).
9. Copy `docker-compose.yml` and `Caddyfile` to the server.
10. Create the server's `.env` from `.env.example`. These keys are required, and the site refuses to start without them:
    - `DJANGO_SETTINGS_MODULE=config.settings.prod`
    - `SECRET_KEY`: a new random key. Never reuse the one from your Mac.
    - `DATABASE_URL`: from step 4.
    - `SYSTEM_UNLOCK_CODE`: 6 to 12 digits.
    - `ADMIN_PATH`: your own value, not the example one.
    - `DEFAULT_FROM_EMAIL=Spa 99 <hello@spa99.uk>`

    Also set:
    - `DOMAIN`, `OFFICE_DOMAIN`, `SYSTEM_DOMAIN`, `CONTROL_DOMAIN`
    - `EMAIL_BACKEND=notifications.backends.SesBackend` and `AWS_SES_REGION_NAME=eu-west-2`
    - `AWS_STORAGE_BUCKET_NAME` (no AWS keys: the server uses its IAM role)
    - `SES_SNS_TOPIC_ARN=arn:aws:sns:eu-west-2:137808120968:spa99-ses-feedback`
    - `SENTRY_DSN`
    - `IMAGE` and `APP_TAG=1.0.0`
11. Start it: `docker compose up -d`. Migrations run by themselves.
12. Check `docker compose logs web | head -30`: the startup line should name the prod settings and Postgres.

## D. First data (once only)

13. `docker compose run --rm web python manage.py seed_phase1`. It loads plans, facilities and site text, and only adds rows that are missing.
14. `docker compose run --rm web python manage.py setup_roles`. It creates the team levels and approval groups.
15. `docker compose run --rm web python manage.py createsuperuser`. Use your own email and a strong password.

## E. Checks

16. Open `https://spa99.uk/health/`. It should answer OK.
17. Run `curl -X POST -d '{}' https://spa99.uk/ses/notifications/`. It should answer 400 or 403, not 404. Then, in SNS, open the topic and create a subscription: HTTPS, endpoint `https://spa99.uk/ses/notifications/`. Its status should turn to Confirmed.
18. **System** (`system.spa99.uk`):
    - Add Barry in Team (Office level).
    - Make him Approver in Approval.
    - Check the opening date, the email settings and that Memberships is still hidden.
19. Test it yourself:
    - Do the journey and enter your email.
    - Register, then confirm the email.
    - Apply for the Gold Card. Check the approver email arrives and that the application shows in Office.
20. Run `docker compose run --rm web python manage.py sentry_test` and check the test error appears in Sentry.

## F. Every deploy after launch

- Take an RDS snapshot first.
- Never edit or delete a migration that is already live.
- Tag the new version (for example `1.0.1`), set `APP_TAG` in `.env`, run `docker compose up -d`, then check `/health/`.
- If something breaks, set `APP_TAG` back to the previous version and run `docker compose up -d` again. If a migration damaged data, restore the snapshot.

## Suggestions (not blockers)

- **Soft launch:** keep Memberships hidden. People get the journey and the email gate and can register. Turn Memberships on only when prices are final.
- **Stay off the server for 2 days:** no new features or deploys for the first 48 hours. Only urgent fixes.
- **Uptime alert:** add a free check (UptimeRobot or Better Stack) on `https://spa99.uk/health/` that emails you if the site goes down.
- **Cloudflare:** turn on "Always use HTTPS" and basic bot protection. It's free and takes the load off the server.
- **Real phone test:** do the journey, register and apply for Gold on an iPhone and an Android, not just your Mac.
- **Tell Barry:** where the Office is and how Gold approvals arrive.
- **Before the first marketing email:** add an unsubscribe link for journey leads. It's not needed for launch, because confirm and approval emails are transactional.
- **Legal:** get the solicitor's sign-off on the men-only wording and the privacy notice.
