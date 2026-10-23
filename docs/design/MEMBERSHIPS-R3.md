# Spa 99: Memberships, round 3 (polish)

For the frontend agent. Date 2026-10-23. Owner: the layout is liked ("nice"), but "it needs more", "a bit more freshness", "still feels a bit not premium" (PROJECT.md 2026-10-23). This is a **polish pass on MEMBERSHIPS-R2.md**: everything in R2 stays unless a row below changes it. `docs/BRAND.md` wins on any conflict. No GSAP on this page (BRAND 7B), CSS plus a few lines in `memberships.js`.

The frontend agent is already fixing the compare plus-to-X icon and the stray focus border: **not in this brief**.

Design read: the same jeweller's case, now lit. Light falls on the counter, the chosen piece glows from underneath, its room "comes on", and the small things (a price tag's pound sign, a fine inlay, a tick before each line) are cut with care. Dials: variance 6, motion 4 (was 3), density 3.

---

## 1. Must not change

- The stage: tag column left, three tall selectable key cards right (desktop); stacked cards with the cream sticky tag (phone). Sizes, gaps, `--tier-h`, `--tier-w`.
- Tier 2 preselected. The whole card is the radio. One Continue. Cream page. Compare closed by default and compact.
- Copy, data, the radio semantics and keyboard, the instant colour/check change on selection, the 8px lift, the shadow layers, the one sheen.
- No chips, no uppercase labels, no new boxes, no new borders stronger than R2's.

---

## 2. Why it still feels "not premium" (from the 1440 and 375 screenshots)

1. **Flat light.** The cream is one even colour edge to edge; the cards have shadows but nothing lights them. Real display cases are lit from above and the object throws warm light down.
2. **The three pictures are equally loud**, so the chosen card's room does not feel chosen; only the card colour changes.
3. **Small type details are default**: the "£" is as big as the digits, list lines are plain, the selected numeral is the same cream as the body text.
4. **The selected card is an espresso rectangle with a thin edge.** It lacks the one fine detail that makes the Gold Card feel made: an inlaid line.
5. **The choice summary jumps**: when you pick another tier, "Tier 2" becomes "Tier 1" with no acknowledgement in the tag.
6. **Below the stage there is little to discover**: single visit and a Gold line. Nothing tells you what every visit includes.

---

## 3. The lifts, most important first

### 3.1 Counter light (static)

`.mem-stage` gets one soft light, behind everything, no motion:
`background: radial-gradient(70% 60% at 64% 40%, var(--color-cream-raised) 0%, transparent 70%), var(--color-cream);`
At 1440 the brightest point sits behind Tier 2; the tag column stays on plain cream. Phone: `radial-gradient(120% 40% at 50% 0%, ...)` at the top of the page. Decoration only; text contrast is measured against the lighter colour (espresso on cream-raised 11.71, muted 5.69: unchanged pass).

### 3.2 The light pool under the chosen card

