# Feature: Spa 99 Office (business dashboard and analytics)

Branch `feature/office`. Decisions: PROJECT.md rows dated 2026-10-23 (Office/Control split, Office users, "no figure calculated on the fly", cookieless visitor counter). Replaces the business half of `docs/features/admin.md` (Control is now only the building control room, parked until the hardware is in).

## What it is

`office.spa99.uk` (dev: `office.localhost:8000`): the private back office for developers, admins and Barry. Same Django project and database, its own app `office`, its own host via the existing host routing, staff sign-in only (roles Owner, Manager, Viewer and Approver from `setup_roles`). Search engines never see it.

Phase 1 sections:

| Section | What it shows / does |
|---|---|
| **Dashboard** | Today and the last 7/30 days at a glance: people started, finished and registered (plain counts), Gold applications waiting, site visitors and page views. Rings for goals, sparklines, a short "what changed" line |
| **Analytics** | Charts with a date range (7d, 30d, 90d, all): visitors and page views, the funnel (visitor, journey started, journey completed, registered), registrations by membership, journey answers (time of day, frequency, facilities, company), suggested plan split, journey drop-off by screen, Gold applications by potential and status, top pages and referrer sites |
| **People** | Registrations list: search, filter (plan, verified, marketing), open a person (details, membership, journey answers, Gold link). CSV export. GDPR export and delete buttons (existing services) |
| **Gold** | Applications list (potential, status, invite state), open one (the same three sections Barry's email has), Approve and invite, Resend invite, Decline (existing `gold.invites` services) |

Content, plans, hours, notification templates and settings stay in the hidden Django admin for now (a later Office section).

## The rule: stored figures only

No figure is calculated when a page opens. Pages read stored rows.

- **Totals** (e.g. registrations all time, by plan) are counters updated in the same transaction as the event (registration saved, email verified, journey completed, Gold application saved, status change, invite used).
- **Daily rows** (`DailyMetric`: date, metric key, optional dimension like plan or page, value) are written as events happen and topped up by a scheduled roll-up (django-q2, hourly) for anything derived (rates, uniques).
- **Weekly/monthly** views are summed from daily rows by the roll-up into their own rows, so charts read ready series.
- A management command `rebuild_metrics` recomputes everything from the source tables, with `--dry-run` (shows differences only). Never in a migration.
- Tests prove: each event moves the right counters; the roll-up is idempotent; rebuild matches live counters.

## Visitors (cookieless)

Our own counter, no cookies, no personal data:

- Each public page view adds to `DailyMetric` (page views, by path group) in a cheap way (a single upsert, or a small buffered write) and never blocks the page.
- Daily unique visitors use an anonymous hash of (salt of the day, IP, user agent); the salt rotates daily and is discarded, the raw IP and user agent are never stored; only the hash for today is kept (to dedupe) and wiped by the roll-up.
- **Counting rules.** Every Office figure follows `docs/features/office-counting-rules.md` (C1 to C5), which wins over anything else here. In short: a person is the account if linked, else the browser (`JourneySession.person_key`, carried over on restart; backfill old rows with `manage.py backfill_person_key --dry-run`, and run `manage.py backfill_counted_answers --dry-run` once after deploy so older finished journeys give answer votes; never in a migration); bots, staff hosts and staff accounts are never counted; started/finished = distinct people with a journey started/finished in the range, answers and suggested tier = one vote per person (latest finished journey), picked tier = registrations in the range; visitors stay the daily anonymous hash (a journey start also counts as a visitor that day, `insights.visitors.record_journey_start`). The per-day hash flags and `people_*` daily metrics are gone. Registered can exceed finished, so the funnel keeps its capped share and "partial" note.
- Bots and staff hosts are excluded. Referrer is stored as the site name only (no full URL, no query string).
- No cookie banner is needed for this.

## Look

Premium, calm and light (see `docs/design/OFFICE.md`: warm surfaces, soft shadows, no ruled boxes, a muted data palette), with an Apple Health feel: activity rings for goals, crisp sparklines, smooth animated charts, big numbers in the brand numerals. One self-hosted chart library (chosen in the design brief, pinned version), plus SVG rings. Mobile usable (Barry will look on his phone).

## Acceptance checks

- `office.localhost:8000` requires staff sign-in; members and the public get no access; the public site has no link to it.
- Dashboard and Analytics pages run a fixed, small number of queries (no counting over source tables), checked in tests with `assertNumQueries`.
- Registering, verifying, completing a journey, applying for Gold and approving it each update the stored figures immediately.
- Visitor counting stores no IP, user agent or cookie; tests prove the hash is daily and discarded.
- `rebuild_metrics --dry-run` reports no differences on a consistent database.
- Works on SQLite and Postgres.

## Built: server side (branch `feature/office`)

The frontend styles the templates from `docs/design/OFFICE.md`; the templates are minimal with stable hooks (`data-office-*`, `data-ring`, `data-stat`, `data-funnel-step`, `data-gold-row`, `data-approve`, `data-decline`, `data-resend`, `data-export-csv`, `data-show-more`) and all data in the context and as `json_script` (`office-dashboard`, `office-series`, `office-pages`).

**Host.** `OFFICE_DOMAIN` (dev `office.localhost`, prod `office.spa99.uk`), `OFFICE_URL`; `HostRoutingMiddleware` sends it to `config/urls_office.py` and adds `X-Robots-Tag: noindex` on both staff hosts. Control (`control.spa99.uk`) is the parked placeholder (sign-in, index, hidden admin). `/insights/summary/` now lives on the Office host only. Sign-in on the Office host uses the public sign-in shell with Office wording and no public links. Open locally: `.venv/bin/python manage.py runserver`, then `http://office.localhost:8000/` (create a staff user with `createsuperuser`, or `setup_roles` and add a group).

**Levels** (rule book `docs/features/user-rules.md`, U2/U3). Office host needs team level Office or higher (`common/levels.py`; a member or someone with no level gets 403). Office level: sees everything, view only (no buttons rendered, 403 on the URLs). **Approver** (extra permission on top of a level; superusers always): approve, decline, resend Gold, and the one-tap confirm page. Admin and up: export (CSV, a person's data) and delete a member (never a team account or yourself). Decorators in `office/permissions.py`: `reader`, `approver`, `admin`. The old Owner/Manager/Viewer roles and the Approver-only Gold restriction are gone (`migrate_roles` maps people across). Create accounts in System > Team, or `manage.py create_team_member --email --level office|admin|developer [--approver] [--invite]` (`create_office_user` is a deprecated alias). Office sign-ins last 30 days.

**Endpoints** (all on the Office host, GET unless noted):

| Path | What |
|---|---|
| `/` , `/dashboard.json?range=today\|7d\|30d\|all` | Dashboard: `{range, ranges, today, what_changed, gold_waiting, rings[{key,label,value,goal,percent,previous,change}], stats[{key,label,value,previous,change,percent,direction,series,link}], funnel[{key,label,value,previous_value,share_bp,step_rate_bp,partial}], funnel_note, waiting{count,items[5]}, latest[5], totals}`. Rings are plain counts of people for the range: `journeys_started` ("Started the journey"), `journeys_completed` ("Finished the journey"), `registrations` ("Registered interest"); for `all` there is no previous period (`previous` and `change` are null, no change lines) and the sparklines are weekly once history passes 120 days; `change = value - previous` (signed count); `goal` is null and `percent` null when no `OfficeGoal` row exists ("No goal set"), `percent` capped at 200. Stats are registrations, visitors, page_views (`change` is a signed count; `percent`/`direction` only drive the small delta). `OfficeGoal` keys: `journeys_started`, `journeys_finished`, `registrations`, all counts per range (old `journey_completion` / `gold_handled` rows are left inert, never read). The "what changed" sentence is in counts ("2 more than last week"); `insights[{key,title,sentence,top{rank,label,value,of_total,share_bp},runner_up|null,options}]` (top 2, from the stored table, absent when no data). Labels: rings and funnel say Started the journey, Finished the journey, Registered interest |
| `/analytics/`, `/analytics/data/?range=7d\|30d\|90d\|all` | `{range, granularity day\|week, labels, previous_labels, series{key:{total,values,previous}}, funnel, registrations_by_plan, suggested_plan, registrations_by_source, journey_answers{time,frequency,facilities,company}, drop_off[{screen,label,reached,left,left_percent}], gold{by_potential,by_status_now}, summaries{chart: sentence}}`. `all` sends weekly points once history passes 120 days; `insights` (same shape, up to 6 options each) and `tier_pair[{label,picked,suggested}]` (tier people picked vs the tier suggested) |
| `/analytics/pages/?range=` | `{labels, page_views, visitors, top_pages[{page,views}], referrers[{site,visits}], summaries}` (`direct` = no referrer) |
| `/people/?q=&plan=&verified=yes\|no&marketing=yes\|no&page=`, `/people/export.csv` (same filters), `/people/<id>/`, `/people/<id>/export/`, POST `/people/<id>/delete/` | People. 50 rows a page, fetched with one extra row for "Show more" (no filtered counts; the total is the stored counter). HTMX requests get only the rows partial |
| GET `/gold/<id>/approve/confirm/` | One-tap approve page for the approver's email button (sign-in, Approver permission; GET changes nothing; POSTs to `/gold/<id>/approve/`; shows the state instead of the button once decided) |
| `/gold/?status=waiting\|approved\|declined\|all&potential=&q=`, `/gold/<id>/`, POST `/gold/<id>/approve/`, `/resend/`, `/decline/` | Gold. Detail has the three sections from `application_sections`, invite state, history. Resend issues a new link and revokes the old one; `gold.invites.decline_application` is new |

**Stored figures.** `insights` models: `MetricCounter` (all-time or current state), `DailyMetric` (London day), `PeriodMetric` (week from Monday, month), `MetricText` (sentences written by the roll-up), `OfficeGoal` (ring goals, edited in the hidden admin), `VisitorSalt` and `VisitorHash` (today only). Keys are in `insights.metrics.K`. Write side `insights/metrics.py` is called from the services inside the event's transaction: registration, verification, plan change and erasure (`users.services`), journey start, screen reach, completion, suggestion and answers (`journey.services`, `journey.engine`), Gold activation and invite use (`gold.invites`). Deviation: Gold application, status and invite figures follow model signals (`insights/signals.py`) because the Django admin edits the status directly and GDPR delete removes rows. Each daily row carries the entity's own date (session start, registration, completion, approval), so `rebuild_metrics` recomputes the same rows. Visitor and page-view rows have no source table and are never rebuilt. Rates are basis points. Weekly and monthly "visitors" are sums of daily uniques (hashes are wiped daily).

**Roll-up** (`insights.rollup.scheduled`, django-q2 hourly, registered by `register_schedules`): wipes finished days' visitor hashes and salts, writes daily rates, weekly and monthly rows, refreshes the visitor and page-view counters and rewrites every `MetricText` sentence. It recomputes from the daily rows in the window, so running it again changes nothing. Dashboard and Analytics read only these rows plus two `LIMIT 5` lists; tests prove the query count does not grow with data.

**Snapshots (nothing is summed on page load).** `insights.OfficeSnapshot` (page dashboard|analytics|pages, range, JSON payload) holds the finished payload of every page and range. `office.snapshots.build_everything` (called by the hourly roll-up, `rebuild_metrics`, and the queued job `office.snapshots.refresh`) loads people and registrations from the source tables once (`insights.people`), writes the sentences, the insights and the snapshots (only changed rows, by unique-key upsert, so overlapping runs are safe on SQLite and Postgres). Freshness: after any counted event (`metrics.count` with a counter, a visitor starting a journey, a goal edited) `snapshots.request_refresh` queues one job via `common.tasks.enqueue` once the transaction commits; `SnapshotRefresh.queued_at` debounces a burst into one job (a flag older than 2 minutes expires, so a stopped queue never blocks it, and the hourly roll-up covers the gap). Views read one row per payload (`selectors.dashboard/analytics/pages`) plus the two LIMIT-5 lists; a missing row (fresh database) renders an empty state. "Today" after midnight is rebuilt by the next hourly job or the first event of the day. Analytics series: the total is distinct people (or registrations) in the whole range, the points are per day (per week for a long All), so the previous-period change compares the total with the sum of daily points.

**What people want (insights).** Written by the same job from the same load, so headline and insight always agree (answers: one vote per person; "4 of 5" is of the people who finished in the range). `insights.Insight` (range today/7d/30d/90d/all, key, rank 1..6, title, label, value, of_total, sentence on rank 1) is written by `insights.facts.write_all` inside that job. Keys: facility, time, frequency, company (journey answers, real option labels; multiple-choice shares are of journeys finished), tier_picked (registrations by plan), tier_suggested, source (referrer sites from visitors, not rebuildable). No data, no rows. Dashboard and Analytics read it with one query; nothing is computed on page load. Rank now runs to 12 (`facts.MAX_RANK`, every option of the biggest question). Data shape: `dashboard.insights` and `analytics.insights` are `[{key, title, sentence, top, runner_up, options[{rank,label,value,of_total,share_bp}]}]`; the Dashboard snapshot carries **every** option (the closed card shows six tiles from `top`/`runner_up`, the open card lists all `options` per key, `source` last), Analytics keeps the first six (`selectors.ANALYTICS_RANK`).

**Command.** `python manage.py rebuild_metrics [--dry-run]` shows differences between stored figures and the source tables, or replaces them and re-runs the whole roll-up. Run once after deploy to backfill; never in a migration.

**Visitor counter.** `insights.middleware.VisitorCounterMiddleware` (last in MIDDLEWARE): counts GET 200 HTML pages on the public host only, not bots or empty user agents, static, media or prefetch. Page views by path group (first segment; `home`), one unique per sha256(day salt, IP, user agent), referrer host only (`direct` when none). Errors are logged and swallowed. Setting `VISITOR_COUNTER = False` switches it off. The same middleware file's helper `record_step` (called from the journey and register views) feeds the people metrics; like visitors they have no source table, so `rebuild_metrics` never rebuilds them, and weekly/monthly figures are sums of daily people. Registrations through other routes (Gold invite, admin) are not counted as people.

New env vars: `OFFICE_DOMAIN`, `OFFICE_URL` (optional). Nothing is Postgres-only (ORM only, `select_for_update` is ignored by SQLite).

**Review fixes.** Journey completion reads its old state from a row-locked copy (`select_for_update().get`), so two tabs count once (the lock only bites on Postgres; SQLite serialises writes). The visitor-sentence refresh is queued with `common.tasks.enqueue`, never run inside the page request. Roles also require `is_staff`. People and Gold lists send `Vary: HX-Request` and are `never_cache`. **Admin and the figures:** a plan change on an `InterestRegistration` is counted by a signal (`insights/signals.py`, the services save through it too); in the admin, `User.email_verified_at` and `marketing_consent` are read only, adding or deleting an `InterestRegistration` is off, deleting a User goes through `delete_user_data` (full erasure, figures move), and `JourneySession` is read only (add, change, delete off). Anything else that bypasses the services is repaired by `rebuild_metrics`.
