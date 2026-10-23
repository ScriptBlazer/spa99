# Spa 99: Gold Card application (round 5)

For the frontend agent. Date 2026-10-23. Owner: "the register interest form is now really nice, but the Gold Card application form (/gold-card/apply/) still looks dated and not nice." Redesign the **look** only, so it reads as the register page's premium sibling and belongs to the Gold Card page he likes. Same steps, fields, logic, endpoints and wording. `docs/BRAND.md` wins on any conflict. Motion is BRAND **7B (restrained)**: CSS and `reveal.js`, no GSAP, no three.js.

Design read: **the private room**. Register is the arrival desk (espresso stage left, raised cream panel right). The Gold application is the room behind it: the whole page stays espresso like the Gold Card page; the stage on the left holds the **Gold Card itself** (the still, resting in a soft glow) and a **ledger** of the three parts; the form sits on a raised panel in the colour of **the back of the card** (`--color-gold-deep`, the G2 "What it holds" panel) with the card's inset gold border, and a gold line along its top edge that fills as he goes. Same building, same bones as register, but gold and after hours. Dials: variance 5, motion 3, density 3.

Screenshots: the sandbox blocks localhost, so this is written from the code. The frontend agent takes the shots in section 10.

Files: `pages/templates/pages/gold_apply.html`, `common/static/common/js/gold-apply.js` (one attribute, section 4), `common/static/common/css/journey.css` (new block at the end, section 8). Nothing in `tokens.css`, `pages.css` or `components.css`.

---

## 1. Why it reads as dated today, and what must stay

1. A bare espresso page: a 2px bar at the top edge, a heading on the left, questions floating on the right. No object, no picture, no texture. The Gold Card page has a floating card, an engraved panel, glow; the application drops all of it the moment he presses Apply.
2. No surface. Seven questions on screen 1 sit straight on the background, so it reads as a long questionnaire, not a quiet exchange.
3. Fields are transparent boxes with a thin line on espresso and the label above (`--s-field: transparent`). Register has moved on to label-inside wells; the two forms now look a generation apart.
4. The progress is a hairline across the top of the window, far from the content. Nothing says "three parts" or names them.
5. The Property follow-ups appear as more questions of the same weight; nothing shows they belong to Property.
6. The sent screen is a glyph and two lines in the middle of nothing. No sense of arrival.

**What stays, untouched** (JS hooks and behaviour): `[data-journey]`, `data-flow="gold"`, `[data-flow-root]`, `[data-progress]` (`role="progressbar"`, `aria-label`, `aria-valuemin/max/now`, `aria-valuetext` set by JS), `[data-progress-fill]` with `--p`, `#gold-config`, the `.screen` / `.screen-head` / `.screen-title` / `.screen-body` / `.action-bar` structure, `data-reveal="hero"` on each screen, `data-live` (set by `settle()`), `[data-primary]`, `[data-back]`, `[data-change-visits]`, `data-working-text="Sending"`, `[data-g]`, `[data-jq]`, `[data-group]`, `[data-sub="industry_other"]`, `[data-error-slot]`, `[data-error-for]`, `data-state`, all markup from `choices.js` (`.tiles`, `.tile`, `.tile-multi`, `.tile-company`, `.segmented`, `.seg`, `.tile-mark`), field names and order (`FIELDS`), every heading, lead, legend, label, hint, error and button text, sessionStorage keys, slugs and URLs, endpoints (`GET /gold/options/`, `GET /journey/state/`, `POST /journey/answer/`, `POST /gold/apply/`), the noscript line, the loading line "One moment".

Behaviour notes the look must respect (from the code, not new):
- Screen 1 "About you." order: What do you do? (industry, required) · the Other text (only when Other) · Your link to property and How large? (only when Property) · Where? · Do you work with BML? · Company and role · Referred by. Values of hidden follow-ups are kept and come back if he switches back.
- Screen 2 "Your visits.": either the "From your earlier answers" summary with **Change**, or the journey's own visit questions (time, frequency, facilities, company). Single-choice visit tiles (`data-jq`) can be tapped again to clear; the Gold tiles (`data-g`) cannot. "How did you hear about us?" is **not** asked here (not in `VISIT_KEYS`), so nothing to style for it.
- Screen 3 "You.": first and last name, email, mobile, Anything else?, privacy (required), news opt-in, Send application.
- Observation for the reviewer, out of scope for this brief: the feature doc lists a `website` honeypot, but `gold-apply.js` neither renders nor sends one. The redesign neither adds nor removes it.

