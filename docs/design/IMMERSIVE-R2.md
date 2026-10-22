# Spa 99: Home, round 2 (rooms you can see, richer scenes, no pins)

For the frontend agent. Date 2026-10-22. Responds to Moishe's review of the built Home (PROJECT decisions log, last row): keep the dark espresso, editorial, scroll-told direction; fix (1) we cannot see the spa, (2) plain and empty, (3) scroll too slow and pinned in the wrong places.

This file **replaces IMMERSIVE.md section 3 (Home)** and the Home rows of sections 8.4, 9 and 14.1. Everything else in IMMERSIVE.md stays, including section 0 (text groups vertically centred, left aligned, one size smaller). `docs/BRAND.md` wins on any conflict; the BRAND amendments this needs are listed in section 7 and must be applied there before build.

Design read: luxury hospitality marketing for men in London, dark editorial magazine with real architecture in it. Dials for Home: variance 7, motion 5 (was 7), density 4 (was 2).

---

## 1. What changes, in one screen

| Before | Now |
|---|---|
| Hero: render 08 (portrait) full-bleed at 1440, cropped to a wall and a swan | Hero: the architect's reception render (water wall, gold-leaf cove, green wall) shown **whole**, in a large frame that bleeds off the right edge. You see a room |
| Every image full-bleed under a veil | Images live in **frames on espresso** with captions and facts under them. Full-bleed only where the source is big enough (nowhere on Home for now) |
| One image per screen | **Compositions**: a main view, an offset detail, type crossing a frame edge, a caption line |
| Pins: hero +90%, ritual +200%, Gold +60% (4.4 screens pinned, 9.5 total) | **No pins on Home.** About 6.7 screens total at 1440×800 |
| Lenis on (desktop) | Lenis **off** (`data-smooth="off"` on `<html>` in `base.html`; the flag and code stay) |
| Scrub 0.8 / 0.5, snap on the ritual | Scrub **0.4** desktop, **0.3** phone. No snap anywhere on Home |
| Settle 1.12 → 1 | Settle **1.06 → 1** (1.12 is what made it feel zoomed in) |
| Three.js water pass on render 08 | **Parked** on Home (render 08 is no longer the hero; see 6.3). Hero becomes a CSS living still of the reception, then an image-to-video loop of it |

Pins that remain on the site: **The spa S2 room walk** (including the dry sauna walk). Recommendation for the next passes, not part of this task: drop the S1 door, S3 steps, Gold G2 and Visit V2 pins the same way (normal scroll with settle and depth).

---

## 2.0 Amendments from Moishe (2026-10-22, win over this whole file)

1. **Images bleed off their side of the screen.** An image placed on the right runs off the right edge of the viewport (no margin on that side) and gets a slight radius on its **left corners only** (`--radius-md` on top-left and bottom-left, 0 on the right). An image on the left mirrors it: runs off the left edge, radius on its right corners only. This replaces rule 1's "square-cornered frame" and rule 2's "one bleed per scene": **every** photo on Home is an edge-bleed frame unless it is a small detail inset (insets keep a slight radius on all four corners). No plain square boxed images. Alternate sides scene to scene so the page swings left and right.
2. **Phone:** the same idea. The image runs off one side (alternating), full width minus the margin on the other side, radius on the inner corners only.
3. **Small text, but don't overdo it.** Small captions, labels and facts make it feel luxury, but at most 2-3 small lines per scene, neatly aligned to the grid. Never clutter corners just to fill them.
4. Capacity is not shown on Home (Moishe, 2026-10-22). "Then cold." uses `cold-tub` (renders 09/10): Moishe confirmed the wooden tub is the cold plunge.

## 2. The system: how bright renders live on espresso

The architect renders are bright cream and gold. Full-bleed under a dark veil they turn muddy; floating on espresso without care they look like a template. Six rules:

