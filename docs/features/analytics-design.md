# Analytics > Visitors: design brief

Branch `feature/analytics`. Designer brief for spec A9 (`analytics.md`). Builds on `docs/design/OFFICE.md` section 5 (Analytics), `office-mobile.md` and `office-2-design.md` (Analytics is a phone tab). Brand rules win; Office tokens only, plus three derived ramp steps (section 9).

**Design read.** A quiet instrument panel for two or three people who run a spa, not a growth dashboard. One hue (slate, the visitor colour) across the whole area, numbers in Signika, sentences instead of jargon, nothing that blinks. The skills' marketing rules (heroes, imagery) do not apply to the Office; their restraint, state and motion rules do.

---

## 1. Where it lives

Analytics becomes two sub-pages under one tab, sharing the range.

| Sub-page | URL | Holds |
|---|---|---|
| **Journey** | `/analytics/` (unchanged) | Everything there today: Visitors hero, KPI tiles, Revenue cards, funnel, plans, answers, heard about us, where people stop, Gold |
| **Visitors** | `/analytics/visitors/` (new) | The nine sections below |

- **Top pages moves** from Journey to Visitors (it becomes the Pages card). The Journey page ends with Gold. The Visitors hero stays on Journey, because it is the top of the funnel; it gains a quiet "See Visitors" link (`o-seelink`, as on the Revenue cards).
- **Sub-nav:** `<nav class="o-seg" style="--n: 2" aria-label="Analytics">` with two links, `aria-current="page"` on the current one, the same markup as the Approvals tabs. Labels: **Journey** and **Visitors**.
  - Computer: first thing in the content, left aligned, width `18rem`. The range picker stays in the header (as now).
  - Phone: full width at the top of the content, 44px tall; the range picker (`place="page"`, 40px, as now) sits under it with `--space-3` between. The sub-nav uses Figtree 600, the range Figtree 500, so the two controls read as two levels.
- The range is the same session value on both sub-pages (7 days, 30 days, 90 days, All). Live now ignores it.
- The phone tab and the computer rail item stay "Analytics"; both sub-pages light it. Header title: "Analytics" on both.

## 2. Order and grid

Computer from `64em`: the existing 12-column `o-charts` grid, gutter `--gutter`, card padding `--space-5`. Phone: one column, card padding `--space-4 --space-3` (16px sides), same order. Nothing scrolls sideways at 320.

| # | Card (computer span) | Component |
|---|---|---|
| A | **On the site now** (12) | Live card (new, 3.1) |
| B | **Overview** tiles (12) | Five `o-kpi` tiles |
| C | **Where visits come from** (12) | Two ranked lists side by side |
| D | **Campaigns** (12) | Table, cards on phone |
| E | **Make a campaign link** (12) | Link maker (new). Office level and up only; Viewer gets no card at all |
| F | **Pages** (12) | Three-way switch over one table, cards on phone |
| G | **Contact taps** (12) | Ranked list + small table |
| H | **What people use** (12) | Three multiples: stack + two ranked lists |
| I | **Countries** (6) and **How long visits last** (6) | Ranked list; rounded columns |
| J | **When people visit** (12) | Heat map (new, 3.9) |

Why this order: who is here now, how many, where from, which links worked, what they read, what they did, who they are, when. The two halves of C, G and H sit side by side from `64em` and stack below it.

## 3. Sections

Every card follows OFFICE.md 5.1: title Signika 500 `--text-lg`, one muted summary sentence `--text-sm` (stored, from the snapshot), content, "View as table" where the content is a picture. Ranked lists are already text, so they need no table.

### 3.1 On the site now (A)

Not a card that shouts. Same surface card as the others, no tint.

- **Left** (computer: 4 of 12 inside the card; phone: top): a small 8px slate disc (static, the one semantic "live" mark on the page) + label "On the site now" (`--text-sm` muted, weight 600). Under it the count, Signika 500 `--office-stat-lg`, espresso. Under that: "in the last 5 minutes" muted `--text-sm`.
- **Right** (computer: 8 of 12, four columns; phone: a 2 by 2 grid from 360px, one column below): four short lists, each a `--text-sm` muted heading and up to 3 rows of name + count (tabular, right aligned), no bars: **Pages**, **Countries**, **Devices**, **How they came** (channel labels from 3.3). Long names truncate with an ellipsis; the full name is in `title`.
- Footnote (`o-footnote`): "Updates every 15 seconds while this page is open."