---

## 2. Layout

### 2.1 Desktop 1440 x 800 (from 64em)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ reduced header (lockup, Leave)                                     72px      │
├────────────────────────────────┬─────────────────────────────────────────────┤
│ espresso, soft gold glow       │  espresso + faint gold swan pattern         │
│                                │   ╭━━━━━━━━━━━━━━░░░░░░░░░░░░░░░░░░░░╮       │ ← gold progress line on the top edge
│     ╭──────────────────╮       │   │ ┌─ inset gold border ───────────┐ │       │
│     │  ≈ GOLD CARD ≈   │       │   │ │ About you.                    │ │       │   the back of the card
│     │   (the still)    │       │   │ │ A few taps, so we know you.   │ │       │   (--color-gold-deep)
│     ╰──────────────────╯       │   │ │ ── What do you do?            │ │       │
│                                │   │ │ [Property   ] [Finance     ]  │ │       │
│ APPLY FOR THE GOLD CARD        │   │ │ [Business o.] [Law         ]  │ │       │
│                                │   │ │ [Medical    ] [Tech        ]  │ │       │
│ (1) About you                  │   │ │ [Creative   ] [Other       ]  │ │       │
│  │                             │   │ │ ┃ Your link to property       │ │       │   follow-ups on a gold thread
│ (2) Your visits                │   │ │ ┃ [Owner / investor] [Dev…]   │ │       │
│  │                             │   │ │ ...  (panel scrolls, stage stays)│      │
│ (3) You                        │   │ │ ───────────────────────────── │ │       │
│                                │   │ │ Back            [Continue  →] │ │       │
│ Free. No account needed.       │   │ └───────────────────────────────┘ │       │
└────────────────────────────────┴───╰───────────────────────────────────╯─────┘
```

Template (the JS still renders only inside `[data-flow-root]`):

```
.journey.gold-flow.gold-apply.on-dark [data-journey data-flow="gold"]
  .container  → messages (unchanged)
  .container.grid.gold-apply-grid
    aside.gold-apply-stage                (server-rendered, decoration + reassurance)
      .gold-apply-card  (photo "gold-card", alt "", data-reveal="hero-image")
      .gold-apply-stage-copy (data-reveal="hero"): label, ledger, note
    .gold-apply-panel
      .progress [data-progress] … (moved here, attributes unchanged)
      .flow-col [data-flow-root] (unchanged)
  noscript (unchanged)
