# Spa 99: The spa opener (round 3)

> **Update 2026-10-23 (Moishe, video):** the robe opener is now Moishe's steam video (`Vapour.mp4`), files `spa-hero-*` in `content/static/content/video/` (details in SOURCES.txt). The loop's fade is baked into the file (the last 1.5 s cross-fade into the first frames), so `<video loop>` restarts invisibly. The video's first frame (the posters, preloaded) is the full-screen still and the frame's picture; the still no longer breathes when a video will play. The video plays inside the same window and keeps playing once shrunk into the right frame; it pauses only off screen or with the tab hidden. Reduced motion or Save-Data: the poster only. No Pause control. Phone: the portrait file (crop round the robe), framed like the poster (`object-position` 50% 30%; desktop 64% 40%). An upload on `intro` replaces the robe and drops the video (`opener_picture()["video"]`). The door's later video (SPA-DOOR-VIDEO.md) uses the same hook.
>
> **Update 2026-10-23 (Moishe, later):** the hero keeps **one line only**: "Open 5am to 3am." with "Every day. Closed for Shabbos and Yom Tov.", then straight to the room chips. Lines 2 to 4 (men only, heat and steam, stay as long as you like) and the ticks are gone from the hero; their `opener_2..4` rows stay in the database, unrendered (`OPENER_HERO_LINES = 1` in `pages/services.py`; an empty line 1 is never replaced by a later row). The pin goes back to Home's length (`--opener-pin` 0.35 phone, 0.5 from 64em) so nobody stops mid-scroll. The gold hairline shows above the statement with and without motion. Mentions of four lines, the cross-fade and the ticks below are superseded.
>
> **Update 2026-10-23 (Moishe):** the Pause control is removed from The spa opener (and Home). The living still keeps its tab-hidden, out-of-view and reduced-motion stops. Mentions of Pause below are superseded.

For the frontend and backend agents. Date 2026-10-23. Replaces **SPA-PAGE.md section 4 S1** (picture, first-paint words, facts row and motion table). Everything else in SPA-PAGE.md stays. The moments woven through the rest of the page are in `docs/design/AMENITIES.md`; the later door video is in `docs/design/SPA-DOOR-VIDEO.md`. `docs/BRAND.md` wins on any conflict.

Owner's words (PROJECT.md 2026-10-23): the full-screen gold swan door is too zoomed in; drop "Eight spaces, one quiet visit."; more text in the opening, and the text changes as you scroll, one line fading out as the next comes in. Then: "the robe gives it a crazy kind of vibe", try the robe hanging as the hero. The door video stays an option for later.

Design read: dark editorial hotel magazine. One quiet object (a robe on a bronze hook) at full screen, four short facts read one at a time while the picture settles into its frame. Dials: variance 7, motion 6, density 3 (this screen only).

---

## 1. What changes, what must not

