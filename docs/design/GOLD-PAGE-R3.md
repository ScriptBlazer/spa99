# Spa 99: Gold Card page, below the card (round 3)

For the frontend and backend agents. Date 2026-10-23. Owner: the card hero is good; everything below it "feels very, very ugly" and not premium (PROJECT.md 2026-10-23). This replaces G2 to G5 of the Gold Card page (IMMERSIVE section 6, as built in `pages/templates/pages/gold.html` and `pages.css` "Gold Card"). `docs/BRAND.md` wins on any conflict.

Design read: the back of a private card. The hero card turns over as you leave it; the page carries on as the back of that card, engraved, then a room, then how to apply. Dials: variance 7, motion 5, density 4.

---

## 1. Do not change

- **G1, the card hero**: words, button, the 3D card, its load sequence, the half turn on scroll, the CSS and still fallbacks, the `gold-card` still, the glow. Not a pixel. (The frontend is fixing the inner-border timing separately; leave that to them.)
- The page stays espresso from top to bottom (`.gold-world.on-dark`), the immersive script stack it already loads, `data-page="marketing"`.
- The content rows `who`, `who_note`, `holds`, `how`, `step_1..3`, `apply` and their wording, except where section 5 says.

## 2. What is ugly today, most important first

1. **"Who it is for" is six huge Signika lines in two columns** (`.roles li` at `--text-xl`): it reads like a menu, louder than the hero, with nothing to look at.
2. **"What it holds" is two plain bullet lists under a gold rule**: the best part of the offer (unlimited visits, two guests, a week ahead) has the weakest typography on the page.
3. **The steps are three big words in a row** ("Apply." "We read it." "We'll be in touch.") with a line under each: the same pattern as everywhere, no rhythm.
4. **The apply panel is a slab** of swan pattern with a gold rule, the same espresso as the page, a duplicate of the hero's call to action with a different label ("Apply for the Gold Card" against the hero's "Apply").
5. **No picture at all** below the card, and every section is the same shape: heading, text, padding.

---

## 3. The new page

| # | Section | Family | Height at 1440 x 800 | Phone 375 |
|---|---|---|---|---|
| G1 | The card (unchanged) | Hero | 1 screen | 1 screen |
| G2 | **What it holds**: the back of the card | One engraved panel | about 0.85 | about 1.6 |
| G3 | **Who it is for**: a room, and the roles as pills | Edge-bleed frame + inset | about 0.75 | about 1.3 |
| G4 | **How it works, and apply** | Steps + the small card | about 0.7 | about 1.4 |
| | Footer | | | |

About **3.3 screens** below the hero at 1440 (today about 4, mostly empty). Every section is content height: `padding-block: var(--space-6)` desktop, `--space-5` phone. No `min-height: 100svh` below the hero.

Grid at 1440: 12 columns, column 80, gutter 32, margin 64 (as SPA-PAGE). Phone margin 20.

### G2. What it holds: the back of the card

The hero card turns to show its bronze back with the swan pattern as you scroll away (GOLD-CARD-3D 2.4). G2 continues that: an engraved panel in the colour of the card's back, holding what the card gives.