```

- `.gold-apply` keeps `.on-dark` (espresso). `min-height: calc(100dvh - var(--header-h))` as today. `html:has(.gold-apply) { scroll-padding-top: calc(var(--header-h) + var(--space-4)); }`
- **Texture**: `.gold-apply::before`, columns 6 to 12 only (`left: 45%` from 64em, as register), `background: url("../img/swan-pattern.svg")` (gold at 8% on espresso, as `.gold-panel`), opacity 0.6, static, `pointer-events: none`, `z-index: -1` (the section gets `isolation: isolate`).
- **Stage** (`.gold-apply-stage`): columns 1 to 5. `position: sticky; top: var(--header-h); height: calc(100svh - var(--header-h)); align-self: start` only under `@media (min-width: 64em) and (min-height: 42em)` (the register rule); otherwise a normal block. Flex column, `justify-content: center`, padding `var(--space-5) var(--space-5) var(--space-5) 0`. Behind the card a static glow: `background: radial-gradient(50% 40% at 40% 32%, var(--color-glow), transparent 70%)` on the stage. No pointer light.
- **Card** (`.gold-apply-card`): the existing `gold-card` still (1280 x 960, the card on espresso), `{% photo "gold-card" alt="" sizes="(min-width: 64em) 30vw, 8rem" eager=True %}`. Box `height: var(--register-photo-h)` (280px at 800 tall), `aspect-ratio: 4 / 3`, `max-width: 100%`, image `object-fit: contain`. Edge melt so the image's own espresso never shows a seam: `mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, #000 60%, transparent 100%)` (the card itself sits fully inside the opaque part). Static: no tilt, no 3D, no float loop.
- **Stage copy** (max width `--signin-w`), margin-top `--space-5`:
  | Part | Spec |
  |---|---|
  | Label | "Apply for the Gold Card" (existing page title; `gold` page `apply.heading`), `<p>`, Figtree `--text-sm` 500, uppercase, `--tracking-engraved`, `--color-gold-light` (8.58 on espresso). Not a heading |
  | Ledger | Section 4.2. margin-top `--space-5` |
  | Note | `gold` page `apply_note.body` ("Free. No account needed."), `{% page_content "gold" as g %}`, `--text-sm`, `--color-text-muted-inverse` (6.50), margin-top `--space-5`, a 1.5rem gold hairline before it (the `.gw-caption` motif). Omit if empty |
- **Panel** (`.gold-apply-panel`): columns 7 to 12, max width 40rem, margin-block `var(--space-6)`, padding `var(--space-6)` (64px). `position: relative; isolation: isolate`. Background `--color-gold-deep`, 1px `--color-tier-edge-gold`, `--radius-md`. The inset border is the card's: `::after { inset: 12px; border: 1px solid var(--color-tier-edge-gold); border-radius: calc(var(--radius-md) - 6px); pointer-events: none; z-index: 0 }` (same as `.gold-back`). Content sits above it (`z-index: 1`). No shadow (it does not read on espresso); depth comes from colour, border and inset line.
- Inside the panel the screen is **one column** at every size: override the 12-column `.screen` grid from journey.css (`.gold-apply .screen { display: flex; flex-direction: column; padding-top: 0 }`, `.gold-apply .screen-head { position: static }`, body and bar full width).
- Fit at 800 tall: 48 + 280 + 40 + label 20 + 40 + ledger 3 x 52 = 156 + 40 + note 22 + 48 = 694 against 728. At 1280 x 720 the card box shrinks to 200px (token clamp) and it still fits.

### 2.2 Tablet 48em to 64em

Stacked as the phone, with the stage row using a 10rem card, the panel max width 40rem, left aligned with the container, panel padding `--space-5`, inset `12px`.

### 2.3 Phone 375 x 812

```
 reduced header 64
 ┌────────┐ APPLY FOR THE GOLD CARD          stage row on espresso, no bleed
 │ ≈card≈ │ (1)──(2)──(3)                     ledger as three numerals
 └────────┘
╭━━━━━━━━━━━░░░░░░░░░░░░░░░░╮   ← panel rises 40px over the stage; gold line = progress
│ ┌ inset ─────────────────┐ │
│ │ About you.              │ │   h1 36px
│ │ A few taps, so we know  │ │
│ │ you.                    │ │
│ │ ── What do you do?      │ │
│ │ [Property ] [Finance  ] │ │   2 columns, 56px tiles
│ │ [Business ] [Law      ] │ │
│ │  owner                  │ │
│ │ [Medical  ] [Tech     ] │ │
│ │ [Creative ] [Other    ] │ │
│ │ ...                     │ │
├─┴─────────────────────────┴─┤
│ Back          [Continue  →] │   sticky bar, panel colour, safe area
└─────────────────────────────┘
```

