# Spa 99: Memberships page (choose a tier, one Continue)

For the frontend and backend agents. Date 2026-10-22. Replaces the current `pages/memberships.html` and `_plan_row.html` layout (cream page, wide horizontal rows, a button per plan), which Moishe called "still ugly".

Binding input (PROJECT decisions log, 2026-10-22): tiers as tall columns side by side, the whole column selectable, one single Continue for the chosen tier; compare stays, compact; compact sections (content height); much more information, pills, small image boxes like the "Escape the Everyday" ad; small neat text, not overdone. `docs/BRAND.md` wins on any conflict. Rule IDs kept: GEN-01 (ex VAT, with inc VAT), MEM-01 (no discounts or packages: nothing on this page suggests one), MEM-03 (aim: most pick Tier 2).

Design read: a quiet choosing screen inside the dark editorial house of Home. Dials: variance 5, motion 3, density 5.

---

## 0. Decisions in one table

| Question | Decision | Why |
|---|---|---|
| Page colour | **Espresso**, the whole page (header solid on espresso) | Same building as Home, which Moishe likes. The selected state can be gold (gold on espresso-raised 5.32:1). On cream, gold is decoration only (1.78:1) and the selected ring would have to be espresso |
| Preselect | **Yes: the `highlight` plan (Tier 2)**, unless the visit says otherwise (order below) | MEM-03. Continue works from first paint, and the sticky bar never shows an empty state. Moishe to confirm (question 1) |
| Preselect order | 1. `?plan=<slug>` if that plan is `interest_allowed`. 2. The signed-in person's current interest. 3. The `highlight` plan. 4. Nothing | Arriving from the journey result or the account page keeps the man's own choice |
| Desktop | Three tall columns side by side, then the Continue bar. All of it fits 1440×800 | Moishe's words |
| Phone | **Stacked selectable cards**, not a carousel | Section 5 |
| Single visit | A small separate card under the Continue bar, not in the radio group | `interest_allowed` is false for it; it opens with booking |
| Intro image tile | **None** | The three columns already carry three pictures; a fourth above them is clutter and costs fold height |
| Library | **No GSAP on this page.** CSS and the shared `reveal.js` only, plus a small `memberships.js` | It is a form (BRAND 7B). One-line heading, so the line rise is CSS |

---

## 1. Page structure (top to bottom)

All sections content height. Container `--container-max`, margins `--page-margin`, 12-column grid with `--gutter` (as Home).

1. **Intro** (`.mem-intro`). Left: `h1` "Memberships." (`--text-2xl` marketing scale, 48px at 1440, 32px phone, Signika 500, cream). Under it one line (`memberships.intro.body`, Figtree `--text-body`, `--color-text-muted-inverse`): "Choose when you come and how often." Right (desktop, bottom-aligned with the lead; phone: under the lead): quiet link "Not sure? Tailor your membership" with the arrow icon → `/journey/` (`.btn-quiet`, cream, from `memberships.not_sure`).
2. **The choice** (`<form class="tier-form" method="get" action="/register/">`).
   - `<fieldset class="tiers">` with a visually hidden `<legend>` "Choose your membership".
   - Three columns (`.tier`), one per visible plan with `interest_allowed`, in plan `order`.
   - **Continue bar** (`.continue-bar`), last child of the form, `position: sticky; bottom: 0` (sticks only while the form is on screen; no JS).
3. **Also** (`.mem-also`), two small cards in one row on desktop (cols 1-6 and 7-12), stacked on phone:
   - **Single visit** (`.plan-aside`): small square picture (72px, `--radius-sm` all corners), "Single visit", "£99 a visit, ex VAT" and "£118.80 inc VAT", the hours pill ("Daytime, 5am to 6pm"), and the note from data `memberships.single_note`: "Single visits open with booking." No button, no radio, no link.
   - **Gold Card line** (`.gold-aside`): the swan mark (24px, gold, static: the draw belongs to the Gold Card page), "There is also the Gold Card, for people in property." and the quiet link "About the Gold Card" → `/gold-card/` (existing `memberships.gold_line`).
