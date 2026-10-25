# Foundation (plumbing)

No visible pages. Everything later phases sit on.

## What exists
- Settings split `base/dev/prod/test`; loader in `common/envloader.py` (env vars, private `.env`, project `.env`, defaults; falls back to `.private/`). One startup log line (logged once per process, so gunicorn workers and the qcluster each log their own); one warning per missing `.env.example` key (keys whose comment says "optional" are skipped).
- Host routing (`common.middleware.HostRoutingMiddleware`): `CONTROL_HOST` gets `config.urls_control`, all else `config.urls`. Sessions are per host.
- Locked by default: `LoginRequiredMiddleware`. Public views are marked `@login_not_required` with a comment (only `/health/` and the login page).
- `/health/`: 200 `{"status":"ok"}` if the database answers, else 503.
- Storage: media on private S3 (`dev/` or `prod/`) when configured, else local; static via WhiteNoise manifest.
- Jobs: django-q2 with the database as queue. `common.tasks.enqueue`, `heartbeat`, `register_schedules`.
- `common`: `BaseModel` (UUID `id`, `created_at`, `updated_at`), `LoginEvent` (login, logout, failed; append-only in admin), `spa_day_for`, validators (email, UK mobile to E.164, password rules) mirrored in `static/common/js/validate.js`, buttons/modal/messages JS, permission helpers (`staff_required`, `group_required`, mixins), CSV export admin action.
- `users.User` (person data only, no status; interest will be an `InterestRegistration` record, membership comes from `memberships`): email login (lowercase, case-insensitive unique), `public_id`, names, mobile (always saved as E.164, unique when set), date of birth, `email_verified_at`, marketing consent, privacy version, history (password excluded). `users.services` has `export_user_data` and `delete_user_data` (UK GDPR).

## Rules and edge cases
- Spa day: 00:00-02:59 belongs to the previous day; 03:00-04:59 to the day about to open. Worked out in Europe/London so clock changes are safe. Boundaries come from `SPA_DAY_START` / `SPA_DAY_END` or are passed in.
- Login does not write user history (last_login is set by a queryset update); the `LoginEvent` is the record.
- Erasing a person deletes their history rows too (history holds personal data). This is the one exception to "history is never deleted".
- Roles (Django Groups) are not created yet: the permission levels need approval first (RULES.md section 23).
- Prod refuses to start without a real `SECRET_KEY` and `DATABASE_URL`. HSTS stays off until the site has run on HTTPS without problems.
- Mail transport and the sender come only from env: `DEFAULT_FROM_EMAIL` (required in prod), `SERVER_EMAIL`, `EMAIL_HOST/PORT/HOST_USER/HOST_PASSWORD/USE_TLS/BACKEND`. Recipients (Gold approver, CC, contact email) are `SiteSettings` fields edited in System (2026-10-23; `CONTACT_EMAIL`, `GOLD_APPROVER_EMAILS`, `GOLD_APPROVER_CC` env vars are gone). Hosts: `DOMAIN`, `CONTROL_DOMAIN`, `OFFICE_DOMAIN`, `SYSTEM_DOMAIN` (+ `*_URL`); the startup log line lists them. Nothing is hard-coded; DKIM is signed by the mail provider/DNS. Dev has a dev-only From default and the console backend.
- `ALLOWED_HOSTS` in the environment adds to the defaults (DOMAIN, CONTROL_DOMAIN, OFFICE_DOMAIN, SYSTEM_DOMAIN, localhost, 127.0.0.1); it does not replace them.
- Prod also refuses to start if `ADMIN_PATH` is unset or still the committed default. Prod logs a loud warning if media is on local disk.
- `DJANGO_SETTINGS_MODULE` is also read from the private / project `.env` (manage.py, wsgi, asgi). Tests use `config.settings.test`, which ignores `.env` files.
- Static files use `common.storage.SpaStaticFilesStorage` so ES module imports get hashed names (cache busting).
- `export_user_data` covers everything `delete_user_data` removes: profile, login events (by user and by attempted email) and history rows.
- Error pages: 400, 403, 404, 500; CSRF failures show the 403 page.

