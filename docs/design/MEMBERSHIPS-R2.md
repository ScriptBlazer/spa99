# Spa 99: Memberships, round 2 ("the key cards")

For the frontend agent. Date 2026-10-22. Responds to Moishe (decisions log, last row): "Memberships page is much much better but still missing elegance. Try light drop shadow, maybe thinner, taller. Don't know what still feels off, generic, not wow."

This file **wins over `MEMBERSHIPS-PAGE.md` sections 1, 2.1, 3 (visual states only), 4, 5, 6 and 8** where they differ. Kept unchanged from that spec: the data (section 2.2, 2.3, 7), the radio-group semantics and keyboard (section 3), preselect order, compare table data and the phone picker, the copy (section 10), no GSAP on this page. `docs/BRAND.md` wins on any conflict; the two BRAND amendments this needs are in section 9.

Design read: a jeweller's display on a cream counter. Three slim objects standing apart on the cream, a small tag beside them that says what you picked. Dials: variance 6 (was 5), motion 3, density 3 (was 5).

**No backend change.** Same context (`tiers`, `single`, `table`, `cards`, `selected_slug`, `m.*`), same fields. Pills data (`t.pills`) is shown as a fine list instead of chips. One optional font build step (section 4.4).

---

## 1. What makes the current page generic (from the screenshots at 375, 1440, 1920)

Most important first.

1. **It is a SaaS pricing table.** Three equal, wide, landscape boxes (416 × 464 at 1440) filling the container edge to edge, then a full-width bar, then two more boxes. Every pricing page on the internet has this shape. Nothing about it is an object you would want to hold.
2. **Boxes everywhere, outlined in a form-field line.** Five bordered boxes on the first screen, all in `--color-control-line` (the field border). Borders say "input", not "luxury". There is no depth: the cream is flat, the boxes are flat, only the selected one has one blob of shadow.
3. **The picture is a thumbnail inside a card.** A letterbox strip inset by 16px of padding, with its own radius: a card inside a card. It reads as "image slot", not as the room.
4. **Thirteen chips.** 3 to 5 bordered pills per column, ragged wrap, same weight as the price. They look like filter tags on a shopping site and make each column busy at the bottom.
5. **The weight is all 500.** Name, price and visits are all Signika 500, all large; "£299" is the loudest thing on the page, three times. No single typographic idea leads. The difference between tiers (6, 8, unlimited visits; when you can come) is buried under the price.
6. **Selected is a slab.** The whole column turns into a dark brown block. Binary, heavy, and it makes Tier 2 look like an ad.
7. **The Continue bar is a cookie banner.** A full-width brown slab with radius under everything, repeating what the selected column already says.
8. **The header area is a split header**: title left, a quiet link floating far right with nothing aligned to it.
9. **Phone**: a small square thumbnail beside the name, three chips stacked like buttons, and a heavy brown sticky slab that covers a third of the second card.

What is right and stays: cream page, Tier 2 preselected, whole column is the choice, one Continue, compare closed, the copy.

---

## 2. The direction in one sentence

**Three slim, tall key cards stand apart on the cream like objects in a jeweller's case, each with its room filling the top and fading into the card, one huge thin numeral (6, 8, ∞) as the idea, a fine list instead of chips, and a small tag beside them that holds your choice and the one Continue; the chosen card turns espresso with a hairline gold edge, rises a few pixels on a softer, deeper shadow, and a slow band of light passes over it once.**

It is the Gold Card's family (a real card, a thin gold edge, one sheen), at a quieter volume.

---

## 3. Layout

### 3.1 Desktop 1440×800 (from 80em)