| Keep exactly (approved, owner likes it) | Change |
|---|---|
| The method: full-screen picture, then on scroll it shrinks into the edge-bleed frame on the right (`windowTo`, same smoothness as Home's arrival) | The picture: `door-gold` (too zoomed) becomes `robe` (new fal photo, section 4). `door-wide` is the alternative (section 6) |
| One short pin, scrubbed, no snapping | The pin gets a little longer (`+=80%` desktop, `+=60%` phone, was 50% / 35%) because four lines now read inside it. Still one flick or two on a trackpad |
| "The spa." as the h1, `--text-hero` | The lead "Eight spaces, one quiet visit." goes. In its place: **the line stack** (section 2), four facts that change as you scroll |
| The room chips (`.chips`), arriving at the end | The facts row (8 / 5am to 3am / Men only) goes: the lines now carry those facts. It stays only in the static layout, as the stacked lines |
| Pause control, header overlay, preload of the LCP picture, the end-state frame on the right | The veil is narrowed for this scene (section 3.3), because the robe is white and sits right of centre |

Do not touch: Home, the header, the chip styles, `windowTo`, the room sections, S3 and S4 (except what AMENITIES.md adds).

---

## 2. The lines (copy and data)

Four lines. Each is a **statement** (Signika) and a **note** (Figtree, small). British English, facts from the data only, no exclamation marks.

| # | Statement | Note | Source |
|---|---|---|---|
| 1 | Open {hours}. | Every day. Closed for {closure}. | `hours_facts().range` ("5am to 3am"), `closure_title()` ("Shabbos and Yom Tov"); CAL-01, CAL-07 |
| 2 | For men only. | 18 and over. | OPS-01, ACC-08 |
| 3 | Heat, steam, cold and rest. | {Rooms} rooms, all part of the same visit. | `{Rooms}` = count of visible facilities in words, capitalised ("Eight"); OPS-06 |
| 4 | Stay as long as you like. | Your robe and slippers are waiting. | BK-11; amenities decision 2026-10-23 |

Rendered: "Open 5am to 3am." / "Every day. Closed for Shabbos and Yom Tov." and so on.

Rules: if `hours_facts()` is None, line 1 is skipped (never print "Open ."). If no closure is set, the note is "Every day." Line 3's note uses the word for the count, so hiding a room never leaves a wrong number. Line 3 deliberately does not open with the number (the owner disliked "Eight spaces...").

### 2.1 Content rows (backend, `content/seed.py`, page `spa`; only create what is missing, never overwrite)

| key | heading | body |
|---|---|---|
| `opener_1` | `Open {hours}.` | `Every day. Closed for {closure}.` |
| `opener_2` | `For men only.` | `18 and over.` |
| `opener_3` | `Heat, steam, cold and rest.` | `{Rooms} rooms, all part of the same visit.` |
| `opener_4` | `Stay as long as you like.` | `Your robe and slippers are waiting.` |
| `opener_image` | (none) | `robe` (the manifest name of the opener picture; `door-wide` switches to the door, section 6) |

Placeholders filled in `pages.services` (new `opener_lines()`): `{hours}`, `{closure}`, `{rooms}` (lower case word), `{Rooms}` (capitalised). Returns a list of `{statement, note}`, skipping rows with an empty heading, max 5 (the motion handles 2 to 5 lines; with 1 line it simply shows it, no change on scroll).

The old intro body ("{rooms} spaces, one quiet visit.") is no longer rendered. Leave the row in the database (no destructive change). `facts_rooms`, `facts_hours`, `facts_men` are no longer rendered either.

`spa.intro.image` (upload) still overrides everything. Order of choice for the picture: upload, then `opener_image` name, then `robe`.

---

## 3. Layout

Grid as SPA-PAGE section 4 (12 columns at 1440: column 80, gutter 32, margin 64; header 72. Phone margin 20, header 64).

### 3.1 Desktop 1440 x 800, first paint

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ header (overlay)                                                             │
│                                                                              │
│  The spa.                                              ╭───╮  bronze hook    │
│                                                        │   │                 │
│  Open 5am to 3am.                                    the robe, swan on the   │
│  Every day. Closed for Shabbos and Yom Tov.          chest, cream wall,      │
│  ─ ─ ─ ─   (four ticks, the first lit)               warm room behind left   │
│                                                                              │
│  solid veil ............. soft ..... clear                         Pause     │
└──────────────────────────────────────────────────────────────────────────────┘
```

- Picture full bleed, full screen, `object-position: 64% 40%` (the robe and hook sit in cols 8 to 11; the soft, darker room fills cols 1 to 6 under the words).
- Words in cols 1 to 5, vertically centred (IMMERSIVE section 0), **max width 26rem**:
  - h1 "The spa." `--text-hero` (about 88px), as now.
  - `--space-5` (40) gap.
  - **The line stack** (`.opener-lines`, an `<ol role="list">`): all lines in the same grid cell (`display: grid; grid-template-areas: "l"`, every `<li>` in `grid-area: l`), so its height is the tallest line and nothing jumps when they change.
    - Statement: Signika 500, `--text-xl` (36px at 1440), `--leading-tight`, `--tracking-display`, cream (on the veil, section 3.3).
    - Note: Figtree 400, `--text-base`, `--leading-snug`, `--color-text-muted-inverse`, margin-top `--space-2`, max one line at 1440 (it fits 26rem).
  - **Ticks** (`.opener-ticks`, `aria-hidden="true"`): one per line, each 24px x 1px, `--color-gold`, gap `--space-2`, margin-top `--space-4`. Current tick opacity 1, others 0.3. Decoration only (gold on espresso; the lines themselves are the content).
- Pause control bottom right (unchanged).

Fit: 88 + 40 + statement 40 + 8 + note 26 + 24 + tick 1 = **227px**, centred in the 728px under the header.

### 3.2 Desktop end state (after the pin)

- The window has shrunk onto `.door-target` (rename to `.opener-target` in new code, keep the old class as an alias so nothing else breaks): cols 9 to 12, bleeding off the right edge, 480 x 624, top `--header-h + --space-5`, inner corners `--radius-md`. Crop `--focus-frame: 60% 42%`: the hook, the collar and the swan on the chest, the full robe to the belt.
- Words have not moved. The line stack now shows line 4. Under it, after `--space-5`: the **room chips** (unchanged component, wraps to two rows in cols 1 to 7).
- The facts row is not rendered in the motion layout.

### 3.3 The veil

Same `.hero-veil` structure, narrower on this scene because the robe is white:
- Desktop: solid `--color-veil` to `calc(var(--bleed) + 27rem)`, clear by `calc(var(--bleed) + 38rem)`. At 1440: solid to 496px, clear by 672px. The robe starts after about 860px, so it is never veiled; the words (max 64 + 416 = 480px) always sit on the solid part.
- Phone: as now (bottom veil, solid to 54% from the bottom, clear by 80%).
- Contrast: measure cream (`--color-cream`) and muted inverse against the brightest pixel under the words on the final `robe` at 1440, 1280, 1024, 375 and 360. Needs 4.5:1 for the note and 3:1 for the statement and h1. If the note fails anywhere, darken the veil there (do not lighten the note).

### 3.4 Phone 375 x 667

- First paint: the portrait picture `robe-portrait` (section 4), full screen, focus `50% 30%`: the robe fills the top 60%. Words on the bottom veil, lower half: h1 `--text-hero` (44px), `--space-4`, line stack (statement `--text-xl` = 24px, note `--text-sm`, up to two lines), ticks `--space-3` under it.
- End state: the window shrinks to `.door-target` at the top: bleeds right, `--page-margin` left, height 38svh (253px), crop `50% 28%`. Words stay. Under the line stack: chips as **one horizontal scroll line** (unchanged).
- Fit: 64 + 12 + 253 + 24 + 44 + 16 + statement 30 + 8 + note 2 lines 40 + 12 + tick 1 + 20 + chips 44 + 24 = **592 ≤ 667**.

### 3.5 Static, reduced motion, no JS

Only the end state, content height (as SPA-PAGE today): frame right (phone: top), h1, then **all lines stacked** as a list: each `<li>` statement + note, `--space-4` apart, a 24px gold hairline above each statement (the caption hairline used site-wide). No ticks. Then chips. Header solid.

This is also exactly what screen readers get in every mode: all four `<li>` are always in the DOM and never `aria-hidden`. Only their opacity changes.

---

## 4. The picture: `robe` (fal remake, required)

**Status 2026-10-23: superseded by Moishe's own mock-up, widened.** No remake: his `robe` photo was outpainted to 16:9 with bria expand (the original pixels untouched) and upscaled 2x (SeedVR, 4896x2752), built to `robe-{480,800,1600,2400}`. `robe-portrait` is his portrait original (phone). The robe sits at 58 to 87% across, so the end frame focus is `78% 40%` (CSS) and the window focus x is 0.73 (JS), not 60% / 0.64. It keeps his salt lamp and massage beds on the left (his choice: "use my mock-ups as they are"). Old file: `.private/fal-renders/robe-old.png`.

The owner's mock-up `docs/design/reference/amenities/robe.jpg` (768 x 1376) **cannot be cropped clean**: it has a salt lamp (a glowing lamp reads as a candle), rolled towels on a massage bed, is portrait only and too small for full screen. Remake with fal in the same look, two crops from one scene (generate both; do not crop the landscape for phone).

References to attach: `robe.jpg` (the subject and the embroidery style), `docs/design/reference/fal/mark-gold.png` (the swan, exactly), the new `wet-sauna-1600.jpg` (the travertine and light of the building). Model and method as FAL-IMAGES.md section 2 and 3; append the **house style block** (FAL-IMAGES section 3) and the **negative list** (section 4) to both prompts, plus: `salt lamp, lamp on a shelf, glowing orb, massage bed, rolled towels, plants, leaves`.

**`robe`, landscape 16:9, 2880 x 1620** (desktop opener, also the source of the end-state frame crop):
> A thick white terry cotton bathrobe hangs from a single brushed bronze wall hook on a warm cream plaster wall, in a men's luxury spa. The robe hangs straight and full length with soft natural folds, the shawl collar falling open, the belt tied loosely at the waist. On the left chest the supplied swan mark is embroidered in a soft gold thread, small, exactly as the reference, with "SPA 99" in the same thread under it. The robe and hook sit right of centre, at about two thirds of the frame width; the left half of the frame looks past the wall edge into a dim, warm travertine corridor that falls softly out of focus, lit by a low warm LED line along the floor and one warm wall light. Warm side light from the right grazes the terry so every loop of the cotton shows. Calm, still, no one there. Camera at chest height, 50mm lens, shallow depth of field, the robe sharp.

**`robe-portrait`, 9:16, 1440 x 2560** (phone opener):
> The same scene in a vertical frame: the bronze hook and the robe fill the upper two thirds, centred slightly right, the swan embroidery clearly visible on the chest. The lower third is the quiet cream wall and the warm travertine floor edge, softly lit, with nothing in it, so text can sit there. Same light, same lens, same robe.

Checks before building: swan shape matches `mark-gold.png` (regenerate with a plain chest and composite the vector mark as embroidery in post if it does not); "SPA 99" spelled exactly or left out; no lamp, plant, candle or towel roll anywhere; the left half of the landscape is darker than the right (that is where the words go). Build with `scripts/build_images.py` (warm grade flag on) to `robe-{480,800,1600,2400}` and `robe-portrait-{480,800,1600}`; preload `robe` (desktop) and `robe-portrait` (phone) by media query, as `door-gold` is preloaded today.

Alt text: "A white robe with the gold swan hanging on a bronze hook".

---

## 5. Motion

GSAP, `pinnedScene` + `windowTo` exactly as today; scroll-tied tweens use ease `none` (the scroll is the easing). Scrub 0.5 desktop, 0.3 phone. Only `opacity` and `transform`. Text never moves, it only fades.

### 5.1 Load (time-based, `soft`)

| t | What |
|---|---|
| 0 to 1.2s | Window fades in from espresso (opacity 0 to 1); inner image scale 1.04 to 1 over 1.6s |
| 0.2s | h1 Line rise (as now) |
| 0.6s | Line 1 and the ticks Fade up as one group (`--duration-hero`, `--rise`) |

Lines 2 to 4 start at opacity 0 (only with `html.motion`).

### 5.2 Scroll, over the pin (progress p 0 to 1)

| p | Lines | Ticks | Picture |
|---|---|---|---|
| 0 to 0.14 | Line 1 holds | 1 lit | Full screen, still |
| 0.14 to 0.24 | 1 out (opacity 1 to 0 over 0.14 to 0.20), 2 in (0 to 1 over 0.18 to 0.24) | tick 1 to 0.3, tick 2 to 1 over 0.18 to 0.24 | Shrink starts at 0.15 |
| 0.36 to 0.46 | 2 out (0.36 to 0.42), 3 in (0.40 to 0.46) | 2 to 3 | |
| 0.58 to 0.68 | 3 out (0.58 to 0.64), 4 in (0.62 to 0.68) | 3 to 4 | Veil holds to 0.55, fades 0.55 to 0.80 |
| 0.68 to 1 | Line 4 holds | 4 lit | Shrink ends at 0.85; frame tint 0 to 0.14 and corner pieces over 0.70 to 0.85 |
| 0.80 to 1 | Chips Fade up as one group | | |

With N lines (2 to 5) the change points are spread evenly over 0.14 to 0.68, same window lengths. The out-fade and in-fade overlap by 0.02 only, so two lines are never both legible on top of each other. Scrolling back plays it in reverse.

Speed check (the owner dislikes slow pins): at 1440 x 800 the pin is 640px of scroll; each line is on screen for about 140 to 180px of scroll, one to two notches of a mouse wheel. The whole opener completes in one firm trackpad flick. If it feels slow in review, shorten to `+=70%` and keep the proportions; do not drop below `+=60%` or line 2 and 3 flash past.

### 5.3 Living still

Inner image scale 1 to 1.03, 24s yoyo, `sine.inOut`, paused by Pause, off screen and when hidden (as now).

### 5.4 Reduced motion and no JS

Section 3.5. No pin, no window, no fades, no ticks, no living still; all lines visible.

---

## 6. The alternative: the door (`door-wide`), and later the video

Kept as a switch, not the plan. Setting `opener_image` to `door-wide` swaps the picture; everything else (lines, motion, veil) is the same, with focus `62% 45%` desktop, `58% 40%` phone, end frame `60% 45%`.

**`door-wide`, landscape 16:9, 2880 x 1620** (fal; references: `door-gold-1600.jpg` for the door itself, `mark-gold.png`, `logo-on-dark.png`):
> The entrance to a men's luxury spa seen from a few metres back in the reception, so the whole doorway and some of the room around it are in frame. A tall frosted glass door in a dark walnut frame, set between rough split-stone jambs, with the supplied swan mark etched into the glass in brushed gold at eye height and "SPA 99" in gold under it, exactly as the reference, and a long walnut pull handle. The door is open a hand's width; warm light from the corridor beyond spills through the gap onto the travertine floor. Around the door: honed travertine floor, warm cream plaster walls, a slim walnut bench against the left wall, a warm LED cove line in the ceiling. The door sits right of centre at about 62% of the frame width and fills about 70% of the frame height; the left third is the quiet, darker reception wall. Camera at standing eye height, 35mm lens, straight verticals.

Portrait `door-wide-portrait` 9:16, 1440 x 2560: same scene, door centred, filling the upper 70%.

Negatives: as FAL-IMAGES section 4, plus `plant, potted plant, fish tank, aquarium` (the plant in today's `door-gold` goes).

**The video** (SPA-DOOR-VIDEO.md) plugs in only when `opener_image` is `door-wide` and the files exist: it plays inside the window exactly as Home's hero video does (poster = the first frame = `door-wide`), keeps playing in the end-state frame, Pause control pauses it, never on Save-Data, poster only under reduced motion.

---

## 7. Classes and tokens

New classes (in `spa.css`): `.opener-lines`, `.opener-line`, `.opener-statement`, `.opener-note`, `.opener-ticks`, `.opener-tick`, `.opener-target` (alias of `.door-target`). Hooks: `data-opener-line`, `data-opener-tick`.

Removed from the template: `.door-lead`, `.door-facts` (motion layout), the `data-count` on the room count.

**Proposed token additions** (derived, add to `tokens.css` and BRAND section 8):

| Token | Value | Use |
|---|---|---|
| `--opener-measure` | `26rem` | Max width of the opener words, keeps them on the solid veil |
| `--opener-pin` | `0.8` (desktop) / `0.6` (phone) | Pin length in screens, read by `spa.js` from the computed style so it can be tuned without a code change |

No new colours. Contrast: cream on the veil (`--color-veil`, 0.82 espresso) over the darkest-to-brightest part of the left half must be measured (section 3.3); gold ticks are decoration.

---

## 8. Acceptance checks (screenshots in `.private/shots/spa-opener/` at 375 x 667 and 1440 x 800: first paint, p 0.2, 0.42, 0.64, end, static)

1. First paint at 1440: the whole robe, the hook and the swan embroidery are visible and sharp; nothing is cropped at the collar; the words sit on solid espresso, never on the robe.
2. No "Eight spaces, one quiet visit." anywhere. Line 1 reads "Open 5am to 3am." with "Every day. Closed for Shabbos and Yom Tov." from the data (change the hours in the admin: the line changes).
3. Scrolling shows the four lines one at a time, each fully faded in before the next starts; at no frame are two lines both above 30% opacity; text never moves, only fades.
4. The picture shrinks into the right frame as smoothly as Home's hero (no jump at pin start or end); the pin ends within one trackpad flick (about 640px at 800 tall).
5. Ticks match the line shown. Chips arrive at the end and link to the rooms.
6. Reduced motion: no pin, all four lines stacked with hairlines, frame on the right, chips; the same in no-JS.
7. Screen reader: h1, then the four lines as a list, then the chips. No line is ever `aria-hidden`.
8. Phone 375: robe in the top 60% on first paint; words on the bottom veil; end state fits 667 without scrolling inside the section; chips scroll sideways.
9. LCP is the robe picture (preloaded), under 2.5s on a mid phone.
10. Setting `opener_image` to `door-wide` swaps the picture with no other change.
