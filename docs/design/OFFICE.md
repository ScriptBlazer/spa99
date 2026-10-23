# Spa 99 Office: design brief (light, round 2)

Spec: `docs/features/office.md`. Decisions: PROJECT.md rows dated 2026-10-23 (Office, stored figures only, cookieless visitors, and the "Office goes light" row). Brand rules: `docs/BRAND.md` win over anything here.

**Supersedes** the first, dark Office brief (iron and espresso shell, gold/caramel/cream data). What carries over unchanged: Chart.js 4.6.1 on Analytics only, server-rendered SVG rings and sparklines on the Dashboard, nav structure, range picker behaviour, roles, HTMX swaps and chart morphing, motion timings, number and date formats, empty/error states, confirm modal copy, "View as table".

**Design read.** The same building in daylight: a calm, warm, light room with soft surfaces and no ruled boxes. Apple Health / Fitness, not PowerPoint: plain counts in big type, rings, gradient areas, rounded bars, colour that is muted but clearly there. Dials: variance 3, motion 4, density 4 (phone 3).

**Moishe's rules for this round**
1. The whole Office is light.
2. Dashboard and Analytics may use the muted data palette (section 2.2). People and Gold use the brand colours only (espresso, gold, caramel, cream) on the light shell.
3. The public site does not change. Every new colour is an Office-only token (`--office-*`), defined in the Office CSS, never in `tokens.css`.
4. Dashboard shows plain counts: people who started the journey, people who finished it, registrations, Gold waiting. No percent-of-goal labels.
5. No hairline-bordered cards. Surfaces are separated by tone, soft shadow and space.

Users: Barry (mostly on his phone: check the day, approve Gold), admins, developers. Roles Owner, Manager, Viewer: Viewers see everything, act on nothing (action buttons not rendered).

---

## 1. Where the tokens live

- All tokens in section 2 go in `common/static/common/css/office.css`, scoped to `.office` (the class already on the Office `<body>`), not `:root`.
- **Remove** the whole "Office" block from `tokens.css` (`--color-office-*`, `--color-ring-*`, `--color-card-edge`, `--shadow-office`, `--color-grid`, `--color-area-top`, `--color-crosshair`, `--color-growth`, `--color-compare`, `--color-overlay-deep`, `--text-stat`, `--text-xs`, `--office-*`, `--ring-*`, `--spark-h`, `--chart-h*`, `--strip-h`, the Office motion durations). A grep confirms only `office*.css` and `office-charts.js` use them. Rename on the way (`--office-*`), so nothing in the public CSS can pick them up by accident.
- Brand tokens (`--color-espresso`, `--color-gold`, fonts, `--space-*`, `--ease-soft`, `--duration-*`) are read, never redefined.
- BRAND.md section 8 "Office tokens" block is replaced by one line pointing here (coordinator, after acceptance).
- JS reads every colour with `getComputedStyle(document.body)`; no hex in JS or templates.

---

## 2. Tokens (Office only, proposed)

### 2.1 Shell

| Token | Hex | Use | Text on it (WCAG) |
|---|---|---|---|
| `--office-page` | `#F4F2ED` | Page, desktop sidebar, sign-in page | espresso 11.07, muted 5.88 |
| `--office-surface` | `#FFFDF9` | Cards, tables, tooltip, modal, phone tab bar, header menu | espresso 12.19, muted 6.47, deep gold 5.77, danger 8.98 |
| `--office-sunken` | `#ECE8E0` | Tonal fills: segmented track, table head, row hover, secondary button, ring-free empty states | espresso 10.13, muted 5.38, deep gold 4.80 |
| `--office-row-alt` | `#FAF7F2` | Zebra rows in People and Gold tables | muted 6.15 |
| `--office-text` | `var(--color-espresso)` `#492E21` | All primary text, numbers, active nav, icons | see above |
| `--office-muted` | `#6B5A4D` | Labels, secondary lines, axis ticks, inactive tabs | 5.38 or more on every surface here |
| `--office-gold-text` | `#8A5A2E` | The only "gold" text on light (Gold links, "Gold" in the People table) | 4.80 to 5.77 |
| `--office-danger` | `var(--color-danger)` `#8B1E1E` | Delete, expired invite | 8.15 or more |
| `--office-header` | `rgb(244 242 237 / 0.82)` | Sticky header with `backdrop-filter: blur(16px) saturate(140%)` | |
| `--office-overlay` | `rgb(73 46 33 / 0.32)` | Modal and sheet backdrop | |

Gold `#E5AC6E` is never text on light (1.98). It is a fill (badges, counts) with espresso text on it (6.17), or a mark.

