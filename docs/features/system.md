# Feature: Spa 99 System (dev-only business rules)

Branch `feature/system`. Decisions: PROJECT.md rows 2026-10-23 (three staff front ends on one backend; System before Control; recipients move from env to System).

## What it is

`system.spa99.uk` (dev: `system.localhost:8000`): the locked room where developers change the rules the site and, later, the building run on. Same Django project and database, its own app `system`, its own host via the existing host routing. Search engines never see it. Nothing in Office or Control links to it.

## Who gets in

- Developers only: superusers, or members of a `System` group (created by `setup_roles`). Everyone else gets a plain 404 (the host does not admit it exists).
- Password asked again on entry ("unlock"), valid 15 minutes of activity, then asked again. Office/public sign-ins never unlock System.
- Every change is logged: who, when, what, old value, new value, with one-click undo (restores the old value as a new logged change). Uses the existing `django-simple-history` where the model has it; a single `system` change list reads it.

## Phase 1 sections

| Section | What you can change |
|---|---|
| **Dashboard** | Light admin overview: site health (`/health/`, queue, last roll-up, last snapshot), key counts from the Office snapshots (no page-load sums), recent System changes, stage switches at a glance |
| **Plans and pricing** | Tiers and single visit: name, price ex VAT, visits, hours, booking window, limits, guests, perks, visible, order; VAT rate |
| **Hours and closures** | Opening rules (periods, daily closure, Shabbos/Yom Tov offsets), one-off closures, capacity |
| **Gold rules** | Potential weights and thresholds; which answers count as property |
| **Journey** | Questions and options: labels, order, hidden, plan and Gold points per option |
| **Emails** | Recipients (Gold approver list, CC, contact email); template wording for each notification. Transport and secrets stay in env |
| **Settings** | Opening date, stage switches (register interest / subscribe / book), wording |
| **Team** | Staff users and their roles (Owner, Manager, Viewer, Approver, System) |

Later (own phases): stay periods, RFID and Face ID rules, access windows, sales and offers (need the access hardware), content and images.

## Look

Compact, dense and calm: small boxes, small controls, tables you can edit in place, a left section list. Different from the Office (not the brand showcase). One small, self-hosted CSS library may be used if it clearly helps (chosen in the design brief, pinned version).

## Rules carried over

- Business rules are data, edited here, never hard-coded.
- Pages read stored rows; nothing heavy computed on page load.
- Settings changes take effect at once (caches cleared on save).
- Works on SQLite and Postgres.

## Built (2026-10-23, foundations; plans, hours, Gold rules and journey screens come next)

**Host and access.** `SYSTEM_DOMAIN` (dev `system.localhost`, prod `system.spa99.uk`), `SYSTEM_URL`; `HostRoutingMiddleware` sends it to `config/urls_system.py`, `X-Robots-Tag: noindex, nofollow`; the startup log line lists the three staff hosts. Allowed: `is_staff` and active and (superuser or `System` group, made by `setup_roles`, which holds no model permissions). Everyone else, anonymous included, gets a plain 404 (`system.permissions`); only `/login/`, `/health/` and `/robots.txt` are open. The sign-in is the shared `LoginView` (rate limited per IP); a person who may not use System sees the ordinary wrong-password answer. Sign-in sets a session flag, so a session made on another host never counts.

**Unlock.** After sign-in, `/unlock/` asks for the password again (5 tries per 5 minutes per person and IP, then 429). The unlock time is in the session; every System request slides it; 15 idle minutes by default locks again. Both limits are edited in System > Settings > Security (`SiteSettings.lock_idle_minutes` 1 to 240, `max_sign_in_hours` 1 to 72; risky, logged, undoable); `SYSTEM_UNLOCK_SECONDS` and `SYSTEM_SESSION_AGE` are only the fallback defaults. The page gets the seconds left from the server (`data-system-remaining`); activity (mouse, keys, scroll, click, tab return) sends `POST /unlock/ping/` at most once a minute, which slides the window and answers `{"remaining": seconds}` (403 when locked; `peek=1` reads without sliding). The top bar shows a lock icon and 'Unlocked', and the countdown with Stay unlocked only in the last 2 minutes. `POST /lock/` is the Lock button. A System sign-in lasts at most 12 hours by default.