States:
| State | Shows |
|---|---|
| First paint | The server renders the live figures into the page (same shape as `live.json`), so there is never an empty flash. |
| **0 people** | The count "0", the line "No one on the site right now." in place of "in the last 5 minutes", the four lists hidden. The disc turns `--office-taupe`. Calm, not an error. |
| 1 person | "1" and "in the last 5 minutes"; lists show one row each. Never "1 people". |
| Poll fails | Figures stay as they were, the footnote becomes "Live figures paused. Trying again." Retry at 15 s, 30 s, 60 s, then a quiet "Try again" button (`o-quiet`). |
| Tab hidden | Polling stops; on return, one poll at once, then every 15 s. |

No `aria-live`: it would speak every 15 seconds. The count has `aria-describedby` pointing at "in the last 5 minutes".

### 3.2 Overview (B)

Five `o-kpi` tiles, all `o-kpi--slate` (new modifier, built like `--sage` from `--office-slate-tint`): one family, site traffic. Visually hidden heading "Overview".

| Label (exact) | Value | Change line |
|---|---|---|
| Visitors | 1,204 (compact from 10,000) | "+120 on the previous 30 days" (existing `change_ana`) |
| Visits | 1,532 | "+140 on the previous 30 days" |
| Pages per visit | 2.4 | "+0.3 on the previous 30 days" |
| Average visit | 1m 20s | "12s longer than the previous 30 days" / "12s shorter than..." |
| Left after one page | 42% | "4 points higher than the previous 30 days" / "lower" |

- Change lines stay muted text with no colour or arrow, so a rising bounce rate is not dressed as good or bad. "Same as the previous 30 days" when equal. All has no previous period: no change line (as now).
- Sparkline per tile from daily points (backend: daily `visits`, `pages_per_visit`, `avg_visit_seconds`, `bounce_rate_bp` in the snapshot series; if a series is missing the tile simply has no line, as `_kpi.html` already allows).
- Tiles are not links (no matching chart to scroll to): render as `<div>`, no hover lift.
- Layout: computer 5 equal columns (`o-kpis--five`). Phone: Visitors full width, then 2 by 2; below 360px, one column.
- Footnote under the row: "A visit ends after 30 minutes without a new page."

### 3.3 Where visits come from (C)

Two `o-rank` lists (slate bars at share of the top row) inside one card, side by side from `64em`.

- **Left, "How they came"**, visits per channel, sorted by visits, every channel shown even at 0 (so the shape is learnable). Labels: **Campaign links**, **Search**, **Social**, **Email**, **Other sites**, **Direct**. Each row: name, visits right, share muted after it ("38%").
- **Right, "Sources"**, top 10 sources by visits (google, instagram, a referring site), "Other" last with a `--office-taupe` bar. Names as stored, first letter capitalised.
- Summary sentence example: "Most visits came from Social, then Search."
- "View as table": Channel, Visits, Started the journey, Finished, Registered, Gold applied, Contact taps (from `channel_steps`). This is where channel steps live; the face of the card stays simple.

### 3.4 Campaigns (D)

- Computer: an `o-list` table on a `o-tablecard`. Columns: **Campaign** (the name in Figtree 600; under it, muted, the placement label from section 4, plus the content tag if it is not a placement), **Visits**, **Started**, **Finished**, **Registered**, **Gold applied**, **Contact taps**. Numbers tabular, right aligned. Sorted by visits. Zeros print as "0", never blank.
- Phone: one card per campaign (office-lists phone pattern): line 1 name + visits right ("86 visits"); line 2 placement muted; line 3 a wrapping row of small label/value pairs, only the non-zero steps ("Started 4", "Registered 1", "Taps 3"). No row link (nothing to open).
- Note under the table, always visible, `o-footnote`: "A campaign counts a step only when it happens on the same day as the visit. Nothing is stored on visitors' phones, so a step on a later day is not linked back."
- Empty: Office level: "No campaign visits yet. Make a link below and post it." Viewer: "No campaign visits yet."

### 3.5 Make a campaign link (E)

Choosing, not filling in. One card, three steps stacked, the result appears as you choose. Office level and up; the card and its endpoint are absent for Viewer.

1. **"Where will you post it?"** Seven chips in a wrapping row (radios styled as the `o-chip` pills of the filter sheet, 44px tall, `--office-sunken`, chosen = espresso fill and cream text, change instant): Instagram post, Instagram story, Instagram bio, WhatsApp, Email, Flyer QR, Other. Nothing chosen at first.
2. **"Give it a short name"** One field (label above, 52px, 16px text), hint under it: "A few words you will recognise later, such as spring open day." As he types, the cleaned name shows under the field, muted: "Saved as spring-open-day" (lower case, spaces to hyphens, letters, digits and hyphens only, 40 characters).
3. **"Which page should it open?"** An `o-select`: Home, The spa, Memberships, Gold Card, Visit us, Book, Start the journey (public URLs from the server, so the list follows the site).