Shadows (warm, espresso based, never black):

```css
--office-shadow-1: 0 1px 2px rgb(73 46 33 / 0.04), 0 8px 24px -12px rgb(73 46 33 / 0.10);  /* every card at rest */
--office-shadow-2: 0 2px 4px rgb(73 46 33 / 0.05), 0 18px 40px -16px rgb(73 46 33 / 0.16); /* hover on clickable cards, menus, tooltip */
--office-shadow-3: 0 4px 8px rgb(73 46 33 / 0.06), 0 32px 64px -24px rgb(73 46 33 / 0.24); /* modal, sign-in card */
```

Shape (one rule, used everywhere): cards `--office-radius-lg` 20px; tiles and inner panels `--office-radius` 14px; buttons and fields keep the brand `--radius-sm` 6px; segmented controls, badges, bars and the active nav item are pills (999px).

### 2.2 The data palette (Dashboard and Analytics only)

Muted, mid-dark, warm-leaning. A metric keeps its colour everywhere (ring, tile, sparkline, chart, funnel step, tooltip swatch).

| Token | Name | Hex | Tint `-tint` (12%, fills) | Track `-track` (24%) | Metric | On surface |
|---|---|---|---|---|---|---|
| `--office-slate` | Slate | `#3F6290` | `#E8EAEC` | `#D1D8E0` | **Site visitors**, top pages, referrers | 6.15 |
| `--office-plum` | Plum | `#7A4A72` | `#EFE8E9` | `#DFD2D9` | **Page views** | 6.78 |
| `--office-sage` | Sage | `#7BA374` | `#EFF2E9` | `#DFE7D9` | **People who started the journey** | 2.82 (relief: labels) |
| `--office-teal` | Deep teal | `#2C7773` | `#E6EDE9` | `#CCDDD9` | **People who finished the journey**, journey answers, where people stop | 5.18 |
| `--office-clay` | Clay | `#B4583A` | `#F6E9E2` | `#EDD5CB` | **Registrations**, plans | 4.70 |
| `--office-ochre` | Ochre | `#C0913A` | `#F7F0E2` | `#F0E3CB` | **Gold applications** | 2.81 (relief: labels) |
| `--office-taupe` | Taupe | `#9B8B7B` | `#F3EFEA` | `#E7E2DB` | Neutral: previous period (dashed), "Other", "No plan chosen", Declined | 3.24 |

Plus `--office-grid: rgb(73 46 33 / 0.06)` (gridlines, decoration) and `--office-crosshair: rgb(73 46 33 / 0.18)`.

**Validated** (dataviz validator, light, surface `#FFFDF9`, order slate, ochre, plum, sage, clay, teal, taupe): lightness band PASS, CVD adjacent PASS (worst 8.1, teal and clay, protan), normal-vision PASS (worst 15.5), funnel order slate, sage, teal, clay PASS, ring trio sage, teal, clay PASS on all pairs. Chroma floor FAILS on purpose (Moishe asked for muted). Sage and ochre are under 3:1: the relief rule applies, so every sage or ochre mark sits beside its number in text. Text never wears a palette colour; text is espresso or muted, the coloured mark beside it carries identity.

**Ordered categories use a ramp of their metric's hue, not other metrics' colours.** Steps: full, 72%, 48%, 28% (mixed with the surface). Plans (always clay): `#B4583A`, `#C9866F`, `#DBAE9D`, `#EACFC4`. Journey answers (always teal): `#2C7773`, `#679D99`, `#9ABDB9`, `#C4D7D3`. A fifth or later category folds into "Other" (taupe). Pale steps are always separated by a 3px surface gap and directly labelled.

If Moishe wants more colour after seeing it, raise chroma on one token at a time and re-run the validator; the structure stays.

### 2.3 Type and layout

```css
--office-stat: clamp(2.25rem, 1.5vw + 1.75rem, 3.5rem);   /* big numbers: 36px phone, 56px at 1440 */
--office-stat-lg: clamp(3rem, 3vw + 2rem, 4.5rem);         /* the Analytics hero number */
--office-text-xs: 0.75rem;                                 /* ticks, badges, tab labels, table heads only */
--office-nav-w: 15.5rem;  --office-header-h: 3.5rem (4.5rem from 64em);  --office-tabbar-h: 4rem;
--office-ring: 6rem (9.5rem from 64em);  --office-ring-stroke: 10px (14px from 64em);
--office-spark-h: 3rem;  --office-chart-h: 15rem (20rem from 64em);  --office-chart-hero-h: 18rem (24rem from 64em);
--office-donut: 10rem (11.5rem from 64em);
```

