# Feature: Analytics plus (devices, countries, engagement, campaigns, live) and junk-probe blocks

Branch `feature/analytics`. Decided 2026-11-21 (PROJECT.md). Builds on the cookieless visitor counter in `office.md` ("Visitors", "Visitor counter", "Stored figures", "Roll-up", "Snapshots") and `office-counting-rules.md` (C1 to C5 still win). No Umami or other outside tool: everything stays in our database, on our servers.

## Principles (unchanged, and they bind everything below)
- **No cookies, no browser storage, no banner.** Nothing is written to the visitor's device. No IP, user agent, full referrer or full URL is ever stored.
- **Today only.** Anything per visitor lives in today's rows (`VisitorHash` and the new visit fields) and is wiped by the roll-up once the London day is over. Everything kept is a count in `DailyMetric` (then `PeriodMetric` and the snapshots).
- **Stored figures only.** Office pages read snapshots, never count raw rows on page load. One exception: the Live card (below) reads today's visit rows, a small indexed query, because it must be live.
- Bots, staff hosts, staff accounts, prefetches, static, media, health and junk probes are never counted (same `should_count` / `counts_here` rules).
- **Caps.** Each key keeps at most 100 distinct dimensions per day; anything after that adds to `other`. All dimension values are lower-cased, cleaned and cut to the column length.

## A1. Device, browser, system
- Counted once per visitor per day (on the visitor's first counted hit of the day) and also per page view.
- Device: `mobile`, `tablet`, `desktop` (existing `common.useragent.device_type`).
- Browser family: `chrome`, `safari`, `edge`, `firefox`, `samsung`, `instagram` (in-app), `facebook` (in-app), `other`.
- System: `ios`, `android`, `windows`, `macos`, `linux`, `other`.
- Parsing is a small regex module in `common/useragent.py` (no new library). The user agent is never stored.

## A2. Country
- From the visitor's IP with the free **DB-IP "IP to Country Lite"** database (CC BY 4.0, no account). Read with the `maxminddb` library, in memory; the IP is looked up and dropped, never stored.
- Stored as the two-letter country code (`gb`, `us`, ...) per unique visitor per day; `unknown` when not found.
- The database file: downloaded in the Docker build (this month's file, else last month's; the build carries on without it). Path from setting `GEOIP_DB_PATH`. Missing file: every country is `unknown`, a warning once at startup, nothing breaks (local and CI work without it). `scripts/update_geoip.sh` fetches it for local use.
- Attribution required by the licence: a small "IP location data by DB-IP" link under the country chart in the Office.

## A3. Visits, bounce, pages per visit, entry and exit pages
- A **visit** is one visitor's run of page views with gaps under 30 minutes. A new visit starts on the first counted hit of the day or after a 30-minute gap. Midnight closes every visit.
- Today's `VisitorHash` row gains: `last_seen`, `visit_started`, `visit_pages`, `visit_seconds`, `entry_group`, `current_group`, `channel`, `source`, `campaign` (the visit's, see A5), `country`, `device`. Only today; wiped as now.
- Figures (daily rows): `visits`, `bounces` (visits with exactly one page view), `visit_pages` (sum), `entry_pages[group]`, `exit_pages[group]`, `visit_length[bucket]` with buckets `0-10s`, `10-30s`, `30s-1m`, `1-3m`, `3-10m`, `10m+`, and `visit_seconds` (sum, for the average).
- Bounce rate = bounces / visits. Pages per visit = visit_pages / visits. Average visit = visit_seconds / visits.
- Counting live: a new visit adds `visits` +1 and `bounces` +1; its second page view takes the bounce back (-1). Exit page, length bucket and seconds are written when the visit closes: by the next hit after a 30-minute gap, or by the roll-up for visits idle 30 minutes or from an earlier day.

## A4. Time on page and how far people read
- A tiny first-party script on public pages (no storage, no cookie, no third party, `navigator.sendBeacon`) sends one beacon when the page is hidden or left: the path, seconds the page was **visible** (capped at 30 minutes) and the furthest scroll depth (0, 25, 50, 75, 100%).
- Endpoint `POST /a/e/` on the public host: no CSRF token (the beacon has none), a small JSON body (max 2 KB), the same counting rules, rate limited per visitor hash, always answers 204. Unknown or odd input is ignored, never stored.
- Figures (daily): `engaged_seconds[group]`, `engaged_views[group]` (average time on page = seconds / views), `scroll[group:bucket]`. The seconds also add to the visit's `visit_seconds`.
- The same beacon carries **contact taps** (A6).

