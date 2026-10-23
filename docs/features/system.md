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

**Unlock.** After sign-in, `/unlock/` asks for the password again (5 tries per 5 minutes per person and IP, then 429). The unlock time is in the session; every System request slides it; 15 idle minutes (`SYSTEM_UNLOCK_SECONDS`) locks again. `POST /lock/` is the Lock button. A System sign-in lasts at most 12 hours (`SYSTEM_SESSION_AGE`).

**Change log.** Model `system.SystemChange` (append-only, no history of its own): section, model, object, field, old, new (JSON), kind, who (FK plus email text), `history_id`, `undo_of`. Written by a receiver on django-simple-history's `post_create_historical_record` for the tracked models (`system/changes.py`: SiteSettings, Plan, OpeningRule, Closure, the Gold rule models, journey Question/Option/SuggestionRule, NotificationTemplate; all already had history), so edits made anywhere are listed (no person = "a script"; seed creates with no person are skipped). Team changes (roles, active) have no history and are written directly (`kind=direct`, not undoable). Undo (`services.undo_change`) saves the old value as a new logged change linked by `undo_of`; refused when the field has changed again since, or for created/deleted/team/file entries. Nothing is deleted.

**Recipients moved from env.** `SiteSettings.gold_approver_emails`, `gold_approver_cc`, `contact_email` (blank defaults, comma separated lists validated; migration `plans.0007`, schema only). `SiteSettings.contact_address` is what the site and Reply-To use (stored address, else the one inside `DEFAULT_FROM_EMAIL`); `approver_list` / `approver_cc_list` feed `gold.tasks.send_gold_emails` (empty list: nothing sent, logged once, never crashes). Env vars `GOLD_APPROVER_EMAILS`, `GOLD_APPROVER_CC`, `CONTACT_EMAIL` are removed. `manage.py import_email_settings_from_env [--dry-run]` copies old env values into blank fields once (never a migration).

**Endpoints** (System host; GET pages are minimal HTML with `data-system-*` hooks, POST needs CSRF):

| Path | What |
|---|---|
| `/` | Dashboard: DB ok, queue size (django-q `OrmQ`), last roll-up (django-q `Success`), snapshot age, key counts from the stored dashboard snapshot, last 10 changes, stage switches (read only, link to Settings) |
| `/login/`, `POST /logout/`, `/unlock/`, `POST /lock/` | Sign-in, sign-out, unlock, lock |
| `/changes/` | Change log, filters `section`, `user`, `date_from`, `date_to`, 50 a page |
| `POST /changes/<id>/undo/` | Undo one entry |
| `/emails/` | Edit the three recipients |
| `/settings/` | Opening date and text, stage switches, wording, VAT |
| `/team/`, `POST /team/<id>/roles/`, `POST /team/<id>/active/` | Staff users and roles (Owner, Manager, Viewer, Approver, System); deactivate or reactivate. Superuser flags are never changed; you cannot deactivate yourself or drop your own System role; only a superuser can change a superuser |
| `/health/`, `/robots.txt` | Open |

Nav entries for Plans and pricing, Hours and closures, Gold rules and Journey are stubs (`data-system-soon`, no link) until the next step. No CSS yet (design brief: `docs/design/SYSTEM.md`).

New env vars: `SYSTEM_DOMAIN`, `SYSTEM_URL` (both optional locally). Removed: `GOLD_APPROVER_EMAILS`, `GOLD_APPROVER_CC`, `CONTACT_EMAIL`. Caddyfile and docker-compose pass `SYSTEM_DOMAIN`. Nothing is Postgres-only. Run `manage.py migrate` then `setup_roles` after pulling; give a developer the System role with the Django admin (Staff status plus the System group).