**Change log.** Model `system.SystemChange` (append-only, no history of its own): section, model, object, field, old, new (JSON), kind, who (FK plus email text), `history_id`, `undo_of`. Written by a receiver on django-simple-history's `post_create_historical_record` for the tracked models (`system/changes.py`: SiteSettings, Plan, OpeningRule, Closure, the Gold rule models, journey Question/Option/SuggestionRule, NotificationTemplate; all already had history), so edits made anywhere are listed (no person = "a script"; seed creates with no person are skipped). Team changes (roles, active) have no history and are written directly (`kind=direct`, not undoable). Undo (`services.undo_change`) saves the old value as a new logged change linked by `undo_of`; refused when the field has changed again since, or for created/deleted/team/file entries. Nothing is deleted.

**Recipients moved from env.** `SiteSettings.gold_approver_emails`, `gold_approver_cc`, `contact_email` (blank defaults, comma separated lists validated; migration `plans.0007`, schema only). `SiteSettings.contact_address` is what the site and Reply-To use (stored address, else the one inside `DEFAULT_FROM_EMAIL`); `approver_list` / `approver_cc_list` feed `gold.tasks.send_gold_emails` (empty list: nothing sent, logged once, never crashes). Env vars `GOLD_APPROVER_EMAILS`, `GOLD_APPROVER_CC`, `CONTACT_EMAIL` are removed. `manage.py import_email_settings_from_env [--dry-run]` copies old env values into blank fields once (never a migration).

**Endpoints** (System host; GET pages are minimal HTML with `data-system-*` hooks, POST needs CSRF):

| Path | What |
|---|---|
| `/` | Dashboard: DB ok, queue size (django-q `OrmQ`), last roll-up (django-q `Success`), snapshot age, key counts from the stored dashboard snapshot, last 10 changes, stage switches (read only, link to Settings) |
| `/login/`, `POST /logout/`, `/unlock/`, `POST /lock/` | Sign-in, sign-out, unlock, lock |
| `/changes/` | Change log, filters `section`, `user` (select of people who made changes), `q` (field, row, person or value), `range` (1, 7, 30 days), `date_from`, `date_to`, 50 a page, fixed query count |
| `POST /changes/<id>/undo/` | Undo one entry |
| `/emails/` | Edit the three recipients |
| `/settings/` | Opening date and text, stage switches, wording, VAT |
| `/team/`, `POST /team/<id>/roles/`, `POST /team/<id>/active/` | Staff users and roles (Owner, Manager, Viewer, Approver, System); deactivate or reactivate. Superuser flags are never changed; you cannot deactivate yourself or drop your own System role; only a superuser can change a superuser |
| `/health/`, `/robots.txt` | Open |

No CSS yet (design brief: `docs/design/SYSTEM.md`).

New env vars: `SYSTEM_DOMAIN`, `SYSTEM_URL` (both optional locally). Removed: `GOLD_APPROVER_EMAILS`, `GOLD_APPROVER_CC`, `CONTACT_EMAIL`. Caddyfile and docker-compose pass `SYSTEM_DOMAIN`. Nothing is Postgres-only. Run `manage.py migrate` then `setup_roles` after pulling; give a developer the System role with the Django admin (Staff status plus the System group).

### Rule sections (2026-10-23)

Each page lists rows as small forms (field prefix = the row id; `new...` prefixes for add forms); one POST saves one row through `services.save_form` / `save_logged`, so the change log and undo cover it. Invalid input re-renders the page with field errors (400) and saves nothing. Every page puts `risky_fields` in its context (and `data-system-risky` on the forms) for the frontend's confirm step (old -> new). Validation lives in `system/forms_rules.py`; views in `system/views_rules.py`. The nav now has real links. No site-settings cache exists in the code (pages read the rows each time; the only `lru_cache` is the static logo), so there is nothing to clear on save.

