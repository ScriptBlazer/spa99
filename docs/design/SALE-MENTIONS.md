# Sale mentions: design brief

Moishe (2026-10-28): during a sale, mention it in more places, elegantly, on top of the bar. Builds on `docs/design/SYSTEM-SALES.md` (bar, bands, price lines) and `docs/features/sales.md`. Rules from there still apply: no red, no strike-through, no badges, no countdown outside the bar and bands, no em dashes, never "Hurry", "Don't miss out", "Last chance", no exclamation marks.

**Design read.** The bar is the announcement. A mention is the front desk repeating it once, quietly, at the moment a man is deciding: just before a "Tailor your membership" or "Register" button. One sentence, small, no link (the button beside it is the action), no motion of its own. Five places, all server rendered.

## 1. Where (and where not)

| # | Place | Pattern | New? |
|---|---|---|---|
| 1 | The spa, closing band "Find the right way to visit." (`pages/spa.html`, `.sp-band`) | A, eyebrow above the heading | new |
| 2 | Home, opening band "LAUNCHING / January 2027." + Register (`pages/home.html`, `.opening-scene`, the last scene before the footer; it is **not** `_footer.html`) | B, note under the hours line | new |
| 3 | Book, "Booking opens soon." + Register (`pages/book.html`, `.soon`) | B, between `.soon-month` and the actions | new |
| 4 | Journey result, only when the suggested plan is in the sale | C, price line under the suggested plan's price | new (needs a payload field) |
| 5 | Register (`users/register.html`) | existing `register_sale` plan line and the note under submit | exists; no change (one fix, section 5) |

**Nothing on:** the footer partial (it is on every page, directly duplicating the bar site-wide); Home's other scenes (Home already has bar + band, a third mention is enough); Memberships (band + price lines already); Gold Card (the Gold Card is free by application and never a sale plan, so a sale line there would be noise; same answer if Gold is ever added to Plans: it stays out); Visit us (address and getting here, a practical page; the bar covers it); Virtual tour (a canvas, the bar is there); Sign in, legal, error pages, My Spa 99 (kept price line exists). No tag on any button: badges are banned and a button label stays a verb.

## 2. Copy

Variables from `sale_bar`: `name`, `percent`, `plans_text` ("Tier 2", "Tier 2 and Tier 3", "Tier 1, Tier 2 and Tier 3", "all memberships", "all memberships and single visits", "single visits"), `months`, `ends_at`, `starts_at`.