**The link** (appears once all three are chosen; before that, a muted line "Choose a place, a name and a page to make the link."): a `--office-sunken` panel, radius `--office-radius`, the full URL in Figtree `--text-sm`, `overflow-wrap: anywhere`, selectable. Under it one primary button **Copy link**. On success the label changes to "Copied" for 2 s (no toast, no movement); if the clipboard is refused, the URL text is selected and the line "Press and hold to copy" appears.

**QR code**: only when Flyer QR is chosen, beside the link on computer, under it on phone: the code at 10rem on white-ish surface (`--office-surface`, quiet zone kept), and a secondary button **Download QR** (SVG, file name `spa99-<name>.svg`). Espresso modules on surface (12.19:1), scans fine.

Placement mapping (frontend and backend use the same table; utm values are already clean):

| Chip | utm_source | utm_medium | utm_content | Shown in Campaigns as |
|---|---|---|---|---|
| Instagram post | instagram | social | post | Instagram post |
| Instagram story | instagram | social | story | Instagram story |
| Instagram bio | instagram | social | bio | Instagram bio |
| WhatsApp | whatsapp | message | | WhatsApp |
| Email | email | email | | Email |
| Flyer QR | flyer | print | qr | Flyer QR |
| Other | other | link | | Other |

`utm_campaign` = the cleaned short name. Links made elsewhere (tags that do not match a row) show their source and medium as written.

### 3.6 Pages (F)

One card, a small segmented switch at the top (`o-seg o-seg--sm`, 3 items, full width on phone): **Most viewed** · **First page** · **Last page**. The switch changes the table in place (client side, all three are in the snapshot); no reload.

| View | Columns (computer table) |
|---|---|
| Most viewed | Page, Views, Average time, Scrolled halfway |
| First page | Page, Visits that started here, Share of visits |
| Last page | Page, Visits that ended here, Share of visits |

- "Average time" = engaged seconds / engaged views, formatted per section 5. "Scrolled halfway" = share of views that reached 50% or more. Header help under the table, `o-footnote`: "Average time counts only while the page is on screen. Scrolled halfway: of the views we heard back from, how many got at least halfway down."
- Top 10 rows; "Show all" quiet link opens the rest (cap 30).
- Each row keeps the existing slate share bar under the page name (from `o-rank`), sized by the first numeric column.
- Phone: cards. Line 1 page name + main number right ("412 views"); line 2 muted: "1m 20s on the page, 64% scrolled halfway" (Most viewed) or "38% of visits" (First, Last).
- Average time and scroll show "Not enough yet" (muted) when fewer than 10 views reported back, so early figures do not mislead.

### 3.7 Contact taps (G)

- **Left, "By kind"**: `o-rank` in fixed order, not sorted, so the eye learns the places: **WhatsApp**, **Phone**, **Email**, **Instagram**, **Map**. Each row: the existing 20px line icon (where the set has one; none drawn new), name, count. Card headline (`o-headline`): total, "86 taps".
- **Right, "By page"**: a short table (cards on phone): Page, Taps, and the kinds as a muted line ("WhatsApp 12, Phone 3"). Top 10.
- Empty: "No contact taps in this range yet."

### 3.8 What people use (H), Countries and How long visits last (I)

- **What people use**: three `o-multiple` columns (stack on phone), headings **Device**, **Browser**, **System**.
  - Device: one `o-stack` pill (3px gaps, slate ramp: Phone `--office-slate`, Tablet `--office-slate-3`, Computer `--office-slate-2`), legend list under it with swatch, name, count, share. Labels: **Phone**, **Tablet**, **Computer**. `role="img"` with the sentence "Phone 71%, Computer 25%, Tablet 4%".
  - Browser: `o-rank`. Labels: Chrome, Safari, Edge, Firefox, Samsung Internet, Instagram app, Facebook app, Other (taupe, last).
  - System: `o-rank`. Labels: iPhone and iPad, Android, Windows, Mac, Linux, Other.
  - Counted once per visitor per day; footnote: "Each visitor counted once a day."
