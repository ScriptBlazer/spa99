# Feature: Spa 99 Office (business dashboard and analytics)

Branch `feature/office`. Decisions: PROJECT.md rows dated 2026-10-23 (Office/Control split, Office users, "no figure calculated on the fly", cookieless visitor counter). Replaces the business half of `docs/features/admin.md` (Control is now only the building control room, parked until the hardware is in).

## What it is

`office.spa99.uk` (dev: `office.localhost:8000`): the private back office for developers, admins and Barry. Same Django project and database, its own app `office`, its own host via the existing host routing, staff sign-in only (roles Owner, Manager, Viewer from `setup_roles`). Search engines never see it.

Phase 1 sections:

| Section | What it shows / does |
|---|---|
| **Dashboard** | Today and the last 7/30 days at a glance: people started, finished and registered (plain counts), Gold applications waiting, site visitors and page views. Rings for goals, sparklines, a short "what changed" line |
| **Analytics** | Charts with a date range (7d, 30d, 90d, all): visitors and page views, the funnel (visitor, journey started, journey completed, registered), registrations by plan interest, journey answers (time of day, frequency, facilities, company), suggested plan split, journey drop-off by screen, Gold applications by potential and status, top pages and referrer sites |
| **People** | Registrations list: search, filter (plan, verified, marketing), open a person (details, plan interest, journey answers, Gold link). CSV export. GDPR export and delete buttons (existing services) |
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
- **The funnel counts people, not sessions.** When a journey starts or is restarted, is finished (`POST /journey/result/`), or a registration is saved on the public site, `insights.visitors.record_step` computes today's same anonymous hash and flips a `started`, `finished` or `registered` flag on that `VisitorHash` row, counting each once per person per day (`people_started`, `people_finished`, `people_registered` daily metrics). A later step also counts the earlier ones, and a person not yet seen as a visitor is counted as one, so visitors >= started >= finished >= registered always holds. Same gates as the visitor counter (public host, no bots, no prefetch, `VISITOR_COUNTER`); errors are logged and swallowed. Flags are wiped with the hashes. The Dashboard rings, both funnels, the Analytics hero (`journeys_started` series = people started, `people_registered`), the rates and the summary sentences use these. The session-based `journeys_started` / `journeys_completed` stay for drop-off per screen and the answer charts.
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

**Roles.** Reads: Owner, Manager, Viewer. Actions (approve, decline, resend, CSV, person export): Owner and Manager. Delete a person: Owner only (never staff or yourself). Viewers get no buttons rendered and a 403 on the URLs.

**Endpoints** (all on the Office host, GET unless noted):

| Path | What |
|---|---|
| `/` , `/dashboard.json?range=today\|7d\|30d` | Dashboard: `{range, ranges, today, what_changed, gold_waiting, rings[{key,label,value,goal,percent,previous,change}], stats[{key,label,value,previous,change,percent,direction,series,link}], funnel[{key,label,value,previous_value,share_bp,step_rate_bp,partial}], funnel_note, waiting{count,items[5]}, latest[5], totals}`. Rings are plain counts for the range: `journeys_started` ("people started"), `journeys_completed` ("finished it"), `registrations`; `change = value - previous` (signed count); `goal` is null and `percent` null when no `OfficeGoal` row exists ("No goal set"), `percent` capped at 200. Stats are registrations, journeys_completed, visitors, page_views (`change` is a signed count; `percent`/`direction` only drive the small delta). `OfficeGoal` keys: `journeys_started`, `journeys_finished`, `registrations`, all counts per range (old `journey_completion` / `gold_handled` rows are left inert, never read). The "what changed" sentence is in counts ("2 more than last week") |
| `/analytics/`, `/analytics/data/?range=7d\|30d\|90d\|all` | `{range, granularity day\|week, labels, previous_labels, series{key:{total,values,previous}}, funnel, registrations_by_plan, suggested_plan, registrations_by_source, journey_answers{time,frequency,facilities,company}, drop_off[{screen,label,reached,left,left_percent}], gold{by_potential,by_status_now}, summaries{chart: sentence}}`. `all` sends weekly points once history passes 120 days |
| `/analytics/pages/?range=` | `{labels, page_views, visitors, top_pages[{page,views}], referrers[{site,visits}], summaries}` (`direct` = no referrer) |
| `/people/?q=&plan=&verified=yes\|no&marketing=yes\|no&page=`, `/people/export.csv` (same filters), `/people/<id>/`, `/people/<id>/export/`, POST `/people/<id>/delete/` | People. 50 rows a page, fetched with one extra row for "Show more" (no filtered counts; the total is the stored counter). HTMX requests get only the rows partial |
| `/gold/?status=waiting\|approved\|declined\|all&potential=&q=`, `/gold/<id>/`, POST `/gold/<id>/approve/`, `/resend/`, `/decline/` | Gold. Detail has the three sections from `application_sections`, invite state, history. Resend issues a new link and revokes the old one; `gold.invites.decline_application` is new |