- Stage: padding `var(--space-4) 0 calc(var(--space-4) + var(--panel-overlap))`. A row (`display: flex; gap: var(--space-3); align-items: center`): card box 7.5rem wide (`height: auto`, `aspect-ratio: 4 / 3`), then label (`--tracking-label` on phone, not engraved, so it fits on one or two lines) and the compact ledger (4.2) under it. The note is hidden on phone (it lives on the Gold Card page already).
- Panel: `margin-top: calc(var(--panel-overlap) * -1)`, full container width, padding `var(--space-4)` and `padding-bottom: 0` (the bar is its foot), inset `8px`.
- First screen at 375 x 812: 64 + 16 + 84 (card row) + 16 = 180, panel from 180 (overlap included): h1 at about 205, lead to 270, "What do you do?" at 310, four rows of 56 + 3 x 12 gaps = 260, ending about 600; the sticky bar sits at 740. All eight industry tiles and the bar are on the first screen. No horizontal scroll.

---

## 3. Fields and choices (inside the panel)

Surfaces: panel `--color-gold-deep`; every control sits in an **espresso well** (`--color-espresso`), a step darker, so it reads as set into the card. Text cream.

### 3.1 Screen head and questions
- `.screen-title`: Signika 400, `--text-2xl` (36px phone, 64px at 1440), cream, `--leading-tight`. Lead: `--text-base`, `--color-text-muted-inverse` (5.33 on gold-deep), margin-top `--space-2`, max width `--measure-lead`.
- Question legends and `.question-title` ("Company and role"): Signika 400 `--text-lg`, cream, preceded by a 1.5rem gold hairline (`::before`, 1px `--color-gold`; decoration), `display: flex; align-items: center; gap: var(--space-3)`. The register motif in gold.
- `.question-help` ("Units or properties"): `--text-sm` muted inverse, aligned under the legend text (padding-left 1.5rem + `--space-3`).
- Space between questions `--space-5` phone, `--space-6` desktop (was `--space-7`); controls `margin-top: var(--space-3)`. First question `--space-5` below the lead.

### 3.2 Choice tiles (single and multi)
| State | Spec |
|---|---|
| Rest | Background `--color-espresso`, 1px `--color-hairline-inverse`, `--radius-md`, cream label Figtree 500 `--text-base` (desktop `--text-base` too inside the panel, not `--text-lg`). Mark: 1.25rem ring, 1px `--color-control-line` (3.09 on espresso) |
| Hover (fine pointer) | border `--color-control-line`; scale 1.01 (existing) |
| Chosen | instant. Border `--color-gold` + `box-shadow: inset 0 0 0 1px var(--color-gold)` (2px, nothing moves), gold wash `--color-chosen-wash` over espresso, mark filled gold (dot for single, gold box with espresso check for multi). Label stays cream |
| Focus | `outline: 2px solid var(--color-gold); outline-offset: 3px` on the tile (`:has(input:focus-visible)`) |
| Cleared (re-tap, visit tiles only) | returns to rest instantly, no fade |
| Error (group) | when its `[data-error-slot]` is `data-state="error"`: every tile in the group gets a 1px `--color-danger-inverse` border (`.question:has([data-error-slot][data-state="error"]) .tile`); the message shows under the group with the warning icon, `--color-danger-inverse` (5.59 on gold-deep). Choosing any tile clears both (existing JS empties the slot) |
| Disabled | not used in this flow; if `aria-disabled` ever appears: opacity 1, border hairline, label muted inverse, no hover |

- Grids inside the panel: **industry** 2 columns at every width (override `.tiles--4`), tile height `--tile-compact-h` (56px), padding `var(--space-3) var(--space-4)`; labels may wrap ("Business owner" on phone) and the tile grows. **Property link** 1 column phone, 2 from 48em (existing `tiles--stack`). **Where?** 2 columns. **Visit tiles** 2 columns; **Company** 2 columns from 48em (override `tiles--1` inside the panel), tall tile as today with the gold swan glyphs.
- No tile is singled out. Property looks exactly like the other seven; nobody should feel "this isn't for me".

### 3.3 Segmented (How large?, Do you work with BML?, visit scales)
Track `--color-espresso` with 1px `--color-hairline-inverse` outside and between segments, `--radius-sm`, height `--control-h` (52px). Chosen segment: gold fill, espresso text (6.17), instant. Focus: 2px gold outline, offset -4px (existing). Hover (fine pointer, unchosen only): segment background `--color-espresso-raised` (cream 9.45), instant. Wrap rule unchanged (`segmented--wrap`).