- **Countries** (6): `o-rank`, top 10 by visitors, full English names (en-GB) from the code, "Unknown" last in taupe, "Other" if past 10. No flags. Credit, always shown, `o-footnote`: "IP location data by [DB-IP](https://db-ip.com)" (a real link, underlined, `rel="noopener"`, opens in a new tab). When the GeoIP file is missing every row is Unknown; the summary then says "Countries are not available yet."
- **How long visits last** (6): vertical rounded columns, the "Where people stop" spec (`borderRadius: 8`, round top, `maxBarThickness: 32`), slate at 48% with the tallest bar full slate and a direct label ("41 visits"). Six buckets in order, labels exactly: **Under 10s**, **10 to 30s**, **30s to 1m**, **1 to 3m**, **3 to 10m**, **Over 10m**. Never rotated; wrap to two lines on phone. "View as table": Length, Visits, Share.

### 3.9 When people visit (J)

A heat map of new visits by London weekday and hour. HTML grid (CSS grid of `<span>` cells), not Chart.js.

- **Sentence first** (`o-headline`): "Most visits start between 20:00 and 21:00. Sunday is the busiest day." When two hours tie, the earlier; under 20 visits in the range: "Not enough visits yet to show a pattern." and the grid is hidden.
- **Computer**: 7 rows (Mon to Sun, labels left, `--office-text-xs` muted) by 24 columns (hour labels on top every 3 hours: 00, 03, 06 ... 21). Cells square-ish, `--office-heat-cell` high, 2px gaps, radius 4px.
- **Phone**: turned on its side so it fits and reads: 7 columns (M T W T F S S) by 24 rows (hour label every 3 hours on the left), rows `--office-heat-cell` high, columns fill the width (about 40px at 375). Total about 440px tall. No sideways scroll.
- Colour: five steps of one hue (sequential, light to dark). 0 = `--office-sunken`; then `--office-slate-4`, `--office-slate-3`, `--office-slate-2`, `--office-slate`, split at quarters of the busiest cell. A small key under the grid: "Fewer" [5 swatches] "More".
- Hover (fine pointer) or tap: the existing `o-tip` tooltip, "Sun 20:00 to 21:00" / "14 visits". Tap outside closes. The cells are not in the Tab order.
- Accessibility: grid `role="img"` with the sentence as `aria-label`; "View as table" gives a 7-row table (day, then the 24 hours, plus a Total column), `<caption>` "Visits by hour, London time".
- Footnote: "London time. Each visit counted at the hour it started."

## 4. Copy

Short, calm, British, no exclamation marks, no "users", "sessions" or "conversions". Plain English labels as written above. Card titles exactly:

On the site now · Overview (hidden) · Where visits come from · Campaigns · Make a campaign link · Pages · Contact taps · What people use · Countries · How long visits last · When people visit

Empty sentences (on the `--office-sunken` pill, OFFICE.md 5.5), one per card: "No visits in this range yet." / "No campaign visits yet." / "No page views in this range yet." / "No contact taps in this range yet." / "Not enough visits yet to show a pattern."

## 5. Numbers

| Kind | Format | Examples |
|---|---|---|
| Counts | en-GB grouping; tiles compact from 10,000 | 1,204 · 12.4k |
| Seconds | under 60: `45s`; under an hour: `1m 20s`, drop zero seconds `2m`; an hour or more: `1h 5m` | 8s · 1m 20s · 3m |
| Rates | whole % from 10%, one decimal under 10% | 42% · 4.6% |
| Rate change | points, words | "4 points higher" |
| Pages per visit | one decimal | 2.4 |
| Hours | 24-hour | 20:00 to 21:00 |
| No figure | the existing table dash; screen readers get "No data" | |

A rate or average built on fewer than 10 visits or views shows "Not enough yet" instead of the figure (tiles keep the label and show it in `--text-sm` muted in place of the number).

## 6. Early days (figures start on deploy day)

- For the first 30 days after the start date, one muted line under the sub-nav: "Visitor figures started on 21 November 2026, so the first weeks will look thin." The date comes from the backend (`visitors_since`), never hard coded.
- When the previous period is wholly or partly before the start date, the change line reads "Counting since 21 Nov" instead of a comparison (a half-empty previous period would show false growth).
- Cards with no data keep their height and show the empty pill; the page never collapses into a blank column.

## 7. States (whole page)

- **Loading**: the page is server-rendered from the snapshot, so nothing loads after paint except Live. Range change: existing HTMX swap; over 300ms, card bodies dim to 0.5; text cross-fades `--office-dur-swap`.
- **Snapshot missing** (fresh database): every card in its empty state, plus "Updating…" (existing `data-updating` line).
- **Range refresh fails**: existing line under the card title, "Couldn't refresh. Showing 7 days." + "Try again".
- **Link maker**: QR request fails: "Couldn't make the QR code." + "Try again". Copy refused: see 3.5.

## 8. Motion

The accepted Office motion only (OFFICE.md 6), nothing new that loops.