1. **Frames, not backgrounds.** A render sits in a square-cornered frame (`.frame`, photography is always square) with generous espresso around it: at least `--space-6` from any other frame, `--page-margin` from the screen edge unless it deliberately bleeds off one side. The espresso around a bright room reads like walking from a dark corridor into a lit space. That is the feeling.
2. **One bleed per scene.** In each scene at most one frame bleeds off a screen edge (hero: right; ritual: none; inside: none; entry: right). The bleed gives scale; the others give order.
3. **A main view plus a detail.** Where a scene has two images, one is the wide room (large), the other a detail (about 1/3 the area), offset down by `--space-6` and overlapping the main frame's edge by one gutter, or sitting in its own column at a different baseline. Never two equal images side by side.
4. **Type crosses a frame edge** once per scene at most (hero heading, rest caption). Where it crosses, the frame carries its own edge veil (`.frame-veil`: `--color-veil` solid for the first 18% of the frame width, clear by 34%), so every letter is on espresso or on the veil. Never on raw image.
5. **A caption under every frame**, outside the image: room name in Signika 500 `--text-lg` cream, then one line from data (`Facility.short_line`) in Figtree `--text-sm` `--color-text-muted-inverse` (6.50:1). A 24px gold hairline (`--color-gold`, 1px) sits above the room name. No labels on top of images.
6. **The warm grade.** Bake a grade into the files (section 5.3) so the renders sit warm and slightly lower than cream; then a static `.frame-tint` layer (`--color-frame-tint`, espresso 14%) inside every frame. On scroll the tint fades from 0.3 to the resting 0.14 as the image settles: the lights come up as you arrive. Opacity only.

**Richness without clutter (the "plain and empty" fix):**
- **Layered depth:** frame, detail inset and type move at slightly different speeds while you scroll (section 4). Text never moves; only image frames do.
- **The thread** (desktop only): a 1px line in the left margin, x = `calc(var(--page-margin) / 2)`, that draws down the page scene by scene (`scaleY 0 → 1`, scrubbed) and ends at the Gold Card, where the swan draws itself. Gold at 45% on espresso (`--color-thread`), caramel at 60% on cream (`--color-thread-light`). Decoration only. It is the visit, as a line.
- **Real information**, quietly: opening hours, how many guests at once, the eight rooms with one line each, all from data (section 3.3). Density goes from 2 to 4.
- **Living details**: the hero still breathes (24s scale cycle inside its frame), the swan pattern drifts on the entry scene (as built), the "22 hours a day" number counts once, the pointer glow on dark scenes (desktop).

What does not get added: no numbered section labels, no pills on images, no marquee, no scroll cue, no locale strip in the hero, no more than two small uppercase labels on the whole page.

---

## 3. Home, scene by scene

Grid at 1440: 12 columns, column ≈ 80px, gutter 32px, margin 64px. Header 72px desktop, 64px phone. "Centred" means IMMERSIVE section 0 placement.

Scene order: Arrival → The ritual → What's inside → Find your membership → Memberships (cream) → The Gold Card → Opening → footer. Two colour changes (into cream, back to espresso), as before.

### R1. Arrival (hero), 1 screen, not pinned

**Desktop 1440×800**
- Frame `arrival` from cols 5-12, **bleeding off the right edge** of the viewport (≈ 928 × 624). Top at `--header-h + --space-5`, bottom `--space-6` above the screen bottom. Source ratio 1.38:1, frame 1.49:1: `object-position: 42% 60%` keeps the gold cove, the whole water wall, the green wall and the bench. The room is fully visible; nothing is cropped tighter than the source.
- Text group in cols 1-6, vertically centred against the frame: "Beyond / Luxury." `--text-hero` (two lines, ≈ 88px), lead, primary "Find your membership", quiet "See the spa". The second line of the heading runs about one column into the frame, over `.frame-veil` (rule 4).
- Pause control bottom right of the frame, outside the image, `btn-quiet` small.
- Glow on, the thread starts under the heading.

**Phone 375×667**
- Frame `arrival` full width (edge to edge), **36svh tall** (≈ 240px), directly under the header. `object-position: 46% 62%`. At 1.56:1 the phone sees the whole wall: water, gold, green, bench (checked: crop shows the room, not a texture).
- Text group under it on plain espresso (no veil needed): heading two lines, lead, primary full width, quiet link. The group is vertically centred in the space between frame and screen bottom.