Fonts: Signika 500 for headings and every number (`font-variant-numeric: tabular-nums`), Figtree for everything else. Charts are created after `document.fonts.ready`.

---

## 3. The shell

**Cards without lines.** A card is `--office-surface` on `--office-page`, `--office-radius-lg`, `--office-shadow-1`, padding `--space-4` phone / `--space-5` desktop. No border, ever. Inside a card, groups are separated by space (`--space-4`) or a tonal panel (`--office-sunken` or a metric `-tint`), never a rule. Clickable cards: hover (fine pointer) lifts 2px and goes to `--office-shadow-2`, 250ms `--ease-soft`; press scale 0.99. Gutter `--gutter`.

### 3.1 Desktop (from 64em)

- **Sidebar**, `--office-nav-w`, background `--office-page` (same as the page: no divider, the content cards float to its right).
  - Top 72px: the swan mark in espresso (dark-on-light lockup) 28px + "Office" Signika 500 `--text-lg` espresso.
  - Items Dashboard, Analytics, People, Gold: 44px pill rows, 20px line icon + Figtree 500 `--text-sm` muted. Current: `--office-surface` pill with `--office-shadow-1`, espresso text and icon. Hover: `--office-sunken` pill.
  - Gold count badge when applications wait: gold fill, espresso Figtree 600 `--office-text-xs`, pill 20px high.
  - Bottom: initials disc (`--office-sunken`, espresso initials), name, role muted, "Sign out" quiet link.
- **Header** sticky, `--office-header` with blur, no line. Once scrolled more than 8px, a soft `0 12px 24px -20px rgb(73 46 33 / 0.18)` appears (opacity transition). Left: page title Signika 500 `--text-xl`. Right: range picker, then the person disc (40px, `--office-surface`, `--office-shadow-1`) opening a menu (surface, `--office-shadow-2`, radius 14px).
- Content: padding `--space-5`, max 80rem.

### 3.2 Phone and tablet (below 64em)

- Header 56px, sticky, same treatment: espresso swan 24px + title Signika 500 `--text-lg`; person disc 36px right.
- **Bottom tabs**, `--office-tabbar-h` + `env(safe-area-inset-bottom)`, `rgb(255 253 249 / 0.92)` with blur, shadow `0 -12px 28px -20px rgb(73 46 33 / 0.22)`, no top line. Icon 24px over Figtree 600 `--office-text-xs`. Current: espresso icon and label, icon on a 56 by 32px `--office-sunken` pill. Others muted (6.47). Gold tab carries the count badge.
- Detail pages hide the tabs and show "‹ People" / "‹ Gold" in the header; Gold detail puts its decision bar where the tabs were (7.4).
- `viewport-fit=cover`, no tap highlight, `touch-action: manipulation`, inputs 16px, `100dvh`.

### 3.3 Range picker

Segmented control, 40px, pill: track `--office-sunken`, segments muted text, the selected one a `--office-surface` thumb with `--office-shadow-1` and espresso text; the thumb slides (`translateX`, 400ms `--ease-soft`). Dashboard **Today · 7 days · 30 days**; Analytics **7 days · 30 days · 90 days · All**. In the URL (`?range=30d`), remembered in the session, back-button safe, HTMX swap as before. Phone: full width at the top of the content.

---

## 4. Dashboard

### 4.1 Layout at 1440 (12 columns)

1. **Greeting** (no card): "Good evening, Barry." Signika 500 `--text-2xl`; under it the stored what-changed line, Figtree `--text-lg` muted, max `--measure`. Copy uses counts, not percent (section 10).
2. **The journey** card (8 columns): three rings side by side | **Gold waiting** tile (4 columns). Same height.
3. **From visit to registration** card (12 columns): the funnel.
4. **Site visitors** tile (6) | **Page views** tile (6).
5. **Waiting for you** (7) | **Latest registrations** (5).

### 4.2 Layout at 375

One column, `--page-margin` 20px, in this order: range picker; greeting (`--text-xl`) and line (`--text-base`); The journey (three rings in one row); Gold waiting; Waiting for you; funnel; Site visitors; Page views; Latest registrations.

### 4.3 The journey: three rings, plain counts

Three single rings in a row (Apple Fitness summary style), not concentric. Each ring has its own count in the middle. Card title "The journey" Signika 500 `--text-lg`, no subtitle.