4. **Compare** (`<details class="compare">`, closed by default): summary "Compare everything" with a plus/minus icon. Table: Tier 1, Tier 2, Tier 3, Single visit. Section 2.4.
5. **VAT note**: one small muted line, "Prices exclude VAT at 20%. Prices including VAT are shown under each price." (rate from `SiteSettings.vat_rate`, sentence from `memberships.price_note`).

No "Recommended" badge anywhere except Tier 2's column. At most two small uppercase labels on the page: "Recommended" is one; the compare summary is not uppercase.

---

## 2. The tier column

### 2.1 Anatomy (top to bottom), desktop

```
┌──────────────────────────────┐  .tier  (label, espresso-raised, radius-md, padding space-3)
│ ┌──────────────────────────┐ │  .tier-media  small picture box, 112px tall, radius-sm all corners
│ │        picture           │ │  no text or pills on it
│ └──────────────────────────┘ │
│ (o) Tier 2        RECOMMENDED│  .tier-head  mark + name (Signika 500, --text-lg)  |  gold label (Tier 2 only)
│     Your evenings, too.      │  .tier-tagline  Figtree --text-sm, muted-inverse
│                              │
│ £399  a month, ex VAT        │  .tier-price  Signika 500 3rem, tabular | Figtree --text-sm muted
│ £478.80 inc VAT              │  Figtree --text-sm muted, tabular
│ ──                           │  24px gold hairline (as Home captions)
│ 8 visits a month             │  .tier-visits  Signika 500 --text-lg; the 8 counts once
│ [Day and evening, 5am to 3am]│  .pills (reused) of .pill.pill--quiet
│ [Book up to 3 days ahead]    │
│ [2 bookings at a time]       │
│ [Leil Shishi option]         │
└──────────────────────────────┘
```

- The whole column is the `<label>`; the real `<input type="radio" name="plan" value="{{ slug }}">` sits inside it, visually hidden (as `.tile input`), and the drawn mark (`.tier-mark`, 20px circle) sits left of the name.
- Columns stretch to equal height (grid `align-items: stretch`); pills sit at the top of the remaining space, not pushed to the bottom.
- No links or buttons inside a column (nothing interactive inside a label).

### 2.2 Content, all from data

| Part | Source | Today (seed) |
|---|---|---|
| Picture | `Plan.image` (upload, wins) → `Plan.render` (manifest name) → the swan placeholder (`images.placeholder`) | Tier 1 `relax-loungers`, Tier 2 `dry-sauna`, Tier 3 `gym`, Single visit `door-gold` |
| Alt text | `Plan.image_alt`, empty = `""` (decorative; the name is right beside it) | "" |
| Name | `Plan.name` | Tier 1 / 2 / 3 |
| Recommended | `Plan.highlight` and the content row `memberships.recommended_label` | "Recommended" on Tier 2 |
| Tagline | `Plan.tagline`, empty = today's `character()` ("Daytime" / "Any time" / "Unlimited") | Tier 1 "For the daytime regular." Tier 2 "Your evenings, too." Tier 3 "Whenever you like." |
| Price ex VAT | `price_whole` + `period` | £299 / £399 / £499, "a month, ex VAT" |
| Price inc VAT | `price_inc` (GEN-01, from `vat_rate`) | £358.80 / £478.80 / £598.80 |
| Visits | `visits_per_month` (None = "Unlimited visits") | 6 / 8 / Unlimited |
| Pills | `plan_pills(plan)` (new, `pages/services.py`), section 2.3 | below |

### 2.3 Pills (`plan_pills`)

In this fixed order, each only when it applies, all words built from fields (never typed in the template):