A warm glow on the counter under the selected card, as if the espresso card is lit from above and its gold edge throws light down.
- Element: `.tier-shadow::after` (the selected shadow layer already exists and already fades in on selection), `content: ""; position: absolute; left: 12%; right: 12%; bottom: -2.25rem; height: 3rem; background: radial-gradient(closest-side, var(--color-pool), transparent); pointer-events: none;`
- It shares the layer's opacity: 0 to 1 over `--duration-tier` (600ms) with the lift. Moving to another card: the old pool fades out, the new one fades in, same 600ms.
- Phone: same, `bottom: -1.5rem`, height 2rem (cards are 24px apart; it must not reach the next card's picture).
- Reduced motion: the pool is simply there under the selected card.

### 3.3 The chosen room comes on

- Unselected cards: a cream veil over the picture, `.tier-media::before { background: var(--color-room-veil); }` at opacity 1 (cream-raised at 24%: the room looks softly unlit).
- Hover (fine pointer, unselected): the veil goes to opacity 0.4 (500ms, `--ease-soft`): the room brightens as you consider it.
- Selected: veil opacity 0, and the photo settles from `scale(1.03)` to `scale(1)` over 1.2s, `--ease-soft`: the room comes into focus. Transform and opacity only. Not on the arrival preselect (the group reveal already settles the photos; R2 6.1).
- The existing fade into the card colour (`.tier-media::after`) stays on top of the veil.
- Reduced motion: veil states change instantly, no scale.

### 3.4 The inlay on the selected card

- `.tier-sheen::before` (the sheen span already clips to the card): `inset: 6px; border: 1px solid var(--color-tier-edge-gold); border-radius: calc(var(--radius-md) - 4px); opacity: 0;` and `opacity: 0.45` on the selected card.
- It runs over the picture too (the line reads as engraved into the card, like the Gold Card's inner border).
- Appears **instantly** with the colour (it is part of "selected", BRAND 7B), not faded.
- Unselected cards: none.

### 3.5 Type details

| Detail | Spec |
|---|---|
| Selected numeral in gold | `.tier:has(input:checked) .tier-num { color: var(--color-gold); }` (6.17:1 on espresso). Unselected stays espresso. Instant with the selection |
| The pound sign as on a price tag | Wrap the "£" in `<span class="cur">` in the card price, the tag summary and the also row: `font-size: 0.58em; vertical-align: 0.62em; margin-right: 0.06em; font-weight: 400`. Digits unchanged. Screen readers still read "£399" (the span is inline, no `aria-hidden`) |
| A fine tick before each list line | `.tier-list li::before { content: ""; display: inline-block; width: 0.5rem; height: 1px; margin-right: 0.625rem; vertical-align: 0.3em; background: var(--color-line); }` (caramel, decoration); on the selected card `--color-gold`. Replaces R2's `content: none` |
| Tagline in Figtree italic | Not adopted: Figtree italic is not self-hosted and the extra file is not worth it. Leave the tagline as is |
| Tabular figures in the tag | `.continue-price, .continue-inc { font-variant-numeric: tabular-nums; }` so the price width does not jitter when the tier changes |

### 3.6 Every visit includes (the freshness below the stage)

From AMENITIES.md 5.2. A new first row in `.mem-also`, full width (cols 1 to 12 on desktop), above Single visit and the Gold line:
- Four small cream mounts (`.frame--mount` cream variant): 40 x 40, mount gap 4px, `--color-cream-raised` mount, 1px `--color-tier-edge` border, `--radius-sm`, photos `towel-bench`, `robe`, `slippers`, `toiletries` (from the `arrive_kit` content row, so it changes in one place). Gap `--space-2`. `alt=""`.
- Beside them: "Every visit: towels, robe, slippers and toiletries, and every room." Figtree `--text-sm`, espresso. Then a quiet link "See the spa" (`.btn-quiet`, `--text-sm`) to The spa.
- Phone: the four mounts on one line, the sentence under them, the link under that.
- Under it, the existing hairline and the two-column Single visit / Gold row.
- Until the fal pictures exist (AMENITIES section 6), the row shows the sentence and link without mounts.
- Motion: one group Fade up with `data-reveal` (as the rest of the also row).

### 3.7 Pointer light inside the chosen card (desktop, fine pointer)

The dark-scene pointer glow, scaled down to one card:
- `.tier:has(input:checked)` gets `background-image: radial-gradient(14rem 14rem at var(--px, 50%) var(--py, 30%), var(--color-glow), transparent 70%);` on top of `--tier-bg`.
- `memberships.js`: on `pointermove` over the selected card, set `--px` / `--py` on that card only (in a `requestAnimationFrame`, one write per frame). On `pointerleave`, remove them (the light rests at 50% 30%).
- Only under `(hover: hover) and (pointer: fine)` and `prefers-reduced-motion: no-preference`. Decoration: cream text over gold at 16% stays above 9:1.

### 3.8 The tag acknowledges the change

When the selection changes, `memberships.js` already writes the new name and prices into the tag. Add: the three summary lines (`data-summary-name`, `-price`, `-inc`) fade from opacity 0 to 1 over 240ms, `--ease-soft` (restart the animation by toggling a class). Opacity only, no movement. Same on the phone sticky tag (name and price). Not on arrival. Reduced motion: none.

### 3.9 The selected check

The check inside the gold disc appears with `scale(0.6)` to `scale(1)` and opacity 0 to 1 over 200ms, `--ease-soft` (the disc itself fills instantly). Unselecting: instant. Reduced motion: instant.

---

## 4. Tokens (proposed additions, derived, decoration only; add to `tokens.css` and BRAND section 8)

| Token | Value | Use |
|---|---|---|
| `--color-pool` | `rgb(229 172 110 / 0.35)` | The warm light pool on the cream under the selected card |
| `--color-room-veil` | `rgb(251 249 236 / 0.24)` | The cream veil over an unselected card's picture |
| `--duration-ack` | `240ms` | The tag's acknowledgement fade |

Reused: `--color-cream-raised`, `--color-tier-edge-gold`, `--color-gold`, `--color-line`, `--color-glow`, `--color-tier-edge`, `--duration-tier`, `--ease-soft`, `--radius-md`, `--radius-sm`. `.frame--mount` and `--mount-gap` from AMENITIES.md.

Contrast (text only; everything else is decoration): gold numeral on espresso 6.17 (large text, passes); espresso on cream-raised 11.71 (tag over the counter light); muted 5.69; "Every visit" sentence espresso on cream 10.95.

BRAND 7B note (amend section 7B "Interaction feedback"): "The selected Memberships card also lights its room (veil off, photo settles 1.03 to 1, 1.2s) and casts a warm pool on the cream (600ms with the lift). The colour, check, inlay and gold numeral still change instantly."

---

## 5. Motion summary

| What | Trigger | Timing | Reduced motion |
|---|---|---|---|
| Counter light | none (static) | | same |
| Light pool | selection | 600ms with the lift | present, no fade |
| Room veil off + photo settle | selection | veil 600ms, settle 1.2s | instant, no scale |
| Room veil 1 to 0.4 | hover, fine pointer | 500ms | n/a |
| Inlay, gold numeral, ticks gold | selection | instant | instant |
| Pointer light | pointer move on the selected card | per frame | off |
| Tag fade | selection change | 240ms | off |
| Check scale-in | selection | 200ms | instant |

Never more than these at once; nothing loops; no sideways travel of text.

---

## 6. Acceptance checks (screenshots `.private/shots/memberships-r3/` at 375 x 667, 1440 x 800, 1920 x 1080; plus a 10-second screen recording of picking Tier 1 then Tier 3)

1. Side by side with R2 at 1440: same positions and sizes for every element (overlay the screenshots: nothing moved more than 1px), but the page now has light: a brighter area behind the cards and a warm pool under the selected card.
2. Picking Tier 1: in the same frame the card turns espresso with gold edge, inlay, gold numeral, gold ticks and check; over 0.6s it rises, its pool fades in and Tier 2's fades out; its room brightens and settles; the tag's text fades in once.
3. Unselected rooms look softly unlit; hovering one (desktop) brightens it a little.
4. The "£" sits small and raised on every price; the digits are unchanged; a screen reader reads "£399 a month, ex VAT".
5. The "every visit" row shows below the stage with four mounts (or without them until the pictures exist) and links to The spa.
6. Reduced motion: no fades, scales or pointer light; selected state complete and correct.
7. Phone: the pool does not touch the next card; the sticky tag is unchanged apart from the fade; nothing overlaps.
8. Keyboard: arrows change the tier with the same visuals; the focus ring is unchanged.