```
 header 72 (unchanged, solid espresso)
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                           │
│  Memberships.                  ┌────────┐      ┏━━━━━━━━┓      ┌────────┐                 │
│  Choose when you come          │ room   │      ┃ room   ┃      │ room   │                 │
│  and how often.                │ fading │      ┃ fading ┃      │ fading │                 │
│  Not sure? Tailor your  →      │        │      ┃        ┃      │        │                 │
│                                │ Tier 1 o│     ┃ Tier 2 ●┃     │ Tier 3 o│                │
│                                │ 6       │     ┃ 8       ┃     │ ∞       │                │
│                                │ ─────   │     ┃ ─────   ┃     │ ─────   │                │
│  Your choice                   │ facts   │     ┃ facts   ┃     │ facts   │                │
│  Tier 2                        │         │     ┃         ┃     │         │                │
│  £399 a month, ex VAT          │ £299    │     ┃ £399    ┃     │ £499    │                │
│  £478.80 inc VAT               └────────┘      ┗━━━━━━━━┛      └────────┘                 │
│  [   Continue   ]                                                                         │
│  Register your interest. Nothing to pay now.                                              │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- **The choosing section** (`.mem-stage`) is one screen: `min-height: calc(100svh - var(--header-h))`, content centred vertically, padding-block `--space-5` minimum. Inside the container (1312 at 1440 and at 1920).
- Grid: `grid-template-columns: var(--tier-tag-w) minmax(0, 1fr)`, column gap `--space-6` (64) minimum. Left: **the tag** (`.mem-tag`, 18rem / 288px). Right: **the case** (`.tiers`), three cards, `justify-content: end`.
- Cards: `--tier-w` 18rem (288) wide, `--tier-h` tall, gap `--tier-gap` (2.5rem, 40). 3 × 288 + 2 × 40 = 944. 288 tag + 944 cards = 1232, leaving 80px between tag and case at 1440 and 1920.
- Card height `--tier-h: clamp(33rem, 100svh - 15rem, 37.5rem)`: **560 at 800 tall** (ratio 1 : 1.94), **600 at 1080 tall** (1 : 2.08), never under 528.
- The tag is a column the same height as the cards: its top group (title, lead, link) aligned to the card tops, its choice group (summary, Continue, note) aligned to the card bottoms (`display: grid; align-content: space-between`).

**Fit check 1440×800:** header 72 + stage 728. Cards 560 + selected lift 8 = 568, centred: 80 above, 80 below. Shadow of the selected card (section 5) needs about 48px below: it has 80. Continue's bottom edge ≈ 72 + 80 + 560 = 712. Nothing below the fold is needed to choose.

**1920×1080:** same composition, cards 600 tall, 304px of cream left and right of the container, 168px above and below the cards. This is the "breathing room" Moishe is missing: the cards never touch anything.

**What sits around them:** cream only. No border on the stage, no background panel, no rules. The space between cards (40) is a little less than one card's padding × 2, so the three read as one set; the 80 between tag and case is twice that, so the tag reads as separate.

### 3.2 Desktop 64em to 80em (1024 to 1279)

Tag and case do not fit side by side. The tag's top group goes above the cards as the intro (left aligned, no link on the right: the link sits under the lead). The cards share the width: `--tier-w: calc((100% - 2 * var(--tier-gap)) / 3)` (≈ 285 at 1024), same `--tier-h`. The tag's choice group sits under the cards as one inline row (no background, no radius): summary left, note and Continue right, top hairline `--color-hairline`. Not sticky (it is on screen at 1024×768: intro 140 + cards 528 + row 64 = 732 under a 72 header... if it is not, it is `position: sticky; bottom: 0` with the phone bar style, section 6.4).

### 3.3 Below the stage (all desktop)

Unboxed. Every border here goes.

- **Also row** (`.mem-also`): `border-top: 1px solid var(--color-hairline)`, padding-top `--space-4`, two columns (cols 1-6, 7-12) with **no card boxes**:
  - Single visit: 56px square picture (`--radius-sm`), then "Single visit" (Signika 500, `--text-lg`), "£99 a visit, ex VAT" and "£118.80 inc VAT" (`--text-sm`, muted, tabular), the hours fact as plain text (`--text-sm`, not a pill), and "Single visits open with booking." (`--text-sm`, muted).
  - Gold line: the swan mark 28px in espresso, the sentence and the quiet link. Same baseline as "Single visit".
- **Compare**: unchanged structure. Selected column style softens (section 5.5).
- VAT note as now.
- Gap between stage and also row: `--space-6`.

---

## 4. The key card (`.tier`)

### 4.1 Anatomy, desktop (288 × 560)

```
┌────────────────────────────┐  .tier  radius --radius-md (12), no padding at the top
│                            │
│   room picture, full bleed │  .tier-media  height 30% of the card (168 at 560, 180 at 600)
│   to the card edges, top   │  fades into the card colour over its lower 45%
│   corners follow the card  │
│▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│
│ Tier 2      Recommended  ● │  .tier-head  padding-inline 24. name | label + mark
│ Your evenings, too.        │  .tier-tagline
│                            │
│ 8  visits                  │  .tier-num  Signika 300, 4.5rem | "visits a month" beside
│    a month                 │
│ ──────────────────────     │  1px hairline, full inner width
│ Day and evening, 5am to 3am│  .tier-list  plain lines, no chips
│ Book up to 3 days ahead    │
│ 2 bookings at a time       │
│ Leil Shishi option         │
│                            │  (flexible space)
│ £399  a month, ex VAT      │  .tier-price  at the foot, like a price tag
│ £478.80 inc VAT            │
└────────────────────────────┘
```

Grid inside the card: `grid-template-rows: auto auto auto auto 1fr auto` (media, head, numeral, list, space, price). Padding: 0 at the top (media bleeds), `--space-4` (24) inline and bottom.

| Part | Spec (desktop) |
|---|---|
| `.tier-media` | `height: calc(var(--tier-h) * 0.3)`, full card width, no inset, no own radius (the card has `overflow: clip` and the radius). `object-fit: cover`, `object-position` from today's defaults. Fade: `::after` `inset: 0; background: linear-gradient(to bottom, transparent 55%, var(--tier-bg) 100%)` where `--tier-bg` is the card colour (switches instantly with selection). The head starts `--space-3` (16) below the image box, always on solid card colour: no text on the picture |
| `.tier-head` | One row: name left; right: "Recommended" (Tier 2 only) then the mark. Name Signika 500 `--text-lg` (20), `--tracking-display`. "Recommended": Figtree 500 `--text-sm`, **sentence case, no tracking**, `--color-text-muted` (unselected) / `--color-gold` (selected, 6.17:1). Mark 1.25rem circle, gap `--space-2` |
| `.tier-tagline` | Figtree `--text-sm`, `--leading-snug`, muted. Margin-top `--space-1` |
| `.tier-num` | Margin-top `--space-4`. The numeral: Signika **300**, `--tier-num-size` (4.5rem, 72px), `line-height: 0.85`, `letter-spacing: -0.04em`, tabular, keeps `data-count`. Beside it, baseline-aligned, gap `--space-2`: "visits" / "a month" on two lines, Figtree `--text-sm`, `--leading-snug`, muted. Tier 3: "∞" in the same style, the words "visits" / "any day" are wrong, so the side text is "Unlimited" / "visits" (section 4.4) |
| hairline | `::before` of `.tier-list`, 1px, `--color-hairline` (unselected) / `--color-hairline-inverse` (selected), full inner width, margin-block `--space-3` |
| `.tier-list` | The `t.pills` strings as a plain list (`<ul role="list">`, one `<li>` each). Figtree `--text-sm`, line-height 1.5, `--color-text` (unselected) / cream (selected), gap `0.375rem`. No borders, no bullets, no icons. Max 5 lines today |
| `.tier-price` | Bottom row. "£399" Signika **400**, `--text-xl` capped at 2rem (32px), tabular, `letter-spacing: -0.02em`; then "a month, ex VAT" `--text-sm` muted on the same baseline. Under it "£478.80 inc VAT", `--text-sm` muted, margin-top `--space-1` |

**Hierarchy, in reading order:** the room (picture), the numeral (what you get), then the details, then the price. The numeral is the only big thing on a card; the price is calm and exact at the foot, like a tag on a watch.

**Height check at 560:** media 168 + 16 + head 24 + tagline 20 + 24 + numeral 61 + 16 + 1 + 16 + list 5 × 21 + 4 × 6 = 129 + space ≥ 8 + price 32 + 4 + 20 + bottom 24 = **563** for Tier 3 (5 lines). Tier 3 is the only one at the limit; if it overflows by a few pixels, the list gap drops to `0.25rem` (not the type). At 600 there is 40px of air.

### 4.2 Unselected

- Background `--color-cream-raised` (#FBF9EC) on the cream page. Edge: `border: 1px solid var(--color-tier-edge)` (espresso 7%, decoration). The shadow, not the line, draws the card.
- Shadow `--shadow-tier` (section 7).
- Mark: 1.5px ring `--color-control-line` (3.79:1 on cream-raised, meets 3:1 for a UI part).
- Text espresso (11.71:1), muted `--color-text-muted` (5.69:1).

### 4.3 Selected (Tier 2 on arrival)

- Background `--color-espresso`; text cream (10.95:1), muted `--color-text-muted-inverse` (6.50:1).
- **Gold edge**: the same 1px border becomes `--color-tier-edge-gold` (gold 55%). Same width, nothing shifts. It is the Gold Card's edge line, at card scale.
- Mark: gold disc with the espresso check (as now).
- "Recommended" turns gold. Hairline turns `--color-hairline-inverse`.
- **Lift**: `transform: translateY(var(--tier-lift))` (−8px) and the shadow becomes `--shadow-tier-selected` (deep, warm, wide). The cream around it darkens softly, as if the card was lifted off the counter.
- **Sheen**: one band of light passes across the card once (section 6.2).
- Not colour only: the check, the gold edge, the lift and the native checked state all change.
- Colour, check, edge and label change **instantly** (BRAND 7B: a choice is acknowledged instantly). Only the lift and the shadow ease in (section 6).

### 4.4 Tier 3's numeral

`visits_count` is None for Tier 3. Show "∞" (U+221E). The self-hosted `signika-latin.woff2` is the Google latin subset, which does **not** contain U+221E, so the browser would fall back to a system font (wrong weight and shape). Frontend:

1. Re-subset Signika from the full Google variable font with U+221E added to the latin range (`pyftsubset`, keep the variable axes, `--flavor=woff2`), script in `tools/`, and add `U+221E` to the `@font-face` (no `unicode-range` today, so nothing else changes). Check the glyph exists in Signika first.
2. If Signika has no ∞: use the word **"All"** in the numeral style (Signika 300, same size), side text "visits" / "you like". Do not draw an SVG and do not use a system-font ∞.

Template: `{% if t.visits_count %}<span class="num" data-count>{{ t.visits_count }}</span>{% else %}<span aria-hidden="true">∞</span>{% endif %}`; the side text carries the meaning for screen readers ("8 visits a month", "Unlimited visits"): visually the numeral and side text are one phrase, so wrap both in one element and keep `aria-describedby` on the input pointing at it. Uses only existing fields.

### 4.5 Hover, press, focus

- **Hover** (fine pointer only, unselected cards): `translateY(var(--tier-hover-lift))` (−4px) and the hover shadow fades in (section 6). Cursor pointer. The picture inside does not zoom.
- Selected card on hover: no further lift (it is already up); nothing changes.
- **Press**: `translateY(-2px)` while `:active`, 120ms.
- **Focus** (`:has(input:focus-visible)`): `outline: 2px solid var(--color-focus); outline-offset: 4px;` (espresso on cream 10.95:1), radius follows the card. Selected and focused: same outline (espresso on cream, outside the card).

---

## 5. The tag (`.mem-tag`) and Continue

### 5.1 Desktop (from 80em)

Top group (aligned to card tops):
- `h1` "Memberships." Signika 500, `--text-2xl` marketing (48).
- Lead "Choose when you come and how often." Figtree `--text-body`, muted, `max-width: 16rem` (two lines), margin-top `--space-2`.
- "Not sure? Tailor your membership →" `.btn-quiet`, `--text-sm`, margin-top `--space-4`.

Choice group (aligned to card bottoms), the receipt for the choice:
- "Your choice", Figtree `--text-sm`, muted, sentence case.
- "Tier 2" (`data-summary-name`), Signika 400, `--text-xl` (36 at 1440), margin-top `--space-1`.
- "£399 a month, ex VAT" (`data-summary-price`) and on the next line "£478.80 inc VAT" (`data-summary-inc`), `--text-sm`, tabular; the first line espresso, the second muted.
- Continue: `.btn.btn-primary` (on cream: espresso, cream label, 10.95:1), full tag width (288), height `--control-h` (52), margin-top `--space-4`.
- "Register your interest. Nothing to pay now." `--text-sm`, muted, margin-top `--space-2`.

The tag is plain text on the cream: no box, no background, no border, no shadow. It is the only text column on the stage; the cards carry the pictures.

### 5.2 What goes

- The full-width `.continue-bar` slab on desktop (its markup becomes the tag's choice group; keep `data-summary-*` and `data-continue` hooks so `memberships.js` keeps working; the middle-dot join of price and inc goes, they are two lines).
- `.continue-inc::before` "·".

### 5.3 Phone and tablet (below 64em): the sticky tag

`position: sticky; bottom: 0`, inside the form (as now), z-index 20. Height `--bar-h` (4.5rem) + `env(safe-area-inset-bottom)`.
- Background `--color-cream-raised`, `border-top: 1px solid var(--color-hairline)`, shadow `--shadow-bar` (upward, very soft). **Not espresso**: on a cream page an espresso slab is the cookie-banner feel.
- Left: "Tier 2" Signika 500 `--text-base`, under it "£399 a month, ex VAT" `--text-sm` muted (inc VAT is on the card).
- Right: Continue, espresso primary, 52px, min-width 9rem.
- Bleeds to the screen edges (negative page margin as now), content inside the page margin.

---

## 6. Motion (BRAND 7B inside a marketing page; CSS only)

### 6.1 Table

| What | How | Timing |
|---|---|---|
| H1 | Line rise from its mask (as now) | `--duration-line`, `--ease-soft` |
| Lead, link, tag choice group | Fade up as the hero group (as now) | 0.8s, 150ms after the H1 starts |
| The three cards | **One group**, Fade up (no stagger) | `--duration-reveal`, `--delay-reveal`, rise `--rise` |
| Pictures | Settle `scale(1.04) → 1` inside `.tier-media` with the group (as now) | 1s, `--ease-soft` |
| Numerals | Count once with the group (existing `memberships.js`); ∞ / "All" does not count | 1.2s |
| Prices | Never move | |
| Selection: colour, check, gold edge, labels, tag text | **Instant** | 0 |
| Selection: lift −8px | `transform`, eases | `--duration-tier` 600ms, `--ease-soft` |
| Selection: deeper shadow | Opacity of the card's shadow layers (6.3) | 600ms, `--ease-soft` |
| Sheen | Once per selection, and once on the preselected card 400ms after the group reveal ends | 1.6s, `--ease-soft` |
| Hover lift −4px + hover shadow | `transform` + shadow-layer opacity, fine pointer only | 500ms, `--ease-soft` |
| Press | `translateY(-2px)` | 120ms |
| Sticky tag (phone) | Not animated | |

### 6.2 The sheen

`.tier::after`: `inset: 0` clipped by the card, `background: linear-gradient(105deg, transparent 35%, var(--color-sheen) 50%, transparent 65%)`, `transform: translateX(-110%)`, `pointer-events: none`. On `.tier:has(input:checked)::after` run `@keyframes tier-sheen { to { transform: translateX(110%); } }` once, 1.6s, `--ease-soft`, `animation-fill-mode: both`. A CSS animation starts each time the selector starts to match, so every new selection gets one pass, with no script. For the arrival pass, delay the first one: `.js .tiers:not(.is-visible) .tier::after { animation: none; }` (reveal.js adds `is-visible` to the group; the animation then starts with `animation-delay: 1.4s`, which is the reveal 1.1s + 0.3s). Opacity of the band is in the token: cream at 10% on espresso. Only on the selected (espresso) card; on cream it would be invisible anyway.

Never more than one band at a time, never loops, never on hover.

### 6.3 Shadows without animating `box-shadow`

BRAND allows only `transform` and `opacity` to animate. So each shadow state is its own layer:
- The card itself carries `--shadow-tier` (static, never transitions).
- `.tier::before` (behind the card content, `inset: 0`, `border-radius: inherit`, `z-index: -1` inside an `isolation: isolate` card, `pointer-events: none`) carries `--shadow-tier-hover`, opacity 0 → 1 on hover.
- A third layer for the selected shadow: `.tier-shadow` (an empty `<span class="tier-shadow" aria-hidden="true">` as the first child of the label), `position: absolute; inset: 0; border-radius: inherit; box-shadow: var(--shadow-tier-selected); opacity: 0;` → `1` when checked.
(If the frontend prefers, the hover layer can also live on a span; the sheen keeps `::after`.)

### 6.4 Reduced motion and no JS

Everything visible, final numbers, no lift transitions (the selected card still sits at −8px, it just does not travel), no sheen, no settle, no count. Without JS: no count, sheen still plays on selection (pure CSS) unless reduced motion.

---

## 7. Tokens (proposed additions, all derived, decoration only unless noted; add to `tokens.css` and BRAND section 8)

All shadows are espresso (hue 20°) at low opacity, never black, in three layers: a contact line, a near soft shadow, a far wide shadow. Negative spread keeps them under the card, so the cream around stays clean at the sides.

```css
/* Memberships round 2 (docs/design/MEMBERSHIPS-R2.md). Derived. */
--shadow-tier:
  0 1px 1px rgb(73 46 33 / 0.04),
  0 6px 12px -4px rgb(73 46 33 / 0.06),
  0 24px 44px -20px rgb(73 46 33 / 0.14);           /* derived: resting card on cream */