| Path | What |
|---|---|
| `/plans/`, `POST /plans/add/`, `POST /plans/<id>/`, `POST /plans/<id>/visibility/` | Plans table (name, price ex VAT with inc-VAT shown by the `inc_vat` filter from the stored rate, visits, hours, booking window, upcoming limit, cancel hours, guests, perks JSON checked for key/label/value, description, highlight, visible, order). Add; hide or show. No delete exists. VAT stays on Settings |
| `/hours/`, `POST /hours/capacity/`, `POST /hours/rules/add/`, `POST /hours/rules/<id>/`, `POST /hours/closures/add/`, `POST /hours/closures/<id>/`, `POST /hours/closures/<id>/delete/` | Capacity and slot sizes; opening rules (times for periods and daily closure, minute offsets for Shabbos / Yom Tov rules); closures add, edit, delete (delete is logged, not undoable) |
| `/gold/`, `POST /gold/add/`, `POST /gold/<id>/` | Gold rules: points, property flag, active; the High threshold cannot fall below Medium |
| `/journey/`, `POST /journey/questions/<id>/`, `POST /journey/questions/<id>/options/add/`, `POST /journey/options/<id>/`, `POST /journey/suggestions/<id>/` | Questions (text, screen, order, min choices, active), options (label, order, active, plan points JSON checked against real plan slugs, Gold points, weight, reason), suggestion rules (conditions and plan slugs checked) |

### Follow-ups (2026-10-23)

- `POST /unlock/ping/` ("Stay unlocked"): slides the 15 minutes, 204; 403 when already locked; 404 for strangers. `system.js` uses it (CSRF header).
- Nav order: Team, then Change log last (the template reorder is gone).
- Dashboard `health`: `failed_tasks_24h` (django-q `Failure`), `gold_waiting` and `people_total` (stored counters), `snapshot_stale` (older than 15 minutes, or no snapshot).
- Change log: `SystemChange.batch_id` (migration `system.0002`, schema only) is one id per System request; changes saved together show "Saved together (N)" and **Undo all** (`POST /changes/batch/<id>/undo/`, only entries not yet undone and still at the saved value). Rows carry `batch_size`, `batch_open`, `batch_first`; `undone_by` is prefetched and the page runs a fixed number of queries (tested). The singleton's first creation is not logged.
- Toasts: after a save the message has `extra_tags="undo:<url>"` (the entry's undo, or undo all when several) via `views.saved()`.
- `SYSTEM_ENV_LABEL` (DEV/LIVE; dev default DEV, prod default LIVE, optional env var) reaches System templates as `system_env` through `system.context.system` (System host only).
- The plan hide/show endpoint is removed: the row's Visible toggle saves through the normal row POST, which is logged and undoable.

### Review fixes (2026-10-23)

- The 12 hour limit is a hard cap: the System sign-in time is stored in the session and checked on every request (`services.sign_in_valid`); after 12 hours the person is signed out and sent to the sign-in, however active they were.
- `SiteSettings.vat_rate` must be 0 to 100 (validator, `plans.0008`, schema only); VAT, opening date, stage switches and the recipients are passed as `risky_fields` so Settings and Emails confirm old to new.
- `system.middleware.SystemGateMiddleware` (after sessions, before CSRF) answers the plain 404 to anyone who may not be on the System host, so real routes and unknown paths look the same. `/login/`, `/health/` and `/robots.txt` stay open.
- Undo all runs in one transaction with a savepoint per entry: a refused entry (changed again, already undone) is skipped and reported while the others go through; any unexpected error rolls the whole batch back. Undo re-reads the entry with `select_for_update()` (no joins) and refuses when it was already undone.
- A locked POST comes back after unlock to the Referer (same host only) or its section page, never to the POST-only URL.