### 3.4 The Other text and the Property follow-ups, revealing in place
- **Other** (`[data-sub="industry_other"]`): a well field (3.5) directly under the industry tiles, margin-top `--space-3`, label inside "{other_label} (optional)".
- **Property** (`property_link`, `size_range`): the two `.sub-question` blocks get a gold thread on the left: `padding-left: var(--space-4); border-left: 1px solid var(--color-thread)` (gold 45%, decoration), margin-top `--space-5`. Legends inside keep the type but **no** hairline (the thread replaces it). They read as part of "Property", not as new questions.
- Showing is the existing `@starting-style` rise (section 7); hiding is instant. The existing `revealFollowUp()` scroll stays.

### 3.5 Text fields: the register well, in the dark
Applies to every `.field` input and the textarea in the panel (Other, Company, Role, Referred by, First and last name, Email, Mobile, Anything else?).
| State | Spec |
|---|---|
| Rest | `min-height: var(--control-h-label)` (60px), background `--color-espresso`, no border except `border-bottom: 1px solid var(--color-control-line)` (3.09 on espresso), radius `var(--radius-sm) var(--radius-sm) 0 0`, cream text 16px, padding `1.5rem var(--space-3) 0.375rem` |
| Label | the real `<label>` inside the well top left, `position: absolute; top: 0.5rem; left: var(--space-3)`, `--text-sm` 500, `--color-text-muted-inverse` (6.50 on espresso). "(optional)" stays inside it. Never moves or shrinks; autofill-safe |
| Hover (fine pointer) | bottom border cream. Instant |
| Focus | `box-shadow: inset 0 -2px 0 var(--color-gold)` (6.17), label cream, `outline: none` on these inputs only. Instant |
| Valid | existing "Looks right" feedback line, muted inverse with the check |
| Error | `inset 0 -2px 0 var(--color-danger-inverse)`, label danger inverse (6.81 on the espresso well), feedback line in danger inverse (it sits on gold-deep: 5.59) |
| Textarea | same well, `min-height: 7.5rem`, padding-top 1.75rem |
- Hints ("A UK mobile, like 07123 456789.", "If someone suggested you apply.") stay as the feedback line under the well, `--text-sm` muted inverse, margin-top `--space-1`, min-height unchanged (no shift).
- Name pair side by side from 48em; Company and Role side by side from 48em.

### 3.6 Consents (screen 3): choosing, not ticking
The two `.check` labels become rows, as register: `min-height: var(--tile-min-h)` (72px), padding `var(--space-3) var(--space-4)`, background `--color-espresso`, 1px `--color-hairline-inverse`, `--radius-md`, `align-items: center`, gap between rows `--space-3`. Box 1.5rem, 1px `--color-control-line`; checked gold fill, espresso check, row border gold + inset 1px gold. Error (privacy): row border `--color-danger-inverse` 2px, message under the row. Focus: 2px gold outline on the row, offset 3px. The privacy notice link stays underlined cream.

### 3.7 "From your earlier answers" (screen 2 summary)
A small engraved card inside the panel: background `--color-espresso`, 1px `--color-tier-edge-gold`, `--radius-md`, padding `--space-4` (`--space-5` desktop). h2 stays Figtree 500 `--text-base`, muted inverse. Each line gets the 1.5rem gold hairline above it (the `.gb-fig` motif), cream `--text-base`, gap `--space-3`. **Change**: `.btn-quiet` cream, 44px tall, margin-top `--space-3`.

---

## 4. Progress

### 4.1 The gold line (the real progressbar)
The existing `[data-progress]` moves to the first child of the panel: `position: absolute; top: 0; left: var(--space-5); right: var(--space-5); height: 2px; z-index: 2`, track `--color-hairline-inverse`, fill gold (`--s-accent`), `transform: scaleX(var(--p))` from the left as today. It is the `.gold-panel` top line, now filling: 1/4 on About you, 1/2 on Your visits, 3/4 on You, full on Sent. All ARIA unchanged.