1. **Hours**: `is_daytime_only` → "Daytime, {range of the daytime OpeningRule}" ("Daytime, 5am to 6pm"); otherwise "Day and evening, {hours_facts().range}" ("Day and evening, 5am to 3am").
2. **Booking window**: "Book up to {n} day(s) ahead" (same words as `plan_facts`; MEM-04 meaning unchanged). 7 stays "7 days".
3. **Bookings at once**: "{n} booking(s) at a time".
4. **Guests**: only if `guests_per_month` > 0: "{n} guest(s) a month".
5. **Perks**: for each perk with a non-empty `pill` key, that text, in perk order. Seed: Tier 2 and 3 `leil_shishi` get `"pill": "Leil Shishi option"`; `merch` gets none ("Buy" is not a perk).

Cancel times and no-show results stay in the compare table (they are rules, not reasons to choose). Max 5 pills per column today (Tier 3).

Result today: Tier 1: Daytime, 5am to 6pm / Book up to 1 day ahead / 1 booking at a time. Tier 2: Day and evening, 5am to 3am / Book up to 3 days ahead / 2 bookings at a time / Leil Shishi option. Tier 3: Day and evening, 5am to 3am / Book up to 7 days ahead / 3 bookings at a time / 1 guest a month / Leil Shishi option.

### 2.4 Compare table

`compare_table` gains: a Single visit column (it is already in `cards`), perk rows (union of perk keys across the shown plans, label from the perk, value or "No"), and keeps cancel. Rows: Price ex VAT, Price inc VAT, Visits a month, When, Book ahead, Bookings at a time, Guests a month, Cancel up to, Leil Shishi, Merch. Compact: Figtree `--text-sm`, row height 40px, one hairline (`--color-hairline-inverse`) under each **group** of rows (price / visits and hours / booking / extras), not every row. Labels `--color-text-muted-inverse`, values cream, tabular numbers.

The **selected tier's column is highlighted** in the table (cream text on `--color-espresso-raised`, header cell with the check icon): `memberships.js` keeps the table's `data-active` in step with the radio group, so one choice shows everywhere. On phone the existing segmented picker stays (4 columns do not fit 375) and starts on the selected tier; changing the picker does **not** change the selection (it is only a view).

---

## 3. States and accessibility

It is a radio group. Real inputs, native behaviour, no ARIA re-implementation.

- `<fieldset class="tiers">` + `<legend class="sr-only">Choose your membership</legend>`.
- Each `<label class="tier">` holds `<input type="radio" name="plan" value="tier-2" aria-labelledby="tier-2-name" aria-describedby="tier-2-price tier-2-facts">`. The accessible name is just "Tier 2"; the price and facts are its description (otherwise the whole column would be read as the name).
- **Keyboard:** Tab enters the group on the checked radio; arrow keys move and select (native); Tab leaves to Continue. Space selects.
- **Focus ring:** `.tier:has(input:focus-visible) { outline: 2px solid var(--color-focus-inverse); outline-offset: 3px; }` (gold on espresso 6.17).
- **Unselected:** `--color-espresso-raised` background, 1px `--color-hairline-inverse` border (decoration), mark = 1.5px ring in `--color-text-muted-inverse` (5.61:1, meets 3:1 for UI), pills `--color-pill-line` borders.
- **Selected (instant, no transition):** 2px gold ring drawn as `box-shadow: inset 0 0 0 2px var(--color-gold)` (nothing moves), mark filled gold with an espresso check (`icon-check.svg` mask, as `.tile-multi`), pills switch to gold borders. Not colour only: the check glyph, the ring thickness and the native checked state all change.
- **Continue:** `<button type="submit" class="btn btn-primary">` with the label from `memberships.continue.cta_label` ("Continue"; becomes "Join" with the site wording later, by `replace_copy` or Control). Never the HTML `disabled` attribute (it cannot be undone without JS). If nothing is selected (no highlight plan, no `?plan`): with JS the button gets `aria-disabled="true"`, the summary reads "Choose a membership", and a click moves focus to the group instead of submitting; without JS it submits with no plan and `/register/` falls back to the journey's suggestion as it already does.
- **No JS:** the form is a plain GET to `{% url 'register' %}`; the checked radio sends `?plan=<slug>`. Everything visible, final numbers, sticky bar is CSS. The summary text in the bar shows the server-side preselection.
- **Summary in the bar** is not a live region (the radio announces itself); it is plain text that `memberships.js` rewrites on `change`.
- Hit target: the whole column (≥ 335×300). Pills are not interactive (no hover, no pointer).
- `user-select: none` on `.tier` (as `.tile`), `touch-action: manipulation`, no tap highlight.