**Fit check phone:** header 64 + frame 240 + gap 24 + heading 2×46 = 92 + gap 16 + lead 3 lines 76 + gap 24 + button 52 + gap 12 + quiet link 24 + bottom 24 = **652 ≤ 667**. If the lead runs to 4 lines on a 360px phone, the frame drops to 32svh (min 200px).
**Fit check desktop:** heading 2×88×1.0 = 176 + 24 + lead 2 lines 56 + 40 + button 52 = 348, centred in 688 of usable height. Fine.

**Motion**
- Load: frame fades in from espresso (`opacity 0 → 1`, 1.2s, `soft`) while the inner image goes `scale 1.04 → 1` over 1.6s. Heading Line rise at 0.2s, lead and actions Fade up at 0.5s.
- Living still: inner image `scale 1 → 1.03`, 24s, yoyo, `sine.inOut` (one cycle per 48s). Pauses with the Pause control and when off screen. Steam layer: **removed** (it belonged to the water-wall close-up; the real water wall does not need fake steam).
- Scroll (not pinned): as the hero leaves (`start: "top top"`, `end: "bottom top"`, scrub 0.4), the inner image moves `yPercent 0 → 6` inside the frame (it lags behind, depth), the tint goes 0.14 → 0.35. Text does not move.
- No window effect (it needed the pin). The statement that used to appear in the pinned window moves to R2.

**Static / reduced motion:** identical layout, image at rest, no living still, no glow, no thread. Pause control hidden.

### R2. The ritual, 1 screen desktop (about 2 on phone), not pinned

One statement and three rooms in sequence: heat, cold, rest.

**Desktop 1440×800**
- Heading in cols 1-7 at the top of the composition: "Heat, cold, quiet, and time that is yours." `--text-2xl` (2 lines, ≈ 106px). Word light **not** used (it needs a pin); Line rise on enter.
- Three frames on staggered baselines, each with its caption under it (rule 5):
  - **Heat**: `dry-sauna`, cols 1-4, 1:1 (416 × 416), top aligned. Caption "Heat, slowly." + dry sauna `short_line`.
  - **Cold**: `cold-plunge` when it exists, else `cold-tub` (interim), cols 5-7, 4:5 (304 × 380), starting `--space-6` lower than heat. Caption "Then cold." + cold plunge `short_line`.
  - **Rest**: `relax-loungers`, cols 8-12, 3:2 (528 × 352), top aligned with heat. Caption "Then nothing at all." + relaxing zone `short_line`, and the quiet "See the spa" link after it.
- The rest caption is the scene's one crossing: none needed, captions sit under frames. Keep it calm.

**Phone 375×667** (normal scroll, about 2 screens)
- Heading (3 lines at 32px).
- Heat: full width inside margins, 1:1 (335 × 335), caption.
- Cold: 72% width, **right aligned**, 4:5, pulled up `--space-6` so it overlaps the bottom of the heat frame by 48px (layered depth on phone too). Caption under it, right column.
- Rest: full-bleed edge to edge, 3:2 (375 × 250), caption inside margins.

**Fit check desktop:** header 72 + top pad 40 + heading 106 + gap 40 + tallest column (cold 64 offset + 380 + caption 72) 516 = 774 ≤ 800, with bottom padding coming from the next scene's top. If fonts render larger, heat and rest go to 92% height (`max-height: 48svh` on frames).
**Phone:** about 1,300px. Allowed by the BRAND amendment in section 7 (scenes read in normal scroll may run longer on phone).

