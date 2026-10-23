# Spa 99: the robe, the towels and the rest (amenities, round 3)

For the frontend and backend agents, and for whoever runs the fal jobs. Date 2026-10-23. Adds to `SPA-PAGE.md` (The spa page) and `SPA-OPENER.md`; small echoes on Home and Memberships. `docs/BRAND.md` wins on any conflict.

Owner's words and decisions (PROJECT.md 2026-10-23, three rows):
- Every visit includes swan towels, a swan robe, swan slippers and toiletries in the swan bottles. Showing them "would make it a lot more premium", "it's missing a lot".
- **No merchandise, no shop, no "coming soon".** The tote bag and the steel bottle appear as if they are simply part of the spa: "embed it within the spa as if it exists... the towel gives this feel... add all these nice thingies rather than just dry sauna and stuff. More get the vibe going."
- Not only small frames: use them big too ("the robe gives it a crazy kind of vibe"). The robe leads the opener (SPA-OPENER.md). The team may experiment on The spa page. Home stays more or less as it is.

Design read: a men's hotel magazine shot in one building. Between the rooms, the things you touch: a folded towel on the sauna bench, the bottles in the shower, slippers by the loungers, a bottle on the gym bench, the tote on the way out. Mixed scales: two full-bleed bands, one overlapping pair, small mounted details. They break the room-after-room rhythm. Dials for the page: variance 8 (was 7), motion 6, density 4.

What must not change: the opener method, the room compositions (feature, tiles, companion), the chips, How a visit works, the closing band, Home's structure.

---

## 1. The new running order of The spa page

| # | Section | Family | Desktop side | New? |
|---|---|---|---|---|
| 1 | S1 Opener: the robe, four lines (SPA-OPENER.md) | Full screen, shrinks into a frame | frame right | changed |
| 2 | **M1 Before the heat**: a folded towel on the sauna bench | Full-bleed band, words below | full width | **new** |
| 3 | S2a Dry sauna | Feature | frame left | as is |
| 4 | S2b Wet sauna, cold plunge, showers, kitchenette | Tile row (4 tiles, intro above) | centre | as is |
| 5 | **M2 In every shower**: the swan bottles and a towel on the rail | Overlapping mounted pair | pair right | **new** |
| 6 | S2c Relaxing zone + massage room | Feature with companion | frame right | as is |
| 7 | **M3 Soft underfoot**: slippers by the loungers | Full-bleed band, words on the veil | full width | **new** |
| 8 | S2d Gym, with the **steel bottle** as its detail inset | Feature + mounted inset | frame left | inset new |
| 9 | S3 How a visit works, with **every visit includes** in step 2 | Steps | frame right | detail new |
| 10 | S4 Next, with **the tote** on the way out | Closing band + one mount | mount right | detail new |

Image-and-text splits never run three in a row: 3 (left), then tiles, then 5 (pair), 6 (right), then a full-bleed band, then 8 (left), 9 (right). Full-bleed bands are two, with different text placement, so they are not a repeated block.

Page length at 1440 x 800: about 6.6 screens today, about **8.4** with the moments (M1 0.75, M2 0.6, M3 0.6, the rest inside existing sections). Phone 375: about 8 today, about **10**.

---

## 2. The mount (the "nice border")

The owner asked for "a nice border or something". Big pictures keep the house style (full bleed or edge bleed, radius on the inner corners). **Small detail pictures get a mount**, the same idea as the Gold Card's inset border: a thin gold line, a narrow espresso-raised margin, then the photo.