--shadow-tier-hover:
  0 2px 2px rgb(73 46 33 / 0.05),
  0 12px 20px -6px rgb(73 46 33 / 0.08),
  0 36px 64px -24px rgb(73 46 33 / 0.20);           /* derived: hover layer, faded in */
--shadow-tier-selected:
  0 2px 3px rgb(73 46 33 / 0.10),
  0 16px 28px -10px rgb(73 46 33 / 0.20),
  0 52px 88px -30px rgb(73 46 33 / 0.38);           /* derived: the lifted espresso card */
--shadow-bar: 0 -10px 28px -18px rgb(73 46 33 / 0.22); /* derived: phone sticky tag, upward */
--color-tier-edge: rgb(73 46 33 / 0.07);             /* derived: unselected card edge, decoration */
--color-tier-edge-gold: rgb(229 172 110 / 0.55);     /* derived: selected card edge (gold on espresso), decoration */
--color-sheen: rgb(245 242 216 / 0.10);              /* derived: one light band across the selected card */
--tier-w: 18rem;                                     /* derived: card width from 80em (288) */
--tier-h: clamp(33rem, 100svh - 15rem, 37.5rem);     /* derived: 560 at 800 tall, 600 at 1080 */
--tier-gap: 2.5rem;                                  /* derived: between cards */
--tier-tag-w: 18rem;                                 /* derived: the tag column */
--tier-num-size: 4.5rem;                             /* derived: the numeral (phone 3.5rem) */
--tier-lift: -8px;                                   /* derived: selected card */
--tier-hover-lift: -4px;                             /* derived */
--duration-tier: 600ms;                              /* derived: lift and shadow */
```

**Retire** (once nothing uses them): `--tier-media-h`, `--tier-media-s` (the picture height is now a share of the card), `--color-pill-line` on this page (check The spa page before deleting), the inline `box-shadow: 0 18px 36px -26px rgb(73 46 33 / 0.55)` raw values in `memberships.css` (raw values, not tokens). `--bar-h` stays (phone).

Reused: `--color-cream-raised`, `--color-espresso`, `--color-gold`, `--color-text-muted`, `--color-text-muted-inverse`, `--color-control-line`, `--color-hairline`, `--color-hairline-inverse`, `--color-focus`, `--radius-md`, `--radius-sm`, `--space-*`, `--ease-soft`, `--duration-line`, `--duration-reveal`, `--rise`.

**Contrast check (all text):** espresso on cream-raised 11.71, muted on cream-raised 5.69, cream on espresso 10.95, muted-inverse on espresso 6.50, gold "Recommended" on espresso 6.17, Continue cream on espresso 10.95, focus ring espresso on cream 10.95. The 72px numeral at weight 300 is espresso or cream (large text, ≥ 10.95). The sheen band at 10% cream raises espresso behind cream text by at most about 4% luminance, so cream text stays above 9:1 during the pass.

---

## 8. Phone, 375×667 (below 48em; tablet 48 to 64em the same, cards max-width 30rem, centred)

**Pattern: stacked key cards** (same reasons as round 1: no carousel). The card keeps its vertical anatomy, so phone and desktop are the same object.

```
 header 64
 Memberships.                       H1 32px
 Choose when you come and how often.
 Not sure? Tailor your membership →