---

## 4. Desktop, 1440×800

Grid: three columns, cols 1-4 / 5-8 / 9-12, gap `--gutter` (32px). Each column ≈ 416px wide.

| Block | Height | Running bottom |
|---|---|---|
| Header (solid) | 72 | 72 |
| Intro top padding `--space-5` | 40 | 112 |
| H1 (48px, leading 1) + `--space-2` + lead (26) | 82 | 194 |
| Gap `--space-5` | 40 | 234 |
| Column: padding 16 + picture 112 + 16 + head 28 + tagline 20 + 16 + price 48 + inc 20 + 12 + hairline/visits 36 + 12 + pills (3 rows × 32 + 2 × 8 = 112) + padding 16 | ≈ 464 | 698 |
| Gap `--space-4` | 24 | 722 |
| Continue bar | 64 | **786** |

Fit check: Continue's bottom edge ≤ 790 at 1440×800. If a column grows (longer data), the sticky bar still keeps Continue on screen; never shrink type to fit.

**Continue bar (desktop):** full container width, height 64, `--color-espresso` with a 1px `--color-hairline-inverse` top line when stuck. Left: "Tier 2" (Signika 500 `--text-lg`) + "£399 a month, ex VAT · £478.80 inc VAT" (Figtree `--text-sm`, muted-inverse). Middle-right: the note from `memberships.continue.body`: "Register your interest. Nothing to pay now." (`--text-sm`, muted-inverse; hidden under 64em). Right: Continue (primary, gold on espresso, min-width 12rem).

Below the fold at 1440: `.mem-also` (≈ 120px), compare summary (56px), VAT note, footer. Whole page ≈ 1.5 screens closed.

---

## 5. Phone, 375×667

**Pattern: stacked selectable cards.** Chosen over a snap carousel because:
- In a carousel, swiping and selecting are confused (does the card in view count as chosen?). Stacked, a tap selects and a scroll only scrolls.
- All three are readable in one scroll with the bar always showing the choice, which is the comparing Moishe asked for; a carousel hides two of three and its peek is too narrow at 335px to read a price.
- Native radio order and arrow keys match what is on screen; no scroll-snap or `scrollIntoView` code, and it works without JS.

**Card on phone** (`.tier`, full width 335):
```
┌─────────────────────────────────┐
│ ┌──────┐ (o) Tier 2             │  picture 88×88 square, radius-sm, left
│ │ pic  │ Your evenings, too.    │  name, tagline
│ └──────┘ RECOMMENDED            │
│ £399 a month, ex VAT            │  price 2.5rem
│ £478.80 inc VAT                 │
│ 8 visits a month                │
│ [Day and evening, 5am to 3am]   │  pills wrap, 2 per row mostly
│ [Book up to 3 days ahead] [...] │
└─────────────────────────────────┘
```
Heights: padding 16 + head 88 + 16 + price 40 + inc 20 + 8 + visits 28 + 12 + pills (3 rows, 112) + 16 ≈ 356. Cards 12px apart (`--space-3`).

| Block | Height |
|---|---|
| Header | 64 |
| Intro: padding 24, H1 32, lead 2 lines 48, link 24, gaps | ≈ 170 |
| Three cards + gaps | ≈ 1090 |
| Continue bar (sticky) | 72 + safe area |

The first card's top is visible on first paint (≈ 258px down), so he sees it is a choice straight away. Tier 1, 2, 3 stay in that order (same as the compare table); Tier 2 is preselected, so the bar already says "Tier 2".