**Stored figures.** `insights` models: `MetricCounter` (all-time or current state), `DailyMetric` (London day), `PeriodMetric` (week from Monday, month), `MetricText` (sentences written by the roll-up), `OfficeGoal` (ring goals, edited in the hidden admin), `VisitorSalt` and `VisitorHash` (today only). Keys are in `insights.metrics.K`. Write side `insights/metrics.py` is called from the services inside the event's transaction: registration, verification, plan change and erasure (`users.services`), journey start, screen reach, completion, suggestion and answers (`journey.services`, `journey.engine`), Gold activation and invite use (`gold.invites`). Deviation: Gold application, status and invite figures follow model signals (`insights/signals.py`) because the Django admin edits the status directly and GDPR delete removes rows. Each daily row carries the entity's own date (session start, registration, completion, approval), so `rebuild_metrics` recomputes the same rows. Visitor and page-view rows have no source table and are never rebuilt. Rates are basis points. Weekly and monthly "visitors" are sums of daily uniques (hashes are wiped daily).

**Roll-up** (`insights.rollup.scheduled`, django-q2 hourly, registered by `register_schedules`): wipes finished days' visitor hashes and salts, writes daily rates, weekly and monthly rows, refreshes the visitor and page-view counters and rewrites every `MetricText` sentence. It recomputes from the daily rows in the window, so running it again changes nothing. Dashboard and Analytics read only these rows plus two `LIMIT 5` lists; tests prove the query count does not grow with data.

**Command.** `python manage.py rebuild_metrics [--dry-run]` shows differences between stored figures and the source tables, or replaces them and re-runs the whole roll-up. Run once after deploy to backfill; never in a migration.

**Visitor counter.** `insights.middleware.VisitorCounterMiddleware` (last in MIDDLEWARE): counts GET 200 HTML pages on the public host only, not bots or empty user agents, static, media or prefetch. Page views by path group (first segment; `home`), one unique per sha256(day salt, IP, user agent), referrer host only (`direct` when none). Errors are logged and swallowed. Setting `VISITOR_COUNTER = False` switches it off. The same middleware file's helper `record_step` (called from the journey and register views) feeds the people metrics; like visitors they have no source table, so `rebuild_metrics` never rebuilds them, and weekly/monthly figures are sums of daily people. Registrations through other routes (Gold invite, admin) are not counted as people.

New env vars: `OFFICE_DOMAIN`, `OFFICE_URL` (optional). Nothing is Postgres-only (ORM only, `select_for_update` is ignored by SQLite).

**Review fixes.** Journey completion reads its old state from a row-locked copy (`select_for_update().get`), so two tabs count once (the lock only bites on Postgres; SQLite serialises writes). The visitor-sentence refresh is queued with `common.tasks.enqueue`, never run inside the page request. Roles also require `is_staff`. People and Gold lists send `Vary: HX-Request` and are `never_cache`. **Admin and the figures:** a plan change on an `InterestRegistration` is counted by a signal (`insights/signals.py`, the services save through it too); in the admin, `User.email_verified_at` and `marketing_consent` are read only, adding or deleting an `InterestRegistration` is off, deleting a User goes through `delete_user_data` (full erasure, figures move), and `JourneySession` is read only (add, change, delete off). Anything else that bypasses the services is repaired by `rebuild_metrics`.
