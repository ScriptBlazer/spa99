# Office on the phone (375px, also 320 and 414)

Branch `feature/office-mobile`. Moishe 2026-10-30: "the office dashboard is very, very not optimized for phone, a lot of things are overlapping." Phone = below `64em` (the existing Office breakpoint). Use existing tokens only (`tokens.css`, `office-tokens.css`); nothing new is proposed. Test at 320, 375 and 414, and on a real phone before calling it done.

Rules for every page: nothing overlaps, no horizontal scroll at 320 (`document.documentElement.scrollWidth` equals the viewport), tap targets at least 44px (`2.75rem`), one tap target per list card, every page has its title in the header.

## Root causes (fix these first, they explain most of the screenshots)

1. **Card in card.** `.o-card` (office.css) is loaded after office-lists.css with the same specificity, so the phone reset `.o-tablecard { padding: 0; background: none; box-shadow: none; ... }` loses. Raise it to `.o-card.o-tablecard` inside the `max-width: 63.99em` block.
2. **Hidden cells come back on even rows.** `.o-list tbody tr:nth-child(even) td { display: block; ... }` (0,2,3) beats `.o-row .c-action / .c-marketing / .c-lists { display: none }` (0,2,0). That is the garbled "View application" on rows 2 and 4 of Gold. Split the rule: `display: block` on `.o-list td` only, the zebra rule resets background only; write the hides as `.o-list .o-row td.c-x { display: none }`.
3. **`.o-hide-md` and `.o-hide-lg` are not defined anywhere.** So People's `c-sale` and `c-payment` render on phone with `order: 0`, before the name ("Not started  donut d…"). Give every phone cell an explicit order (below); hide what the card does not need.
4. **`.o-totalline` is `display: flex`.** Every text node, `<em>` and `<span>` inside it becomes its own flex item, which is the Invited hint breaking into orphan lines and the italics jumping. Text in a total line must sit in one `<span>`; long explanations move out (see Invited).
5. **`.u-truncate` is `display: block`.** Anything placed before it in the same cell sits on its own line (the Leads stray "·" above "localhost").

## 1. Bottom tab bar (base.html, office.css)

- **Five slots at most.** Phone tabs: Home (Dashboard), Leads, People, Gold, More. "More" holds Analytics, Chats, Invited (each only if the user may see it). If a user has five items or fewer in total, show them all and no More.
- Desktop rail is unchanged: all items, full labels.
- Template: keep the one `<ul class="o-nav-list">`. Add `data-nav-overflow` to the Analytics, Chats and Invited `<li>`. Add a last `<li class="o-nav-more">` with `<button type="button" data-nav-more aria-haspopup="dialog" aria-controls="nav-sheet">` (icon + "More"); give it `aria-current="page"` styling (class `is-current`) when `section` is analytics, chats or invited. Wrap the Dashboard label as `<span class="o-only-wide">Dashboard</span><span class="o-only-narrow">Home</span>` (the `o-only-*` helpers switch at 64em, which matches).
- Sheet: `<dialog class="o-sheet o-navsheet" id="nav-sheet" data-nav-sheet aria-label="More">` after the nav, listing the overflow links. Each row: `display: flex; align-items: center; gap: var(--space-3); min-height: 3.5rem; padding-inline: var(--space-3); border-radius: var(--office-radius)`, icon, label (`--text-base`, weight 500), chevron-right pushed right in `--office-muted`; current page row has `background: var(--office-sunken)`. Opens with `showModal()`, closes on backdrop tap, on a link tap and on Escape (native). Same entrance as the filter sheet (`modal-in`, `--office-dur-swap`, already 0 under reduced motion). JS in office-ui.js, next to the filter sheet code.
- CSS (phone block): `.o-nav-list li[data-nav-overflow] { display: none }` only when `.o-nav-more` exists (`.o-nav-list:has(.o-nav-more) li[data-nav-overflow]`); `.o-nav-more { display: none }` from 64em. Grid stays `grid-auto-columns: minmax(0, 1fr)`; `li { min-width: 0 }`.
- Labels never overlap: `white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%` on the label span, `--office-text-xs`, weight 600. With five slots at 320 each slot is 64px; the active icon pill `padding: 4px 16px` (56px) still fits.
- Badge fully visible: `left: calc(50% + 0.5rem); top: 0.375rem`; the `<a>` keeps `overflow: visible`. Check at 320 that the Gold badge with "12" is inside the screen.
- Icons: Leads, Invited and Chats all use `envelope` today. Add to `_icons.html`, same 24px stroke style: `i-more` (three dots), `i-chat` (speech bubble). Leads keeps `envelope`, Invited uses the existing `person-plus`, Chats `chat`.
- Safe area: the existing `padding-bottom: env(safe-area-inset-bottom)` stays; the sheet already pads with it.