**Sticky bar (phone):** `position: sticky; bottom: 0` inside the form, so it sits over the cards while they scroll and settles under the last card. Height 72 plus `env(safe-area-inset-bottom)`, `--color-espresso` with the top hairline. Left: "Tier 2" (Signika 500 `--text-base`) over "£399 a month ex VAT" (`--text-sm`, muted-inverse; inc VAT is on the card). Right: Continue, 52px (`--control-h`), auto width ≥ 9rem. Z-index 20 (BRIEF stacking: sticky action bar). Scroll padding: `scroll-padding-bottom: 88px` on the page so a focused card is never under the bar.

Breakpoints: below 64em (phone and tablet) the stacked pattern, cards max-width 40rem on tablet; from 64em, the columns.

---

## 6. Motion (7B inside a marketing page)

| What | How | Timing |
|---|---|---|
| H1 "Memberships." | Line rise from a mask (CSS: wrapper `overflow: clip`, inner `translateY(100%) → 0`), on load | `--duration-line` 1.1s, `--ease-soft` |
| Lead and the Not sure link | Fade up with the hero group | 0.8s, rise `--rise`, after the heading starts (0.15s) |
| The three columns + bar | **One group**, Fade up (no stagger, BRAND 7B "form parts arrive as one group") | `--duration-reveal`, `--delay-reveal`, 15% visible |
| Pictures in the columns | Settle `scale(1.04) → 1` inside the box, with the group | 1s, `--ease-soft` |
| Visits number | Counts 0 → n once when the group reveals ("6", "8"; Unlimited is text, no count) | 1.2s, once |
| Prices | Never animate | |
| Selection, ring, check, pill borders, bar text | Instant. No transition | 0 |
| Column hover / press | `scale(1.01)` / `0.99`, fine pointer only for hover | `--duration-press` |
| Continue | Button hover/press as everywhere; the "working" state on submit (`buttons.js`) | |
| `.mem-also`, compare | Fade up each, own group | as sections |
| Compare open | No height animation; content fades in 0.4s (opacity only) | |
| Sticky bar | Not animated (sticky controls never are) | |

Reduced motion and no JS: everything visible, final numbers, no scale or rise.

---

## 7. Data the backend needs (none of it hard-coded)

**`Plan` model (migration, all optional, history kept):**

| Field | Type | Help text |
|---|---|---|
| `image` | `FileField(upload_to=plan_image_path, blank=True)` | "Picture on the memberships page. Wins over the render." |
| `render` | `CharField(max_length=40, blank=True)` | "Name of a built render (content image manifest), used when no picture is uploaded." Validate against `content.images.manifest()` in the admin form |
| `image_alt` | `CharField(max_length=200, blank=True)` | "Describes the picture. Empty = decorative." |
| `tagline` | `CharField(max_length=80, blank=True)` | "One calm line under the name. Empty = Daytime / Any time / Unlimited." |

**`perks` JSON:** a new optional key `pill` (short chip text). No new column. Seed: `leil_shishi` on Tier 2 and 3 → "Leil Shishi option". Existing installs: add to `backfill_site_data` (only fills empty keys).

**Seed values** (`plans/seed.py`, only when missing): render Tier 1 `relax-loungers`, Tier 2 `dry-sauna`, Tier 3 `gym`, Single visit `door-gold`; taglines in 2.2.

**`pages/services.py`:**
- `plan_pills(plan)` (2.3), daytime range from the `OpeningRule` period whose key is `daytime`, full range from `hours_facts()`.
- `plan_card` adds `tagline`, `pills`, `visits_count` (int or None), `image`, `render`, `image_alt`.
- `compare_table` adds the perk rows and keeps a `slug` per column (for `data-col`).
- `selected_plan_slug(request, cards)`: the order in section 0.

**Content rows (`content/seed.py`, `memberships`):**
- `intro`: "Memberships." / "Choose when you come and how often." (unchanged)
- `not_sure`: heading "Not sure?", cta_label "Tailor your membership" (existing installs: `replace_copy "Explore your membership" "Tailor your membership"` and "Not sure? Find yours." → "Not sure?")
- `continue` (new): cta_label "Continue", body "Register your interest. Nothing to pay now."
- `recommended_label` (new): "Recommended"
- `single_note` (new): "Single visits open with booking."
- `register_label`: no longer used on this page (keep the row).