**Motion** (all `scrub: 0.4` desktop / `0.3` phone, `start: "top bottom"`, `end: "bottom top"` on the section unless noted)
- Heading Line rise once (`top 80%`).
- Settle on each frame's inner image: `scale 1.06 → 1`, from the frame's `top bottom` to its `center center`.
- Depth: heat frame `yPercent 0` (anchor), cold frame `yPercent 12 → -12`, rest frame `yPercent 5 → -5`. Captions are inside the frame wrappers' columns but **not** inside the moving element (text never moves).
- Tint 0.3 → 0.14 with the settle.
- Captions Fade up once each (`top 88%`), 0.1s apart on desktop (they are a progression), no stagger on phone.

**Static / reduced motion:** same composition, no movement, tint 0.14, everything visible.

### R3. What's inside, 1 screen desktop (about 1.4 on phone), not pinned

The "plain and empty" answer: real facts, the eight rooms, one preview.

**Desktop 1440×800**
- Left, cols 1-5, vertically centred as a group:
  - Heading "What's inside." `--text-2xl`.
  - **Preview frame**, 4:3, cols 1-5 (528 × 396). Default image `showers`. Hovering or focusing a room in the list cross-fades the frame to that room's image (`opacity`, 0.4s, `soft`, desktop with fine pointer only). Rooms without an image keep the current picture. Caption under the frame updates to the room's name (live region off; it is decoration of the list, the list itself carries the text).
  - **Three facts** in a row under the frame, each a number or short phrase in Signika 500 `--text-xl` cream with a one-line label in `--text-sm` muted:
    - "5am to 3am" / "Open every day" (from `OpeningRule` periods: earliest start, latest end).
    - "22" (Count, once) / "hours a day" (computed from the same rules).
    - "25" (Count, once) / "guests at most, at any time" (`SiteSettings.capacity`). **Pending Moishe, question 1.**
- Right, cols 7-12: the **room index**, all visible `Facility` rows in order, as two groups of four (first half, second half; one gold hairline above each group, no line per row). Each row: name in Signika `--text-xl` cream, `short_line` under it in `--text-sm` muted. Each row is a link to `/the-spa/#<slug>` (The spa page anchors). Hover: name goes gold (`--color-gold`, 6.17:1), 0.25s.

**Phone 375×667**
- Heading, then `showers` frame full width 3:2 (335 × 223), then the three facts stacked as one line each ("Open 5am to 3am, every day", "22 hours a day", "Never more than 25 guests"), then the eight rooms as a single list (name + line), one hairline above the list. No hover preview.

**Fit check desktop:** heading 58 + 24 + frame 396 + caption 48 + 32 + facts 64 = 622 ≤ 688 usable. List: 8 rows × 64 + 2 group gaps 40 = 592. Fine.
**Phone:** ≈ 64 + 40 + 58 + 24 + 223 + 32 + 3×28 + 32 + 8×56 + 40 ≈ 1,045px (1.6 screens). Accepted under the section 7 amendment.

**Motion:** heading Line rise; frame settle and tint as R2; list rows Fade up as **one** group (no stagger: it is a list); facts Count once at `top 85%` (never the hours phrase); preview cross-fade on hover. Thread continues in the margin.

**Static / reduced motion:** final numbers, default image, hover swaps the image instantly (no fade).

### R4. Find your membership, 1 screen, not pinned

As built (journey entry, `home-entry.js`, BRAND 7B rules for the tiles), plus one image so it stops feeling empty:

- **Desktop:** text and the tiles in cols 1-6, vertically centred. Frame `lounge` (4:5 crop, focal 55% 60%: curved sofa, window, gold cove), cols 8-12, **bleeding off the right edge**, height 72svh, vertically centred. Caption under it: "The lounge." + kitchenette `short_line` ("Tea, coffee and somewhere to sit after."). Swan pattern drift stays behind everything (as built).
- **Phone:** no image (the fit check is tight with four tiles). As built.

**Motion:** as built, plus frame settle, tint and depth (`yPercent 6 → -6`) on the lounge frame.
**Static:** as built, image at rest.

### R5. Memberships, briefly, 1 screen, not pinned (cream)

As built. Two changes: the thread continues in caramel (`--color-thread-light`), and the rows Fade up as one group on phone. No image (cream renders on cream would go flat; this scene is the breath between two dark chapters).