## 2. List pages: rows are the cards, straight on the page (People, Leads, Gold, Invited, Chats)

Pick: **one surface card per row on the page background**, no outer card (root cause 1).

- Row card: `padding: var(--space-3)`, `margin-bottom: var(--space-2)`, `border-radius: var(--office-radius-lg)`, `box-shadow: var(--office-shadow-1)` (as now). Press feedback: `.o-row:active { transform: scale(0.99) }` under `prefers-reduced-motion: no-preference`, `transition: transform var(--office-dur-lift) var(--ease-soft)`.
- One anatomy for every list, top to bottom:
  1. **Title line**: the main name, `--text-base`, weight 600, `flex: 0 0 100%`, ellipsis only when it fills the whole line. Optional pill (status, business badge) may sit at the right of this line only on Leads and Gold, `flex: none`.
  2. **Second line**: email or the second identifier, `--text-sm`, `--office-muted`, `flex: 0 0 100%`.
  3. **Badges line** (Leads, Gold): pills with `gap: var(--space-2)`.
  4. **Meta line**: `--text-sm`, `--office-muted`, items separated by `gap: var(--space-1) var(--space-3)` (no "·" characters), the date last with `margin-left: auto`.
- No link, button or "View" text inside a card on phone except the card link itself (`.o-rowlink::after` covers the row).

### People (`_people_rows.html`)
- Order: `c-name` 1 (full width), `c-email` 2, `c-plan` 3, `c-verified` 4, `c-payment` 5, `c-date` 9 (margin-left auto). Hidden on phone: `c-marketing`, `c-sale`, `c-journey`, `c-action`.
- `c-gold`: on phone show "Gold" as a non-link pill (`.o-badge--s-approved`, `pointer-events: none` on `.o-goldlink`), order 6, so the card has one target. The Gold application is one tap away on the person page.
- Export CSV: move into the filter sheet on phone like Leads (`o-export--bar` / `o-export--sheet`, the classes exist in office-leads.css).

### Gold (`_gold_rows.html`)
- Order: `c-name` 1 (name, then the business badge wraps under it if needed), `c-potential` 3 and `c-status` 3 on the badges line, `c-invite` 5 full width, `c-date` 9.
- `c-action` (`.o-row-go`, "View application") hidden on phone, via the fixed selector from root cause 2. No chevron: every list card behaves the same.

### Leads (`_leads_rows.html`, office-leads.css)
- Keep the current order. Fix the source: `.o-list--leads .o-row td.c-source .u-truncate { display: inline }` so it reads "Seen yesterday · localhost" on one line, ellipsis at the end. Keep the `o-only-narrow` "·" span (it now sits inline).
- Summary tiles (`.o-leadsum`) at 320: below `24em` set tile `padding: var(--space-2) var(--space-3)` and the label to `--office-text-xs`, so "Registered" fits a third of 280px.

### Invited (`invited.html`, `_invited_rows.html`)
- Header title "Invited" (section 5).
- The hint, replace the whole `<p class="o-totalline" data-region="invited-total">` text with:
  - `<p class="o-sub">Invited by email, no account yet.</p>`
  - `<details class="o-hint"><summary class="o-quiet">How to read this</summary><p class="o-sub">Clicked the link means he used his personal link. Opened email is known only for invites sent after tracking began, and Apple Mail marks every email as opened.</p></details>` (summary `min-height: 2.75rem`; no italics).
  - Then the `o-totalline` keeps only Clear, "Invite again from System > Groups", Apply, Export.
- Row: `c-name` 1, `c-email` 2, meta line `c-clicked` 3, `c-opened` 4, `c-expired` 5, `c-date` 9. Shorter narrow labels: "Clicked: No", "Opened: 28 Oct" (use `|dm`), "Expired: No".

### Chats (`chats.html`)
- Header title "Chats" (section 5). Intro: `<p class="o-sub">Chats with the assistant, newest first. Kept for 90 days.</p>` (one span, not inside the flex total line). "View only" is obvious; drop it.
- Template: move `o-rowlink` from the date to the question (better link name); give the cells classes: `c-date`, `c-question`, `c-who`, `c-count num`, `c-cost num`, `c-note`.
- Phone card: `c-question` order 1, full width, `--text-base` weight 600, two-line clamp (it already uses `lines=2`); meta line `c-who` 2, `c-count` 3 as "1 message" / "6 messages" (narrow-only " message{{ pluralize }}" after the number), `c-cost` 4; `c-note` 5 as a quiet pill (`.o-badge--p-low`), hidden when empty (`td:empty { display: none }`); `c-date` 9, margin-left auto, short form on phone (`|dm` plus time, e.g. "29 Oct, 11:21").
- `chat_detail.html`: set `data-office-detail`, put the back link in the header (`header_left`: `o-back` "Chats", like person.html) and drop the in-page "Chats" link; move the inline `style=""` on `.o-chat` to office-lists.css.

