# Spa 99 software

Django 5.2 (Python 3.13) for the Spa 99 website and Spa 99 Control. Read `docs/PROJECT.md` first.
This README is the practical side: run it, test it, back it up, configure it.

## Set up (once)

```bash
cd "/Users/moishe/Documents/My Apps/spa99-software"
/opt/homebrew/bin/python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_phase1            # plans, prices, hours, facilities, site copy, journey questions, Gold rules (safe to repeat; --dry-run to preview)
python manage.py setup_roles            # Owner / Manager / Viewer groups (proposed permissions)
python manage.py createsuperuser        # email + password; use it for Control and the hidden admin
```

No `.env` and no private folder are needed locally. With neither, the app uses dev defaults and a SQLite
database at `.private/db.sqlite3`. On start it logs one line saying which config sources, database and media
storage it used, plus a warning for every key from `.env.example` that is missing.

## Run locally

```bash
python manage.py runserver
```

- Public site: <http://localhost:8000>: home, `/the-spa/`, `/memberships/`, `/gold-card/`, `/book/`, `/visit/`, `/privacy/`, `/terms/`, the guided journey at `/journey/`, the Gold application at `/gold-card/apply/`, `/register/`, `/login/`, `/account/`, plus the data endpoints `/journey/...`, `/gold/...` and `/health/`. Run `python manage.py seed_phase1` first so the pages have their copy.
- Emails print in the terminal running `runserver` / `qcluster` (console backend). Queued emails need `python manage.py qcluster` running.
- Spa 99 Control: <http://control.localhost:8000> (`*.localhost` resolves to your Mac automatically; sign in with a staff user)
- Hidden Django admin (superuser fallback): `http://control.localhost:8000/<ADMIN_PATH>` , default `/backstage-7d3f9a/`. Change `ADMIN_PATH`.

Background worker (separate terminal; needed for queued and scheduled jobs):

```bash
python manage.py register_schedules     # creates the recurring jobs (safe to repeat)
python manage.py qcluster
```

Jobs use django-q2 with the database as the queue (no Redis). Queue a job from code with
`common.tasks.enqueue("app.tasks.name", ...)`. Recurring jobs are listed in `common/management/commands/register_schedules.py`.

## Tests

```bash
python manage.py test                   # uses config.settings.test automatically
```

Tests are mocked: no network, in-memory media storage, background jobs run synchronously.
GitHub Actions runs the same tests against a PostgreSQL service container on every push and PR.
Nothing in the code is Postgres-only.

## Configuration

Order, earlier wins: real environment variables, then `$SPA99_PRIVATE_DIR/env/.env`, then the project `.env`,
then dev defaults. If the private folder is missing or unreadable, `.private/` in the project is used instead.

Private folder (default `/Users/moishe/Library/CloudStorage/OneDrive-Personal/BML/Spa 99/Software Files`):
`env/.env` (secrets), `db-backups/`, `media/`. The working database is never kept there.

| Key | What it is for |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` locally (default), `config.settings.prod` on the server |
| `SECRET_KEY` | Django secret. Prod refuses to start without a real one |
| `DOMAIN` | Public domain, no `https://` (prod default `spa99.uk`) |
| `CONTROL_DOMAIN` | Control domain (prod `control.spa99.uk`; local default `control.localhost`) |
| `DATABASE_URL` | Managed PostgreSQL on live (required in prod, `sslmode=require` added). Unset locally = SQLite |
| `DEBUG` | Dev only. Prod forces it off |
| `ALLOWED_HOSTS` | Optional extra hosts, comma separated (added to the defaults) |
| `ADMIN_PATH` | URL path of the hidden Django admin on the Control domain. Required in prod and must not be the default |
| `SPA99_PRIVATE_DIR` | Private folder location override (also read from the project `.env` by the backup scripts) |
| `SPA99_DB_FILE` | Scripts only (env var, not in `.env`): SQLite file that `backup_db.sh` / `restore_db.sh` use. Default `.private/db.sqlite3` |
| `AWS_STORAGE_BUCKET_NAME` | S3 media bucket (`spa99-media`). Empty = local file storage, never a crash |
| `AWS_S3_REGION_NAME` | Bucket region (`eu-west-2`) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Local dev keys, allowed into `dev/` only. Never on the server (it uses its instance role) |
| `EMAIL_BACKEND` | Dev: console (default). Live: `notifications.backends.SesBackend` (SES via the server IAM role) or the default SMTP backend |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | SMTP settings (only with the SMTP backend) |
| `DEFAULT_FROM_EMAIL` | From address (default `Spa 99 <hello@spa99.uk>`); replies go to the contact email in Site settings |
| `AWS_SES_REGION_NAME` | Region for `SesBackend` (default `eu-west-2`) |
| `SITE_URL`, `CONTROL_URL` | Absolute links in emails (defaults from `DOMAIN` / `CONTROL_DOMAIN`; dev `http://localhost:8000` and `http://control.localhost:8000`) |
| `SENTRY_DSN` | Error reporting. Off when empty |
| `IMAGE`, `APP_TAG` | Read by `docker-compose.yml`: image name and the git tag to run |
| `GUNICORN_WORKERS` | Web workers in the container |

Media goes to `dev/` (dev settings) or `prod/` (prod settings) inside the bucket; files are private and served by signed URL.
Without S3 settings, files go to `$SPA99_PRIVATE_DIR/media` or `.private/media`.

## Backup and restore (local SQLite)

```bash
scripts/backup_db.sh      # consistent copy to db-backups/ named db-YYYY-MM-DD_HH-MM-SS.sqlite3, keeps the newest 30
scripts/restore_db.sh     # lists backups, you pick one and type RESTORE; the current DB is kept as a safety copy (newest 5 kept)
```

Live uses managed PostgreSQL: take an RDS snapshot before every deploy and backfill.

## Live (Docker)

Images are built by GitHub Actions on a version tag (`1.2.3`, no `v`) after the tests pass. The server holds
`docker-compose.yml`, `Caddyfile` and `.env` only. Services: `caddy` (HTTPS), `web` (runs migrations, then gunicorn),
`worker` (background jobs). Deploy by changing `APP_TAG` in the server `.env`, then `docker compose up -d`.
Check `https://<domain>/health/` afterwards. Pushing the image needs repo variables `REGISTRY`, `IMAGE_NAME` and
secrets `REGISTRY_USERNAME`, `REGISTRY_PASSWORD`; until set, the workflow builds the image and skips the push.

## Project layout

`config/` settings (`base`, `dev`, `prod`, `test`) and URLs (`urls.py` public, `urls_control.py` Control). `common/` shared
code (base models, validators, spa-day helper, permissions, audit, rate limiter, shared JS/CSS, settings loader). `users/` custom User, register interest, verification, reset, GDPR. `plans/` plans, site settings, hours, facilities (and the `seed_phase1` command). `content/` editable copy. `journey/` guided journey and suggestion engine. `gold/` Gold applications. `notifications/` email sending and log. `insights/` statistics (JSON for the Control dashboard).
Apps are added per `docs/PROJECT.md` section 5. Backfills are management commands with `--dry-run`, never migrations.