- Cards rise once (1000ms, 8px phone, 12px computer); ranked bars `scaleX` from the left, 900ms; columns grow, 900ms `easeOutQuint`; range change morphs (600ms) and cross-fades text (240ms).
- Live: a changed count cross-fades (`opacity`, `--office-dur-swap`). No counting up, no pulse, no colour flash; the disc never animates.
- Heat map: the whole grid fades in once when 15% visible (opacity, `--office-dur-chart`), no per-cell stagger.
- Pages switch: the table cross-fades (240ms); the segment thumb slides (400ms).
- Link maker: chip choice is instant; the link panel fades in (opacity 240ms) the first time it appears; "Copied" swaps text with no movement.
- Reduced motion: everything final and instant (the Office tokens already go to 0ms; Chart.js `animation: false`).

## 9. Tokens

All from `office-tokens.css` and `tokens.css`: `--office-surface`, `--office-page`, `--office-sunken`, `--office-text`, `--office-muted`, `--office-slate`, `--office-slate-tint`, `--office-slate-track`, `--office-taupe`, `--office-grid`, `--office-shadow-1`, `--office-radius-lg`, `--office-radius`, `--office-pill`, `--office-stat`, `--office-stat-lg`, `--office-text-xs`, `--office-chart-h`, `--office-dur-*`, `--space-*`, `--gutter`, `--text-sm`, `--text-lg`, `--control-h`, `--ease-soft`.

**Proposed additions (derived, Office only, in `office-tokens.css`; decoration only, never text):**

```css
/* Analytics > Visitors (docs/features/analytics-design.md 9). Proposed, derived. */
--office-slate-2: #758DAD;   /* slate 72% over surface: heat map step 4, Computer in the device split */
--office-slate-3: #A3B3C7;   /* slate 48%: heat map step 3, Tablet */
--office-slate-4: #C9D2DC;   /* slate 28%: heat map step 2 */
--office-heat-cell: 1.125rem; /* heat map row height on phone; 1.75rem from 64em */
```

The slate steps are the same full/72/48/28% ramp the Office already uses for clay and teal (OFFICE.md 2.2). Pale steps are always beside their numbers (tooltip and table) and separated by 2 to 3px surface gaps.

## 10. Build notes for frontend

1. New template `office/templates/office/analytics_visitors.html` extending `office/base.html`, same head (Chart.js, `office-charts.js`), same `header_range` block. Sub-nav as a small include `_analytics_nav.html` (Approvals `o-seg` link markup), used by both sub-pages. Move the Top pages section out of `analytics.html`.
2. Reuse: `_range.html` as is; `_kpi.html` (add `o-kpi--slate` and allow a non-link `<div>` and the five-up `o-kpis--five`); `o-rank` for every ranked list (add a `--taupe` row modifier for Other/Unknown); `o-stack` + `o-legend` for devices (add slate segment modifiers); `o-multiples`/`o-multiple` for What people use; `o-table` "View as table"; `o-empty-chart`/`o-empty-line` empties; `o-error` + `data-retry`; `o-footnote`, `o-summary`, `o-headline`, `o-seelink`.
3. Tables to cards on phone: `o-tablecard` + `o-list` from `office-lists.css`, with the `office-mobile.md` fixes (explicit cell `order`, `.o-card.o-tablecard` reset). Campaigns, Pages and Contact taps by page use it.
4. How long visits last: add one spec to `office-charts.js` copied from the drop-off chart (slate instead of teal). It is the only new Chart.js chart. Heat map, Live, ranked lists and the device split are server-rendered HTML.
5. New small module `office-visitors.js` (no library): live polling (15 s, Page Visibility, backoff, fills the four lists and cross-fades the count), the Pages switch, the heat map tooltip (reuse `.o-tip` markup and styles), the link maker (cleaning rule, link build, Copy). CSS in `office-analytics.css` (new `.o-live`, `.o-heat`, `.o-linkmaker` blocks).
6. Link maker chips: the filter sheet chip style (`office-leads.css` `.o-sheet .o-seg .o-seg-item`), lifted into a shared `.o-chips` class rather than copied. Fields and select: existing `o-select` and Office field styles.
7. QR code: there is no QR library in the repo. Proposed: a small server endpoint (Office level, only our own public URLs accepted) returning SVG made with `segno` (pure Python, no dependencies). Fetched with HTMX when Flyer QR is chosen and the link is complete; the same SVG is the download. Backend to confirm.
8. Check at 320, 375, 414 and 1440: no sideways scroll, the phone heat map fits, tap targets 44px, Viewer sees no link maker, reduced motion is instant.