| Ring | Colour | Number in the middle | Line under the ring | Goal line | Change line |
|---|---|---|---|---|---|
| Started | `--office-sage` | `42` | "people started" | "Goal 60" | "+12 on last week" |
| Finished | `--office-teal` | `31` | "finished it" | "Goal 40" | "+4 on last week" |
| Registered | `--office-clay` | `18` | "registered" | "Goal 25" | "Same as last week" |

- Number: Signika 500, `--text-xl` phone (inside a 96px ring) / `--office-stat` desktop (inside 152px), espresso, tabular, centred. Under-ring line Figtree 500 `--text-sm` espresso; goal and change lines `--text-sm` muted, one each. The change line is a **count**: "+12 on last week", "6 fewer than last week", "Same as last week", "New this week" when last period was 0. For Today: "on yesterday". Minus is written as "fewer".
- "Started" is `journeys_started` (one per browser, as stored). "Finished" is `journeys_completed`. Labels say people, never "journeys completed" or a rate.
- **With a goal:** track in the metric `-track`; arc in the full colour from 12 o'clock clockwise, round caps, length = count / goal. Over 100% the arc continues into a second lap (cap 200%); the cap end gets a 3px `--office-surface` halo (`stroke` underlay) so the overlap reads. The big number stays the count; the goal is only the small "Goal 60" line.
- **No goal set:** no track and no arc; the full ring is drawn in the metric at 48% (`color-mix(in oklab, var(--office-sage) 48%, var(--office-surface))`), a calm closed circle, the count in the middle, and no goal line (no "No goal set" text on the Dashboard; the Django admin is where goals are set).
- Geometry: `--office-ring` 96px / 152px, stroke 10px / 14px, `pathLength="100"`. Rings are 24px apart on phone, spread evenly on desktop.
- Draw-in: arc `stroke-dashoffset` 100 to target, 1400ms, left to right 120ms apart, on first view. Range switch: transitions from the old value (600ms). Reduced motion: final.
- The row is one `role="img"` with `aria-label`: "42 people started the journey, goal 60. 31 finished it, goal 40. 18 registered, goal 25." (goal parts omitted when unset). Each ring links to its Analytics chart.

### 4.4 Gold waiting tile

- Fill `--office-ochre-tint` (`#F7F0E2`, espresso 10.92, muted 5.80), radius 20px, no shadow (the tint is the surface).
- Small ochre swan glyph or 10px ochre disc beside the label "Gold applications" Figtree 500 `--text-sm` muted.
- Number Signika 500 `--office-stat` espresso; under it "waiting for you" `--text-base`.
- Button "Review" (espresso fill, cream text 10.95, `.btn-sm`) to `/gold/?status=waiting`. Owner, Manager and Viewer all see it (it only opens the list).
- Zero: number "0", line "Nothing waiting.", no button.

### 4.5 From visit to registration (funnel)

Four steps, plain counts, no percent on the Dashboard.

- Desktop: four columns in one card. Each: label Figtree 500 `--text-sm` muted ("Visitors", "Started the journey", "Finished it", "Registered"); number Signika 500 `--text-xl` espresso; a 10px pill bar in the step's colour (slate, sage, teal, clay) on its `-track`, length = share of visitors (`scaleX`, origin left, min 6px so a small step still shows). Under the bar, muted `--text-sm`: "31 of 42 who started" (count of the previous step, never a rate).
- Phone: four rows, label left, number right, bar full width under, the "of" line under the bar.

### 4.6 Site visitors and Page views tiles

Clickable `--office-surface` cards linking to Analytics. Label muted `--text-sm`; number Signika 500 `--office-stat`; change line as counts ("+204 on last week"); sparkline `--office-spark-h` full width at the bottom: 2px line in the metric colour, area gradient from the metric at 22% to 0, last point a 7px dot with a 2px surface ring. No axes, no grid. 7 points for Today and 7 days, 30 for 30 days.

### 4.7 Waiting for you, Latest registrations

Surface cards. Rows have no rules: 64px rows separated by 4px, each row a 14px-radius pill that fills `--office-sunken` on hover. Name Figtree 600 espresso, potential badge (7.5), "Applied 2 days ago" muted, desktop: "Approve and invite" (`.btn-sm` primary, Owner and Manager) and a chevron. Heading "Waiting for you" with the count in a gold-fill badge. Empty: "Nothing waiting for you." Latest registrations: five rows (name, plan in muted, "Today, 18:40"), "See everyone" quiet link. These two cards use brand colours only (badges), no palette.

---

## 5. Analytics

### 5.1 Layout