## A5. Campaigns and channels
- On the first page of a visit, `utm_source`, `utm_medium`, `utm_campaign` and `utm_content` are read from the address (lower-cased, letters, digits, `-` and `_` only, 60 characters). Nothing else from the query string is kept.
- **Channel** for every visit: `campaign` (has utm tags), `search` (Google, Bing, DuckDuckGo, Yahoo, Ecosia), `social` (Instagram, Facebook, TikTok, X, LinkedIn, WhatsApp, Pinterest, YouTube), `email` (utm_medium email, or mail sites), `referral` (any other site), `direct`.
- Figures (daily): `visits_by_channel[channel]`, `campaign_visits[source|medium|campaign|content]`.
- **Conversions by campaign:** when the same visitor (today's hash) starts the journey, finishes it, registers or applies for Gold, the visit's campaign and channel get +1 for that step: `campaign_steps[campaign key:step]`, `channel_steps[channel:step]`. Same day only (no cookie, so no longer memory); this limit is said on the page.
- **Link maker** in Office > Analytics > Campaigns: pick where it will be posted (Instagram post, Instagram story, Instagram bio, WhatsApp, email, flyer QR, other), type a short name, pick the page, get the tagged link with a Copy button (and a QR code for flyers). Office level and up; Viewer can see the figures.

## A6. Contact taps
- Taps on WhatsApp, phone, email, Instagram and map/directions links on the public site, found by the link itself (`wa.me`, `tel:`, `mailto:`, `instagram.com`, maps), or a `data-track` name. Sent with the beacon (A4) the moment they happen.
- Figures (daily): `contact_taps[kind]`, `contact_taps_page[kind:group]`, and by channel (`channel_steps[channel:contact]`).

## A7. When people visit
- Per new visit, the London weekday and hour: `visit_hour[dow:hour]` (`mon:09`). Shown as a 7 by 24 heat map, plus "busiest hour" and "busiest day" sentences.

## A8. Live now
- Visitors seen in the last 5 minutes (today's visit rows with `last_seen` in the window): the count, then by page group, country, device and channel. No list of individual people, no times per person.
- `GET office /analytics/live.json`, polled every 15 seconds while the page is open and visible. Viewer level and up.

## A9. Office screens (designer brief first, then frontend)
Analytics gets a **Visitors** area (exact layout from the designer): Live, Overview (visitors, visits, pages per visit, average visit, bounce rate, each with the previous period), Devices / browsers / systems, Countries (+ DB-IP credit), Pages (views, average time, scroll, entry, exit), Channels and sources, Campaigns (visits and steps per campaign, the link maker), Contact taps, When people visit (heat map). Same ranges (7d, 30d, 90d, all), same snapshot approach, phone friendly, brand tokens only.

## A10. Privacy notice
`content/legal.py`, "The visitor counter": add device type, browser and system (from the browser's own description, not stored), country (worked out from the IP, then the IP is dropped), time on page and how far the page was scrolled, contact taps, and campaign tags in links. Still no cookies and nothing stored on the device, so still no banner.

## A11. Junk probe blocks
- Paths that only bots try, answered with a bare 404 and never passed to Django: `/.env*`, `/.git*`, `/.aws*`, `/.ssh*`, `/.DS_Store`, `/wp-admin*`, `/wp-login.php`, `/wp-content*`, `/wp-includes*`, `/wp-json*`, `/xmlrpc.php`, any `*.php`, `/phpmyadmin*`, `/pma*`, `/cgi-bin*`, `/vendor/*`, `/server-status*`, `/actuator*`, `/boaform*`, `/HNAP1*`.
- In Caddy on every host (`(probes)` snippet imported by each site), plus the same list in a first Django middleware so local, CI and anything that reaches Django behave the same (404, no Sentry, not counted, not logged as an error). `/.well-known/` is never blocked.
- A count of blocked hits per day (`probes_blocked`, Django side only) for the System health page. Not shown in Office.

## Checks (acceptance)
- Works on SQLite and Postgres; no Postgres-only code.
- Tests (mocked GeoIP reader, no network): UA parsing table; visit start, 30-minute gap, bounce take-back, close by roll-up and at midnight; beacon validation, caps, rate limit and 204; utm cleaning and channel rules; same-day campaign step attribution; caps to `other`; nothing personal stored (no IP, UA or full URL in any row); roll-up wipes visit rows; probes give 404 and are not counted; Office live and snapshot endpoints keep a fixed query count; permissions (Viewer sees, Office makes links).
- No backfill: the new figures start from deploy day; the old visitor and page-view rows stay as they are.

## Built (backend, 2026-11-21)
A1 to A8, A10, A11 and the Checks are built; A9 (Office screens) is built too (see "Built (frontend)" below). Code: `common/useragent.py`, `common/geoip.py` + `common/geoip_fetch.py`, `insights/visitors.py` (visits, steps, closing), `insights/campaigns.py` (utm, channels, link maker), `insights/beacon.py` + `common/static/common/js/beacon.js`, `insights/live.py`, `common/probes.py` + the `(probes)` snippet in the `Caddyfile`, `office/analytics_visitors.py` (the `visitors` snapshot), endpoints in the `office.md` API table. Migration `insights/0008`. Settings: `GEOIP_DB_PATH`. Pinned: `maxminddb`, `segno`.

Deviations (one line each):
- The campaign key keeps each utm part to source 20, medium 15, campaign 30, content 20 characters (not 60) so `key:step` fits the 100 character dimension column.
- A visit tagged `utm_medium=email` has channel `email`; any other tagged visit is `campaign`. `campaign_visits` still counts every tagged visit.
- An in-app Instagram or Facebook browser with no referrer counts as `social`, not `direct`.
- Visit length is the larger of (last page seen minus start) and the beacon's visible seconds; a visit with neither is under 10s. A step (started, finished, registered, gold) counts once per visit; every contact tap counts.
- The beacon carries `n` (0 for the first beacon of a page view): only the first counts the page as reported and records the scroll step; later beacons add seconds.
- `/.private/deploy/Caddyfile` is not tracked in git, so it was not edited.
- Contact taps accept only whatsapp, phone, email, instagram and map (one list in `insights/metrics.py`); `data-track` names are not used, so junk kinds can't fill the daily cap. The beacon ignores webhook paths (`/ses/`, `/postmark/`, `/phone/`).
- The `www` Caddy block doesn't import `(probes)`: it only redirects, and the bare domain blocks them.
- The privacy notice date moved to 21 November 2026; the privacy version number was left at 2026-11-05 (a bump needs a model default migration and asks nobody to accept again). `backfill_site_data` gets the new paragraph (dry run supported).

## Built (frontend, 2026-11-21)
A9 is built from `analytics-design.md`: `/analytics/visitors/` (reader; Journey and Visitors share the range and the sub-nav `_analytics_nav.html`; Top pages moved there as the Pages card). Code: `office/views_visitors.py` (page and `GET /analytics/link.json`, Office level and up, which calls `campaigns.build_link` so the cleaning rules live in one place), `office/visitors_page.py` (the snapshot worded for the page: numbers, "Not enough yet" under 10, "Counting since", live first paint), `analytics_visitors.html` + `_vis_rank.html` + `_visitor_kpi.html`, `office-visitors.js` (live polling, Pages switch, heat map tip, link maker), a new `length` chart in `office-charts.js`, a `Visitors` block in `office-analytics.css`, slate ramp tokens `--office-slate-2/3/4` and `--office-heat-cell` in `office-tokens.css`. Tests: `office/tests/test_visitors_page.py`.

Deviations (one line each):
- The campaign name is cut at 30 characters (the backend limit), not 40 as the brief says.
- Summary sentences other than busiest, channels and campaign are made in `visitors_page.py` from the stored figures (the snapshot stores only those three).
- The overview tile is its own include (`_visitor_kpi.html`) rather than a variant of `_kpi.html`, because its figures are already worded; same classes and look.
- The live card words countries with the browser's `Intl.DisplayNames`; its first paint uses the server's country list, so a rare name can differ by a letter.