**View:** `memberships` passes `tiers` (cards with `interest_allowed`), `single` (the one-off card), `table`, `selected`.

---

## 8. Tokens and classes

**Proposed additions (derived, not brand colours; add to `tokens.css` and BRAND section 8):**

| Token | Value | Use |
|---|---|---|
| `--color-pill-line` | `rgb(245 242 216 / 0.28)` | Quiet pill border on espresso / espresso-raised. Decoration (pills are not controls); text in them is cream, 9.45:1 on raised |
| `--tier-media-h` | `7rem` (112px); phone uses a square `5.5rem` | Picture box height in a column |
| `--bar-h` | `4.5rem` (72px) phone, `4rem` desktop | Continue bar; also `scroll-padding-bottom` |

Everything else reuses existing tokens: `--color-espresso-raised`, `--color-gold`, `--color-text-muted-inverse`, `--color-hairline-inverse`, `--color-focus-inverse`, `--radius-md` (columns), `--radius-sm` (picture boxes), `--space-*`, `--ease-soft`, `--duration-*`.

**Classes:** reuse `.pills`, `.pill` (Home), `.btn`, `.btn-primary`, `.btn-quiet`, `.label`, `.sr-only`, `.compare`, `.compare-table`, `.segmented`. New: `.mem-intro`, `.tier-form`, `.tiers`, `.tier`, `.tier-media`, `.tier-mark`, `.tier-head`, `.tier-tagline`, `.tier-price`, `.tier-inc`, `.tier-visits`, `.pill--quiet` (border `--color-pill-line`; `.tier:has(input:checked) .pill--quiet` border gold), `.continue-bar`, `.continue-summary`, `.mem-also`, `.plan-aside`, `.gold-aside`. Delete `_plan_row.html` and the `.plan*` row styles once nothing uses them (check Home R5 first; it uses its own rows).

**JS:** `memberships.js` (module, < 1.5 KB): on `change` of `input[name=plan]` rewrite the bar summary from `data-name` / `data-price` on the input, set the compare table's `data-active` and the picker; `aria-disabled` handling when nothing is checked. Replaces `compare.js` on this page.

---

## 9. Pictures later (fal, in the look of the "Escape the Everyday" ad)

Small boxes, so 3:2 at 1200px wide is plenty; crop to the 112px band (desktop) and 88px square (phone) by `object-position`. Each prompt ends: "Warm low light, honed travertine and pale oak, brushed bronze fittings, gold swan mark where shown. No people, no candles, no stones, no plants in water. Photographic architectural interior, 3:2."

| Plan | Render name | Prompt |
|---|---|---|
| Tier 1 | `tier-day` | "A quiet travertine relaxation room in soft morning daylight from a high clerestory window, three upholstered cream loungers on oak frames, folded towels with a small embroidered gold swan, calm and empty." |
| Tier 2 | `tier-evening` | "A warm wood dry sauna in the evening, curved pale aspen benches with hidden amber light strips under each bench, glass door with a frosted gold swan, low warm glow, empty." |
| Tier 3 | `tier-any` | "A dark private gym late at night, smoked oak floor, two treadmills and a bench, a large brushed gold swan mark on a dark plaster wall, warm cove light, empty." |
| Single visit | `visit-one` | "A reception desk of honed cream stone with backlit SPA 99 letters, gold-leaf ceiling cove, a single folded robe on the desk, empty, evening." |

Until then: `relax-loungers`, `dry-sauna`, `gym`, `door-gold` (set by `Plan.render`, so the swap is a Control edit, not code).

---

## 10. Copy check

Every visible string: "Memberships." / "Choose when you come and how often." / "Not sure? Tailor your membership" / "Recommended" / taglines / "a month, ex VAT" / "inc VAT" / "visits a month" / pills / "Continue" / "Register your interest. Nothing to pay now." / "Single visit" / "Single visits open with booking." / Gold line / "Compare everything" / VAT note. No exclamation marks, no hype words, no em or en dashes (the compare table says "No", never a dash).