Desktop: 12 columns. Phone: one column. Each chart card: title Signika 500 `--text-lg`, the stored one-sentence summary under it (`--text-sm` muted), the chart, and "View as table" (a quiet pill toggle opening `<details>`, the table on `--office-sunken` panel, radius 14px, rows without rules).

| # | Card (desktop span) | Form |
|---|---|---|
| 1 | **Visitors** hero (12) | Big number + area line |
| 2 | **Four KPI tiles** (3 each; 2 by 2 on phone) | Tinted tiles with sparkline |
| 3 | **From visit to registration** (12) | Centred funnel |
| 4 | **Registrations by plan** (6) and **Suggested plan** (6) | Donuts |
| 5 | **Journey answers** (12) | Three donuts and one bar list |
| 6 | **Where people stop** (8) | Rounded columns |
| 7 | **Gold applications** (4) | Stacked pill bars |
| 8 | **Top pages** (6) and **Referring sites** (6) | Ranked lists |

### 5.2 The charts

1. **Visitors (hero).** Top left: the range total Signika 500 `--office-stat-lg`, "visitors" `--text-lg` muted beside it, change line under ("+1,204 on the previous 30 days"; Analytics may also show "▲ 18%" after it in muted). Top right: small segmented toggle Visitors · Page views (page views replace visitors; colour switches slate to plum with a morph). Chart `--office-chart-hero-h`: line `cubicInterpolationMode: 'monotone'`, `borderWidth: 2.5`, `pointRadius: 0`, `pointHoverRadius: 6` (fill metric, 2px surface border); fill a vertical gradient metric 28% at the top to 0 at the baseline. Previous period: taupe, `borderWidth: 1.5`, `borderDash: [4, 4]`, no fill. HTML legend above the plot (2 series).
2. **KPI tiles**: Visitors (slate), People who started (sage), Registrations (clay), Gold applications (ochre). Fill = the metric `-tint`, radius 20px, no shadow, padding `--space-4`. Label muted `--text-sm`, number Signika 500 `--office-stat` espresso, change line muted, a 40px sparkline (2px metric line, area metric at 18% to 0). Clicking scrolls to the matching chart.
3. **Funnel**, centred and designed: horizontal **floating bars** (`indexAxis: 'y'`, data `[-v/2, v/2]`) so each step is a pill centred on one axis, narrowing downwards; colours slate, sage, teal, clay; `borderRadius: 999`, `borderSkipped: false`, `barPercentage: 0.78`, `minBarLength: 10`, x and y axes hidden, no grid. Left of each pill: label `--text-sm` muted; right: count Signika 500 `--text-lg`. Between pills, centred, a small muted line: "74% carried on" (rates are allowed on Analytics, worded as people). The largest drop's line is espresso 600. Height 4 by 64px.
4. **Registrations by plan** and **Suggested plan**: doughnut `cutout: '76%'`, `borderRadius: 8`, `spacing: 3`, `borderWidth: 0`, clay ramp in plan order (from `plans`), "No plan chosen" taupe last. Centre (HTML overlay): the total Signika 500 `--text-xl` and "registered" / "suggested" muted. Legend list to the right (below on phone): 10px pill swatch, plan name, count right aligned tabular, share muted.
5. **Journey answers** (teal ramp): Time of day, How often, Company as three doughnuts (same spec as 4, `--office-donut`), answers in journey order; Facilities as a bar list (members could choose more than one, so not parts of a whole): horizontal bars `borderRadius: 999`, teal on a full-length `--office-teal-track` track (a second dataset, `grouped: false`, drawn behind), `barThickness: 10`, label above each bar, count right. Note under Facilities: "Members could choose more than one."
6. **Where people stop**: vertical bars, one per screen in order; `borderRadius: 8`, `borderSkipped: 'start'` (round top only), `maxBarThickness: 32`; bars `--office-teal` at 48%, the highest bar full teal with a direct label "23 left here". Short screen names, wrapping to two lines, never rotated.
7. **Gold applications**: one row per potential (High, Medium, Low), horizontal stacked to 100%, `barThickness: 14`, pill ends (scriptable `borderRadius` on the first and last segment only), 3px surface gaps. Approved ochre, Waiting ochre at 48% with a 45° ochre hatch (canvas pattern), Declined taupe. Legend shown; totals as direct labels at row end.
8. **Top pages** (slate) and **Referring sites** (slate): not charts. Top 10 rows, no rules: name, count right aligned, and under each a 6px pill bar in slate on `--office-slate-track` at its share of the top value. "Direct or unknown" is a normal row.

### 5.3 Chart.js defaults (`office-charts.js`, set once)