### R6. The Gold Card, 1 screen, not pinned

As built in layout (swan cols 7-11, text cols 1-5 now vertically centred per section 0). Changes:
- **Not pinned.** The swan Draw plays **once, time-based** (2.4s, `soft`, section 8.7 total 2.4) when the scene reaches `top 55%`, right as the thread arrives: the thread's last segment ends on the scene's centre line and the draw starts there.
- Heading Line rise and body Fade up with the draw (0.6s and 1.2s after it starts).
- Glow on (desktop).

**Static / reduced motion:** filled swan, everything visible.

### R7. Opening, a closing band (about 0.7 screen), not pinned

"January 2027." `--text-hero`, "99 Vale Road, London N4." `--text-lg`, primary "Register interest". `min-height: 70svh` (not a full screen), content vertically centred, footer follows in the same espresso. Motion as built (Line rise, Fade up).

### Totals

Desktop 1440×800: 1 + 1 + 1 + 1 + 1 + 1 + 0.7 = **6.7 screens**, no pins. Phone: about 9 screens of normal native scroll.

---

## 4. Motion implementation (replaces Home in IMMERSIVE 8.4 and 9)

Same `scenes.js` setup and `gsap.matchMedia` (IMMERSIVE 8.2). Home registers no `pinnedScene`. New shared helpers, all created inside the `mm.add` callback so reduced motion reverts them:

```js
const SCRUB = desktop ? 0.4 : 0.3;

function settle(frame) {                                   // inner image arrives, lights come up
  const img = frame.querySelector('.frame-media > *'), tint = frame.querySelector('.frame-tint');
  gsap.timeline({ defaults: { ease: 'none' }, scrollTrigger: { trigger: frame, start: 'top bottom', end: 'center center', scrub: SCRUB } })
    .fromTo(img, { scale: 1.06 }, { scale: 1 }, 0)
    .fromTo(tint, { opacity: 0.3 }, { opacity: 0.14 }, 0);
}

function depth(el, amount) {                               // data-depth="12" on a frame wrapper (never on text)
  gsap.fromTo(el, { yPercent: amount }, { yPercent: -amount, ease: 'none',
    scrollTrigger: { trigger: el.closest('.scene'), start: 'top bottom', end: 'bottom top', scrub: SCRUB } });
}

function thread(scene) {                                   // desktop only
  const line = scene.querySelector('.thread');
  gsap.fromTo(line, { scaleY: 0 }, { scaleY: 1, ease: 'none', transformOrigin: '50% 0',
    scrollTrigger: { trigger: scene, start: 'top 60%', end: 'bottom 60%', scrub: SCRUB } });
}
```

- `depth` values: R2 cold 12, R2 rest 5, R4 lounge 6. Nothing else moves on scroll.
- The hero scroll lag (R1) is `depth`-like on the inner image only: `yPercent 0 → 6`, `start: "top top"`, `end: "bottom top"`.
- `will-change: transform` only on `.frame-media > *` and `[data-depth]`, and only under `html.motion`.
- Phone: settle and depth run (they are cheap transforms), thread and glow do not.
- Lenis: `data-smooth="off"` in `base.html`. Native scroll everywhere. Keep the code path.

Markup sketch (one frame):

```html
<figure class="frame" data-depth="12" style="--focus: 50% 60%">
  <div class="frame-media">{% photo "cold-tub" alt="..." sizes="(min-width: 64em) 22vw, 72vw" %}</div>
  <div class="frame-tint" aria-hidden="true"></div>
</figure>
<figcaption class="frame-caption">...</figcaption>   {# outside the moving element, so text never moves #}
```

(Use a wrapper `div` holding the figure and a sibling caption; the figure is what `depth` moves.)

---

## 5. Images

### 5.1 The 17 provided renders (architect, `02 Launch/Pics/Provided 3D renders`)

Numbered in folder order. All are 1600px wide, so nothing is used full-bleed at 1440 until upscaled (5.4 job 5).