## 3. Filter sheet (all list pages)

- Inside `.o-sheet`, segmented controls become wrapping chips (choosing, not filling in): `.o-sheet .o-seg { display: flex; flex-wrap: wrap; gap: var(--space-2); padding: 0; background: none }`, `.o-sheet .o-seg-thumb { display: none }`, `.o-sheet .o-seg-item { min-height: 2.75rem; padding-inline: var(--space-3); border-radius: var(--office-pill); background: var(--office-sunken) }`, checked: `background: var(--office-text); color: var(--color-cream)`. This fixes Invited's five-option control overflowing at 320.
- Sheet: `max-height: 85dvh; overflow-y: auto; overscroll-behavior: contain`; the "Show results" button `position: sticky; bottom: 0` with the surface behind it.
- Selects in the sheet are full width.

## 4. Dashboard

- `.o-card` padding below `48em`: `var(--space-4) var(--space-3)` (24px top/bottom, 16px sides). Applies everywhere in the Office.
- **Recent activity** (`.o-feed-row`, office-dashboard.css), below `48em`: grid `grid-template-columns: var(--office-feed-dot) minmax(0, 1fr); grid-template-areas: "dot text" ". when"; column-gap: var(--space-3)`. `.o-latest-when` goes under the text, left aligned, `--text-sm`, muted. `.o-feed-who` becomes its own line: `display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap`. `.o-feed-text` uses `overflow-wrap: break-word` (not `anywhere`), so emails no longer split mid-word.
- **What people want**: the Everyone/Leads control spans the card width under the title. Move the reserved space for the plus button from `.o-wants-head` to the `.o-h3` only (`padding-right: calc(2.75rem + var(--space-2))` on the title, 0 on the head). Plus button stays 44px.
- Rings at 320: fine as they are (they shrink with the column). Keep `.o-ring-line` at `--text-sm`; check that no ring label goes past three lines at 320.
- Hot leads and Latest rows: same rule as the feed, the time goes under the text below `48em` if it squeezes the name.

## 5. Header titles (base.html)

- Every page has a title. Add `chats` → "Chats" and `invited` → "Invited" to the title chain in `header_left` (better: a `{% block header_title %}` each page fills, with the chain as the default).
- Detail pages (person, lead, Gold application, chat) keep the back link as the title.
- Header side padding: `padding-inline: max(var(--page-margin), env(safe-area-inset-left))` (landscape notch).

## 6. Analytics

- KPI cards (`.o-kpis`): two columns at 360px and up, card padding `var(--space-3)`; one column below `22.5em` (360px). The empty sparkline row ("." under "New in the last 30 days") must not take height when there is no line.
- Funnel (`office-charts.js`, `funnel.make`): when `narrow`, `barPercentage: 0.5`, `maxBarThickness: 24`, `minBarLength: 24`, so the steps read as slim pills, not ovals, and Registered is not a hairline. The label column (84px) stays.
- Legend chips and the hero chart are fine.

## 7. Person, lead and Gold application pages

- **Bug, high:** in `_chats_card.html` each chat link uses `.o-rowlink`, whose `::after` is `position: absolute; inset: 0` but the `<li>` is not positioned, so the overlay can cover the whole card or page and steal taps. Give `[data-chat-list] li { position: relative }` (and a little padding and min-height 2.75rem), or use a plain link class.
- `.o-detail-head h1` and `.o-person-name`: `overflow-wrap: break-word` instead of `anywhere` (long emails wrap at a boundary when they can).
- `.o-alert` (Said NO to business) below `48em`: `padding: var(--space-3) var(--space-4)`.
- Gold decision bar (`.o-bar`) at 320 with three actions (Send back, Decline, Approve): `flex-wrap: wrap`; when `.o-state` is present it takes its own line (`flex: 0 0 100%`) above the buttons; buttons keep `min-height: var(--control-h)`.
- The two-column person order (`display: contents` + order) stays; check the Chats card gets an order (add `[data-person-chats] { order: 8 }`, after journeys).

## 8. Touch details

- `.o-totalline .o-quiet` and `.o-error .o-quiet` are 2rem tall: `min-height: 2.75rem` under `(pointer: coarse)`.
- `.o-seg--sm .o-seg-item` (2rem): `min-height: 2.75rem` under `(pointer: coarse)`.
- `.o-menu-item:hover` underline goes inside `@media (hover: hover) and (pointer: fine)`.

## Order of work

1. Root causes 1 to 5. 2. Tab bar and More sheet. 3. Header titles. 4. People, Gold, Leads, Invited, Chats cards. 5. Chats card overlay bug on person pages. 6. Filter sheet chips. 7. Dashboard feed and padding. 8. Analytics KPIs and funnel. 9. Touch details. Then screenshots at 320, 375, 414 and 1440 (desktop must not change), and tests still green.