- `Chart.defaults.font = { family: 'Figtree', size: 12 }`, `color` = `--office-muted`.
- Grid: y only, `color: --office-grid`, `lineWidth: 1`, `border: { display: false }`, `drawTicks: false`, `ticks: { padding: 10, maxTicksLimit: 4 }`, `beginAtZero: true`. x: `grid: { display: false }`, `border: { display: false }`. Donuts and the funnel: no scales.
- `layout.padding: { top: 8 }`, `responsive: true`, `maintainAspectRatio: false` (the card sets the height).
- Interaction: lines `mode: 'index', intersect: false` with a 1px `--office-crosshair` vertical line plugin; bars and donuts `mode: 'nearest', intersect: true`. Donut hover: `hoverOffset: 6`.
- Chart.js legend off; our HTML legends.
- Gradients are scriptable, built once the chart area is known:

```js
backgroundColor: (ctx) => {
  const { chart } = ctx; const a = chart.chartArea;
  if (!a) return 'transparent';
  const g = chart.ctx.createLinearGradient(0, a.top, 0, a.bottom);
  g.addColorStop(0, tint(color, 0.28)); g.addColorStop(1, tint(color, 0));
  return g;
}, fill: 'origin'
```

- **No new library.** Floating bars, doughnut `borderRadius`/`spacing`, scriptable options and canvas patterns are all core 4.6.1. Value labels and the centre text are a ~20-line inline plugin or HTML overlay; `chartjs-plugin-datalabels` is not worth adding.
- Large ranges ("All", over 120 points) stay weekly from the server.

### 5.4 Tooltip

HTML `external` tooltip, one element reused: `--office-surface`, `--office-shadow-2`, radius 14px, padding 12px 14px, no border. Title Figtree 600 `--text-sm` espresso ("Thu 23 Oct"). Rows: 10px pill swatch in the series colour, label muted, value espresso tabular right aligned ("Visitors 1,204", "Previous 30 days 980"; donuts "Tier 2 · 41 · 38%"). Opacity only, 120ms, clamped inside the card; phone: tap shows it above the plot, tap outside hides.

### 5.5 Empty, busy, error

As before, restyled: empty = no axes, the card keeps its height, centred muted sentence on a `--office-sunken` pill ("No visitors in this range yet."), table toggle hidden. Busy (over 300ms): chart areas dim to 0.5. Error: muted line under the title "Couldn't refresh. Showing 7 days." with "Try again".

---

### 5.6 Built deviations (frontend, 2026-10-23)

- **Gold applications (5.2.7):** the backend stores counts by potential and counts by status now, not potential by status, so the stacked-per-potential chart is not built. The card shows "By potential" as three ochre pill bars and "Where they stand now" as one stacked pill (Approved ochre, Waiting ochre 48% hatched, Declined taupe). Both are server-rendered HTML. Revisit if the roll-up ever stores potential by status.
- Facilities, Gold, top pages and referrers are HTML bar lists (same colours, same rounded bars), not Chart.js.

## 6. Motion

Unchanged from the accepted Office motion (PROJECT 2026-10-23): cards rise in once (1000ms, 8px/12px), rings draw (1400ms, 120ms apart), sparklines draw (900ms), funnel bars `scaleX` (900ms), numbers count on the first Dashboard load in a session (900ms), charts draw in when 15% visible (900ms, `easeOutQuint`) and morph on range switch (600ms), HTMX text cross-fades (240ms), picker thumb 400ms, tooltip 120ms, hover lift 250ms. New: donuts sweep in clockwise (`animateRotate: true`, `animateScale: false`, 900ms). Reduced motion: everything final and instant, Chart.js `animation: false`.

---

## 7. People and Gold (brand colours on the light shell)

No palette colours here. Espresso, gold, caramel, cream (and the light shell neutrals) only.

### 7.1 Lists

- Filter bar (no card): search field (shared field, light: 40px, `--office-surface` fill, 1px `--color-control-line` border 3.94; inputs keep a visible edge for accessibility, that is not a card line), segmented filters (3.3 style), export button right.
- **Desktop table** on a `--office-surface` card (radius 20px, `--office-shadow-1`, padding 8px). Head row: `--office-sunken` pill (radius 14px), uppercase `--office-text-xs`, `--tracking-label`, muted; sticky under the header. Rows 56px, **no rules**: zebra `--office-row-alt`, hover `--office-sunken`, row radius 14px. Whole row links (first cell real link). Numbers right, tabular.
- **Phone cards**: one surface card per row (radius 20px, `--office-shadow-1`, padding `--space-3`, 8px apart). Filters collapse into search + "Filters" opening a bottom sheet (surface, radius 20px top, `--office-shadow-3`).
- Paging "Show more"; total from the stored counter ("1,204 people"); empty sentences unchanged.