| # | File | Room | Verdict | Why / crop / focal | fal later |
|---|---|---|---|---|---|
| 01 | Fish Tank.jpeg | Reception with aquarium, SPA 99 swan sign, three men in robes | **No** (Home) / maybe The spa | Saturated blue tank fights the palette; pebbles in the planter; recognisable faces. Gold cove is lovely | Remove pebbles; tone the tank warmer; only if Moishe wants the tank shown |
| 02 | Lounge.jpeg | Relaxation room, backlit onyx panels, upholstered loungers | **Yes, The spa** (relaxing zone alt) | TV on the left wall must go. Focal 65% 60% | Remove TV (job 3) |
| 03 | Reception.jpeg | Reception desk, gold cove, linen shelves | **No** | Office monitor, black office chair, coral chandelier. Gold cove top-left usable only as a detail | Not worth it |
| 04 | Showers.jpeg | Showers with fan mosaic, marble column, bench | **Yes, The spa** (showers alt) | Crop right edge (0, 0, 0.80, 1) to drop the foot-spa chair. Focal 35% 55% | none |
| 05 | 10.23.31 (1) | Lounge: green wall, water sheet, curved sofa, window | **No** | iMac in the foreground. 15 shows the same room better | |
| 06 | 10.23.31 (2) | Water spouts, green wall, water sheet | **Spa only, after clean** | Pebbles and glowing balls in the planter | Job 4 |
| 07 | 10.23.31 (3) | Reception desk with iMac and office chair | **No** | Office | |
| 08 | 10.23.31 (4) | Relaxation room, wooden zero-gravity loungers, travertine, moss circles | **Yes, Home R2 rest** (`relax-loungers`) | Clean. Uncropped. Focal 60% 62% (loungers). Phone 3:2 band works as is | Upscale (job 5) |
| 09 | 10.23.31 (5) | Showers behind glass, column, stone bench, wooden tub with steps | **Yes, Home R3** (`showers`) and interim cold (`cold-tub`) | `showers`: crop (0, 0, 0.84, 1) removes the half tub. Focal 30% 55%. `cold-tub`: crop (0.52, 0.28, 1, 1), focal 70% 60%, small use only (≤ 320px wide) | Upscale |
| 10 | 10.23.31 (6) | Corridor, column, wooden tub, frosted door | **No** (spare) | Big tinted glass pane in the left foreground | |
| 11 | 10.23.31 | Reception desk "SPA name", water and green wall | **No** | Placeholder lettering, monitor, pebbles, glow balls | |
| 12 | 19.03.33 (1) | Reception, water curtain, gold cove, "BML SPA" desk | **No** (duplicate of 13, less gold) | | |
| 13 | 19.03.33 (2) | Reception, water curtain, gold-leaf cove, "BML SPA" desk | **Yes, The spa arrival, after clean** (`reception`) | Interim crop (0.40, 0, 1, 1): water curtain, cove, corridor, no lettering. Full frame after job 1 | Job 1 |
| 14 | 19.03.34 (1) | Reception water wall, green wall | **No** (duplicate of 16, less gold) | | |
| 15 | 19.03.34 (2) | Lounge: water wall, green wall, curved sofa, window, gold-leaf ceiling | **Yes, Home R4** (`lounge`) | Uncropped file; frames use 4:5 at focal 55% 60% (sofa, window, gold). Also the kitchenette/lounge room on The spa | Upscale |
| 16 | 19.03.34 (3) | Reception water wall under gold cove, green wall, bench, desk edge | **Yes, Home R1 hero** (`arrival`) | Crop (0.08, 0, 1, 1) removes the partial wayfinding letters and the brass pole. Desktop focal 42% 60%, phone 46% 62% | Job 2, upscale, video (job 6) |
| 17 | 19.03.34 (5) | Corridor: marble column, two doors with brass slats, stone bench | **Yes, The spa** (`corridor`: arrival, "how a visit works") | Uncropped. Focal 50% 55% | none |

Brand checks: no candles, no women; pebbles and placeholder lettering excluded or cleaned; green walls desaturated by the grade (BRIEF 10).

