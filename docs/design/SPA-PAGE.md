# Spa 99: The spa page (round 3 house style)

For the frontend and backend agents. Date 2026-10-22. This file **replaces IMMERSIVE.md section 4 (S1 to S4)** and the The spa rows of IMMERSIVE 8.4 and 9. IMMERSIVE section 0 (text centred, one size smaller), IMMERSIVE-R2 sections 2.0, 2 (frames, captions, tint) and 4 (settle, depth, drift helpers) and section 8 (round 3) all apply. IMMERSIVE 14.2 (dry sauna walk) stays, re-homed in section 5 below. `docs/BRAND.md` wins on any conflict.

> **Round 3 (2026-10-23):** S1 is replaced by `docs/design/SPA-OPENER.md` (the robe opener with the changing lines). The amenity moments between the rooms, the gym's bottle inset, "every visit includes" in S3 and the tote in S4 are in `docs/design/AMENITIES.md`. The rest of this file stands.

Design read: luxury hospitality marketing for men in London, dark editorial magazine in the Home round 3 style, with more facts in small type. Dials for this page: variance 7, motion 6, density 5 (Home is 4; Moishe asked for "way more info", neatly placed).

---

## 1. What changes, in one screen

| Now (built) | New |
|---|---|
| Espresso intro: "The spa." left, a square boxed door picture right, a lot of empty space | **The door**: the door picture full screen with the heading on it; on scroll it shrinks into a tall portrait frame bleeding off the right edge (Home's window effect, short pin). Facts and room chips arrive beside it |
| Cream rooms list: index left, eight equal square pictures in a column | **The rooms in four compositions**: a large edge-bleed feature, a row of small portrait tiles (the ad), a wide bleed with a companion inset, a second feature with a companion inset. Every room: picture, name, one line, pills from data |
| Steps as three big words and a 21:9 square picture | **How a visit works**: compact, numbered, with pills from plan and hours data, a scrubbed gold line joining the steps |
| Cream "Find the right way to visit." | Compact espresso closing band, "Tailor your membership" only (2026-10-25: "See memberships" removed), the lowest monthly price from data |
| About 5 tall sections, every picture square | About **6.5 screens** at 1440x800, **8** at 375x667, one short pin, no square boxed pictures |

The whole page is espresso (one theme, as Home's dark chapters). No cream scene: cream renders on cream go flat, and this page is one walk through one building.

---

## 2. Rules carried over (do not re-decide)

- **Edge-bleed frames** (`.frame--right`, `.frame--left`): run off their side of the screen, `--radius-md` on the inner corners only. Sides alternate down the page (order below).
- **Small detail insets and tiles**: `--radius-md` on all four corners (`.frame--inset`).
- **No labels or pills on pictures.** Names, lines and pills sit under or beside the picture, on espresso.
- **Captions**: 24px gold hairline, name in Signika 500, line in Figtree muted inverse (6.50:1).
- **Small text, not too much**: at most one line of description plus one row of pills per room. Pills max 4 per room.
- **Compact**: no `min-height: 100svh` except the opening (it is the pinned window). Every other section is content height with `--space-6` top and bottom (phone `--space-5`).
- **Text never moves on scroll**; only frames, insets and the step line do. Only `transform` and `opacity` (BRAND 7).

Side order down the page: door frame **right** (opening), dry sauna **left**, tiles (insets, no side), relaxing zone **right**, gym **left**, lockers **right**. So the page swings right, left, centre, right, left, right.

---

## 3. Data the page needs (backend)

Everything below is editable in Control. Nothing is typed into templates.

### 3.1 New `Facility` fields

| Field | Type | Use |
|---|---|---|
| `display` | `CharField(choices=feature, tile, companion)`, default `tile` | Which composition the room takes (section 4.2). Not a side: sides alternate automatically |
| `image_name` | `CharField(blank)` | Name of a built render in `content/image_manifest.json`. Replaces the code map `FACILITY_IMAGES` (move its values here in the seed). Order of choice: uploaded `image` wins, then `image_name`, then the type tile |
| `image_focus` | `CharField(blank, default "50% 50%")` | CSS `object-position` for every crop of this picture, e.g. `"40% 60%"` |
| `detail_image` | `FileField(blank)`, same storage as `image` | Optional small inset for a feature room |
| `detail_image_name` | `CharField(blank)` | Built render for the inset, when nothing is uploaded |
| `detail_alt` | `CharField(blank)` | Alt text for the inset. Empty means the inset is decorative (`alt=""`) |
| `facts` | `JSONField(default=list)` | Short pill phrases, shown in order, max 4 (validate in the admin form, 32 characters each). Help text: "Short facts shown as small pills, e.g. 80 to 90°C. Leave empty to show none." |

Keep `name`, `slug`, `short_line`, `description`, `image`, `image_alt`, `order`, `visible` as they are. `description` is now shown (one or two lines, feature and companion rooms only).

Service: `pages.services.facility_cards()` returns, per visible facility in order: `slug, name, line, description, display, facts, image, image_name (only if has_image), focus, alt, detail_image, detail_image_name (only if has_image), detail_alt`. Then a new `spa_sections(cards)` groups them for the template:

- A `feature` starts a section. Every following `companion` joins it (max 1 shown beside it; a second companion becomes a tile).
- Consecutive `tile` rooms form one tile row (2 to 4 tiles). A run of 5 or more splits into rows of 3 and 2.
- A `companion` with no feature before it renders as a tile.
- Feature sides alternate from the first feature: left, right, left (the opening frame is right).

So hiding, reordering or re-classifying a room in Control never breaks the layout.

### 3.2 Seed values (only where a row has no value yet; never overwrite Control edits)

Facts marked **(confirm)** are proposed, typical for a spa of this kind, not measured. They ship only if Moishe confirms (question 1 in the report); otherwise seed them empty and the pills simply do not show.

| slug | display | image_name | image_focus | detail_image_name | facts |
|---|---|---|---|---|---|
| dry-sauna | feature | `dry-sauna` | `50% 55%` | (none until fal) | "80 to 90°C" (confirm), "10 to 15 minutes", "Sit on a towel" |
| wet-sauna | tile | (none: type tile until fal) | | | "About 45°C" (confirm), "Soft steam", "10 to 15 minutes" |
| cold-plunge | tile | `cold-tub` | `100% 62%` | | "Cold water" , "1 to 3 minutes", "After the heat" |
| showers | tile | `showers-mosaic` | `35% 55%` | | "Rain showers", "Towels waiting" |
| relaxing-zone | feature | `relaxing-zone` | `55% 60%` | | "Loungers", "Low light", "No time limit" |
| massage-room | companion | (none: type tile until fal) | | | "Part of your visit" |
| gym | feature | `gym` | `40% 55%` | | "Free weights", "Machines", "Part of your visit" |
| kitchenette | companion | `lounge` | `55% 60%` | | "Tea and coffee", "Somewhere to sit" |

Notes for the seed and Moishe:
- **As built (2026-10-22):** the seed holds only soft facts. No temperatures or times are seeded (Moishe has not confirmed them), so "80 to 90°C", "About 45°C", "10 to 15 minutes" and "1 to 3 minutes" are left out; the values are in `plans/seed.py` `FACILITY_SPA_PAGE` and can be added in Control once confirmed. The massage line is fixed to "A quiet room for massage, part of your visit." (OPS-06), the intro uses `{rooms}`, and the spa button reads "Tailor your membership".
- "Part of your visit" comes from OPS-06 (gym and massage room are part of the same visit, no separate booking or charge). The seeded massage `short_line` says "by appointment", which contradicts OPS-06. Proposed line: "A quiet room for massage, part of your visit." Flag to Moishe; do not change silently.
- The spa intro body "Eight spaces, one quiet visit." hard-codes a number that goes wrong when a room is hidden. Proposed: "Every room, one quiet visit." (change through `replace_copy`, dry run first).
- `spa.next.cta_label` is still "Explore your membership" in `content/seed.py`; it must read "Tailor your membership" (decision 2026-10-22). Update the seed and run `replace_copy` on existing databases.
- Room areas exist in SPA99_RULES section 15 (m²). Not shown: square metres read as a floor plan, not a feeling.

### 3.3 New content rows (`content/seed.py`, page `spa`)

| key | heading | body | cta |
|---|---|---|---|
| `facts_rooms` | (none) | "rooms, one visit" | |
| `facts_hours` | (none) | "every day" | |
| `facts_men` | "Men only" | "18 and over" | |
| `tiles_intro` | "Steam, cold, water." | "Between rounds of heat." | |
| `step_1_pills` | | one pill per line (empty by default; data pills come first) | |
| `step_2_pills` | | "Towel, robe and slippers\nYour own locker\nPhones stay in the locker" | |
| `step_3_pills` | | "Every room is part of the visit" | |
| `next_from` | | "Memberships from {price} a month, {price_inc} inc VAT." | |

"Phones stay in the locker" is OPS-04 (no phones inside). "18 and over" is the sign-up rule. `{price}` and `{price_inc}` are filled from the lowest visible monthly plan (`purchasable_plans()`), GEN-01 shows both.

### 3.4 Data pills computed in `pages.services` (new `visit_pills()`)

- **Book**: "Book {min} to {max} days ahead" from the visible monthly plans' `booking_window_days` (one value: "Book up to {n} days ahead"); "Cancel up to {h} hours before" from `cancel_hours` when all monthly plans agree, otherwise omitted. While `booking_open` is off, add "Booking opens with membership" from a content row, not code.
- **Arrive**: content pills only (`step_2_pills`).
- **Stay**: "Open {range}" from `hours_facts()["range"]`; "Closed for {closure_title()}" when set; then `step_3_pills`.

---

## 4. Scene by scene

Grid at 1440: 12 columns, column 80px, gutter 32px, margin 64px, header 72px. Phone: margin 20px, header 64px. "Centred" means IMMERSIVE section 0.

Order: **S1 The door** (pinned, short) → **S2 Rooms** (four compositions) → **S3 How a visit works** → **S4 Next** → footer.

### S1. The door (the one short pin: `+=50%` desktop, `+=35%` phone)

The striking moment, and the only pin on the page until the dry sauna walk exists.

**Picture:** `door-gold` (frosted glass door, gold swan, stone jambs; 2048 square, sharp at full screen). Content row `spa.intro.image` overrides it.

**Desktop 1440x800, first paint**
- The door full bleed, full screen, `object-position: 58% 45%` (the swan sits in cols 7-10, the stone jamb and dark wood under the words).
- `.hero-veil` as Home round 3: solid under the header and under the words on the left (to `--bleed + 25rem`, clear by `--bleed + 45rem`).
- Words in cols 1-6, centred: "The spa." `--text-hero` (one line, about 88px), the intro body `--text-lg` (one line). Nothing else: no button (the header carries "Tailor your membership").
- Pause control bottom right (living still).

**Desktop end state (after the pin)**
- The window has shrunk into `.door-target`: cols 9-12, **bleeding off the right edge** (480 x 624), top at `--header-h + --space-5`, inner corners radiused (the two espresso corner pieces, as Home). Portrait crop `50% 45%`: the whole swan and the bronze handle.
- The words have **not moved**. Under them, arriving in the last third of the pin:
  1. **Facts row**, three figures in cols 1-6 (each Signika 500 `--text-xl` cream, label Figtree `--text-sm` muted inverse under it):
     - "8" (count of visible facilities, Count once) / `facts_rooms` "rooms, one visit"
     - "5am to 3am" (`hours_facts().range`) / `facts_hours` "every day"
     - `facts_men` "Men only" / "18 and over"
  2. **Room chips**: one `.chip` link per visible room, in visiting order, to `#<slug>` on this page. Wraps to two rows in cols 1-7 (eight chips at about 120 to 150px).
- Fit: heading 88 + 16 + lead 28 + 40 + facts 64 + 32 + chips 2 x 44 + 8 = **364px**, centred in the 688px under the header. The frame is 624 tall. Calm, not empty.

**Phone 375x667**
- First paint: the door full screen, focus `55% 40%`. Words in the lower half on the bottom veil (solid to 54%, clear by 80%, as Home).
- End state: the window shrinks to `.door-target` at the top: bleeds right, `--page-margin` on the left, height 38svh (about 253px), inner corners radiused. The words stay where they are. Under them: facts as a three-column row (figures `--text-lg`, labels `--text-sm`, 103px each), then the chips as **one horizontal scroll line** (no wrap; scroll-snap proximity, `overscroll-behavior-x: contain`, the line runs off the right edge so the next chip peeks).
- Fit: header 64 + 12 + frame 253 + 24 + heading 44 + 8 + lead 2 lines 52 + 24 + facts 60 + 20 + chips 44 + 24 bottom = **629 ≤ 667**. If the lead runs to three lines, the frame drops to 34svh.

**Motion** (reuse `windowTo`, IMMERSIVE 8.6, exactly as Home R1; scrub 0.5 desktop, 0.3 phone)
| Pin progress | What moves |
|---|---|
| Load | Window fades in from espresso (opacity 0 to 1, 1.2s, `soft`), inner image scale 1.04 to 1 (1.6s). Heading Line rise at 0.2s, lead Fade up at 0.5s |
| 0 to 0.7 | Window shrinks onto `.door-target` (counter-scaled, the picture stays a pure crop) |
| 0 to 0.45 | Veil holds at full strength while the picture is still under the words |
| 0.45 to 0.7 | Veil opacity 1 to 0 (the picture has left the text column); frame tint 0 to 0.14; corner pieces fade in |
| 0.66 to 1 | Facts Fade up as one group; "8" Counts (1.2s, once); chips Fade up as one group (no stagger, it is a list) |

Living still: inner image scale 1 to 1.03, 24s yoyo, `sine.inOut`, paused by Pause, off screen and when hidden.

**Static / reduced motion / no JS:** only the end state, as a normal section of content height: frame right, words, facts with final numbers, chips. No full-screen first paint (shorter than Home's static hero on purpose). Header solid.

### S2. The rooms

Four compositions from `spa_sections()`. Each room is an `<article id="<slug>">` with an `<h2>` (the name), `scroll-margin-top: calc(var(--header-h) + var(--space-4))` so the chips and Home's "What's inside" links land cleanly. With the seed data:

#### S2a. Feature, picture left: Dry sauna (about 0.85 screen)

**Desktop**
- Frame `dry-sauna` `.frame--left`: from the left screen edge to the end of col 7 (816 x 544, 3:2), height capped at `--frame-h-feature`. Inner corners (right) radiused.
- **Detail inset** (when the room has one): `.frame--inset` 4:5, 192 x 240, its left edge at col 7, hanging `--space-6` below the frame's bottom and overlapping its right edge by one gutter. Until fal makes the dry sauna detail there is no inset (`door-gold` is already the opening, never twice on a page).
- Text in cols 9-12, centred against the frame: gold hairline; name `--text-2xl`; `short_line` `--text-lg` cream; `description` `--text-base` muted inverse (max 2 lines); pills row (`.pills`, max 4).
- This is where the **dry sauna walk** sits later (section 5).

**Phone:** frame bleeds left, `--page-margin` on the right, 4:3 (355 x 266). Inset (if any) 40% wide, right aligned, pulled up `--space-5` over the frame's bottom edge. Then hairline, name (`--text-2xl` = 32px), line, description, pills (wrap). About 600px.

#### S2b. Tile row: Wet sauna, Cold plunge, Showers (about 0.9 screen)

Moishe's "small boxes with pics", the ad's tall tiles.

**Desktop**
- Cols 1-3: `tiles_intro` heading "Steam, cold, water." `--text-2xl` (2 lines) and its body `--text-base` muted inverse, top aligned with the first tile.
- Cols 4-6, 7-9, 10-12: three `.room-tile`s, each a `.frame--inset` at 3:4 (304 x 405), all corners radiused. **Staggered**: the middle tile starts `--space-6` lower, the third `--space-4` lower (the ritual's rhythm, not three equal cards).
- Under each tile: hairline, name `--text-lg`, line `--text-sm` muted inverse, pills (`.pill`, wrap, max 3 shown on tiles).
- A room with no picture shows the **type tile** (`.frame--type`): `--color-espresso-raised`, the swan pattern at `--color-pattern`, the swan mark 64px in gold centred, nothing written on it (the name is under it as for every tile). Reads as a deliberate brand tile, not a hole.
- With 2 tiles: cols 5-8 and 9-12. With 4: cols 1-3 become a tile too and the intro moves above the row.

**Phone**
- Intro heading and body, then the tiles as a **horizontal scroll row**: tiles 72vw wide (270 x 360), gap `--space-3`, first tile on the page margin, the next one peeking. `scroll-snap-type: x proximity`, `scroll-snap-align: start`, `scroll-padding-inline: var(--page-margin)`, `overscroll-behavior-x: contain`, no visible scrollbar. The row is a `<ul>` with `aria-label` from the intro heading, focusable (`tabindex="0"`) so arrow keys scroll it. Captions sit under each tile inside the row. About 570px.

#### S2c. Feature, picture right, with companion: Relaxing zone + Massage room (about 0.8 screen)

**Desktop**
- Frame `relaxing-zone` `.frame--right`: from col 6 to the right screen edge (816 x 408, 2:1, the wide render shown wide), inner corners (left) radiused.
- Text in cols 1-4, centred against the frame: relaxing zone hairline, name `--text-2xl`, line, description, pills.
- **Companion** under it, after `--space-5`: a row with a `.frame--inset` 4:5 thumbnail (120 x 150; massage room has no picture yet, so the type tile at this size) and beside it the companion's name `--text-lg`, line `--text-sm` muted, pills. The companion is its own `<article id="massage-room">` with its own `<h2>`.

**Phone:** frame bleeds right, margin left, 16:9 (355 x 200). Text. Companion row: thumbnail 96 x 120 left, text right. About 640px.

#### S2d. Feature, picture left, with companion: Gym + Kitchenette (about 0.8 screen)

Same composition as S2c, mirrored and with a different frame shape so it does not read as a repeat:
- Frame `gym` `.frame--left`, left screen edge to the end of col 7, **16:10** (816 x 510). The gym render is dark: tint stays at 0.14, no extra veil.
- Text cols 9-12. Companion: kitchenette with `lounge` as the 4:5 thumbnail (focus `55% 60%`: sofa, window, gold).
- Phone: as S2c, mirrored (frame bleeds left).

Three image-and-text splits do not run in a row: S2a, then the tile row breaks the pattern, then S2c and S2d (two), then S3 changes the family again (steps).

**Motion, all rooms** (scrub 0.4 desktop / 0.3 phone; helpers from IMMERSIVE-R2 section 4 and round 3)
- Room name: Line rise once (`top 80%`). Line, description: Fade up with it. Pills: Fade up, 0.06s apart on desktop (they read as a short sequence), one group on phone.
- Feature frames: settle (inner image 1.06 to 1, tint 0.3 to 0.14, from the frame's `top bottom` to `center center`) and depth `data-depth="4"`.
- Detail insets and companion thumbnails: depth `data-depth="12"` (they travel more than the big frame: two layers of depth).
- **Scrubbed detail**: the gold hairline above each feature name draws `scaleX 0 to 1` (transform origin left), scrubbed from `top 85%` to `top 55%` of its article. On tiles it is a plain Fade up (too small to scrub).
- Tile row, desktop: settle on each tile, depth `0 / 10 / 5` (left, middle, right), so the staggered tiles drift apart and back as you pass. Captions drift 12px against their tile (`data-drift`). Phone: settle only on the tile in view; no depth inside the horizontal row (it would fight the swipe).
- Pointer glow on (desktop, fine pointer), as Home.

**Static / reduced motion:** the same compositions at rest. Tint 0.14, hairlines drawn, everything visible. The phone tile row still scrolls sideways (that is layout, not motion); `scroll-behavior` stays `auto`.

### S3. How a visit works (about 0.85 screen)

**Desktop**
- Frame `lockers` `.frame--right`: from col 8 to the right screen edge (624 wide), height `min(60svh, 30rem)` (480), focus `70% 50%` (the swan lockers). Content row `spa.how_it_works.image` overrides it.
- Cols 1-6: heading "How a visit works." `--text-2xl` (it is visible now, no longer `sr-only`). Under it an `<ol>` of three steps, `--space-5` apart. Each step is a two-column row:
  - Left (48px): the number "1", "2", "3" in Signika 500 `--text-lg` gold (6.17:1). A 1px vertical line (`.steps-line`, `--color-thread`) runs from under "1" to above "3" behind the numbers.
  - Right: the word ("Book.", "Arrive.", "Stay.") Signika 500 `--text-xl`, its line `--text-base` muted inverse, then its pills (section 3.4).
- Under the steps, after `--space-5`: the opening hours as a small two-column `dl` (`opening_hours()`, `--text-sm`, labels muted inverse, values cream), max 5 rows, and a quiet link "Visit us".
- Fit: heading 58 + 32 + 3 x (30 + 26 + 8 + 36) + 2 x 40 = 470 + 40 + hours 5 x 22 = 620. Centred against the 480 frame, the text runs past it; that is fine (content height, no forced screen).

**Phone:** heading, frame bleeding right 4:3 (355 x 266), steps (number column 32px), hours, link. About 900px.

**Motion**
- Heading Line rise. Each step Fades up as it enters (`top 85%`), not staggered from one trigger.
- **The step line draws**, scrubbed: `.steps-line` `scaleY 0 to 1` (origin top) from the `<ol>`'s `top 70%` to `bottom 60%`. Each number goes from opacity 0.4 to 1 at the moment the line reaches it (three short scrubbed tweens on the same trigger at 0, 0.5, 1). Opacity only, the gold never changes value.
- Lockers frame: settle and depth 6.

**Static:** line drawn, numbers at full opacity.

### S4. Next (closing band, about 0.45 screen)

As Home's Opening band: a hairline on top (`--color-hairline-inverse`), espresso, content height.
- **Desktop:** cols 1-7: "Find the right way to visit." `--text-2xl`, then `next_from` `--text-sm` muted inverse ("Memberships from £X a month, £Y inc VAT."). Cols 8-12, aligned to the heading's baseline at the right: primary "Tailor your membership" (journey) and secondary "See memberships" (memberships page), side by side.
- **Phone:** heading, line, both buttons full width, stacked (primary first).
- Swan pattern drift behind, as Home's entry scene, at `--color-pattern`.
- **Motion:** Line rise, Fade up. Static: visible.

Footer follows in the same espresso.

### Totals

| Scene | 1440x800 | 375x667 |
|---|---|---|
| S1 The door (1 screen + pin) | 1.5 | 1.35 |
| S2a Dry sauna | 0.85 | 0.9 |
| S2b Tiles | 0.9 | 0.85 |
| S2c Relaxing zone + massage | 0.8 | 0.95 |
| S2d Gym + kitchenette | 0.8 | 0.95 |
| S3 How a visit works | 0.85 | 1.35 |
| S4 Next | 0.45 | 0.6 |
| **Page (without footer)** | **about 6.2** | **about 7** |
| With footer | about 6.6 | about 8 |

The old spec was about 12 screens at 1440 with 7.4 screens pinned.

---

## 5. The dry sauna walk (IMMERSIVE 14.2), later

- **Where:** inside S2a, in the dry sauna feature frame. The words stay in cols 9-12 beside it, so the canvas needs no veil and no caption on top.
- **Until it exists (now):** the `dry-sauna` render with settle and depth, as specified in S2a. Phones, reduced motion and every gate failure keep this forever.
- **When it ships (desktop, gate passed):** S2a pins (`start: "top top"`, `end: "+=180%"`, scrub 0.4), and the frame grows to the full stage height while pinned. Walk time `w` 0 to 3 maps over the pin exactly as 14.2's storyboard; the hold at D ends the pin; no snap. Labels and the S2 room pin of 14.2 no longer exist (there is no room walk pin), so the "wet sauna cross-fades in" handover is replaced by the pin simply ending and the tile row scrolling up.
- **Pin budget:** that would make two pins on one page (S1 and the walk). Question 2 in the report. The recommendation: when the walk ships, S1 keeps its window effect but loses its pin (the window shrink runs scrubbed from `top top` to `bottom top` over the section's own height, about 0.6 screen), so the walk is the page's one pin.

---

## 6. Images

### 6.1 Now (current manifest) and later (fal)

| Place | Now (manifest name, focus) | Later (fal file name to build) | Size to generate |
|---|---|---|---|
| S1 The door | `door-gold` `58% 45%` desktop, `50% 45%` frame | keep (it is the brand moment); optional upscale | n/a |
| Dry sauna (feature) | `dry-sauna` `50% 55%` | `dry-sauna-2` and inset `dry-sauna-detail` | 3:2, 2400x1600; inset 4:5, 1280x1600 |
| Wet sauna (tile) | type tile | `wet-sauna` | 3:4, 1536x2048 |
| Cold plunge (tile) | `cold-tub` `100% 62%` (768px: fine at tile size, soft above) | `cold-plunge` | 3:4, 1536x2048 |
| Showers (tile) | `showers-mosaic` `35% 55%` | `showers-2` | 3:4, 1536x2048 |
| Relaxing zone (feature) | `relaxing-zone` `55% 60%` | `relaxing-zone-2` | 2:1, 2800x1400 |
| Massage room (companion) | type tile | `massage-room` | 4:5, 1280x1600 |
| Gym (feature) | `gym` `40% 55%` | `gym-2` | 16:10, 2560x1600 |
| Kitchenette (companion) | `lounge` `55% 60%` | `kitchenette` | 4:5, 1280x1600 |
| S3 How a visit works | `lockers` `70% 50%` | keep | n/a |

Swapping later is data only: build the file with `scripts/build_images.py`, then set `image_name` (or upload `image`) on the Facility in Control. No template change.

Not used on this page: `fish-tank` (Home's hero; never repeat the hero image on the next page), `door-white` (same door as `door-gold`), `hero` (render 08: a water wall that the building no longer has, since the fish tank replaced it), the architect renders except `lounge` (Moishe dislikes them; `lounge` stays only as a 120px thumbnail until `kitchenette` exists).

### 6.2 fal prompts

Model: a text-to-image model with image references (for example Nano Banana Pro or FLUX Kontext Pro). Attach two references to every job: the "Escape the Everyday" ad (`02 Launch/Ads/Escape the Everyday.png`, for the look) and the swan mark PNG (`common/static/common/img/` mark export, for the swan). If the model mangles the swan, regenerate with a **plain** panel in its place and composite the real vector mark in post; never ship a wrong swan. Then grade and build as IMMERSIVE-R2 5.3 (warm grade flag on).

**Shared ending for every prompt** (append verbatim):
"Photorealistic architectural interior photograph of a men's luxury day spa in London, in the same look as the reference ad: warm low light around 2700K, soft indirect LED cove lines, honed travertine and warm oak or cedar, brushed bronze details. Calm, finished and empty. No people. No candles, no pebbles or stacked stones, no flowers, no plants in water, no towels with stones, no screens or televisions, no fireplace, no text or lettering except where described. Eye-level camera, 28 to 35mm lens, straight verticals, natural depth of field, warm grade, colours kept to cream, caramel, espresso and gold."

1. **`dry-sauna-2`** (3:2): "A Finnish dry sauna. Light aspen benches in one wide stepped bench across the room, a curved cedar ceiling that sweeps down into the back wall, warm LED strips under each bench lip and along the curve of the ceiling. The heater is centred on a split-stone feature wall, a dark metal heater with sauna stones only inside its cage. A frosted glass door on the right with a small gold swan at eye height. A faint haze of heat. Camera from the door looking towards the stone wall." (Matches the 3D walk, Concept B.)
2. **`dry-sauna-detail`** (4:5): "Close-up of the corner of the dry sauna bench: aspen slats, the warm LED line under the bench lip, a folded cream towel with a small embroidered gold swan, a wooden bucket and ladle out of focus. Shallow depth of field."
3. **`wet-sauna`** (3:4): "A steam room clad in honed travertine with a curved travertine bench along two walls and a low vaulted ceiling with small warm downlights. Soft steam fills the room and catches the light. A thin warm LED line under the bench. A clear glass door with a bronze handle. Vertical composition."
4. **`cold-plunge`** (3:4, add the ad "The coolest part.png" as a third reference: it is the real tub): "A round cold plunge tub built from vertical oak slats with a pale rim, filled with still, clear, very cold water, wooden steps with a handrail beside it. Pale veined marble floor and walls, a marble column behind, a warm cove light along the ceiling, the gold swan and 'SPA 99' in brushed gold on the right wall. A finished room: no tools, lamps, wires or building materials. Vertical composition."
5. **`showers-2`** (3:4): "Open rain showers: two square ceiling rain heads over a travertine floor with a linear bronze drain, walnut slatted screens between the showers, a lit niche in the travertine wall holding bronze bottles with the small gold swan. A few water drops on the floor, no water running. Vertical composition."
6. **`relaxing-zone-2`** (2:1): "A relaxation room with travertine walls and vertical warm LED lines between the panels, a row of four upholstered cream zero-gravity loungers on curved oak frames, each with a folded caramel throw, small travertine side tables, a recessed brushed-gold swan on the end wall. Low, even warm light. Wide composition."
7. **`massage-room`** (4:5): "A small private massage room: a padded massage table with a cream linen cover on a walnut base, an oak slatted wall behind it, a niche with folded white towels embroidered with the small gold swan, a bronze wall light, dimmed warm cove light. Vertical composition."
8. **`gym-2`** (16:10): "A dark private gym. Smoked oak floor, espresso plaster walls, a large brushed-gold swan mark on a dark wall panel, warm LED cove lines in the ceiling and backlit shelves. A dumbbell rack, one cable machine, a bench and a treadmill by a tall window with the night outside. Never crowded: empty."
9. **`kitchenette`** (4:5): "A small lounge kitchenette: a travertine counter with a built-in bronze coffee machine and a kettle, a row of cream cups, an open oak shelf, two low lounge chairs in caramel bouclé around a small round travertine table, a warm pendant light. Vertical composition."

Priority: `cold-plunge`, `wet-sauna`, `massage-room` (the three rooms with no or weak picture), then `dry-sauna-2`, `gym-2`, `relaxing-zone-2`, `showers-2`, `kitchenette`, `dry-sauna-detail`.

---

## 7. Classes and tokens

### 7.1 Reused from Home (no change)

`.frame`, `.frame-media`, `.frame-tint`, `.frame--right`, `.frame--left`, `.frame--inset`, `.frame-caption` (hairline, name, line), `.hero-veil`, `.hero-corner`, `.hero-pause`, `.pills`, `.pill`, the facts figure markup from Home R3, `data-depth`, `data-drift`, `data-rise`, `data-fade`, `data-pill`, and the `scenes.js` helpers `lineRise`, `fadeUp`, `settle`, `depth`, `drift`, `windowTo`, `count`, `initGlow`.

Note: `.tile` is already the journey's choice tile (components.css). Do not reuse that name for picture tiles.

### 7.2 New classes (put them in a new `common/css/spa.css`, imported by `app.css` after `scenes.css`, so they do not collide with the Home work going on now)

| Class | What |
|---|---|
| `.door-scene`, `.door-target` | S1 (same structure as `.hero-first` / `.hero-end` / `.hero-target`; share the CSS where the frontend can) |
| `.chips`, `.chip` | Room links. `.chip`: inline-flex, `min-height: var(--chip-h)` (44px tap target), padding `0 var(--space-3)`, 1px border `--color-control-line` (3.09:1 on espresso, UI contrast), `--radius-md`, `--text-sm`, cream. Hover (fine pointer): border and text `--color-gold`, 0.25s `soft`. Focus: 2px `--color-focus-inverse` outline, 3px offset. `.chips--scroll` (phone): one line, horizontal scroll, snap proximity |
| `.room` | An article: `scroll-margin-top`, grid placement by modifier |
| `.room--feature`, `.room--left`, `.room--right` | S2a, S2c, S2d |
| `.room-companion` | The thumbnail row inside a feature |
| `.room-tiles`, `.room-tile` | S2b row and one tile. `.room-tiles` becomes the horizontal scroll row under 48em |
| `.frame--type` | The type tile: espresso-raised, swan pattern, centred gold mark, `aria-hidden` picture part |
| `.steps`, `.step`, `.steps-line`, `.step-num` | S3 |
| `.next-band` | S4 (shares Home's opening band CSS if the frontend extracts it) |

Pills are text only (no icons), never on pictures, never links.

### 7.3 Proposed token additions (derived, add to `tokens.css` and BRAND section 8)

| Token | Value | Use |
|---|---|---|
| `--chip-h` | `2.75rem` | Height of a link chip (44px tap target) |
| `--pill-h` | `2rem` | Height of a static pill (the value Home's `.pill` already uses inline; move it to a token) |
| `--frame-h-feature` | `min(68svh, 34rem)` | Max height of a feature frame (desktop) |
| `--tile-w-phone` | `72vw` | Width of a tile in the phone scroll row |
| `--ratio-tile` | `3 / 4` | Tile aspect ratio |

No new colours. Contrast used on this page: cream on espresso 10.95; muted inverse 6.50; gold numbers and chip hover 6.17; cream on espresso-raised (type tile) 9.45; chip border 3.09 (UI). Words on the S1 veil: same veil as Home round 3; measure cream against the brightest pixel under the words on `door-gold` at 1440, 1024, 375 and 360 (needs 4.5 body, 3 headings) and darken the veil if any fails.

---

## 8. Implementation notes (frontend)

- `pages/templates/pages/spa.html` is rebuilt. `spa-index.js` is no longer needed (the chips are plain anchors); remove it from the template.
- `scenes.js`: add `SCENES.door` (copy of `SCENES.hero` with the new selectors, or a shared function both call), `SCENES.rooms`, `SCENES.steps`, `SCENES.next`. Nothing new in the vendor set; JS budget stays under 75 KB gzip.
- Page sets `data-page="marketing"` and `header_mode overlay` (dark first screen).
- `<link rel="preload">` the `door-gold` srcset with `imagesizes="100vw"` (LCP image).
- Every `{% photo %}` passes `override=` (the uploaded file) and the Facility's `image_focus` as `style="--focus: ..."`.
- Rooms with `facts` empty render no `.pills` element at all.
- Screenshots for review: `.private/shots/spa/` at 375 and 1440, static and motion, at S1 first paint, S1 mid pin, S1 end, each room composition, S3, S4.