### 7.2 Buttons and focus

- Primary: espresso fill, cream text (10.95). Hover (fine pointer) `--color-espresso-raised`.
- Secondary: `--office-sunken` fill, espresso text (10.13), no border.
- Quiet: espresso text link, underline on hover. Danger: `--office-danger` text (quiet) or fill with cream text (confirm button in the danger modal).
- Focus everywhere: 2px espresso outline, 2px offset.

### 7.3 Person detail

Header: name Signika 500 `--text-2xl`, "Registered 23 Oct 2026" muted, badges. Desktop 8/4: sections Details, Plan interest, Journey answers, Gold as surface cards of label/value rows (label muted `--text-sm`, value espresso `--text-base`, rows separated by `--space-3`, no rules). Right rail card **Data**: "Export his data" (secondary), "Delete this person" (quiet danger). Phone: one column, Data last. Delete modal copy unchanged.

### 7.4 Gold application detail

Same structure and copy as before. Decision card (right rail, sticky): surface, `--office-shadow-2`, badges, "Approve and invite" primary block, "Decline" secondary block, helper muted. Approved: a gold-fill strip at the top of the card with espresso "Approved 23 Oct by Barry". Phone decision bar: `rgb(255 253 249 / 0.94)` with blur, upward soft shadow, safe-area padding, Decline (1/3) secondary + Approve and invite (2/3) primary, 52px. Approve success check on the email confirm page: gold circle draws, then an espresso tick (gold tick on light would fail).

### 7.5 Badges (light)

Figtree 600 `--office-text-xs`, 22px pill, padding 0 10px. Text first, colour second.

| Value | Look | Contrast |
|---|---|---|
| Potential High | Gold fill, espresso text | 6.17 |
| Potential Medium | Caramel 18% fill `#F3E8DB`, espresso text | 10.25 |
| Potential Low | `--office-sunken` fill, muted text | 5.38 |
| Waiting | Espresso fill, cream text | 10.95 |
| Approved | Gold fill, espresso text | 6.17 |
| Declined | No fill, muted text | 6.47 |
| Invite expired / email not sent | `--office-danger` text with warning icon | 8.98 |

### 7.6 Confirm modal

`confirmModal()` light skin: panel `--office-surface`, radius 20px, `--office-shadow-3`, max 28rem, title Signika 500 `--text-xl` espresso, message muted, backdrop `--office-overlay`. Buttons stacked on phone (primary first), right aligned on desktop. Copy table from the first brief unchanged.

---

## 8. Office sign-in (light)

- Page `--office-page`; one centred card `--signin-w` (26rem), `--office-surface`, radius 20px, `--office-shadow-3`, padding `--space-5` (`--space-4` phone, card goes edge to edge minus 20px margins).
- Inside, top to bottom: espresso swan 40px; "Office" Signika 500 `--text-2xl`; "Spa 99 staff only." Figtree `--text-base` muted; email and password (shared fields, light variant, 52px, visible 1px control-line edge, labels above); "Sign in" primary block (espresso); "Forgotten your password?" quiet link. No public links, no imagery, no footer beyond a muted "Spa 99 · BML Group" line under the card.
- Errors: `--office-danger` text under the field and in a summary line above the button. Focus 2px espresso.
- The email confirm page (approve from email) and expired-link page use this same card.

---

## 9. Phone (Barry)

- 375 first. Nothing scrolls sideways; charts fill the card width; nothing sits under the home indicator (tab bar and decision bar include `env(safe-area-inset-bottom)`).
- Dashboard order in 4.2. Rings row: 3 by 96px with 20px gaps fits 335px content.
- Analytics: hero chart 18rem, other charts 15rem, donuts 10rem centred with the legend list under; KPI tiles 2 by 2; journey answers stack one per row.
- Tap targets 44px or more (tabs 64px, list cards whole, picker segments wider than 80px). Tooltips on tap, above the finger.
- Lists become cards; Gold detail uses the bottom decision bar; no inline approve on the phone Dashboard list (rows open the detail).

---

## 10. Numbers, dates, copy

Formats unchanged (en-GB, Europe/London): 1,204 · 12.4k from 10,000 on tiles · ticks compact (0 · 500 · 1k) · rates 4.6% / 38% (Analytics only) · 23 Oct · Thu 23 Oct · w/c 20 Oct · 23 Oct 2026, 18:40 · Today, 18:40.