**For The spa later:** arrival `reception` (13 cleaned) or `arrival`; water wall `arrival`; lounge / kitchenette `lounge`; relaxation `relax-loungers` and `relax-onyx`; showers `showers` and `showers-mosaic`; corridor `corridor`. Still missing from any source: wet sauna, cold plunge (N2), massage room, gym (Gemini 12 stays). Dry sauna stays Gemini 14 / the 3D walk.

### 5.2 Names for the build

| Name | Source file (exact) | Crop (left, top, right, bottom) | Used in |
|---|---|---|---|
| `arrival` | `WhatsApp Image 2026-08-26 at 19.03.34 (3).jpeg` | (0.08, 0, 1, 1) | Home R1 (new LCP image) |
| `lounge` | `WhatsApp Image 2026-08-26 at 19.03.34 (2).jpeg` | None | Home R4, The spa |
| `relax-loungers` | `WhatsApp Image 2026-08-20 at 10.23.31 (4).jpeg` | None | Home R2, The spa |
| `showers` | `WhatsApp Image 2026-08-20 at 10.23.31 (5).jpeg` | (0, 0, 0.84, 1) | Home R3, The spa |
| `cold-tub` | `WhatsApp Image 2026-08-20 at 10.23.31 (5).jpeg` | (0.52, 0.28, 1, 1) | Home R2 cold, until `cold-plunge` (N2) exists |
| `reception` | `WhatsApp Image 2026-08-26 at 19.03.33 (2).jpeg` | (0.40, 0, 1, 1) until job 1, then None | The spa |
| `corridor` | `WhatsApp Image 2026-08-26 at 19.03.34 (5).jpeg` | None | The spa |
| `showers-mosaic` | `Showers.jpeg` | (0, 0, 0.80, 1) | The spa |
| `relax-onyx` | `Lounge.jpeg` | after job 3 only | The spa |

`dry-sauna`, `gym`, `door-gold`, `door-white`, `lockers`, `relaxing-zone`, `hero` stay as they are.

### 5.3 How to build them (exact)

`scripts/build_images.py` takes **one folder** and reads every file named in its `SOURCES` dict from it. It **deletes all existing WebP/JPEG outputs first**, so the folder must hold the old Gemini originals too, or those images disappear.

1. Copy originals into the gitignored `.private/renders/` (frontend does this; never into the repo):
   - The seven Gemini files already named in `SOURCES`, from `~/Library/CloudStorage/OneDrive-Personal/BML/Spa 99/01 Branding/Assets/`.
   - The architect files in 5.2, from `.../Spa 99/02 Launch/Pics/Provided 3D renders/`.
2. Add the 5.2 rows to `SOURCES` (same `(filename, crop)` shape). Skip `relax-onyx` until job 3.
3. Proposed (frontend): an optional grade step before resizing for the architect renders only, so they sit warm on espresso: `ImageEnhance.Color(0.85)` (greens down), `ImageEnhance.Brightness(0.94)`, then a warm multiply of channels R ×1.00, G ×0.98, B ×0.93. Flag it per source (a third tuple item `grade=True`), not global.
4. Run from the repo root: `pip install pillow` once, then
   `python scripts/build_images.py ".private/renders"`
5. Swap the Home preload from `photo_srcset "hero"` to `photo_srcset "arrival"` with `imagesizes="(min-width: 64em) 65vw, 100vw"`.

Note: the sources are 1600px wide, so the largest width built is 1600. At 1440 the hero frame is ≈ 928 CSS px (1856 device px on retina): slightly soft until job 5.

### 5.4 fal clean-up jobs (later, in this order)

All image edits with an instruction-editing model (for example FLUX Kontext or Nano Banana edit) at the source resolution; the prompt always ends "Keep everything else exactly the same: camera angle, lighting, materials, colours."