### 4.2 The ledger (decoration, `aria-hidden="true"`)
Server-rendered from `gold_config.copy.screen_N.heading` without the full stop ("About you", "Your visits", "You"). A list of three rows; one JS line drives it: in `updateProgress()`, `wrapper.dataset.step = String(current)` (4 when sent). CSS reads `.gold-apply[data-step="2"] …`.
- Desktop: rows `display: grid; grid-template-columns: 2rem 1fr; gap: var(--space-3); align-items: center`, height 52px. Numeral in a 2rem ring (1px `--color-control-line`), Signika 500 `--text-sm`. Name Figtree `--text-base`. A 1px thread joins the rings (`--color-hairline-inverse`), its gold overlay (`--color-thread`) `scaleY` 0 → 1 for parts done.
  - Upcoming: ring control line, numeral and name muted inverse (6.50).
  - Current: ring and numeral gold, name cream 500.
  - Done: ring filled gold with an espresso check (icon-check mask), name cream.
- Phone and tablet: numerals only, three 1.75rem rings in a row joined by a 1.5rem thread; same states. The panel heading names the part.

---

## 5. Buttons

- **Continue** (screens 1 and 2): `.btn.btn-primary` = gold, espresso label (6.17 on gold), `--control-h` 52px, min width 12rem, text "Continue" + arrow icon. **Send application** (screen 3): same button, `type="submit"`.
- **Back**: `.btn-quiet`, cream, 44px tall, left.
- **Bar**: desktop: static at the panel foot, after a 1px `--color-hairline-inverse` divider and `--space-5` above; `justify-content: space-between`; Back left, primary right (on screen 1 the primary sits right alone). Phone: sticky as today, but inside the panel: `margin-inline: calc(var(--space-4) * -1)`, padding `var(--space-3) var(--space-4) calc(var(--space-3) + env(safe-area-inset-bottom))`, background `--color-gold-deep`, border-top 1px `--color-hairline-inverse`, bottom corners `--radius-md`. It covers the inset line while stuck; that is fine.
- **Working** (send): label swaps to "Sending" (`setWorking`), `aria-busy="true"`, opacity 0.7, no spinner, no width change (min width holds it). On failure it returns to "Send application" and the existing message shows at the top.
- Hover scale 1.01 / press 0.99, 0.25s, fine pointer only for hover (existing `.btn`).

---

## 6. Sent and closed

- **Sent**: the ledger shows all three done; the gold line is full. The panel content (`.gold-sent`) centres vertically and horizontally, with `min-height: 24rem` on desktop: the swan glyph `.mark-glyph--lg` gold; h1 "Thank you." Signika 400 `--text-2xl` cream; lead (copy unchanged) muted inverse; the reference as an engraved line: `--text-sm` 500 uppercase, `--tracking-engraved`, `--color-gold-light` (7.04 on gold-deep), tabular numbers, a 1.5rem gold hairline either side (decoration). Then "Back to home" `.btn-quiet` cream.
- **The one flourish**: on arrival at Sent, one sheen crosses the stage card once (section 7). It says "the card is yours to apply for" without a word.
- **Closed** (stage switch off, or a 403): same layout, ledger hidden (`data-step` not set), the panel holds heading, lead and the gold "Back to home" button.
- **Loading** ("One moment"): inside the panel, muted inverse, panel `min-height: 20rem` so nothing jumps when the screen renders.
- **Boot failure** ("The application is not available just now…"): `.lead` cream inside the panel.

---

## 7. Motion (7B)