Copy: short, calm, British, no exclamation marks.
- Dashboard change lines are counts: "+12 on last week", "6 fewer than last week", "Same as last week", "New this week". Today: "on yesterday".
- What-changed line (stored by the roll-up) uses counts: "18 people registered this week, 4 more than last week. Two Gold applications are waiting." / "A quiet day so far."
- Ring labels exactly: "people started", "finished it", "registered", "Goal 60".
- Never "journeys completed", "completion rate" or "% of goal" on the Dashboard.

---

## 11. Accessibility

- Text contrast: every pair in 2.1 is 4.5 or more (lowest: deep gold on sunken 4.80, muted on sunken 5.38). Big numbers are espresso (10 or more). Gold, caramel and palette colours never carry text.
- Data marks: slate, plum, teal, clay, taupe 3:1 or more on the surface; sage and ochre 2.8, so they always sit beside their number in text; pale ramp steps are separated by 3px gaps and directly labelled. Legend for 2 or more series; a fourth status is hatched.
- Every chart: summary sentence, `role="img"` with `aria-label` = summary, working "View as table" (`<caption>`, `scope`). Rings: one full-sentence label (4.3). Change lines read as words ("12 more than last week").
- Keyboard: nav, tabs, picker (radios, arrow keys), table rows, modal (focus trapped, Escape, focus returns). Charts skipped by Tab.
- `forced-colors: active`: series still differ by dash and hatch; badges get a border; the active nav pill gets an outline.
- Toast after actions `role="status"`.

---

## 12. Backend changes this needs (for the server agent)

1. Rings: replace the three ring definitions with `journeys_started` (count), `journeys_completed` (count), `registrations` (count); each ring `{key, label, value, goal, percent, previous, change}` where `change = value - previous` (count). Drop the journey-completion rate and "Gold handled" rings.
2. `OfficeGoal` keys: `registrations`, `journeys_started`, `journeys_finished`, all counts per range (migration renames/replaces `journey_completion` and `gold_handled`; existing rows can be dropped).
3. Dashboard JSON adds `gold_waiting` (stored counter) at the top level and `page_views` to stats; stats carry `previous` so templates print count changes.
4. Funnel items carry `previous_value` (the step before) for "31 of 42 who started".
5. The what-changed sentences in `MetricText` are rewritten in counts (section 10).

---

## 13. Acceptance checklist (frontend verifies)

1. No hex or Office token appears in `tokens.css` or any public CSS; all `--office-*` tokens are defined in `office.css` under `.office`; the public site renders identically before and after (spot-check Home, Memberships, Register at 375 and 1440).
2. No card, tile, table or list has a border or a rule between rows; separation is tone, shadow and space. Only form fields keep their 1px edge.
3. Page `#F4F2ED`, cards `#FFFDF9` with `--office-shadow-1`, radius 20px; text espresso and `#6B5A4D` only.
4. Dashboard rings show the count in the middle ("42"), "people started", "Goal 60" when set; with no goal the ring is a closed 48% circle with the count and no goal text. No percent anywhere on the Dashboard. `aria-label` reads all three counts.
5. Gold waiting tile shows the stored count and "Review"; zero shows "Nothing waiting." with no button.
6. Each metric keeps its colour on every page: visitors slate, page views plum, started sage, finished teal, registrations and plans clay, Gold ochre, previous period taupe dashed.
7. Analytics: hero area chart with gradient fill and monotone line; donuts with `cutout 76%`, rounded arcs and centre totals; centred floating-bar funnel; rounded bars (`borderRadius` 8 or pill); y gridlines only at 6% espresso, no axis borders; surface tooltips with swatches and British formats.
8. People and Gold use only espresso, gold, caramel, cream and the shell neutrals; badges match 7.5.
9. Office sign-in is the light card in section 8, no public links.
10. 375: header, bottom tabs with Gold badge, Dashboard order as 4.2, three rings in one row, no horizontal scroll, nothing under the home indicator. 1440: sidebar on the page tone with a surface pill for the current item.
11. Range switch morphs charts and rings, fades numbers, updates the URL, survives Back, dims only after 300ms.
12. Reduced motion: no drawing, counting, sweeping or morphing; final values at once.
13. Contrast spot checks with a tool: muted on sunken 5.38 or more, espresso on every tint 10 or more, focus ring visible on every control.
14. Viewer sees no action buttons; Owner and Manager approve via list (desktop), rail, phone bar and email page, each through a confirmation.
15. Lighthouse Dashboard 375, mid phone: LCP 2.5s or less, CLS 0.