1. **Reception lettering** (13, `19.03.33 (2)`): "Remove the words BML SPA from the front of the curved reception desk, leaving plain honed cream stone with the same texture and light. Remove the computer monitor and the black office chair behind the desk, leaving an empty stone desk top."
2. **Arrival tidy** (16, `19.03.34 (3)`): "Remove the small white pebbles on the floor around the bench base on the left. Remove the partial gold letters on the far left wall."
3. **Relaxation room TV** (02, `Lounge.jpeg`): "Replace the television on the left wall with the same plain travertine wall, continuous with the stone around it."
4. **Water spouts planter** (06, `10.23.31 (2)`, optional): "Remove all pebbles, rocks and the glowing white spheres in the planter at the base of the green wall; replace them with low dark green planting."
5. **Upscale** `arrival` (after job 2), `lounge`, `relax-loungers`, `showers`: 2× with a low-creativity upscaler (for example Clarity upscaler, creativity ≤ 0.2, resemblance high) to 3200px wide. Rebuild; the script then makes 2400w.
6. **Hero loop** (replaces HERO-VIDEO concept A's source): image-to-video from cleaned `arrival`, 8s, 24fps, locked camera: "Locked-off static camera. Only the water moves: a steady curtain of water falls down the backlit travertine wall into the long stone trough, with soft ripples in the trough. Nothing else moves. No people, no camera movement, no light changes. Seamless loop." Landscape 1920×1080 crop of the frame area, and a 1.56:1 phone band. Budgets as IMMERSIVE section 10.
7. **Cold plunge N2** (still the priority render): use BRIEF 10's N2 prompt with render 09 as the image reference and add "same materials and light as the reference: honed travertine, ribbed travertine wainscot, brushed bronze fittings".

---

## 6. Notes for other docs

### 6.1 Copy (content rows, all short)
New Home content keys: `inside` (heading "What's inside."), `facts_hours_label` ("Open every day"), `facts_hours_count_label` ("hours a day"), `facts_capacity_label` ("guests at most, at any time"), `lounge_caption` (uses the kitchenette `short_line`, no new copy). The ritual statement and captions are the existing `statement`, `scene_heat`, `scene_cold`, `scene_rest` rows. Hours and capacity numbers come from `OpeningRule` and `SiteSettings`, never typed into copy.

### 6.2 Contrast (all on espresso unless noted)
Cream on espresso 10.95; gold room-name hover 6.17; muted-inverse captions 6.50; cream heading on `.frame-veil` solid part ≥ 6.5 (same veil value as IMMERSIVE 8.12). Thread and tint are decoration. Cream scene unchanged.

### 6.3 Three.js
IMMERSIVE 14.1 (water pass over render 08) is parked: render 08 is no longer on Home and the frame is not full-bleed. If the job-6 video exists it plays in the hero frame; until then the CSS living still. 14.2 (dry sauna walk on The spa) is unchanged.

---

## 7. Token and BRAND amendments (proposed, derived; add to `tokens.css` and BRAND section 8)

| Token | Value | Use |
|---|---|---|
| `--color-frame-tint` | `rgb(73 46 33 / 0.14)` | Resting tint inside every frame on dark scenes. Decoration |
| `--color-thread` | `rgb(229 172 110 / 0.45)` | The thread on espresso. Decoration |
| `--color-thread-light` | `rgb(187 136 85 / 0.6)` | The thread on cream (caramel). Decoration |
| `--frame-gap` | `var(--space-6)` | Minimum espresso between two frames |

BRAND 7A amendments needed:
- "Every section is one screen" becomes: "Every section fits one screen on desktop. On phone, a scene read in normal scroll (no pin) may run to two screens; nothing inside it may depend on a pin."
- "Scroll drives the story. Pinned scenes scrub ..." becomes: "Scroll drives the story with no pins on Home: image settle (1.06 → 1), depth between image layers, the thread. Pins only where a whole sequence changes in place (The spa room walk). Scrub 0.4 desktop, 0.3 phone."
- "Smooth scrolling (Lenis) only on desktop" becomes: "Smooth scrolling is off (flag `data-smooth`, kept for later)."
- The Draw on Home is time-based on enter, not scrubbed.
