# Spa 99 Office: design brief

Spec: `docs/features/office.md`. Decisions: PROJECT.md rows dated 2026-10-23 (Office, Office users, stored figures only, cookieless visitors). Brand rules: `docs/BRAND.md` (they win over anything here).

**Supersedes for the Office** the "Spa 99 Control" section of `docs/design/BRIEF.md` (section 8: light theme, no chart library, "charts don't animate"). What carries over from it: tables, filters in the URL, status and potential badges (re-coloured for dark below), detail views, "View as table". Control keeps BRIEF section 8 when it is built.

**Design read.** The back office of the same building after closing: dark, warm, quiet, with the data lit like instruments. Apple Watch, not a trading terminal: three rings, big numbers, thin gold lines, one idea per card. Mode is BRAND 7B (restrained) plus the chart motion defined in section 5. Dials: variance 3, motion 4, density 5 (phone 3).

Users: Barry (mostly on his phone: check the day, approve Gold), admins, developers. Roles Owner, Manager, Viewer: Viewers see everything, act on nothing (no Approve, Decline, Resend, Export, Delete buttons rendered, not just disabled).

---

## 1. Chart library: Chart.js 4.6.1

| Library | Licence | No-build use | Size (min / gzip) | Animation | Verdict |
|---|---|---|---|---|---|
| **Chart.js 4.6.1** | MIT | UMD `chart.umd.min.js` | 205 KB / 71 KB | Built in: draw-in, and smooth morph when data changes (`chart.update()`) | **Picked** |
| Apache ECharts 6.1.0 | Apache-2.0 | UMD | about 1 MB / 330 KB full; smaller only through their custom builder | The best | Too heavy for Barry's phone without a build step |
| ApexCharts | No longer MIT (`SEE LICENSE IN LICENSE.md`, commercial terms) | UMD | about 500 KB / 130 KB | Good | Excluded on licence |
| uPlot 1.6.32 | MIT | UMD / ESM | 50 KB / 20 KB | None (by design) | Fastest, but static; we would hand-build tooltips and motion |

**Why Chart.js:** MIT, one self-hosted file, no build, canvas (crisp at any DPR, cheap on phones), animated draw-in and data morphs out of the box, HTML tooltips through `external`, and every chart we need (line, bar, horizontal bar, stacked bar) is in the core.

- Vendor at `common/static/common/vendor/chartjs/4.6.1/chart.umd.min.js` with its `LICENSE.md`, pinned exactly (no `^`, no CDN). Record the file's sha256 in the commit message.
- Use the **UMD** file, not the ESM `dist/chart.js` (that one imports `@kurkle/color` and needs a resolver). Load it with a plain `<script defer>` on **Analytics only**; our own `office-charts.js` is an ES module that reads `window.Chart`.
- **No time scale** (it needs a date adapter). The server sends category labels already formatted (section 6).
- The **Dashboard does not load Chart.js.** Rings and sparklines are server-rendered inline SVG (a template tag turns the stored series into a path), so the page Barry opens most is light and works without JS.
- Rings: custom SVG, no library (section 3.3).

---

## 2. The shell

Page background is the deepest brown, cards sit one step up, popovers one more. Gold is kept for data, the active tab and primary actions.

| Layer | Token | Hex |
|---|---|---|
| Page, sidebar, tab bar | `--color-office-bg` (alias of `--color-iron`) | `#2C1C14` |
| Cards, table surface | `--color-office-card` (alias of `--color-espresso`) | `#492E21` |
| Tooltips' neighbours, modal, menus, active nav pill | `--color-office-raised` (alias of `--color-espresso-raised`) | `#553729` |