- **Months:** "for your first month" when 1, otherwise "for your first {n} months".
- **End (`until` / `by` form), London time, one server helper `sale_until(sale_bar)`:**
  - Ends at 00:00 → the previous date, no time: "24 December" (a sale ending 25 Dec 00:00 reads "24 December").
  - Ends at 23:59 → that date, no time: "24 December".
  - Any other time → "24 December, 18:00".
  - Ends today (other time) → "18:00 today"; ends at the coming midnight → "midnight tonight".
  - No weekday, no year (the bar's screen-reader text already has the full date).
- **No prices in A and B.** They are seen before the email gate; percent and plan names are fine (the bar already shows them), pounds are not. Only C (after the gate, or with the gate off, where the result already shows the price) carries a price.

| Pattern | Text |
|---|---|
| A eyebrow | `{name} · {percent}% off {plans_text} · until {end}` → "Christmas sale · 20% off Tier 2 and Tier 3 · until 24 December" |
| B note | `{name}: register by {end} to keep {percent}% off {plans_text} for your first {n} months.` → "Christmas sale: register by 24 December to keep 20% off all memberships for your first 3 months." |
| C journey | the existing `register_sale_line` sentence → "Register during the Christmas sale and keep £76 a month for your first 3 months." ("£36 a visit" for single visit) |
| Preview of an upcoming sale | A: replace "until {end}" with "from 1 December". B: unchanged (uses the end). No "Preview" tag here: the bar carries it. |

## 3. Look (existing tokens only, no new tokens)

Markup: one partial `common/_sale_mention.html` with `kind="eyebrow"` or `kind="note"`, rendering nothing unless `sale_bar` is set. Styles in `sale-bar.css` (already loaded whenever `sale_bar` is in context). Classes `.sale-mention`, `.sale-mention--eyebrow`, `.sale-mention--note`.

**A, eyebrow (The spa band, espresso with the swan pattern)**
- Inside `.sp-band-main`, before the `h2`, `margin-bottom: var(--space-3)`, `max-width: var(--measure)`.
- Figtree `--text-sm`, weight 500, `--leading-snug`, `--tracking-body`, sentence case (not the uppercase launch label: a long uppercase line shouts).
- Name `--color-gold` (6.17); offer `--color-text-inverse`; "until …" and the `·` separators `--color-text-muted-inverse` (6.50). Separators `margin-inline: var(--space-2)`. Same colour logic as the bar, so it reads as the same voice.
- Each of the three groups `white-space: nowrap`; the line may wrap between groups only. 375px: usually two lines, `text-wrap: balance`. 1440px: one line, left aligned with the heading.

**B, note (Home opening band and Book hero, espresso)**
- Home: in `.opening-main` after `.opening-hours`, `margin-top: var(--space-4)`. Book: after `.soon-month`, `margin-top: var(--space-4)`, inheriting the hero's alignment. `max-width: var(--measure)`.
- Starts with the gold swan glyph (`.mark-glyph`, `aria-hidden`, as the price lines), then the text.
- Figtree `--text-base`, weight 400, `--leading-snug`, `--color-text-inverse`; "{name}:" weight 500 in `--color-gold`.
- 375px: wraps to two or three lines under the hours, above the full-width Register button. 1440px: one or two lines in the left column (columns 1-8), Register stays at the right, bottom aligned as now.

**C, journey result**
- Directly under the suggested plan's price, same look as the Memberships `.tier-sale` line: glyph, `--text-sm`, weight 500, `--leading-snug`, `margin-top: var(--space-3)`, `--color-text` on cream, `--color-gold` on espresso. Alternatives ("Or choose another") get nothing; Register shows each chip's line if he switches.
- Data: add `sale_line` (string or null) for the suggested plan to the result JSON (`engine.preview` / `engine.complete`), built from `register_offer` (live sale only, never a preview, so it always matches what Register then says).

`prefers-contrast: more`: muted parts go `--color-text-inverse`. Large screens: rem tokens only, nothing in `wide.css`.

## 4. Motion, accessibility, end

- **Motion:** none of their own. A and B join their scene's existing fade group (`data-fade` on The spa and Home, so they fade up after the heading rises; Book is already inside the `data-reveal="hero"` group). C arrives with the result. Reduced motion and no JS: visible at once, like everything else.
- **Screen readers:** plain text, never a link, never `aria-live`, never a countdown, so nothing ticks and nothing is announced twice. Wording differs from the bar, so it is not a verbatim repeat. `·` separators `aria-hidden` with an `sr-only` ", " each. Glyph `aria-hidden`. C must be inserted in the same DOM update as the result (if the result region is live, it is read once with it, not as a second announcement).
- **Sale end:** mentions are server rendered and disappear on the next load. No `data-` hooks, no JS, `sale-bar.js` does not touch them (removing a line mid-page would jump the layout; the band already sets this precedent). C is computed when the result is fetched.
- **Preview:** A and B follow `sale_bar`, so they show in a preview session (handy for checking). C and Register stay live only (existing rule).

## 5. Checks for frontend

1. Register already shows `register_sale` on the plan card and "Your sale price is saved with your registration." Verify only. Fix: `register_sale_line` always says "a month"; use "a visit" when the plan is single visit (as `sale_line` does).
2. Screenshots at 375 and 1440: The spa band (A, one line at 1440, two at 375), Home opening band (B), Book (B), journey result with the suggested plan in and out of the sale; each with a 1-plan sale, an "all memberships and single visits" sale, a sale ending today at 18:00, and a 1-month sale.