`.frame--mount` (new, in `spa.css`; also used on Home and Memberships below):
- Outer box: `background: var(--color-espresso-raised)`; `border: 1px solid var(--color-tier-edge-gold)` (gold at 55%, decoration); `border-radius: var(--radius-md)`; `padding: var(--mount-gap)`.
- Inner photo: `border-radius: var(--radius-sm)`, `overflow: clip`, `object-fit: cover`, `object-position: var(--focus)`.
- No shadow on espresso (it would not show and would muddy the edge). On cream (Memberships), the outer box is `--color-cream-raised` with `--color-tier-edge` border and `--shadow-tier`, same gap.
- Caption under it (never on it): the existing `.frame-caption` (24px gold hairline, name Signika 500, line Figtree muted inverse).

Proposed tokens (derived, add to `tokens.css` and BRAND section 8):

| Token | Value | Use |
|---|---|---|
| `--mount-gap` | `0.5rem` (8px); `0.375rem` (6px) under 48em | Margin between the gold line and the photo |
| `--band-h` | `min(62svh, 36rem)` | Height of a full-bleed band, desktop |

---

## 3. The moments, one by one

Grid as SPA-PAGE section 4. Every moment is a `<section>` with an `<h2>` (the moment's heading) so the outline reads well; padding-block `--space-6` desktop, `--space-5` phone (same as the rooms). Text never sits on a picture except M3, which uses the veil.

### M1. Before the heat (full-bleed band, words below)

**Picture:** `towel-bench` (fal, section 6), 21:9 desktop, `towel-bench-portrait` 4:5 phone.

**Desktop:** the band runs edge to edge of the screen (not the container), height `--band-h` (496 at 800 tall), no radius (full bleed, like the hero), focus `40% 55%` (the swan embroidery and the bench lip). Under it, inside the container, after `--space-4`: cols 1 to 5, `.frame-caption`: hairline, h2 "Before the heat." (`--text-2xl`, not the small caption size: this is a moment, not a label), then "A swan towel, folded on the bench." `--text-lg` muted inverse. Cols 8 to 12 empty: the quiet is the point.

**Phone:** the band is 4:5 at full screen width (375 x 469), then the words (h2 32px, line `--text-base`).

**Motion:** the photo is a little taller than the band (`height: 112%`, `top: -6%`) and travels from `translateY(-4%)` to `translateY(4%)` as the band crosses the screen (scrubbed, `top bottom` to `bottom top`, ease none), with settle scale 1.06 to 1 from `top bottom` to `center center`. h2 Line rise, line Fade up (`top 80%`). Phone: settle only, no travel.

**Copy row:** `moment_towel`: heading "Before the heat.", body "A swan towel, folded on the bench.", image (upload, optional).

### M2. In every shower (overlapping mounted pair)

**Pictures:** `toiletries` (4:5) and `towel-rail` (3:4), both mounted.

**Desktop:**
- Cols 1 to 4, vertically centred against the pair: `.frame-caption` hairline, h2 "In every shower." `--text-2xl`, line "Toiletries in the swan bottles. A fresh towel on the rail." `--text-base` muted inverse (two lines).
- Cols 6 to 9: `toiletries` mount, 4:5, 432 x 540 including the mount.
- Cols 9 to 12: `towel-rail` mount, 3:4, 288 x 384, its top `--space-7` (96) lower than the toiletries' top, overlapping the toiletries mount's right edge by one gutter (32). It sits in front (`z-index: 1` inside the section only).
- Fit: 540 + 96 = about 640 tall with the offset; section about 0.6 of a screen with padding... the pair's bottom is 96 below the toiletries' bottom; that is fine (content height).

**Phone:** words first; then `toiletries` mount at 78% of the content width, left aligned; `towel-rail` mount at 52% width, right aligned, pulled up `--space-6` over the toiletries' lower right corner. About 620px.

**Motion:** both photos settle (1.05 to 1). Depth: toiletries `data-depth="4"`, towel-rail `data-depth="12"` (the front one travels more, two layers). The mount border is part of the moving element (it moves with its photo; it is not text). Words Line rise + Fade up. Phone: settle only.

**Copy row:** `moment_shower`: heading "In every shower.", body "Toiletries in the swan bottles. A fresh towel on the rail."

### M3. Soft underfoot (full-bleed band, words on the veil)

**Picture:** `slippers` (fal), 21:9 desktop, `slippers-portrait` 4:5 phone.

**Desktop:** band edge to edge, `--band-h`, focus `62% 60%` (the pair of slippers sits right of centre; the left of the frame is the dim travertine floor and wall). Words **on** the band, cols 1 to 5, vertically centred: hairline, h2 "Soft underfoot." `--text-2xl` cream, line "Swan slippers, from the lockers to the loungers." `--text-lg` cream. A left veil like the hero's (`--color-veil` solid to `--bleed + 22rem`, clear by `--bleed + 34rem`); measure cream on it (4.5:1 for the line).

**Phone:** band 4:5 full width, words **below** it (no veil on phone: a 4:5 band has no quiet side), as M1.

**Motion:** as M1 (travel and settle), but the words do not move: they Fade up once at `top 60%` of the band. Phone: settle only.

**Copy row:** `moment_slippers`: heading "Soft underfoot.", body "Swan slippers, from the lockers to the loungers."

Why this differs from M1: M1's words sit below in calm space after the opener; M3 sits between two rooms and carries its words like a magazine spread. Same family of picture, different composition.

### M4. The steel bottle (detail inset on the gym)

No new section. The gym feature (S2d) already supports a detail inset (`Facility.detail_image_name`, SPA-PAGE 3.1). Set it to `bottle-gym` (seed: only when empty) and render that inset as a **mount** instead of the plain `.frame--inset`: 4:5, 192 x 240 including the mount, left edge at col 7, hanging `--space-6` below the gym frame, overlapping its right edge by one gutter (SPA-PAGE S2a rules). `detail_alt`: "A steel Spa 99 bottle on the gym bench". No caption: it is a detail of the gym, the gym's text already sits beside it. Phone: 40% wide, right aligned, pulled up `--space-5` over the frame's bottom edge (existing rule).

### M5. Every visit includes (inside S3, step 2 "Arrive.")

Step 2 today: "Arrive." / "A towel, robe and slippers are waiting." / pills "Towel, robe and slippers", "Your own locker", "Phones stay in the locker".

New: under the step line, before the pills, a row of **four small mounts** with a label under each:
- Mount 1:1, 72 x 72 desktop, 64 x 64 phone (mount gap 6px). Label Figtree `--text-sm` cream, centred, margin-top `--space-2`. Gap between items `--space-4` desktop, `--space-3` phone. Phone: the four fit in one row (4 x 64 + 3 x 16 = 304 ≤ 335).
- Items: Towels (`towel-bench`, focus `45% 50%`), Robe (`robe`, `66% 38%`), Slippers (`slippers`, `62% 60%`), Toiletries (`toiletries`, `50% 55%`). Each `alt=""` (the label says it).
- The first pill ("Towel, robe and slippers") goes (the row says it); "Your own locker" and "Phones stay in the locker" stay.
- `<ul role="list" aria-label="Every visit includes">`.
- Motion: the row Fades up as one group with the step (no stagger: it is a list). Reduced motion: visible.

**Content rows:** `arrive_kit`: heading "Every visit includes", body one item per line as `Label | image-name | focus`, seeded:
```
Towels | towel-bench | 45% 50%
Robe | robe | 66% 38%
Slippers | slippers | 62% 60%
Toiletries | toiletries | 50% 55%
```
Parsed by `pages.services.arrive_kit()` (max 5 items; an unknown image name shows the swan type tile at this size). Update `step_2_pills` to `Your own locker\nPhones stay in the locker` with `replace_copy` (dry run first; exact old wording only).

### M6. On the way out (the tote, inside S4)

S4 today: heading "Find the right way to visit.", the from-price line, two buttons.

New on desktop: cols 10 to 12, one `tote` mount, 4:5, 240 x 300, vertically centred on the band; caption under it: hairline, "On the way out." Signika 500 `--text-lg`. The heading and buttons move to cols 1 to 8 (they fit: heading 2 lines at 48px, buttons side by side under the from-line instead of right-aligned). Phone: the mount sits above the heading at 56% width, left aligned, caption beside... keep it simple: mount, caption, then heading, line, buttons stacked.

Copy row: `moment_tote`: heading "On the way out.", body empty. No price, no "buy", no link: the bag is part of the visit's picture, not an offer.

Motion: mount settle and Fade up with the band. Static: visible.

---

## 4. Data (backend)

- Content rows on page `spa` (create only when missing): `moment_towel`, `moment_shower`, `moment_slippers`, `moment_tote`, `arrive_kit` (section 3). Each row's `image` upload, when set, overrides the default picture.
- Placement: `pages.services.spa_sections()` adds a `moment` key to the sections, so the page never breaks when rooms are hidden or reordered:
  - `towel` goes before the first section (always, after the opener).
  - `shower` goes after the first `tiles` section; if there is none, after the first feature.
  - `slippers` goes after the feature that follows the `shower` moment; if there is none, before S3.
  - A moment whose row has an empty heading is skipped (that is how Moishe turns one off in the admin).
- Gym detail inset: seed `Facility(gym).detail_image_name = "bottle-gym"`, `detail_alt` as above, only when empty.
- Default picture names are passed in the template (`{% photo "towel-bench" override=spa.moment_towel.image %}`), the same pattern as the opener and S3 lockers today.

---

## 5. Echoes elsewhere (small)

### 5.1 Home (owner: leave it more or less; one small touch)

R2 "Then nothing at all." (the rest frame, `relax-loungers`, `.frame--right`): add one `slippers` mount, 4:5, 160 x 200 desktop / 120 x 150 phone, overlapping the frame's lower left corner by one gutter (desktop) or right aligned under it pulled up `--space-5` (phone), `data-depth="12"` like the cold inset, `alt=""`. No new words. Nothing else on Home changes. If it crowds the caption at 1440 in review, drop it: Home is fine without it.

### 5.2 Memberships ("every visit includes")

In the also row (MEMBERSHIPS-R3.md section 3.6): one line with four tiny cream-mounted thumbnails (40 x 40, mount gap 4px, `--color-cream-raised` mount, `--color-tier-edge` border) and "Every visit: towels, robe, slippers and toiletries, and every room." `--text-sm`. Uses the same `arrive_kit` data (labels and images), so it changes in one place.

### 5.3 Gold Card page

Nothing this round (owner's correction). The existing "Each merch release" perk is a separate question (GOLD-PAGE-R3.md section 6).

---

## 6. Images: the owner's mock-ups, and the fal remakes

The mock-ups in `docs/design/reference/amenities/` are the look to match (the embroidery, the bottles, the bag). **Every one has to be remade** for the site: most have clichés in the background, and none is large enough or in the right shape for full bleed.

| Mock-up | Size | Problem | Crop clean? | Decision |
|---|---|---|---|---|
| `robe.jpg` | 768 x 1376 | Salt lamp (reads as a candle), rolled towels on a massage bed, too small | No | Remake `robe` + `robe-portrait` (SPA-OPENER.md section 4) |
| `towel-folded.jpg` | 1536 x 2752 | Stacked stones and eucalyptus behind | Only a tight crop of the towel (no room, no light); not usable full bleed | Remake `towel-bench` + portrait |
| `towel-hanging.jpg` | 1536 x 2752 | Two lit candles and a fireplace behind; chrome rail (we use bronze) | No | Remake `towel-rail` |
| `slippers.jpg` | 1600 x 1600 | Ten pairs reads as a shop display; a soap like a pebble on the shelf | A 4:5 crop of the front pair (x 480 to 1584, y 220 to 1600) is clean and could serve as an interim small mount only | Remake `slippers` + portrait for the band |
| `toiletries.jpg` | 1536 x 2752 | Olive branch, wooden body brush | No (the plant overlaps the left bottle's top) | Remake `toiletries` |
| `steel-bottles.jpg` | 1536 x 2752 | Potted plants behind, three bottles reads as product shot | No | Remake `bottle-gym` (in the gym) |
| `tote-bags.jpg`, `tote-bags-2.jpg` | 1600 x 1600 | Candle, flowers, plants, three bags reads as a shop | No | Remake `tote` (one bag) |

**Method:** FAL-IMAGES.md sections 2 to 4. Attach the mock-up as the subject reference, `docs/design/reference/fal/mark-gold.png` for the swan (and `logo-on-dark.png` where "SPA 99" appears), and one current site photo of the room it sits in for the light and materials. Append the **house style block** (FAL-IMAGES section 3) and the **negative list** (section 4) to every prompt, plus for all of these: `plants, leaves, branches, eucalyptus, olive branch, salt lamp, lamp on a shelf, brush, several products in a row, shop display, price tag, packaging`. If the swan comes out wrong, regenerate with plain fabric or metal there and composite the vector mark in post. Then `scripts/build_images.py` with the warm grade flag.

Generate each wide and tall version as **separate generations of the same scene** (not crops), so both are composed for their frame.

### 6.1 `towel-bench` (M1 band 21:9, 3360 x 1440; M5 thumbnail) and `towel-bench-portrait` (4:5, 1280 x 1600)
Room reference: `dry-sauna-1600.jpg`.
> 21:9: Inside the Finnish dry sauna of a men's luxury spa: a thick white terry towel folded in three lies on the pale aspen bench, the supplied swan mark embroidered in soft gold thread on its top fold, exactly as the reference. The bench runs across the whole frame, with a warm LED light line glowing under its front lip; the curved cedar wall behind is soft and out of focus, with a faint haze of heat in the warm light. The towel sits left of centre at about 40% of the frame width, the right part of the frame is the long empty bench fading into soft warm shadow. Camera low, just above bench height, 50mm, shallow depth of field, the embroidery sharp.
> 4:5: the same towel and bench, vertical frame, towel in the lower middle, the warm wall and bench light above it.

### 6.2 `toiletries` (M2, 4:5, 1280 x 1600; M5 thumbnail)
Room reference: `showers-1600.jpg`.
> Three frosted glass pump bottles with brushed bronze pumps stand in a lit niche of honed travertine in a men's spa shower, each with the supplied swan mark printed in soft gold, exactly as the reference, and no other text. A thin warm LED line lights the niche from above; beside the niche the travertine wall carries a few fine water drops. Calm, close, the bottles sharp. Vertical composition, camera at niche height, 60mm.

### 6.3 `towel-rail` (M2, 3:4, 1200 x 1600)
Room reference: `showers-1600.jpg`.
> A white terry bath towel hangs over a slim brushed bronze rail fixed to a honed travertine wall beside an open rain shower, the supplied swan mark embroidered in soft gold thread low on the hanging end, exactly as the reference. Behind, out of focus, the shower's walnut slatted screen and a warm cove light. Vertical composition, 50mm, shallow depth of field.

### 6.4 `slippers` (M3 band 21:9, 3360 x 1440; M5 thumbnail; Home inset) and `slippers-portrait` (4:5, 1280 x 1600)
Room reference: `relax-loungers-1600.jpg`.
> 21:9: One pair of white terry spa slippers placed neatly side by side on a honed travertine floor at the foot of a curved oak lounger, in the relaxation room of a men's luxury spa. The supplied swan mark is embroidered in soft gold thread on each slipper, exactly as the reference. The pair sits right of centre at about 62% of the frame width; the left of the frame is the dim travertine floor and the base of the wall with a thin warm LED line along it, quiet and darker. Low camera, just above the floor, 50mm, shallow depth of field, the embroidery sharp, the lounger's oak frame soft above.
> 4:5: the same pair, vertical frame, slippers in the lower middle, the lounger's curve above.

### 6.5 `bottle-gym` (M4 inset, 4:5, 1280 x 1600)
Room reference: `gym-1600.jpg`.
> A single brushed stainless steel water bottle with a steel cap stands on the dark leather end of a weight bench in a dark private gym, the supplied swan mark and "SPA 99" engraved into the steel, exactly as the logo reference. A folded white towel beside it. Behind, out of focus, the dark wall panel, warm cove light and the black dumbbell rack. Vertical composition, 60mm, shallow depth of field.

### 6.6 `tote` (M6, 4:5, 1280 x 1600)
Room reference: `door-white-1600.jpg` (the entrance stone and walnut).
> One espresso brown heavy canvas tote bag with brown handles stands on a honed travertine bench by the spa entrance, the supplied swan mark and "SPA 99" printed in soft gold on its front, exactly as the logo reference. A folded cream towel just visible inside the bag. Behind, out of focus, a walnut door frame and warm stone. Vertical composition, 50mm, calm and still.

### 6.7 Priority
`robe` (opener, LCP), `towel-bench`, `slippers`, `toiletries`, `towel-rail`, `bottle-gym`, `tote`. Until a picture exists, its moment is not rendered (the template checks `has_photo` or an uploaded image), so the page never shows a hole.

Alt texts: M1 "A white towel with the gold swan, folded on the sauna bench"; M2 "Three frosted bottles with the gold swan in a stone niche" and "A swan towel on a bronze rail by the shower"; M3 "A pair of white swan slippers by a wooden lounger"; M6 "An espresso canvas bag with the gold swan on a stone bench".

---

## 7. Motion summary and reduced motion

| What | Motion | Phone | Reduced motion / no JS |
|---|---|---|---|
| M1, M3 bands | Photo travels -4% to 4% inside the band (scrubbed) + settle 1.06 to 1 | Settle only | Static, photo at rest |
| M2 mounts | Settle; depth 4 (back) and 12 (front) | Settle only | Static |
| Words of every moment | h2 Line rise once; line Fade up (M3: Fade up only) | Same | Visible |
| M4, M6 mounts | Settle, depth 12 (M4) | Settle | Static |
| M5 kit row | One group Fade up with the step | Same | Visible |

GSAP helpers `settle`, `depth`, `lineRise`, `fadeUp` from `scenes.js`; new `bandTravel(el, scrub)` for the bands (transform only, ease none). Budget stays under 75 KB gzip. Pointer glow on the dark sections as now.

---

## 8. Acceptance checks (screenshots in `.private/shots/spa-amenities/` at 375 x 667 and 1440 x 800)

1. Scrolling The spa at 1440 never shows three room splits in a row; the two bands and the pair break the rhythm.
2. No candle, stone, plant, flower, salt lamp or product line-up in any picture; every swan matches the mark; "SPA 99" is spelled right wherever it appears.
3. Nothing reads as a shop: no prices, "buy", "coming soon", "merch" or links on the bottle, the bag or any amenity.
4. Mounts: a thin gold line, an even margin, the photo with a smaller radius; no caption or label on any photo; the gold line is crisp at 1x and 2x.
5. M3's line is readable on the veil (cream 4.5:1 against the brightest pixel under it at 1440, 1280, 1024).
6. Hiding the showers or the relaxing zone in the admin keeps every moment on the page in a sensible place (section 4 placement rules).
7. Step 2 shows the four mounted items with labels in one row at 375; the pills "Your own locker" and "Phones stay in the locker" follow.
8. Reduced motion: every moment visible at rest, no travel, no depth.
9. A moment without its picture built is not rendered (no empty frame).
10. Home: only the slippers inset is new; Memberships: only the "every visit" line is new.