## Errors and Sentry
- `common/observability.py`: `init_sentry` runs from `base.py` after the env loads. Off when `SENTRY_DSN` is empty. Env: `SENTRY_DSN`, `SENTRY_ENVIRONMENT` (default `dev`, `live` under prod settings), `APP_VERSION` (release; docker-compose passes `APP_TAG`; no git calls at runtime), `SENTRY_TRACES_SAMPLE_RATE` and `SENTRY_PROFILES_SAMPLE_RATE` (default 0). Dev sends too when a DSN is set; tests never do.
- Getting the DSN: Sentry > create a new Django project > Settings > Client Keys (DSN). Locally put it in `SPA99_PRIVATE_DIR/Secrets/.env`; on live put it in the server env file. Test with `manage.py sentry_test` (prints whether a DSN is set and the event ids, never the DSN).
- Events: Django integration, ERROR+ log records become events, INFO records are breadcrumbs. django-q failures are logged at ERROR by its monitor (`Failed '...'`), so they arrive with no extra hook.
- Privacy: `send_default_pii=False`; `before_send` removes cookies, Authorization/Cookie/X-CSRFToken headers, request bodies, query strings on `/journey/ /register/ /gold-card/apply/ /login/ /unlock/`, values under keys containing password/token/secret/key/email/phone/mobile/name/address, and email addresses in messages. Only user id plus `staff` and `host` (public/office/control/system, `worker` for jobs) tags are sent (`SentryContextMiddleware`).
- In the Sentry project settings (Settings > Security & Privacy) switch ON "Prevent storing of IP addresses" and keep "Data scrubber" on (default). Headers are an allowlist (Accept, Accept-Language, User-Agent, Host, Content-Type, Content-Length), local variables are never sent, and query strings are dropped on office/control/system hosts (`q`/`search` are treated as sensitive elsewhere).
- Ignored: Http404, PermissionDenied, DisallowedHost, client disconnects (`RequestAborted`; `ConnectionResetError`/`BrokenPipeError` only when the event has a request), our own 429 responses. The startup log line ends with `sentry=on(live)` or `sentry=off`. Server side only: no browser SDK, so the CSP needs no change.

## Team levels and commands

- Levels are the groups `Office`, `Admin`, `Developer` (plus the superuser flag) and the extra group `Approver`; the one helper is `common/levels.py` (`level_of`, `can_manage`, `is_approver`). Rules: `docs/features/user-rules.md`. The hidden Django admin is superuser only (`common.admin_site.SuperuserAdminSite`).
- `manage.py setup_roles [--dry-run]` creates the four groups (no model permissions: the level is the membership) and removes the retired Owner/Manager/Viewer/System groups once everyone in them holds a level.
- `manage.py migrate_roles [--dry-run]` (a command, never a migration): Owner and Manager to Admin, Viewer to Office, System to Developer, Approver stays (plus Office if no level). Run it before `setup_roles` on an existing database.
- `manage.py create_team_member --email x --level office|admin|developer [--approver] [--invite]`: asks for a password, or `--invite` sends the set-your-password email. `create_office_user` still works and prints a deprecation note.

## Known follow-ups
- (Closed) Public login route: `/login/` now works on both hosts (see `register-interest.md`).
- Rate limiting uses Django's database cache (`CACHES` in base settings, table `spa99_cache`), so all gunicorn workers share one count. Create the table with `manage.py createcachetable` (idempotent; `entrypoint.sh` runs it after `migrate`; locally run it once after `migrate`). Tests and the e2e run use a dummy or in-memory cache and need no table. If the cache cannot be reached, `common.ratelimit.hit` lets the request through and logs it. Postgres and SQLite both work; the count is not atomic under a burst (`incr` reads then writes), which is acceptable for throttling.