| What | How | Timing |
|---|---|---|
| Card still | `data-reveal="hero-image"`: opacity 0 → 1, scale 0.98 → 1, no travel | 1s (`--duration-reveal`), delay 0.1s, `--ease-soft` |
| Stage copy (label, ledger, note) | one group, `data-reveal="hero"`: opacity, rise `--rise` (8px phone, 12px desktop) | 0.8s (`--duration-hero`), `--ease-soft` |
| Each screen | existing `data-reveal="hero"` on `.screen` (the panel itself never animates, so a step change only fades the content) | 0.8s, rise `--rise` |
| Progress line | existing `scaleX` transition | 700ms (`--duration-slow`), `--ease-soft` |
| Ledger | ring and text states instant; the gold thread overlay `scaleY` 0 → 1 | 700ms, `--ease-soft` |
| Follow-ups (Other, Property) | existing `@starting-style` on `[data-live] .sub-question`: opacity 0 → 1, rise `--rise`; hiding instant | 700ms, `--ease-soft` |
| Tiles, segments, checks, fields | chosen, focus, error, cleared: instant. Press 0.99 / hover 1.01 on tiles and buttons | 250ms (`--duration-press`) |
| Sent sheen | `.gold-apply-card::after`, the `.gold-back` band (`linear-gradient(105deg, transparent 35%, var(--color-sheen) 50%, transparent 65%)`), `translateX(-110%)` → `110%`, once, when `data-step="4"`, clipped to the card box (`overflow: hidden`) | 1.6s, `--ease-soft` |
| Texture, glow, inset border | static | |

No pointer glow, no tilt, no parallax, no loops, no sideways text, no blur.

**Reduced motion / no JS:** everything visible at once; no rise, scale, thread fill or sheen (the 7B tokens go to 0; the `@starting-style` and sheen rules sit inside `prefers-reduced-motion: no-preference`; the scrolls already use `behavior: 'auto'`).

---

## 8. Tokens and where the CSS goes

**No new tokens, no new colours.** Uses: `--color-espresso`, `--color-gold`, `--color-gold-deep`, `--color-gold-light`, `--color-cream` (via `--color-text-inverse`), `--color-text-muted-inverse`, `--color-control-line`, `--color-hairline-inverse`, `--color-danger-inverse`, `--color-tier-edge-gold`, `--color-chosen-wash`, `--color-thread`, `--color-glow`, `--color-sheen`, `--radius-sm`, `--radius-md`, `--control-h`, `--control-h-label`, `--tile-min-h`, `--tile-compact-h`, `--signin-w`, `--measure-lead`, `--register-photo-h` (reused as the card box height), `--panel-overlap`, `--tracking-label`, `--tracking-engraved`, `--space-*`, `--ease-soft`, `--duration-hero`, `--duration-reveal`, `--delay-reveal`, `--duration-slow`, `--duration-press`, `--rise`.

One note for BRAND section 8 later (not now, another branch owns `tokens.css`): `--color-gold-deep` is commented "decoration only", but `.gold-back` and now this panel carry text on it. Ratios on `#5A3A26`: cream 8.98, gold 5.06, gold-light 7.04, muted inverse 5.33, danger inverse 5.59, caramel 3.27 (large text only), control line 2.53 (never a control edge on it; controls sit in espresso wells).

**Where:** append one block at the end of `common/static/common/css/journey.css`, headed `/* ---------- Gold application, round 5 (docs/design/GOLD-APPLY-ROUND5.md) ---------- */`. journey.css already owns the Gold application rules, it is not touched by the other branch, and it loads after components.css, so no import changes. Every selector is scoped under `.gold-apply` so the journey is unaffected. Remove nothing shared; the old `.gold-sent` and `.summary-panel` rules may stay (the new ones override under `.gold-apply`).

---

## 9. Accessibility