**The panel (`.gold-back`)**, desktop:
- Inside the container, full container width (1312 at 1440), `--radius-md`.
- Background `--color-gold-deep` (#5A3A26, the card back's colour, already a token) with the swan pattern (`swan-pattern.svg`, as `.gold-panel` uses it) and one static warm light: `radial-gradient(60% 80% at 15% 0%, var(--color-glow), transparent 70%)` laid over it.
- **The engraved border**: a `::after` at `inset: 12px`, `border: 1px solid var(--color-tier-edge-gold)`, `border-radius: calc(var(--radius-md) - 6px)`, `pointer-events: none`. The same inset line as the Gold Card's face and the Memberships selected card.
- Padding `--space-6` (64).
- Inner grid 12 columns (the panel's own), gap as the page.

Inside, desktop:

| Where | What |
|---|---|
| Cols 1 to 6, top | h2 `holds.heading` "What it holds." Signika 500 `--text-2xl` (48) cream. Lead (new row `holds_lead`) "The fullest membership, and a little more." Figtree `--text-lg`, `--color-text-muted-inverse` (5.33:1 on gold-deep), margin-top `--space-2` |
| Cols 1 to 6, after `--space-5` | Small group title "Your visits" Figtree 500 `--text-sm` muted inverse, sentence case. Then **four figures** in a 2 x 2 grid (row gap `--space-5`, column gap `--gutter`). Each figure: a 24px x 1px gold hairline (`--color-gold`), then the value Signika 500 `--text-xl` (36) cream (8.98:1), then its label Figtree `--text-sm` muted inverse. Then, after `--space-4`, a row of **pills** (`.pill`, the house pill: 1px `--color-gold` border, 5.06:1 on gold-deep; text cream `--text-sm`; `--radius-md`; `--pill-h`) |
| Cols 8 to 12, aligned to the figures' top | Group title "Beyond the spa" (same style as "Your visits"). Then the **perks**, `--space-4` apart, each: 24px gold hairline, name Signika 500 `--text-lg` cream, note Figtree `--text-sm` muted inverse (one line) |
| Bottom, full width, after `--space-6` | One engraved line, centred: "BEYOND LUXURY" Figtree 500 `--text-sm`, uppercase, letter-spacing 0.2em (as on the card's back), `--color-gold-light` (7.04:1). The only uppercase text on the page; it is the brand line, not a section label |

Figures, from the Gold plan (backend `gold_facts()`, section 5), seeded values:

| Value | Label |
|---|---|
| Unlimited | visits |
| Any time | 5am to 3am |
| 7 days | to book ahead |
| 2 | guests a month |

Pills: "3 bookings at a time", "Cancel up to 5 hours before", "First call from the waitlist".

Perks (from the plan's `perks`, in order, excluding the waitlist which is a pill):

| Name (perk `phrase`) | Note (new perk key `note`) |
|---|---|
| Leil Shishi when offered | The Thursday evening meal, included. |
| BML members' events | Invitations through the year. |
| Each merch release | shown as it is (owner, 2026-10-23: keep as is) |

Fit at 1440: padding 64 + h2 58 + lead 32 + 40 + title 20 + 16 + figures 2 x (1 + 8 + 40 + 22) + 40 + 24 + pills 32 + 64 + engraved 20 + 64 = **about 640**. Section with padding: about 0.85 of a screen.

**Phone 375**: panel at container width (335), padding `--space-4` (24), engraved border `inset: 8px`. Stack: h2 (32), lead, "Your visits", figures **2 x 2** (each about 140 wide, values `--text-lg` 20px), pills wrap, "Beyond the spa", perks, engraved line. About 980px.

**Motion** (GSAP, the page's existing stack):
- Panel: Fade up as one block (`top 85%`), 1s, `--rise`; the swan pattern and border come with it.
- h2 Line rise; lead Fade up.
- Figures: one group Fade up (four items: 0.1s apart on desktop, none on phone). "7" and "2" Count once (1.2s) when the group enters; "Unlimited" and "Any time" do not count.
- **One sheen**: when the panel is 50% in view, one band of light crosses it once, left to right: a `::before` layer, `linear-gradient(105deg, transparent 35%, var(--color-sheen) 50%, transparent 65%)`, `translateX(-110%)` to `110%`, 1.8s, `--ease-soft`, once per page view. The Gold Card family (card sheen, Memberships sheen). Never on hover, never again.
- Desktop, fine pointer: the existing pointer glow (`data-glow`) on the section.

**Static / reduced motion:** panel visible, final numbers, no sheen, no count.

### G3. Who it is for: a room, and the roles as pills

**Desktop:**
- Frame `gym` (`.frame--right`): from col 7 to the right screen edge (about 752 wide), 4:3 (564 tall, capped at `--frame-h-feature`), focus `30% 50%` (the gold swan and "SPA 99" on the dark wall). Inner corners radiused, `frame-tint` 0.14. The gym is dark espresso with a gold swan: it is the room that matches this page.
- **Inset** `kitchenette` (gold ceiling, the swan on walnut) in a **mount** (`.frame--mount`, AMENITIES.md section 2), 4:5, 192 x 240, overlapping the frame's lower left corner by one gutter, hanging `--space-6` below the frame's bottom.
- Caption under the frame, right of the inset: `.frame-caption` hairline + "Any time, {range}." (`hours_facts().range`) Figtree `--text-sm` muted inverse.
- Cols 1 to 5, vertically centred against the frame:
  - h2 `who.heading` "Who it is for." `--text-2xl`.
  - The roles (`who.body`, one per line) as **pills**, margin-top `--space-4`, gap `--space-2`: the larger static pill, `min-height: var(--chip-h)` (44px), padding `0 var(--space-3)`, 1px `--color-gold` border (6.17:1), cream Figtree `--text-base`, `--radius-md`. Not links, no hover. They wrap to three rows in cols 1 to 5.
  - `who_note` "Not in property? You're still welcome to apply." `--text-sm` muted inverse, margin-top `--space-4`.

**Phone:** h2, pills (wrap), note; then the frame bleeding right with `--page-margin` on the left, 4:3 (355 x 266); the inset mount 40% wide, right aligned, pulled up `--space-5` over the frame's bottom; caption. About 860px.

**Motion:** frame settle (1.06 to 1) and depth 4; inset depth 12; h2 Line rise; pills one group Fade up (no stagger: six items); note Fade up. Phone: settle only. Static: at rest.

### G4. How it works, and apply

**Desktop:**
- Cols 1 to 6: h2 `how.heading` "How it works." `--text-2xl`, then the three steps as **The spa's vertical steps** (`.vsteps`, SPA-PAGE S3): gold number Signika 500 `--text-lg` in a 48px column, a 1px `--color-thread` line joining 1 to 3 behind the numbers; the word ("Apply." "We read it." "We'll be in touch.") Signika 500 `--text-xl`; its line Figtree `--text-base` muted inverse. `--space-5` between steps. No pills.
- Cols 8 to 12, vertically centred against the steps: **the apply block** (no box, no slab):
  - The card, small: the existing `gold-card` still (`photo "gold-card"`, the reduced-motion still of the 3D card, already on espresso), width 20rem (320), no frame, no radius of its own (the image already shows the card on espresso). `alt=""` (decorative: the card is described in the hero).
  - h2 `apply.heading` "Apply for the Gold Card." `--text-xl`, margin-top `--space-4`.
  - Body `apply.body` "A few taps, and we will be in touch." `--text-base` muted inverse.
  - Button `.btn.btn-primary` gold, label **the hero's label** (`hero.cta_label`, "Apply") with the arrow icon, margin-top `--space-4`. One label per intent on the page.
  - Under it: "Free. No account needed." `--text-sm` muted inverse (new row `apply_note`; LC-26 as overridden for Phase 1).

**Phone:** h2, steps (number column 32px); `--space-6`; then the apply block: card still at 70% width, heading, body, button full width, note. About 900px.

**Motion:** h2 Line rise; the step line draws scrubbed (`scaleY 0 to 1`, from the list's `top 70%` to `bottom 60%`) and each number goes 0.4 to 1 opacity as the line reaches it (exactly SPA-PAGE S3, reuse the code); the card still settles (scale 0.98 to 1, opacity 0 to 1, 1s); heading, body, button, note Fade up as one group. Static: line drawn, numbers full, all visible.

---

## 4. What goes

- [ ] `.roles` big Signika list and its two columns.
- [ ] `.perk-groups` / `.perk-group` (gold top rule, plain lists) on this page.
- [ ] `.steps` three-column big words on this page (Book keeps whatever it uses).
- [ ] The `.gold-panel` slab in G5 (the component stays for the journey result, which uses it).
- [ ] `sr-only` on the "What it holds" and "How it works" headings: both are visible now.
- [ ] `data-reveal` on these sections (they use the GSAP helpers like The spa).

---

## 5. Data (backend)

- New `plans` or `pages.services.gold_facts()`: from the visible Gold plan, returns `figures` (list of `{value, label}`) and `pills` (list of strings):
  - visits: `is_unlimited` gives `("Unlimited", "visits")`, else `(n, "visits a month")`.
  - hours: daytime only gives `("Daytime", "5am to 6pm")` from the daytime rule, else `("Any time", hours_facts().range)`.
  - window: `(f"{n} days", "to book ahead")` (`"1 day"` when 1).
  - guests: `(n, "guests a month")` when `guests_per_month`, else no figure (the grid then shows 3: the 2 x 2 becomes a row of three on desktop, 2 + 1 on phone).
  - pills: `f"{upcoming_limit} bookings at a time"` (or "1 booking at a time"), `f"Cancel up to {cancel_hours} hours before"`, "First call from the waitlist" when the perk is on.
- `gold_groups()` stays (Home uses it); the new page uses `gold_facts()` plus the perks below.
- Perks: add an optional `note` key to each perk in the Gold plan's `perks` JSON (seed only when missing: Leil Shishi "The Thursday evening meal, included.", events "Invitations through the year."). Add an optional `public` key (default true): perks with `public: false` are not shown anywhere on the site (this page, Home's Gold pills). See question 6.
- Content rows (page `gold`, create only when missing): `holds_lead` body "The fullest membership, and a little more."; `apply_note` body "Free. No account needed."
- Existing `apply.cta_label` ("Apply for the Gold Card") is no longer rendered; the button reads `hero.cta_label`.

## 6. Open question for the owner

The Gold plan lists "Each merch release" as a perk (PRICING.md, EXT-02), and it shows on Home's Gold pills today. The owner said on 2026-10-23: no merch or shop framing anywhere this round. Options:
**Answered 2026-10-23: C, keep as is.**
- **A (recommended):** set the merch perk to `public: false`: it disappears from this page and Home until merch is on sale; the rule stays in the data.
- **B:** keep it as a perk, worded "New Spa 99 pieces, as they come", no word "merch".
- **C:** keep it as it is.

Until answered, build with A.

---

## 7. Tokens

No new colours. Reused: `--color-gold-deep` (panel), `--color-gold`, `--color-gold-light`, `--color-tier-edge-gold`, `--color-sheen`, `--color-glow`, `--color-thread`, `--color-text-muted-inverse`, `--radius-md`, `--chip-h`, `--pill-h`, `--frame-h-feature`, `--space-*`, `--ease-soft`. Uses `.frame--mount` and `--mount-gap` from AMENITIES.md.

Contrast on `--color-gold-deep`: cream 8.98, muted inverse 5.33, gold (pill borders, numbers) 5.06, gold light 7.04. On espresso: cream 10.95, muted inverse 6.50, gold 6.17, gold button label 6.17.

## 8. Acceptance checks (screenshots `.private/shots/gold-r3/` at 375 x 667 and 1440 x 800, static and motion)

1. G1 is pixel-identical to today (compare screenshots before and after at 1440 and 375).
2. 1440: G2 panel fits on one screen with the whole panel visible; the inset border is crisp; numbers and pills come from the plan (change "booking window" in the admin and the figure changes).
3. No section below the hero is taller than one screen at 1440 x 800.
4. "Who it is for" shows the six roles as pills next to the gym picture with the kitchenette inset; nothing is louder than the hero heading.
5. One call-to-action label on the page ("Apply"), twice (hero and G4).
6. Sheen passes once over the panel and never again on that page view; no motion under reduced motion; numbers final.
7. Three different section shapes below the hero (panel, edge-bleed frame, steps with the card); no two in a row look alike.
8. Phone: no horizontal scroll; figures stay 2 x 2; pills wrap; the apply button is full width.
9. The merch perk "Each merch release" stays visible, worded as it is (owner's answer 2026-10-23).