Cards: `--radius-md`, padding `--space-4` (phone) / `--space-5` (desktop), 1px `--color-card-edge` border, no shadow at rest (shadows don't read on dark). Gutter between cards `--space-4` / `--gutter`.

### 2.1 Desktop (from 64em)

- **Left nav**, `--office-nav-w` (248px), `--color-office-bg`, fixed, full height, 1px `--color-hairline-inverse` on its right.
  - Top (72px): swan mark 28px gold + "Office" Signika 500 `--text-lg` cream.
  - Items: Dashboard, Analytics, People, Gold. 44px rows, 20px line icon + label, Figtree 500 `--text-sm`, `--color-text-muted-inverse`. Current: cream text, gold icon, `--color-office-raised` pill (`--radius-sm`). Gold shows a count badge when applications are waiting (gold fill, espresso text, Figtree 600 `--text-xs`, 20px high, number from the stored counter).
  - Bottom: the signed-in person (initials disc, name, role muted `--text-sm`), "Sign out" quiet link.
- **Header**, `--office-header-h` (72px), sticky, `--color-office-header` with `backdrop-filter: blur(16px)`, 1px hairline at the bottom once scrolled.
  - Left: page title Signika 500 `--text-xl`.
  - Right: range picker (2.3), then the person: 40px disc `--color-office-raised`, gold initials Figtree 600, opens a small menu (name, role, Sign out). On desktop the person shows in both header and nav bottom; that is fine, the header one is the menu.
- Content: margin `--space-5`, max width 80rem, left aligned beside the nav.

### 2.2 Phone and tablet (below 64em)

- **Header** 56px (`--office-header-h` phone value), sticky, same colour: swan 24px + page title Signika 500 `--text-lg`; person disc 36px right (menu as above).
- **Bottom tabs**, `--office-tabbar-h` (64px) plus `env(safe-area-inset-bottom)`, `--color-office-bg`, 1px hairline on top, four equal tabs: icon 24px over label Figtree 600 `--text-xs`. Current tab gold icon and label (gold on iron 8.15); others muted inverse (8.59). Gold tab carries the badge dot with the count. Content gets bottom padding equal to the bar.
- **Detail pages** (a person, a Gold application) hide the tab bar and show "‹ People" / "‹ Gold" as the header's left item; Gold detail puts its decision bar where the tabs were (5.3).
- `viewport-fit=cover`, no tap highlight, `touch-action: manipulation` on controls, inputs at 16px (no zoom), `100dvh` for the shell.

### 2.3 Range picker

A segmented control (the shared `.segmented`, dark variant), 40px high (`--control-h-compact`).

- Dashboard: **Today · 7 days · 30 days**. Analytics: **7 days · 30 days · 90 days · All**.
- Track `--color-hairline-inverse`; segments muted-inverse text; the selected segment is a `--color-office-raised` thumb with cream text. The thumb slides (`transform: translateX`, `--duration-base`, `--ease-soft`); text does not move.
- Choice is in the URL (`?range=30d`), remembered in the session for the next visit, back-button safe.
- Phone: full width at the top of the page content (not in the header), scrolls with the page.

---

## 3. Dashboard

### 3.1 At 1440

12-column grid inside the content area (about 1110px wide).

1. **Greeting row** (full width, no card): "Good evening, Barry." Signika 500 `--text-2xl`, under it the "what changed" line Figtree `--text-lg` muted inverse, max `--measure`: e.g. "Registrations are up 18% on last week. Two Gold applications are waiting." The line is stored by the roll-up (one or two sentences, never more).
2. **Rings card** (6 columns) | **Stat cards** 2 by 2 (6 columns). Same height.
3. **Funnel strip** (12 columns).
4. **Waiting for you** (7 columns) | **Latest registrations** (5 columns, five rows, "See everyone" quiet link).

### 3.2 At 390

Single column, `--space-3` page margin feel (`--page-margin` resolves to 20px), cards full width, in this order (Barry's priorities):

1. Range picker. 2. Greeting (Signika `--text-xl`) and the what-changed line (`--text-base`). 3. Rings card (rings centred, legend rows below). 4. **Waiting for you** (moved up on phone). 5. Stat cards in a 2 by 2 grid. 6. Funnel as four stacked rows. 7. Latest registrations.

### 3.3 The rings

Three concentric rings, Apple Watch style, inline SVG, start at 12 o'clock, clockwise, round caps.

| Ring | Measures | Colour | Track |
|---|---|---|---|
| Outer | **Registrations** against the stored goal for the range ("34 of 50") | `--color-ring-1` gold `#E5AC6E` | `--color-ring-1-track` gold at 20% |
| Middle | **Journeys completed**: completed out of started, against the stored target rate ("62% of 70%") | `--color-ring-2` caramel `#BB8855` | `--color-ring-2-track` caramel at 22% |
| Inner | **Gold handled**: applications approved or declined out of those received ("5 of 7") | `--color-ring-3` cream `#F5F2D8` | `--color-ring-3-track` cream at 14% |

- Geometry (desktop / phone): SVG `--ring-size` 220px / 176px; stroke `--ring-stroke` 18px / 14px; gap between rings 4px. Radii desktop 101, 79, 57; phone 81, 63, 45. `pathLength="100"` on each circle so dash maths is in percent.
- Over 100%: the ring keeps going for a second lap (cap at 200%); the cap end gets a 2px `--color-office-bg` shadow ring so the overlap reads. Never clamp silently.
- Goals and target rates are stored rows (set in the hidden Django admin for now); if a goal is missing, that ring shows its track only and the legend says "No goal set".
- Legend beside the rings (desktop, vertically centred) or below (phone), one row per ring: 10px colour dot, label Figtree 500 `--text-sm` muted inverse, value Signika 500 `--text-xl` cream, then "of 50" muted. Text carries the meaning, the colour only matches it.
- The SVG has `role="img"` and an `aria-label` that says all three: "Registrations 34 of 50. Journeys completed 62%, target 70%. Gold handled 5 of 7."

### 3.4 Stat cards

Four cards: **Registrations**, **Journeys completed**, **Site visitors**, **Conversion** (visitors to registered).

- Label Figtree 500 `--text-sm` muted inverse, top left.
- Number Signika 500 `--text-stat`, cream, `font-variant-numeric: tabular-nums`, `--leading-display`.
- Delta under it, `--text-sm`: rising "▲ 18%" in `--color-growth` (gold), falling "▼ 6%" in muted inverse, flat "No change" muted; then "vs last week" muted. No red or green anywhere: a quieter week is not an alarm. Minus is U+2212.
- Sparkline at the bottom, full card width, `--spark-h` (40px): 2px gold line (`vector-effect: non-scaling-stroke`, round joins), area below filled with a vertical gradient `--color-area-top` to transparent, a 6px gold dot on the last point with a 2px card-colour ring. No axes, no grid. 7 points for Today and 7 days (hourly would be noise), 30 for 30 days.
- The whole card links to the matching Analytics chart. Hover (fine pointer only): scale 1.01, `--duration-press`.

### 3.5 Funnel strip

Visitors, Started the journey, Completed it, Registered.

- Desktop: four equal columns in one card. Each: label `--text-sm` muted, number Signika 500 `--text-xl` cream, then a 6px bar (radius 3px, gold, track `--color-ring-1-track`) whose length is that step's share of visitors (`transform: scaleX()`, origin left). Between columns a small muted "42% ›" (step-to-step rate).
- Phone: four rows, label and number on one line, bar full width under, step rate right aligned on the bar's line.

### 3.6 Waiting for you

Gold applications with status Waiting, newest first, up to five; "See all 7" quiet link when more.

- Heading "Waiting for you" Signika `--text-lg` with the count beside it in gold.
- Row (64px desktop, card-row on phone): name Figtree 600 cream, potential badge (5.4), "Applied 2 days ago" muted `--text-sm`, then on desktop a small "Approve and invite" button (`.btn-primary .btn-sm`) and a chevron to open. On phone the row opens the detail (no inline approve: the decision is made with the application in front of him).
- Empty: "Nothing waiting for you." muted, one line, no illustration.

---

## 4. Analytics

### 4.1 Layout

One page, cards in reading order. Desktop: a 2-column grid, wide charts span both. Phone: one column. Each card: title Signika 500 `--text-lg`, a one-sentence **summary** under it (`--text-sm` muted, stored by the roll-up or composed from stored figures, never computed from source tables), the chart, then "View as table" (a `<details>` with the real table, Figtree `--text-sm`, numbers right aligned).

Chart heights: `--chart-h` 18rem desktop / 14rem phone; `--chart-h-sm` 12rem for small multiples.

| # | Card (span) | Type | Series and colour | Notes |
|---|---|---|---|---|
| 1 | **Visitors** (2) | Line, smooth (`cubicInterpolationMode: 'monotone'`, no overshoot) | This range: gold 2px, area gradient `--color-area-top` to 0. Previous period: caramel 1.5px dashed `[4, 4]`, no fill | Toggle in the card header: Visitors · Page views (segmented, small). Never two y-axes: page views replace visitors, they are not added |
| 2 | **The funnel** (2) | Horizontal bar, 4 bars | Gold, track behind each bar in `--color-ring-1-track` (full length = visitors) | Count and step rate as direct labels at the bar end (HTML overlay or a tiny plugin), largest drop's label in cream, others muted |
| 3 | **Registrations by plan** (1) | Horizontal bar | Gold, one colour | Order is plan order (from `plans`), not by size. Direct value labels |
| 4 | **Suggested plan** (1) | One 100% stacked bar (a segment strip, 28px high) plus a legend list under it | Plans in fixed order: gold, caramel, cream; a 4th plan uses cream with a 45° hatch | 2px card-colour gap between segments. Legend rows: dot, plan, count, share |
| 5 | **Journey answers** (2) | Four small multiples: Time of day, How often, Facilities, Company | Horizontal bars, gold, one colour per multiple | Facilities note: "Members could choose more than one." Answers keep journey order |
| 6 | **Where people stop** (2) | Vertical bar, one per journey screen in order | Gold bars; share who left at that screen | Screen names as x labels (rotate never: wrap to two lines, or use short names); the highest bar gets a direct label |
| 7 | **Gold applications** (1) | Horizontal stacked bar, one row per potential (High, Medium, Low) | Status in fixed order: Approved gold, Waiting cream, Declined caramel with 45° hatch | Legend always shown (3 series) plus direct totals at row end |
| 8 | **Top pages** (1) and **Referring sites** (1) | Not charts: ranked lists, top 10 | Each row: name, count right aligned, a 4px gold bar under the row at its share of the top value | Referrers show site names only. "Direct or unknown" is a normal row |

### 4.2 Chart.js defaults (set once in `office-charts.js`)

Read every colour from CSS tokens with `getComputedStyle` (never hard-code hex in JS).

- `font`: Figtree, 12px (`--text-xs`), colour `--color-text-muted-inverse`.
- Grid: horizontal lines only, `--color-grid`, 1px, no border on the axis line, `drawTicks: false`, 4 to 5 y ticks, y starts at 0, ticks padded 8px. No x grid.
- Bars: `borderRadius: 4` on the data end only (`borderSkipped: 'start'`), `maxBarThickness: 28`, `categoryPercentage: 0.7`, `barPercentage: 0.9`; stacked segments get a 2px `--color-office-card` border.
- Lines: `borderWidth: 2`, `pointRadius: 0`, `pointHoverRadius: 5`, hover point gold with a 2px card-colour border.
- Legend: Chart.js legend off; our HTML legend (dot + label) above the plot whenever there are 2 or more series.
- Interaction: `mode: 'index', intersect: false` on lines (with a 1px `--color-crosshair` vertical line plugin), `mode: 'nearest'` on bars. Hit areas larger than marks.
- `responsive: true`, `maintainAspectRatio: false` (the card sets the height), `devicePixelRatio: window.devicePixelRatio`.
- Large ranges ("All", more than 120 points): the server sends weekly rows (labels "w/c 6 Oct"), never thousands of points.

### 4.3 Tooltips

HTML `external` tooltip, one element reused.

- `--color-cream-raised` background, espresso text (11.71), `--radius-sm`, padding `--space-2` `--space-3`, `--shadow-office`. Figtree `--text-sm`.
- Title: the date ("Thu 23 Oct") or category. Rows: a 10px line or square in the series colour, label, value right aligned tabular ("Visitors 1,204"; "Previous 30 days 980"). Bars: value and share ("Tier 2 · 41 · 38%").
- Appears with opacity only, 120ms; follows the crosshair horizontally and is clamped inside the card. Phone: tap shows it above the plot's top edge (never under the finger), tap outside hides.

### 4.4 Empty, loading, error

- **Empty** (no rows, or all zero in the range): no axes, no fake line. The card keeps its height; centred muted text "No visitors in this range yet." on a single 1px `--color-grid` baseline. The summary line says the same. Table toggle hidden.
- **First load**: none needed; the server renders the data into the page (`json_script`), charts draw from it.
- **Range switch**: if the response takes longer than `--delay-busy` (300ms), the chart areas dim to 50% opacity (`--duration-swap`) and the picker shows `aria-busy`. No spinners, no shimmer, no skeleton blocks.
- **Error**: the chart area keeps the old data and a muted line appears under the card title: "Couldn't refresh. Showing 7 days." with a quiet "Try again".

### 4.5 Range switch behaviour

- The picker is a set of links with `hx-get="?range=30d"`, `hx-target="#office-main"`, `hx-select="#office-main"`, `hx-push-url="true"`.
- Each `<canvas>` has a stable `id` and `hx-preserve="true"` so it survives the swap. The response includes a fresh `<script type="application/json" id="office-series">`; on `htmx:afterSwap` the script reads it and calls `chart.data = ...; chart.update()` on each existing chart, so lines and bars **morph** to the new range instead of redrawing.
- Numbers, summaries, tables and deltas swap as HTML with a 240ms opacity cross-fade (no counting on a switch).
- Rings and sparklines on the Dashboard do the same: the new SVG values transition from the old ones (section 5).

---

## 5. Motion

Office is a tool: BRAND 7B entrances, plus instrument motion for data. Everything uses `--ease-soft` (`cubic-bezier(0.22, 1, 0.36, 1)`); in Chart.js the closest named easing is `easeOutQuint`.

| What | When | Duration | Detail |
|---|---|---|---|
| Cards enter | 15% in view, once | `--duration-reveal` 1000ms, `--delay-reveal` 100ms | Rise `--rise` (8px phone, 12px from 48em), opacity 0 to 1. The four stat cards stagger 100ms on desktop, none on phone. Nav, header, tabs never animate |
| Rings draw | When the rings card enters | `--duration-ring` 1400ms | `stroke-dashoffset` from 100 to target, outer first, `--stagger-ring` 120ms between rings |
| Ring change (range switch) | On swap | `--duration-morph` 600ms | CSS transition on `stroke-dashoffset` from the current value |
| Sparkline draws | With its card | `--duration-spark` 900ms | Stroke dash draw left to right, area fades in over the same time, last dot fades in at the end (120ms) |
| Funnel bars | With the strip | `--duration-spark` 900ms | `scaleX` from 0, 80ms between steps (desktop only) |
| Big numbers count | First Dashboard load in a session only, with their card | `--duration-count` 900ms | Count up from 0, tabular numerals so width holds; final value is in the HTML (JS only animates) |
| Charts draw in | When the card is 15% in view (create the chart lazily then) | `--duration-chart` 900ms | Chart.js default draw-in with `easeOutQuint`; lines grow from the baseline (`y` from 0), bars grow from their base. Dataset delay: previous-period line starts 150ms after |
| Chart morph | Range switch, toggle | `--duration-morph` 600ms | `chart.update()`, `easeOutQuint` |
| Cross-fade | HTMX swaps of text | `--duration-swap` 240ms | Opacity only |
| Busy dim | Response slower than 300ms | 240ms | Opacity to 0.5 |
| Picker thumb | Selection | `--duration-base` 400ms | `translateX` |
| Tooltip | Hover, tap | 120ms | Opacity only |
| Buttons, clickable cards | Hover (fine pointer) / press | `--duration-press` 250ms | Scale 1.01 / 0.99 |
| Modal | Open / close | 240ms in, 160ms out | Opacity, and the panel scale 0.98 to 1. Backdrop opacity |
| Approve success check | After approving on the confirm page | 600ms | Gold circle stroke draws, then the tick, once |

**Proposed BRAND 7B additions (Office only), for Moishe's approval:**
1. SVG stroke drawing is allowed for Office rings, sparklines and the approve check (BRAND 7 currently allows it on the swan only).
2. Office numbers may count on first load (BRAND 7A counts only small numbers that matter; these are the point of the page). Never on range switch, never prices.
3. Chart.js draw-in and morph animate canvas pixels, not CSS layout, so the "transform and opacity only" rule is kept for all DOM.

**Reduced motion:** Chart.js `animation: false` and `transitions.active.animation.duration: 0`; rings, sparklines and funnel bars render at their final value; numbers show final; swaps, dim and thumb are instant; card entrances off (tokens already go to 0). Tooltips still appear (instantly). Check both `matchMedia` at chart creation and on change.

---

## 6. Numbers and dates (British)

All formatting is done once: server side with `en-GB` and Europe/London (template filters), client side with `Intl.NumberFormat('en-GB')` and `Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London' })` for tooltips.

| Kind | Format | Examples |
|---|---|---|
| Counts | Thousands separator | 1,204 · 38 |
| Big counts (stat cards, from 10,000) | Compact, one decimal | 12.4k · 1.2m |
| Axis ticks | Compact | 0 · 500 · 1k · 1.5k |
| Rates | One decimal under 10%, whole above | 4.6% · 38% |
| Deltas | Sign, whole percent, vs the same length before | ▲ 18% · ▼ 6% · No change · "New" when the previous period was 0 |
| Day labels | Short day and month | 23 Oct · Thu 23 Oct (tooltip) |
| Week labels | Week commencing | w/c 20 Oct |
| Month labels | Short month, year when it changes | Oct · Jan 2027 |
| Date and time (tables) | Day month year, 24-hour | 23 Oct 2026, 18:40 |
| Relative (lists) | Plain | Today, 18:40 · Yesterday · 2 days ago · 14 Oct |
| Money (later) | Pound sign, no pence when whole | £419 |

---

## 7. People and Gold

### 7.1 Shared list pattern

- Filter bar above the list, in one row on desktop: search field (the shared field, dark variant, 40px), segmented filters, then the export button right. Filters live in the URL. "Clear" quiet link only when a filter is set. Results update through HTMX (`hx-trigger="input changed delay:300ms"` on search).
- **Desktop: table** on a `--color-office-card` surface (`--radius-md`). Header row: label style (uppercase `--text-xs`, `--tracking-label`, muted inverse), sticky under the header. Rows 52px, 1px `--color-hairline-inverse` between, hover row `--color-office-raised`. Whole row is a link (real link on the first cell). Numbers right aligned tabular. Busy: table dims to 60%.
- **Phone: cards** (one per row), `--color-office-card`, `--radius-md`, padding `--space-3`, `--space-2` apart: name Figtree 600 `--text-base` cream, second line muted `--text-sm`, badges row, date right. Whole card is the link. Filters collapse to the search field plus a "Filters" button that opens a bottom sheet (the shared modal as a sheet, rounded top) with the segmented controls and a "Show results" button.
- Paging: "Show more" button at the end (`hx-swap="beforeend"`, 50 at a time). No filtered counts (they would be computed on the fly); the unfiltered total comes from the stored counter: "1,204 people".
- Empty: one sentence. People: "No one matches that. Try fewer filters." Gold: "No applications here."

### 7.2 People

- Columns: Name · Email · Plan interest · Verified ("Verified" / "Not yet") · Marketing ("Yes" / "No") · Journey ("Completed" / "Started" / "Not started") · Registered (23 Oct 2026, 18:40) · Gold (a gold "Gold" link when he applied).
- Filters: Plan (select), Verified (All · Verified · Not yet), Marketing (All · Yes · No). Export: "Export CSV" (`.btn-secondary .btn-sm`), exports what is filtered.
- **Person detail.** Header: name Signika 500 `--text-2xl`, "Registered 23 Oct 2026" muted, badges. Desktop two columns (8 / 4): main has sections **Details**, **Plan interest**, **Journey answers**, **Gold** (link to his application), each a card of label/value rows (label muted `--text-sm`, value cream `--text-base`). Right rail card **Data**: "Export his data" (secondary) and "Delete this person" (quiet, `--color-danger-inverse` text, 6.81 on espresso). Phone: one column, the Data card last.
- Delete confirm (shared modal, danger): title "Delete Daniel Cohen?", message "This removes his registration, journey answers and Gold application. It cannot be undone.", confirm "Delete for good", cancel "Keep".

### 7.3 Gold

- Columns: Name · Potential · Status · Invite ("Sent 21 Oct" / "Expires in 3 days" / "Expired" / "Account set up" / blank) · Applied · action (Waiting rows: "Approve and invite" `.btn-primary .btn-sm`, Owner and Manager only).
- Filters: Status (Waiting · Approved · Declined · All, default **Waiting**), Potential (All · High · Medium · Low).
- **Application detail.** Desktop two columns (8 / 4). Main: the three sections from Barry's email, same names and order, as cards of label/value rows. Right rail (sticky under the header): **Decision** card: status and potential badges; then
  - Waiting: "Approve and invite" (`.btn-primary .btn-block`), "Decline" (`.btn-secondary .btn-block`), helper muted `--text-sm`: "He gets an email to set up his account. The link lasts 14 days."
  - Approved: "Approved 23 Oct by Barry", invite state, "Resend invite" (secondary).
  - Declined: "Declined 23 Oct by Barry". No buttons.
  - Below: History list (`--text-sm` muted, "23 Oct 2026, 18:40 · Barry approved").
- **Phone:** one column; the Decision becomes a sticky bottom bar (replacing the tab bar), `--color-office-bg` with top hairline, safe-area padding: "Decline" secondary (1/3) and "Approve and invite" primary (2/3), 52px (`--control-h`). Approved/declined: the bar shows the state line and "Resend invite" where it applies.

### 7.4 Confirm modal and the email confirm page

Reuse `confirmModal()` (`common/static/common/js/modal.js`) with a dark skin under the Office: panel `--color-office-raised`, cream title Signika 500 `--text-xl`, message muted inverse, `--radius-md`, max width 28rem, backdrop `--color-overlay-deep`, `--shadow-office`. Buttons full width stacked on phone (primary first), side by side right aligned on desktop.

| Action | Title | Message | Confirm | Cancel |
|---|---|---|---|---|
| Approve and invite | Approve Daniel Cohen for Gold? | He gets an invite to set up his account. His Gold month starts today, 23 October. | Approve and invite | Not now |
| Decline | Decline Daniel Cohen? | He will not be invited. This cannot be changed here. | Decline (danger) | Keep waiting |
| Resend invite | Send Daniel a new invite? | A new link replaces the old one and lasts 14 days. | Send invite | Cancel |

(Backend to confirm the resend wording matches `gold.invites`: if the old link stays valid, drop "replaces the old one".)

After confirming: the button shows its working text ("Approving"), then the row or rail updates in place via HTMX and a message toast says "Daniel is approved. His invite is on its way."

**Email confirm page** (Barry taps Approve in his email; sign-in still required): the shell without nav or tabs, one centred card (`--signin-w` wide): "Approve Daniel Cohen for Gold?" Signika `--text-xl`, three muted lines (potential, property, applied), "Approve and invite" primary block, "Open the full application" quiet link. This page is the confirmation, so no modal on top. Success state on the same card: the gold check draws (600ms, section 5), "Approved." and "His invite is on its way.", then "Back to the Office". Already decided: "Daniel was approved on 23 Oct by Barry." and the link. Expired or unknown: "This link has expired. Open the application in the Office."

### 7.5 Badges on dark

Text first, colour second. Figtree 600 `--text-xs`, 22px high, `--radius-sm`, padding 0 8px.

| Value | Look | Contrast |
|---|---|---|
| Potential High | Gold fill, espresso text | 6.17 |
| Potential Medium | 1px caramel border, cream text | border 3.99, text 10.95 |
| Potential Low | Muted inverse text, no box | 6.50 |
| Waiting | 1px cream border, cream text | 10.95 |
| Approved | Gold fill, espresso text | 6.17 |
| Declined | Muted inverse text, no box | 6.50 |
| Invite expired / email not sent | `--color-danger-inverse` text with a warning icon | 6.81 |

---

## 8. Tokens

Nothing changes in the four brand colours. Everything below is **proposed, derived**, for `tokens.css` under a "Office (docs/design/OFFICE.md 8)" comment, and BRAND section 8 to be updated when accepted. Aliases add no new colour; the rgba values are brand colours at reduced opacity, decoration only unless stated.

```css
/* Office (docs/design/OFFICE.md 8). Proposed, derived. */
:root {
  /* Surfaces: aliases, no new colours */
  --color-office-bg: var(--color-iron);          /* #2C1C14: cream 14.47, gold 8.15, muted-inverse 8.59, caramel 5.27 */
  --color-office-card: var(--color-espresso);    /* cream 10.95, gold 6.17, muted-inverse 6.50, caramel 3.99 (UI and marks only) */
  --color-office-raised: var(--color-espresso-raised); /* cream 9.45, gold 5.32, muted-inverse 5.61 */
  --color-office-header: rgb(44 28 20 / 0.86);   /* iron, sticky header with blur */
  --color-overlay-deep: rgb(44 28 20 / 0.72);    /* modal backdrop on the dark shell (--color-overlay would lighten it) */
  --color-card-edge: rgb(245 242 216 / 0.06);    /* 1px card border, decoration */
  --shadow-office: 0 1px 0 rgb(245 242 216 / 0.04) inset, 0 24px 48px -16px rgb(44 28 20 / 0.9); /* modal, menus, tooltip; warm, never black */

  /* Data */
  --color-ring-1: var(--color-gold);
  --color-ring-2: var(--color-caramel);
  --color-ring-3: var(--color-cream);
  --color-ring-1-track: rgb(229 172 110 / 0.20);
  --color-ring-2-track: rgb(187 136 85 / 0.22);
  --color-ring-3-track: rgb(245 242 216 / 0.14);
  --color-growth: var(--color-gold);             /* the one accent for "up" */
  --color-compare: var(--color-caramel);         /* previous period, dashed */
  --color-grid: rgb(245 242 216 / 0.08);         /* gridlines, decoration */
  --color-crosshair: rgb(229 172 110 / 0.5);
  --color-area-top: rgb(229 172 110 / 0.22);     /* area gradient start; ends at 0 */

  /* Type */
  --text-xs: 0.75rem;                            /* chart ticks, tab labels, badges, table heads only; never body */
  --text-stat: clamp(2.25rem, 1.5vw + 1.75rem, 3.5rem); /* stat card numbers: 36px phone, 56px at 1440 */

  /* Layout */
  --office-nav-w: 15.5rem;                       /* 248px */
  --office-header-h: 3.5rem;                     /* 56px; 4.5rem from 64em */
  --office-tabbar-h: 4rem;                       /* plus safe area */
  --ring-size: 11rem;                            /* 176px; 13.75rem from 64em */
  --ring-stroke: 14px;                           /* 18px from 64em */
  --spark-h: 2.5rem;
  --chart-h: 14rem;                              /* 18rem from 64em */
  --chart-h-sm: 12rem;

  /* Motion */
  --duration-ring: 1400ms;
  --stagger-ring: 120ms;
  --duration-spark: 900ms;
  --duration-chart: 900ms;
  --duration-count: 900ms;
  --duration-morph: 600ms;
  --duration-swap: 240ms;
  --delay-busy: 300ms;
}
@media (min-width: 64em) {
  :root { --office-header-h: 4.5rem; --ring-size: 13.75rem; --ring-stroke: 18px; --chart-h: 18rem; }
}
@media (prefers-reduced-motion: reduce) {
  :root { --duration-ring: 0ms; --stagger-ring: 0ms; --duration-spark: 0ms; --duration-chart: 0ms; --duration-count: 0ms; --duration-morph: 0ms; --duration-swap: 0ms; }
}
```

Scope the dark component variants (fields, segmented, buttons, modal) with an `.office` class on `<body>` that sets the existing surface variables (`--s-accent`, `--s-text`, `--s-seg`, `--s-tile-line` and so on in `components.css`), not by copying components. Primary button: gold fill, espresso text (6.17). Secondary: 1px cream border, cream text. Focus: 2px `--color-focus-inverse` (gold) outline, 2px offset, everywhere.

Fonts: the self-hosted Signika and Figtree already in the site. Chart.js gets `Figtree` by name after `document.fonts.ready` (create charts after it, so canvas text is not drawn in the fallback).

---

## 9. Accessibility

- **Contrast** (all measured): text on cards uses cream (10.95) or muted inverse (6.50); on raised surfaces 9.45 / 5.61; on the page and nav 14.47 / 8.59. Gold text is fine everywhere dark (5.32 or more). Caramel is never body text; on cards it is marks and borders only (3.99, 3.44 on raised). Ring tracks, grid and area fills are decoration.
- **Palette check** (dataviz validator, dark, on `#492E21`): gold, cream, caramel pass CVD separation (worst pair cream and gold, deltaE 17.9 deutan) and contrast (all at least 3:1). They fail the generic lightness and chroma bands (cream is near neutral, gold very light): brand wins, so the rules are **at most three series per chart, legend always shown for 2 or more, direct labels on bars, the previous period dashed, a fourth category hatched.** Colour never carries meaning alone.
- **Every chart has text**: the summary sentence, `role="img"` with `aria-label` equal to the summary on the canvas, and "View as table" with a real `<table>` (caption, `scope` on headers).
- Rings: full sentence `aria-label` (3.3); the legend repeats every value as text.
- Deltas: arrow plus words in the accessible name ("up 18% on last week").
- Tooltips are a convenience; nothing is only in a tooltip.
- Keyboard: nav, tabs, picker (arrow keys inside the segmented, real radios), table rows (first-cell link), modal (focus trapped, Escape cancels, focus returns). Charts are skipped by Tab (the table holds the data).
- Tap targets at least 44px on phone (tabs 64px, list cards whole, picker 40px high but full width so each segment is wider than 80px).
- `forced-colors: active`: charts keep working because series differ by dash and hatch; badges keep borders.
- Live region: the toast after an action is `role="status"`.

---

## 10. Copy

Short, calm, British. No exclamation marks, no em dashes, no "Oops".

- Greeting by London time: "Good morning, Barry." / "Good afternoon" / "Good evening".
- What changed: facts, one or two sentences: "Registrations are up 18% on last week. Two Gold applications are waiting." / "A quiet day so far." when nothing moved.
- Page titles: Dashboard, Analytics, People, Gold. Card titles plain nouns.
- Buttons: "Approve and invite", "Decline", "Resend invite", "Export CSV", "Export his data", "Delete this person", "Show more", "Try again".

---

## 11. Acceptance checks

1. `chart.umd.min.js` 4.6.1 is vendored with its licence, loaded only on Analytics, from our own static files; the Dashboard loads no chart library and renders rings and sparklines without JS.
2. 1440: nav left, header with title, range picker and person; Dashboard rows as 3.1. 390: header, bottom tabs with the Gold badge, order as 3.2, no horizontal scroll, nothing under the home indicator.
3. Rings draw outer to inner in about 1.5s on first view, show a second lap above 100%, and their `aria-label` reads all three values.
4. Range switch on Analytics morphs every chart (no flash, no re-creation), swaps numbers with a fade, updates the URL, survives Back, and dims only after 300ms.
5. No two y-axes anywhere; three series at most; a legend for 2 or more; tooltips in cream with British numbers and dates (1,204 · 4.6% · Thu 23 Oct · w/c 20 Oct).
6. Empty ranges show the one-line empty state, no axes.
7. Reduced motion: no drawing, counting, morphing or entrances; final values immediately.
8. Every chart has a summary sentence and a working "View as table".
9. Contrast: every text pair in section 9 measured at 4.5 or more (large numbers 3.0 or more); focus ring visible on every control.
10. Viewer role sees no action buttons; Owner and Manager can approve from the list (desktop), the detail rail, the phone decision bar and the email confirm page, each through a confirmation.
11. All tokens used are in BRAND section 8 or this section 8; no raw hex in templates, CSS components or JS.
12. Lighthouse on the Dashboard at 390 (mid phone throttling): LCP 2.5s or less, CLS 0 (cards reserve their height; charts do not shift the layout).