- Contrast (all measured): cream on gold-deep 8.98; muted inverse lead on gold-deep 5.33; cream on espresso wells and tiles 10.95; well label muted inverse on espresso 6.50; field edge control line on espresso 3.09; focus gold on espresso 6.17 and on gold-deep 5.06; chosen gold border on espresso 6.17; gold button label espresso on gold 6.17; danger inverse on gold-deep 5.59 and on espresso 6.81; engraved gold-light 8.58 (espresso) / 7.04 (gold-deep); ledger muted 6.50. Hairlines, threads, glow, pattern and inset border are decoration only.
- Focus visible on every control: tiles and consent rows 2px gold outline offset 3px; segments 2px gold inset; fields the 2px gold bottom edge; buttons and quiet links the existing gold focus ring (`--s-focus`). Moving to a new screen still focuses the h1 (`tabindex="-1"`, outline none on the heading only).
- Targets: tiles 56px or more, segments 52px, buttons 52px, Back / Change / Back to home 44px, consent rows 72px.
- Labels: every input keeps its real `<label>`; tile groups keep `fieldset` + `legend`; segmented keeps `role="radiogroup"` + `aria-labelledby`.
- Live regions: feedback and `[data-error-slot]` lines stay `aria-live="polite"`; the progressbar's `aria-valuetext` ("About you, part 1 of 3", "Sent") is the spoken progress. The ledger and card are `aria-hidden`.
- Reading order: stage (label, note) then the panel; on phone the stage row is above the panel, so the order matches the screen.
- 16px minimum on all inputs (no iOS zoom). `scroll-padding-top` keeps focused fields clear of the header and the sticky bar (`scroll-padding-bottom: calc(var(--bar-h) + var(--space-3))` on phone).

---

## 10. Acceptance checks

Shots in `.private/shots/gold-apply-r5/` at 375 x 812, 768 x 1024, 1280 x 720 and 1440 x 800: About you (nothing chosen), About you with Property chosen, with Other chosen, error (Continue with nothing chosen), Your visits (fresh and with the summary), You (empty, and with errors after Send), Sending, Sent, Closed.

1. 1440: espresso page; the stage shows the Gold Card still in a soft glow with no visible image edge, the engraved "Apply for the Gold Card", the three-part ledger and "Free. No account needed."; the gold-deep panel with the inset gold border sits right over a just-visible swan pattern. Scrolling screen 1 keeps the stage in place.
2. The gold line on the panel's top edge is 1/4, 1/2, 3/4 and full on the four screens; the ledger shows current, done and upcoming correctly, also after Back, browser Back and refresh on each slug.
3. 1280 x 720: the stage fits (card smaller); under 42em tall the stage scrolls with the page and nothing is cut off.
4. 375: card thumbnail, label and numeral ledger in one row; the panel overlaps the espresso; all eight industry tiles and the sticky bar on the first screen; no horizontal scroll; the bar respects the safe area.
5. Industry: eight equal tiles in two columns; Property looks like the others. Choosing is instant (gold edge, wash, dot). Property reveals "Your link to property" and "How large?" in place on a gold thread with one soft rise; choosing Finance hides them instantly; switching back restores the earlier answers. Other reveals its optional text well.
6. Continue with nothing chosen: "Choose the one closest to what you do." in danger inverse with the icon, the industry tiles edged in danger inverse, focus on the first tile; choosing clears it. Same for "Choose your link to property.".
7. Fields: label inside every well and always visible (also after autofill); focus shows a 2px gold bottom edge instantly; errors show the danger edge, label and message without layout shift.
8. Visits: the summary card with gold hairlines and Change; Change swaps in the visit questions; a chosen single visit tile clears when tapped again; Company tiles sit two across from 48em with their glyphs.
9. You: consent rows 72px, the whole row toggles; the privacy error marks the row; Send shows "Sending" without the button changing width; a server 400 for an early field returns to About you with the message, as today.
10. Sent: all ledger parts done, full gold line, engraved reference, one sheen across the card (none under reduced motion).
11. Nothing changed in behaviour: same requests to `/gold/options/`, `/journey/state/`, `/journey/answer/`, `/gold/apply/` with the same payload keys; slugs and sessionStorage unchanged; the only JS change is `wrapper.dataset.step`. Existing Gold tests pass.
12. Keyboard: tiles, segments, fields, consents, Back, Continue reachable in reading order with a visible focus indicator; Space and arrows work on tiles and segments.
13. Reduced motion: everything visible at once; no rise, scale, thread fill or sheen.
14. No new colours or tokens, no em dashes or exclamation marks in new copy, only `transform` and `opacity` animate, journey pages unchanged (spot-check `/journey/` at 375 and 1440). Lighthouse accessibility 100, CLS under 0.1 (the card box is sized before the image loads).
