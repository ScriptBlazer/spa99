# Foundation (plumbing)

No visible pages. Everything later phases sit on.

## What exists
- Settings split `base/dev/prod/test`; loader in `common/envloader.py` (env vars, private `.env`, project `.env`, defaults; falls back to `.private/`). One startup log line; one warning per missing `.env.example` key (keys whose comment says "optional" are skipped).
- Host routing (`common.middleware.HostRoutingMiddleware`): `CONTROL_HOST` gets `config.urls_control`, all else `config.urls`. Sessions are per host.
- Locked by default: `LoginRequiredMiddleware`. Public views are marked `@login_not_required` with a comment (only `/health/` and the login page).
- `/health/`: 200 `{"status":"ok"}` if the database answers, else 503.
- Storage: media on private S3 (`dev/` or `prod/`) when configured, else local; static via WhiteNoise manifest.
- Jobs: django-q2 with the database as queue. `common.tasks.enqueue`, `heartbeat`, `register_schedules`.
- `common`: `BaseModel` (UUID `id`, `created_at`, `updated_at`), `LoginEvent` (login, logout, failed; append-only in admin), `spa_day_for`, validators (email, UK mobile to E.164, password rules) mirrored in `static/common/js/validate.js`, buttons/modal/messages JS, permission helpers (`staff_required`, `group_required`, mixins), CSV export admin action.
- `users.User`: email login (lowercase, case-insensitive unique), `public_id`, names, mobile (E.164, unique when set), date of birth, `email_verified_at`, marketing consent, privacy version, `status` (`interest`, `member`), history (password excluded). `users.services` has `export_user_data` and `delete_user_data` (UK GDPR).

## Rules and edge cases
- Spa day: 00:00-02:59 belongs to the previous day; 03:00-04:59 to the day about to open. Worked out in Europe/London so clock changes are safe. Boundaries come from `SPA_DAY_START` / `SPA_DAY_END` or are passed in.
- Login does not write user history (last_login is set by a queryset update); the `LoginEvent` is the record.
- Erasing a person deletes their history rows too (history holds personal data). This is the one exception to "history is never deleted".
- Roles (Django Groups) are not created yet: the permission levels need approval first (RULES.md section 23).
- Prod refuses to start without a real `SECRET_KEY` and `DATABASE_URL`. HSTS stays off until the site has run on HTTPS without problems.