┌─────────────────────────────────┐  card 335 wide
│ room picture, full bleed, fades │  9rem (144) tall
│▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│
│ Tier 1                       o  │
│ For the daytime regular.        │
│ 6  visits                       │  numeral 3.5rem (56)
│    a month                      │
│ ──────────────────────────────  │
│ Daytime, 5am to 6pm             │
│ Book up to 1 day ahead          │
│ 1 booking at a time             │
│ £299  a month, ex VAT           │
│ £358.80 inc VAT                 │
└─────────────────────────────────┘
        24 of cream
┌─────────────────────────────────┐  Tier 2, espresso, gold edge, sheen
...
 [sticky tag: Tier 2 / £399 a month, ex VAT        (Continue)]
```

- Page margin 20; cards full width (335), radius `--radius-md`, padding 0 at the top, `--space-4` (24) inline and bottom.
- Card height is content height on phone (no `--tier-h`). Picture 9rem. No `1fr` spacer: price follows the list after `--space-4`.
- Height ≈ 144 + 16 + 24 + 20 + 20 + 48 + 12 + 1 + 12 + list (3 to 5 lines, 63 to 129) + 24 + 56 + 24 ≈ **460 to 530**. Gap between cards `--space-4` (24): the shadows need it.
- Intro: padding-top `--space-4`; H1 32 + lead 2 lines + link: the first card's picture starts about 230px down, so the first room is on the first screen with its name.
- **No lift on phone** (`--tier-lift: 0` below 64em): selected = espresso, gold edge, `--shadow-tier-selected`, sheen once. Hover does not exist.
- Sticky tag as section 5.3. `scroll-padding-bottom: calc(var(--bar-h) + var(--space-3))` stays.
- Order Tier 1, 2, 3 (matches the compare table). Tier 2 preselected, so the sticky tag reads "Tier 2" on arrival.

---

## 9. BRAND amendments needed (propose; apply to `docs/BRAND.md` before build)

1. **7B Interaction feedback**: "Selectable cards that are tall objects (the Memberships key cards) lift 4px on hover and 2px on press instead of scale 1.01 / 0.99: scaling a tall card blurs its type. The selected card sits 8px up; its colour and check change instantly, the lift eases (0.6s)." 
2. **7B (one light band)**: "The selected Memberships card gets one light band across it on selection (1.6s, once, CSS). Same family as the Gold Card sheen. Not on hover, never looping, off under reduced motion." (BRAND 7 bans sideways travel of text; the band is not text.)
3. Section 8: the tokens in section 7 above.

---

## 10. What to remove (checklist for the frontend)

- [ ] `.pill`, `.pill--quiet`, `.pills` inside `.tier` (data now renders as `.tier-list`).
- [ ] All `border: 1px solid var(--color-control-line)` on `.tier`, `.plan-aside`, `.gold-aside`.
- [ ] The inset picture box (`.tier-media` with padding around it and its own radius); the phone thumbnail layout (`grid-template-columns: var(--tier-media-s) ...`).
- [ ] `.tier-visits` and its `::before` 24px rule; visits become `.tier-num`.
- [ ] The uppercase `.label` on "Recommended" (sentence case, no tracking). This brings the page to zero uppercase labels.
- [ ] The desktop `.continue-bar` slab and its raw shadow; the espresso phone bar (`on-dark`) becomes the cream sticky tag.
- [ ] The split header (`.mem-intro-inner` two columns with the link far right).
- [ ] `transform: scale(1.01)` / `scale(0.99)` on `.tier`.
- [ ] Compare: `.compare-table .is-selected { background: var(--color-espresso) }`. New: `background: var(--color-cream-raised)`, values Figtree 600 espresso, header cell with the check icon in espresso; one 2px espresso line on top of the selected header cell. A light column, not a brown block.

## 11. Template changes (no backend)

- `memberships.html`: wrap intro + form in `.mem-stage` (grid: `.mem-tag` | `.tiers`). The tag's top group is the current intro markup; its choice group is the current `.continue-bar` markup (hooks unchanged). The form must contain both the radios and the Continue: make `.mem-stage` the `<form>` itself (or put the form around the stage), so the tag sits inside the form.
- Per card: add `<span class="tier-shadow" aria-hidden="true"></span>` first; `.tier-num` replaces `.tier-visits`; `{% for p in t.pills %}` renders `<li>` in `<ul class="tier-list" role="list">` instead of pills; the price group moves to the end.
- The single visit's hours pill renders as plain text.
- `memberships.js`: no change needed beyond the counter selector if `data-count` moves (it stays on the numeral).

## 12. Acceptance (screenshots at 375×667, 1440×800, 1920×1080)

1. 1440×800: the three cards, the tag and Continue are fully visible; nothing touches the header or the fold; the selected card's shadow is not cut off.
2. Cards are portrait, about 1 : 2. No border on any card stronger than 7% espresso; at 1440 the eye finds the edges by the shadow.
3. One big type idea per card (the numeral); prices are smaller than numerals.
4. No chip, no uppercase label, no full-width bar anywhere on the first screen.
5. Clicking Tier 1: it turns espresso with the gold edge and check in the same frame; it rises over 0.6s; one band of light passes; Tier 2 drops back to cream; the tag says "Tier 1".
6. Keyboard: Tab lands on Tier 2, arrows change the choice (same visual as click), Tab goes to Continue; focus ring visible on cream.
7. Reduced motion: no travel, no band, no count; the selected card is still up and espresso.
8. 375: first room visible on arrival; the sticky tag is cream, not a brown slab; no card is hidden under it when focused.
