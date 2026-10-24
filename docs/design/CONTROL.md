# Spa 99 Control: design brief v2 (DEMO with a real Library)

Scope: round 2 of the building control room at `control.spa99.uk` (branch `feature/control-demo`). Replaces the v1 brief (built 2026-10-24; v1 is in git history at `45522f6`). Decisions: PROJECT.md rows 2026-10-23 and the two rows dated 2026-10-24 (v1 built; Moishe's v2 decisions). Access stays Admin level and up (`docs/features/user-rules.md` U2), plain 404 for everyone else. Brand rules in `docs/BRAND.md` win over anything here.

**What Moishe said about v1:** "a bit confusing, not crazy about the dimming glow, a bit boring. For music and screens I want upload video/audio, connect to Spotify, play, pause, select track/video. It's all a bit basic."

**What v2 changes, in one line each**
1. **Clear tabs, one job each:** Overview, Rooms, Music, Screens, Schedule, Library. Every control has one home: lights and climate live in Rooms, music in Music, screens in Screens. Other places show the state and link to the home. (v1 put music and screens inside the room drawer too, which was the confusing part.)
2. **The spa is drawn.** Overview is an illustrated floor plan; each room is lit by its own light state.
3. **The photo is the preview.** Room cards show the real room photo, re-lit by brightness and warmth. The glow is gone.
4. **Real media.** Library uploads are real and stored (S3 on live, local on the Mac). Players and screens use those real files. Playback into rooms, lights, climate and Spotify stay simulated.

**Design read.** An operations console for a few people looking after one building from home, often late. A quiet hotel night desk, or a Lutron or Sonos app done with restraint: dark, calm, values exact, photography doing the emotional work. Dials: variance 3, motion 3, density 5 (phone 4). Motion 7B (restrained), CSS and small plain JS only, no animation library.

---

## 1. The look (kept, refined)

Keep the v1 dark look and every v1 `--ctl-*` token in `common/static/common/css/control.css` (scoped to `body.control`, no hex outside that file). Kept rules: tone steps instead of lines on cards, 12px containers, 6px things you press, pills only for tracks, toggles, chips and badges; Figtree tabular for values, Signika for titles and room names; base text 14px (16px for inputs on a phone); gold is the only accent; blue only means DEMO; state is never colour alone.

Refinements:
- **More air, fewer boxes.** Page padding 32px desktop (16px phone); 48px between page sections. Lists inside panels separate by space, not cards inside cards.
- **Page titles visible on every tab** (Signika 500, 32px, one line), with at most one short line under them in `--ctl-text-2`. Overview uses a status sentence instead (section 4).
- **Photography and real media are the colour.** Chrome stays espresso-black; the rooms, artwork, thumbnails and previews bring the warmth.
- **Removed:** the glow pool (`--ctl-glow`), the 4-cell status strip on every page (its numbers move to Overview), music and screen controls inside the room panel.

## 2. Tokens

### 2.1 Proposed additions (v2, Control only, in `control.css` under `body.control`; derived, not brand colours)

| Token | Value | Use | Contrast / note |
|---|---|---|---|
| `--ctl-night` | `#0A0705` | The dimming layer over room photos (section 5) | decoration |
| `--ctl-cool` | `#DCE4EA` | Cool cast above 3000K in the photo preview only | decoration; outside brand hues, never UI |
| `--ctl-tank` | `#6E9C99` | Fish tank on the floor plan, at 0.45 alpha | decoration only |
| `--ctl-wall` | `rgb(245 242 216 / 0.08)` | Plan furniture hints, list dividers, drop zone edge at rest | decoration only |
| `--ctl-chip-bg` | `rgb(20 16 13 / 0.88)` | Small chips on thumbnails (duration, "Off") | cream on it over a white frame: 11.9 |
| `--ctl-wash` | `var(--color-pattern)` | Alias, no new colour: gold 8% wash on a drop target and a chosen tile | decoration |
| `--ctl-panel-w` | `480px` | Side panel (replaces `--ctl-drawer-w` 440) | |
| `--ctl-rail-w` | `360px` | Overview right column, Music zone list is `280px` (`--ctl-zones-w`) | |
| `--ctl-art-lg` | `240px` | Player artwork, desktop (phone: `min(72vw, 280px)`) | |
| `--ctl-art-sm` | `48px` | Artwork in lists and the mini player | |
| `--ctl-play` | `56px` | The main play/pause button (gold circle) | `--ctl-bg` icon on gold 9.42 |
| `--ctl-fade` | `240ms` | Cross-fades: tab content, preview content, toasts | |
| `--ctl-art-fade` | `400ms` | Artwork and title change on a new track | |
| `--ctl-panel-in` / `--ctl-panel-out` | `280ms` / `180ms` | Side panel and sheet enter / leave | |
| `--ctl-sheet-peek` | `56svh` | Phone sheet resting height (full: `92svh`) | |

All motion uses `--ease-soft`, except progress bars (linear, constant motion).

### 2.2 Retired
`--ctl-glow`, `--ctl-strip-h`, `--ctl-drawer-w`. The warmth scale (`--ctl-warm-2200` to `--ctl-warm-4000`) stays: it paints the warmth slider track and the floor plan light.

## 3. Shell and navigation

```
+-----------------------------------------------------------------------------------------+
| DEMO  Rooms, music and screens are pretend. The Library is real.          [Reset demo]  | 32
+-----------------------------------------------------------------------------------------+
| [swan] Control   Overview  Rooms  Music  Screens  Schedule  Library    21:14  [bell 1] [MW] | 56
+-----------------------------------------------------------------------------------------+
|  page                                                                                    |
|                                                         [mini player: Lounge  > Track ] | 64 (Music not open)
```

- **Routes:** `/` Overview, `/rooms/` (`?room=slug` opens the panel), `/music/` (`?zone=slug`), `/screens/` (`?screen=slug`), `/schedule/`, `/library/` (`?item=id`, `?playlist=id`). Old `/` with `?room=` keeps working (opens the panel on Overview).
- **Top bar:** swan + "Control", six text tabs (14px 500, current in `--ctl-text` with the 2px gold bar and `aria-current`), clock, **alerts bell** (count badge in `--ctl-danger` when above 0, opens the alert popover; "No alerts" in the popover otherwise), initials menu (name, level, Open Office, Change password, Sign out).
- **Mini player** (desktop and phone, every tab except Music): a slim bar docked bottom-centre (desktop 560px wide, 64px, `--ctl-raised`, radius 12px; phone full width above the tabs, 56px): zone name, artwork 40px, title, play/pause, next, tap anywhere else opens Music on that zone. Shows the zone you last touched (default Lounge). Hidden when nothing plays anywhere.
- **Phone (below 48em):** top bar keeps swan, page title, bell, initials. **Bottom tabs, five:** Overview, Rooms, Music, Screens, More. "More" opens a sheet with Schedule, Library, Reset demo, account links. Tabs: Phosphor 24px over 12px 600 label, `--ctl-tab-h` + safe area.
- **Tab change:** content cross-fades (View Transitions, opacity only: out 120ms, in `--ctl-fade`); bars stay still. Instant under reduced motion.

### 3.1 DEMO banner and chips

- Banner as v1 (blue, 32px, not dismissible, sticky on desktop), new text: "Rooms, music and screens are pretend. The Library is real." Phone: "Pretend building. Library is real."
- **Reset demo** confirm: "Put rooms, music and screens back to their starting values? Library files and playlists stay." Cancel / Reset. Reset never touches the Library.
- **DEMO chip** (new): pill 20px, 11px 600 uppercase, 0.08em tracking, 1px `--ctl-demo` border, `--ctl-demo` text, no fill. One chip per simulated group, beside its title, never on every control: Lights (room panel), Climate, "Playing in" (player header), the Spotify source, "On the screen" (screen panel), Scenes. Tooltip / `title` and visually-hidden text: "Demo: nothing is sent to real equipment."
- **Never a DEMO chip in the Library.** The Library header has instead a quiet line: "Files here are stored for real." in `--ctl-text-2` with a `lock-simple` icon.

## 4. Overview: the floor plan

**Desktop (from 64em):**
```
+-----------------------------------------------------------------------------------------+
| Open until 03:00. 17 guests in.                                     (Signika 32, 1 line)|
| Scenes  [Opening] [Daytime] [Evening Active] [Closing] [Cleaning]   Now: Evening, since 18:00 |
+----------------------------------------------------------------+------------------------+
|                                                                | The building now       |
|                    FLOOR PLAN (SVG)                            | 17 of 25 in   21 lockers|
|                                                                | 17 bands      1 alert   |
|                                                                |                        |
|                                                                | Playing                |
|                                                                | Lounge zone  Track  ||  |
|                                                                | Wet area     Track  ||  |
|                                                                | ...                    |
|                                                                | Screens  [][][][][][]  |
+----------------------------------------------------------------+------------------------+
```
- Status sentence from real hours and the sim: "Open until 03:00. 17 guests in." / "Closed. Opens at 05:00." / "Nearly full. 23 guests in." (warn word, never colour alone).
- **Scenes bar (v2.1, replaces v1's apply-on-press):** labelled "Scenes" (with the DEMO chip and "Tap one to see and change what it sets"), five chips: Opening, Daytime, Evening, Closing, Cleaning. **A chip never applies anything: it opens the scene editor** (see 4.2). The chip whose scene is the current one AND whose values every room's light matches shows a small gold "Active" mark (and a 2px gold underline); change a room by hand and the mark goes. "Now: Evening, since 18:00" stays on the right. Lives on Overview and Rooms only.
- **Right column** (`--ctl-rail-w`): the four building numbers (32px values, 12px labels, 2 by 2), Playing (one 52px row per music zone: zone, title, play/pause; row opens Music), Screens (six 16:9 thumbnails 48px wide; opens Screens).
- **Tap a room on the plan (or the 3D model):** the right column becomes that room's panel (section 6.2, same content as on Rooms), with a back arrow "The building". The plan stays visible and re-lights live as sliders move: this is the moment that sells the demo. Esc or back returns the column. URL `?room=slug`.

### 4.0 The 3D model (v2.1, replaces the coloured plan as the main Overview picture)

Moishe on v2: the coloured plan was too hard and worse than v1. The Overview now shows a **simple 3D model** of the same real plan (`control/plan.py` `model()` gives the outlines; the browser extrudes them with the vendored three.js, `js/control/overview3d.js`, loaded only on the Overview).

- **Look:** clean architectural massing, no textures. A low slab, light warm-white floors and thin low walls (22 units high on a 1200 long building, so you see in), one soft hemisphere (sky and ground) light plus one directional light. No shadows or AO (kept out so nothing can look noisy). Tokens (control.css first block): `--ctl-m-floor`, `--ctl-m-wall`, `--ctl-m-dim`, `--ctl-m-slab`; gold is `--ctl-accent`. The background is the Control shell (`--ctl-surface`).
- **Colour is calm.** No fill per room. A room's light shows only as a soft warm tint on its floor: radial, stronger in the middle, **opacity 0.12 + 0.43 x brightness** at the centre (about a third of that at the edge), colour from the warmth scale (`--ctl-warm-*`). Off rooms are plain. Spaces with no controls (plant rooms, WCs, stairs and lift, dry riser, electrical) have a slightly darker floor, no label and cannot be clicked. The "not surveyed" ghost is not drawn.
- **Labels:** small HTML labels (Figtree 12px, 13px from 48em, espresso with a cream halo, 700 when hovered or selected) placed from the 3D position of each controllable room's centre; they are real `<a href="?room=slug" data-open-room>` links (keyboard works, `aria-label` has the lights and any alert), `pointer-events: none` so the canvas gets the touches. A room with an alert gets a small dark-red dot. Labels wrap inside the room's on-screen width. A quiet note "Entrance, Vale Road" sits under the entrance edge.
- **Camera:** perspective, 26 degree lens, starts **straight above** and fitted to the building (it re-fits as you turn and zoom). On a narrow canvas (aspect under 0.95, so phones in portrait) it starts turned 90 degrees so the long side runs down the screen. **Drag** (mouse or one finger) tilts from top view to **55 degrees** and turns; **wheel or pinch** zooms (0.85x to 3x); shift-drag or two fingers move the view (only when zoomed in); **Top view** button (top right) eases back (420ms). The page never scrolls while a finger is on the model (`touch-action: none`).
- **Hover and select:** hovering a room (or focusing its label) outlines it in gold (a thin ring on the floor edge plus its own half of the walls); the room whose panel is open keeps the gold outline. **Tap or click (not a drag: under 6px and 700ms) opens that room's Rooms panel** exactly as in 4.2; a tap on a space with no controls does nothing.
- **Performance and cleanup:** renders only on interaction, a state change (light, selection, alert) or the 420ms reset tween; `devicePixelRatio` capped at 2; the model is disposed (geometry, materials, texture, renderer, context, listeners) when you leave the tab and rebuilt on return.
- **Fallback:** no WebGL (or the model fails to build), or `prefers-reduced-motion: reduce`: the model is not shown and the **2D plan (4.1) stays**, with calmer colours too (light tint opacity 0.06 + 0.22 x brightness, gradient centre 0.7 alpha). Without JavaScript the 2D plan is the page.

### 4.1 The plan drawing (2D, the fallback)

**The plan follows Moishe's real drawing**, not the first sketch of this brief: Panorama Interior, "99 Vale Road - Shvitz, Proposed ground floor lighting", Rev 04, 1:80 (OneDrive, BML / Spa 99 / Plans). One long rectangle, drawn stylised: the right rooms in the right places at roughly the right proportions, no architecture. The geometry lives in `control/plan.py` (one list, so a new room is a data change).

One inline SVG per size, `viewBox="0 0 1200 440"` on desktop. Rooms are rounded rectangles (radius 8) separated by 8-unit gaps of `--ctl-bg` (the gaps are the walls; no stroked outlines). Left to right:

```
     x 12        142             307      467            757  837   955          1190
y 14  +-----------+---------------+--------+--------------+----+-----+-----------+
      | Dry sauna | Showers       | WCs    | Stairs and   | WC | Plant| Not        |
      | (heater)  | (4 heads)     |        | lift         |    | room | surveyed   |
 192  +-----------+ Cold plunge   +--------+              +----+-----+ - - - - - -+
      | Wet sauna | (pool,benches)| Chang- +--------------+                       |
      | (benches) +---------------+ ing    | Plant|Riser  | ENTRANCE (lounge and  |
 247  |           | Relaxing zone +--------+------+-------+ reception, sofas,     |
      |           | (six loungers)| Hallway   (links all)  | curved feature wall,  |
 305  |           |               +-----------+---------+--+ fish tank) +----------+
      |           |               |Kitchenette| Massage | Gym |          |Electrical|
 390  +-----------+---------------+-----------+---------+-----+----------+----------+
```

| Room (plan id) | State room (slug) | Controls |
|---|---|---|
| Dry sauna GF07 | `dry-sauna` | lights, climate |
| Wet sauna GF06 | `wet-sauna` | lights, climate |
| Showers, Cold plunge (both GF08, drawn as two rooms) | `showers`, `cold-plunge` | lights, music, climate on the plunge |
| Relaxing zone GF05 | `relaxing-zone` | lights, music, screen |
| Changing room GF09 | `changing-room` | lights, music |
| Hallway GF11 (replaces the "Corridor" of the first sketch) | `hallway` | lights, music, screen |
| Kitchenette GF04 | `kitchenette` | lights, music, screen |
| Massage room GF03 | `massage-room` | lights, music |
| Gym GF02 | `gym` | lights, music, screen |
| Entrance GF01 = lounge and reception (one space) | `reception-lounge` | lights, music, screen, tank water |
| WCs, Stairs and lift, Plant rooms, Dry riser, Electrical | none | drawn unlit, not links, label in `--ctl-text-3` |

Hints (`--ctl-wall`, decoration): sauna benches and the dry sauna heater, shower heads, the cold plunge pool and benches, six loungers, locker row, the stair and lift, a round table in the kitchenette, the massage table, gym equipment, and in the Entrance the **curved feature wall**, the **fish tank** along it (`--ctl-tank` at 0.45 alpha, labelled "Fish tank"), sofas and armchairs. The Entrance doors are a gold dash on the bottom wall with "Entrance, Vale Road" below, and the planters of the pavement are a row of faint rounded rectangles under the plan. The unsurveyed corner is a dashed outline.

**Lighting a room:** each room has three stacked shapes. (1) base fill `--ctl-surface`; (2) a light shape filled with a radial gradient (centre 40% from top-left, warmth colour from the warmth scale at 0.7 alpha at the centre to 0 at the edge) whose **opacity = 0.06 + brightness × 0.22** when on (v2.1: calmer, was 0.12 + 0.55), 0 when off; (3) the label. Lights off: base only, label `--ctl-text-3`, line "Off". On: label `--ctl-text` (Signika 500 16px; 13px for rooms under 200 wide), value line 12px `--ctl-text-2` "60%  2700K" (saunas and plunge add the temperature: "86°C"). People count, when above 0, sits top-right in 12px `--ctl-text-2` ("3"), with the full phrase in the accessible name. Light opacity changes ease over `--ctl-glide` for scenes and presets, instantly while dragging.

**Interaction:** each controllable room is an SVG `<a href="?room=slug">` with `aria-label` "Dry sauna. Lights 60 percent, 2700 kelvin. 86 degrees. 3 people." Hover (fine pointer): base fill to `--ctl-raised`, 160ms. Focus: 2px gold outline drawn as an inset rect. Selected: the same gold outline, persistent. Alert in a room: a 2px `--ctl-danger` inset outline plus the word "Alert" in the value line.

**Phone plan:** the same geometry transposed (x and y swapped, `viewBox="0 0 470 1200"`), labels kept upright, so the plan fills the width (about 343px wide, 876px tall) and every controllable room is at least 56px on its short side (the Hallway band is stretched by 30 units to get there; a test checks it). Under the plan, the four building numbers in a 2 by 2 block, then Playing rows. Tapping a room opens the room sheet at peek height (`--ctl-sheet-peek`), so the top of the plan stays visible above it and visibly re-lights. (With the 3D model on, the phone shows the model full width instead, turned 90 degrees; the transposed 2D plan is the fallback.)

### 4.2 Opening a room from the Overview, and the history rules (v2.1)

- **Every controllable room in `plan.py` opens the same Rooms panel** (light and warmth, climate where it has it, small read-only Music and Screen lines with "Open in Music" and "Open in Screens"). Tapping a room never switches tab. Rooms with a screen or a music zone (Relaxing zone, Entrance, Hallway, Gym, Kitchenette) used to show "Off" or "Welcome to Spa 99" full panel: the screen preview was mounted on the whole Screen section, and its absolutely positioned stage covered the panel. It is now mounted on its own 16:9 box.
- **History:** only a real tab change pushes one entry (and the entry you leave is cleaned to its bare path, except Music which keeps `?zone=`). Opening or closing a panel (room, screen, Library item, scene), picking a zone and moving between Library views all use `replaceState`. A panel that closes because the tab changed or another panel replaced it never touches the address. Back goes to the previous tab once, Forward likewise; Back or Forward pressed while a page is loading is queued and handled when it finishes.

### 4.3 Scene editor (v2.1)

Tapping a scene chip opens a panel (a full-height side panel on desktop, a full sheet on a phone) titled with the scene name, a DEMO chip and the scene's one-line description. **Nothing is applied by opening it.**

- **Rooms:** one block per room with its name, a **Light** slider (0 to 100, 0 reads "Off") and a **Warmth** slider (2200 to 4000 K), prefilled with the scene's current values (its own defaults, e.g. Daytime 80% at 3000 K with the Relaxing zone at 40%, or the values saved earlier).
- **Music:** one row per zone with a select: "Leave the music as it is", "Music off", the six demo Spotify playlists and the Library music playlists (loaded a moment later without losing a choice already made). A saved choice whose playlist was deleted reads "Playlist no longer available" and is skipped on apply.
- **Buttons:** **Save scene** (primary; enabled only when something changed) stores the scene in the demo state (`localStorage` key `spa99.control.demo.v2`, field `sceneEdits`; nothing goes to the server) and toasts "Daytime saved."; **Apply now** (separate, secondary; enabled only when nothing is unsaved) applies the saved scene to the rooms and zones with the usual glide, the toast "Daytime applied to 11 rooms." and Undo (Undo also restores each zone's queue); **Back to the original** (link, only when an edit exists) removes the saved edit. A note says "You have changes that are not saved. Save the scene, then apply it." while dirty and "Saved in this browser only." otherwise. On a phone the sheet closes after Apply so the change is seen.
- The Schedule still refers to scenes by name; when a scheduled scene runs it uses the saved values. Reset demo clears saved scenes with the rest of the browser state.
- Hidden scene "Saunas heat" has no chip and no editor.

## 5. The photo light preview (replaces the glow)

The room photo itself is re-lit. Only opacity changes (BRAND 7: never animate filters), so it is cheap and glides smoothly.

**Layers inside a 3:2 frame, bottom to top:**
1. **Photo:** `<picture>` with the room's 800w webp (480w on phone), `object-fit: cover`. A static grade `filter: saturate(0.92)` (never animated).
2. **Night:** solid `--ctl-night`, opacity `d`.
3. **Lamps:** a pre-made "lamps map" of the same photo (only the light sources: cove LEDs, downlights, sauna strips, the tank), `mix-blend-mode: screen`, opacity `d × 0.85` when on, 0 when off. As the room dims the light sources stay lit, which is what makes it read as dimmed lighting and not a darkened photo.
4. **Pool:** a radial gradient from transparent (centre 45% / 40%) to `--ctl-night` at the edges, opacity `d × 0.6`. Light gathers in the middle of the room as it dims.
5. **Warm:** solid `--ctl-warm-2200`, `mix-blend-mode: color`, opacity `clamp(0, (3000 − K) / 800, 1) × 0.28`.
6. **Cool:** solid `--ctl-cool`, `mix-blend-mode: soft-light`, opacity `clamp(0, (K − 3000) / 1000, 1) × 0.35`.

`d` (darkness) = `0.88 × (1 − b/100)^1.2` while on. **Off:** night 0.94, lamps 0, warm and cool 0; the room becomes a faint silhouette with the word "Off" on a `--ctl-chip-bg` chip, bottom-left. 3000K is "as photographed" (the renders are warm already), so the default looks exactly like the site.

**Lamps maps** would be made once, offline, by a small management command (Pillow; not installed here, see below): keep pixels above the 88th luminance percentile, feather 6px, everything else black; save `<name>-lamps-800.webp` and `-480.webp` beside the photo in `content/static/content/img/`. Photos used: lounge (for Reception and lounge), corridor (for the Hallway), lockers (for the Changing room), dry-sauna, wet-sauna, cold-plunge, showers, relaxing-zone, massage-room, gym, kitchenette. **Built with CSS spots instead of lamps maps:** Pillow is not installed in this project, so each room has two or three soft warm radial gradients (`present.LAMPS`, blended with `screen`) standing in for the lamps map; same layer, same opacity rule. A lamps map made from the photo can replace them later without changing the page. A room without a photo gets the swan pattern on espresso and the same night layer.

Motion: while a slider is dragged, layers follow instantly (`transition: none`). Scenes and presets: `transition: opacity var(--ctl-glide) var(--ease-soft)`, rooms 60ms apart in order. Reduced motion: always instant.

## 6. Rooms

Title "Rooms", line "Light and temperature in every room." Scene bar under it.

### 6.1 Room card

Grid `repeat(auto-fill, minmax(320px, 1fr))`, 24px gap: 3 across at 1440 (content 1360), 1 column on phone. Order: Reception and lounge, Hallway, Changing room, then the Office's rooms as v1.

```
+------------------------------------------+
|                                          |
|        [ re-lit room photo, 3:2 ]        |
|                                    [Off] |
+------------------------------------------+
| Dry sauna                    [At target] |
| 86°C  target 85°C            3 people    |
| Light  [=========o------]  60%           |
| Warmth [====o-----------]  2700K         |
| Music: Wet area, Low Light   Screen: none|
+------------------------------------------+
```
- `--ctl-surface`, radius 12px, photo flush to the top (top corners 12px), body padding 20px. No border, no shadow.
- Name Signika 500 20px, opening the panel (stretched link over the photo and name; sliders sit above it). Status badge as v1.
- Climate line only on saunas and plunge (value 24px 500).
- **Two sliders on the card: Light (brightness) and Warmth**, because moving them visibly re-lights the photo above. A light on/off toggle is the 0 end of the slider plus a tap on the photo chip "Off" to turn on at the last level.
- Music and Screen are one 12px `--ctl-text-2` line each, as links to Music and Screens ("Music: Wet area, Low Light"). No player here.
- Hover (fine pointer): photo scales 1.02 inside its frame over 600ms; card does not move. Press on the photo: 0.99.

### 6.2 Room panel

Desktop: right side panel `--ctl-panel-w` on Rooms (overlay with `--ctl-overlay` backdrop), or the right column on Overview. Phone: sheet (peek, drag up to full). Focus to the title, trapped in the overlay versions, Esc and backdrop close and return focus.

Top to bottom:
1. **Photo** 3:2, full width, the live preview at its largest. Close button over it top-right (36px, `--ctl-chip-bg` disc).
2. Name (Signika 32), status badge, people line.
3. **Light** [DEMO chip]: presets segmented Bright / Day / Calm / Off; Light slider; Warmth slider (track painted with the warmth scale).
4. **Climate** [DEMO chip] (saunas, plunge): big current value, target stepper, Heating toggle (as v1).
5. **Music:** one row "Wet area zone, Low Light, playing" with a volume slider "In this room" (trim, 0 to 100) and the link "Open in Music". No source or track choice here.
6. **Screen** (rooms with one): a 16:9 live thumbnail, what it shows, link "Open in Screens".
7. Footer 12px `--ctl-text-3`: "Saved in this browser only."

## 7. Music

Title "Music". DEMO chip beside "Playing in" (the speakers are pretend; the files are real).

### 7.1 Zones

Default zones (DEMO values, editable):

| Zone | Rooms |
|---|---|
| Lounge | Reception and lounge, Kitchenette, Hallway |
| Wet area | Cold plunge, Showers, Changing room (no speakers in the saunas) |
| Relaxing zone | Relaxing zone |
| Massage room | Massage room |
| Gym | Gym |

**Desktop layout:** left column `--ctl-zones-w` lists zones; the rest is the selected zone's player.
```
+--------------------+---------------------------------------------------------------+
| Zones   [Group all]|  Playing in  Lounge zone [DEMO]       Reception, Lounge, +2   |
|                    |                                                               |
| [art] Lounge       |  +-----------+   Low Light                                    |
|       Playing      |  |  artwork  |   Night Shift Quartet                          |
| [art] Wet area     |  |  240      |   Library  .  Evening playlist                 |
|       Paused       |  +-----------+                                                |
| [art] Relaxing     |   1:42 [===========o-----------------------] 4:05             |
| [art] Massage      |   [shuffle] [prev] ( PLAY ) [next] [repeat]   vol [====o--]   |
| [art] Gym  Off     |   [headphones Listen here]          [Change music]            |
|                    |                                                               |
| [Mute all]         |  Up next                                          Clear       |
|                    |  [=] [art] Track two      Artist              3:12   [x]      |
|                    |  [=] [art] Track three    Artist              4:40   [x]      |
+--------------------+---------------------------------------------------------------+
```
- **Zone row** (64px): artwork 48px, zone name 16px 600, state word 12px ("Playing", "Paused", "Off", "Muted"). Selected row `--ctl-selected` with the gold bar at its left.
- **Rooms in the zone:** the header line lists them; "Edit rooms" opens a small sheet of room chips (toggle chips; a room belongs to one zone, so choosing it here moves it, with the line "Moves Gym from the Gym zone").
- **Group all:** every room follows the selected zone (zone list collapses to one row "All rooms", button becomes "Ungroup"). **Mute all:** mutes every zone at once, toast "All music muted." with Undo. Both instant.

### 7.2 The player

- **Artwork** `--ctl-art-lg`, radius 6px. Library tracks: the track's cover if one was set, else the playlist cover, else the default cover (swan on espresso with the track waveform in gold at 30%). Spotify demo: the sample cover.
- **Title** Signika 500 28px (one line, ellipsis), **artist** 16px `--ctl-text-2`, **source line** 12px `--ctl-text-3` ("Library, Evening playlist" or "Spotify, Warm Room" + DEMO chip on Spotify).
- **Scrub bar:** 6px track, gold fill (`transform: scaleX`), 16px thumb shown on hover, focus and drag (always on touch). Elapsed and total 12px tabular either side. Native range underneath, `aria-valuetext` "1 minute 42 of 4 minutes 5".
- **Transport:** shuffle and repeat (40px icon toggles, on = gold icon + `aria-pressed`, repeat cycles Off / All / One with the word in its label), previous and next (44px), **play/pause** `--ctl-play` gold circle with `--ctl-bg` icon. Space toggles play when focus is in the player (not in a text field).
- **Volume:** zone volume slider 0 to 100 with a mute button; per-room trims live in the room panel.
- **Listen here** (headphones toggle, Library sources only): plays the actual file in this browser, in sync with the shown position, so you can hear what the room would hear. Off by default; turning on another zone's Listen here turns this one off. On Spotify it is disabled with the hint "Spotify plays on the spa speakers only."
- **Without Listen here** playback is silent and simulated: the position advances in real time, tracks advance at their real durations, queue and shuffle and repeat behave correctly. Durations come from the real files.
- **Up next (queue):** rows 56px: drag handle, artwork 40, title, artist, duration, remove. Reorder by drag (pointer) or with the handle focused, Up/Down arrows move the row (announced: "Track three moved to position 1"). "Clear" empties it (Undo toast). Tap a row: plays it now.
- **Change music** opens the source picker.

### 7.3 Source picker

Desktop: side panel; phone: full sheet. Segmented at the top: **Library** | **Spotify**.

- **Library:** "Playlists" as cover tiles (2 across in the panel, 160px squares, name and "12 tracks, 48 min"), then "All music" as rows with a search field. Each item: tap = Play now (replaces the queue); a `+` button = Add to queue (toast "Added to Lounge queue"). Only items tagged Music appear.
- **Spotify, not connected:** the Spotify logo (official monochrome, cream), "Connect Spotify to play your playlists on the spa speakers." Button "Connect Spotify". Under it, 12px: "Demo: no Spotify account is used."
- **Connect flow (demo):** a dialog styled as a hand-off (not a fake Spotify page): "Spotify will ask you to sign in and allow Spa 99 to play music on the spa speakers." Cancel / Continue. Continue shows "Waiting for Spotify" for 1.2s (static line, no spinner), then "Connected (demo)" with the account "Spa 99 Music" and a check. The dialog closes after 1s; the Spotify tab now shows the account line with "Disconnect" and six sample playlists.
- **Sample playlists** (invented names and artists, nothing copyrighted): Warm Room, Low Light, Slow Morning, Gym Tempo, Kitchen Radio, After Hours. Covers are typographic tiles: one flat brand field each (espresso, caramel, gold, cream, espresso-raised, `--ctl-selected`) with the name in Signika set large and cropped by the tile edge. Never fake Spotify artwork.
- Choosing a Spotify playlist plays it in the zone (simulated), source line "Spotify, Low Light" + DEMO chip.

## 8. Screens

Title "Screens", line "What each screen shows, and when."

Screens (DEMO values): Reception, Lounge, Hallway, Gym, Relaxing zone, Kitchenette.

### 8.1 Screen grid

`repeat(auto-fill, minmax(360px, 1fr))`, 24px gap. Card: **16:9 live preview** (radius 6px), then name 16px 600, what it shows 12px `--ctl-text-2` ("Evening reel, 3 items, looping"), state word ("Playing", "Paused", "Off"), a 40px play/pause button. The card opens the screen panel.

**Live previews** are the real thing at small size: a muted, looping, `playsinline` `<video>` for videos, the image for images, playlists advancing at their real timings, and the built-in slides as real miniature HTML scaled with `transform: scale()` (the v1 technique). Videos load `preload="metadata"` with the poster and play only while the card is on screen (IntersectionObserver) and the tab is visible; at most 3 playing at once (the rest show poster + "Playing"). Save-Data or reduced motion: posters only, with a play button per card.

### 8.2 Screen panel

Side panel `--ctl-panel-w` (phone: full sheet).
1. **Preview** 16:9 at full panel width, live. "On the screen" label + DEMO chip.
2. **Transport:** play/pause (`--ctl-play`), previous / next item (playlists only), Loop toggle, power toggle "Screen on".
3. **Show:** segmented **Slides** | **Library**.
   - Slides: four tiles with miniature previews: Welcome, Hours, Menu, Notices (Notices keeps the v1 editable line, 80 characters).
   - Library: grid of items tagged Screens (videos, images) and screen playlists, with a filter Videos / Images / Playlists. Tap = show now (preview cross-fades over `--ctl-fade`).
   - Under the choice: "Show on" radio rows: This screen / All screens.
4. **Schedule** (optional): toggle "Change through the day". When on, up to four rows: time (native time input styled as a 44px field) and what to show (opens the same chooser). Example rows: 05:00 Welcome, 18:00 Evening reel, 02:30 Notices "We close at 03:00". Rows sort by time; "Add a change" adds one. Shown also on the Schedule tab as small markers on a "Screens" lane.
5. Footer: "Saved in this browser only."

## 9. Schedule

Kept from v1 (05:00 to 05:00 lanes, read-only opening hours and closures, Shabbos spans with the example-time note, scene events with popover, now line, phone list). v2 additions: a second thin lane under today labelled "Screens" with the scheduled screen changes as 8px markers (popover lists which screen shows what), and the v2 page title and spacing. No other change.

## 10. Library (real)

Title "Library", line with lock icon "Files here are stored for real." Right of the title: storage meter "1.2 GB of 10 GB" (a thin bar, gold fill, words always present) and the **Upload** button (primary: gold fill, `--ctl-bg` text, `upload-simple` icon).

### 10.1 Layout

```
+-----------------------------------------------------------------------------------------+
| Library                                      1.2 GB of 10 GB  [====------]   [Upload]   |
| Files here are stored for real.                                                         |
| [Files] [Playlists]        All  Music  Screens        [search........]   [grid][list]  |
| Audio  Video  Images                                                                    |
+-----------------------------------------------------------------------------------------+
| +--------+ +--------+ +--------+ +--------+ +--------+                                  |
| | thumb  | | wave   | | image  | | thumb  | | wave   |                                  |
| |   2:14 | |   4:05 | |1920x1080| |  0:30 | |   3:12 |                                  |
| +--------+ +--------+ +--------+ +--------+ +--------+                                  |
| Evening   Low Light  Hours bg   Steam     Night Sh..                                    |
| Screens   Music      Screens    Screens   Music                                         |
```
- Sub-tabs **Files** | **Playlists**. Filters: tag segmented All / Music / Screens; type chips Audio / Video / Images (toggle chips); search by name; view toggle grid / list.
- **Grid** `repeat(auto-fill, minmax(200px, 1fr))`, 16px gap. Tile: preview 16:9 for video and image, square for audio; name 14px 500 (one line), tag word 12px `--ctl-text-2`. Duration or dimensions on a `--ctl-chip-bg` chip bottom-right of the preview (the one allowed overlay: it is data, not decoration).
  - Video: poster frame. Hover (fine pointer): the video plays muted from the start inside the tile; leaves on pointer out.
  - Audio: waveform (gold bars at 60% on `--ctl-raised`, from stored peaks) with a 36px play button centre; plays in this browser, the bars fill gold as it plays.
  - Image: the image, `object-fit: cover`.
- **List:** rows 56px: thumb 40, name, type, tags, duration or size, date, menu.
- **Select:** a checkbox appears top-left of a tile on hover or focus (always visible once one is selected). A selection bar slides up at the bottom: "3 selected", Add to playlist, Tag, Delete, Clear.

### 10.2 Upload

- **Ways in:** Upload button (native file picker, `multiple`, `accept` from the limits table), drag and drop anywhere on the Library page, and the empty state.
- **Drop overlay:** while dragging files over the page, the page dims under `--ctl-overlay` and a centred panel shows "Drop to add to the Library" (Signika 28) with the limits line under it. 2px gold edge on the panel, `--ctl-wash` fill. Fades in 160ms. Dropping elsewhere in Control does nothing (no surprise uploads).
- **Upload tray:** bottom-right 400px panel (phone: sheet above the tabs), title "Uploading 3 of 5", collapsible. Each file row: type icon, name, size, a 4px progress bar (`transform: scaleX`, linear), state word: Waiting, Uploading 42%, Preparing, Added, Stopped. Cancel per row while uploading; "Retry" when stopped. Two uploads at a time; the rest wait. When all are done: "5 files added." and the tray closes itself after 4s (stays open if anything failed).
- **Preparing** (in the browser, before the item is saved): read duration and dimensions; for audio, decode and compute 200 waveform peaks; for video, grab a poster frame at 1s (or 10% in) as a JPG. These are uploaded with the file, so the server needs no ffmpeg.
- **Defaults:** name from the file name, tidied ("evening-reel_v3.mp4" becomes "Evening reel v3"); tag Music for audio, Screens for video and images. New tiles fade in and rise 8px over 400ms at the top of the grid.
- **Leaving mid-upload:** the browser's leave warning while anything is uploading.

### 10.3 Limits (proposed)

| Type | Formats | Max per file | Notes |
|---|---|---|---|
| Audio | MP3, M4A (AAC), WAV | 50 MB | WAV is large; MP3 or M4A preferred |
| Video | MP4 (H.264), WebM | 500 MB | Up to 3840×2160; 1920×1080 recommended; sound is ignored on screens |
| Image | JPG, PNG, WebP | 20 MB | At least 1280×720; under 1920×1080 adds the note "May look soft on large screens" |

- Up to 20 files per drop. Library total 10 GB (a setting, DEMO value; the meter warns from 90%: "Library nearly full").
- Rejected before any upload starts (checked in the browser by type and size, then again on the server by content, not by file name). Messages, each on the file's row:
  - "This file is 612 MB. Videos can be up to 500 MB."
  - "This type can't be used. For music use MP3, M4A or WAV."
  - "HEIC pictures can't be shown on screens. Save it as JPG and try again."
  - "The Library is full. Delete something to make room."
  - "Upload stopped. Check the connection and try again." [Retry]

### 10.4 Item panel

Side panel (phone: sheet), `?item=id`:
1. Preview with a real player: video with native-styled controls (play, scrub, time), audio as the large waveform with play and scrub, image at fit.
2. **Name:** shown as text with a pencil button; click turns it into a field (Enter saves, Esc cancels, saves on blur). 80 characters. Audio also has **Artist** (optional).
3. **Tags:** two toggle chips, Music and Screens (an audio file can't be Screens-only; video and images can't be Music).
4. **Details:** type, size, duration or dimensions, uploaded by (name), date.
5. **Used in:** playlists, screens and zones using it, as links.
6. **Delete** (text button in `--ctl-danger`): confirm "Delete Evening reel? It's used on 2 screens; they'll show Welcome instead." Cancel / Delete. Deleting is real and final.

### 10.5 Playlists

- Playlists sub-tab: cover tiles (cover = first four items as a 2×2 mosaic, or the swan pattern if empty), name, kind (Music / Screens), count and total time. "New playlist" opens a small dialog: name and kind (two choice tiles, "Music" / "Screens"), Create.
- **Playlist view** (`?playlist=id`, full page, not a panel): cover, name (rename as above), kind, "12 tracks, 48 min". Items as rows 56px: drag handle, thumb, name, duration; Screens playlists add "Show for" per image (seconds, stepper 4 to 60, default 8; videos play their length). Reorder by drag or keyboard (as the queue). Remove per row. **Add items** opens a picker sheet of Library files of the matching kind with checkboxes and "Add 4"; already added items show a check. "Play in a zone" (Music) or "Show on a screen" (Screens) as the primary action; "Delete playlist" at the bottom (files stay in the Library).
- Drag motion: the lifted row moves with the pointer (`transform`), sits on `--ctl-raised` with a 1px gold edge; other rows shift over 200ms `--ease-soft`. Keyboard moves are instant.

### 10.6 Real vs pretend (for the developer)

| Real (stored on the server) | Pretend (this browser only, `localStorage`) |
|---|---|
| Library files, posters, waveform peaks, names, artists, tags | Zones, what plays where, position, queue, volume, shuffle, repeat, mute |
| Playlists and their order and timings | Spotify connection and sample playlists |
| Who uploaded, when | Screen choices, play state, loop, schedules |
| Deletion | Lights, climate, scenes, people, alerts (as v1) |

- New models in a `control` (or `media`) app with migrations: media item, playlist, playlist item. Storage is the default storage (S3 on live, local media on the Mac). Files private; pages get short-lived signed URLs.
- Writes are POSTs, Admin level and up, CSRF, logged in the change history like other edits. Uploads use XHR (fetch has no upload progress). Recommendation: on live, video goes from the browser straight to S3 with a presigned POST so the web server never holds 500 MB; locally, through Django.
- This ends v1's "nothing is sent after load" rule for the Library only. Pretend state still never reaches the server. If a zone or screen points at a deleted file, it falls back (music stops with "This file was deleted"; screens show Welcome).

## 11. Empty states (copy)

| Where | Copy | Action |
|---|---|---|
| Library, no files | "Nothing here yet." / "Drop music, video or pictures here." + limits line | Choose files |
| Library, filters match nothing | "Nothing matches." | Clear filters |
| Playlists, none | "No playlists yet." / "Put music or screen media in order." | New playlist |
| Playlist, no items | "This playlist is empty." | Add items |
| Zone, nothing chosen | "Nothing playing in the Gym." | Choose music |
| Queue empty | "Nothing up next. Music stops after this track." | |
| Library picker, no Music items | "No music in the Library yet." | Go to Library |
| Screen off | "Off" on the preview | Turn on |
| Spotify, not connected | section 7.3 | Connect Spotify |
| Alerts | "No alerts" | |

Empty states sit centred in their area, a 32px Phosphor icon in `--ctl-text-3`, line 1 in 16px `--ctl-text`, line 2 in 14px `--ctl-text-2`, one button. No illustrations.

## 12. Motion (7B, restrained)

| What | How |
|---|---|
| Page load | Nothing animates on load. Data you read does not move for style |
| Tab change | Opacity cross-fade, out 120ms, in `--ctl-fade` |
| Side panel | `translateX(24px)` + opacity in `--ctl-panel-in`; out `--ctl-panel-out`; backdrop opacity |
| Phone sheet | `translateY(100%)` to peek in `--ctl-panel-in`; drag to full or down to close; a quick flick closes (velocity above 0.11 px/ms) |
| Scenes and presets | Light layers, plan light and values glide over `--ctl-glide`, rooms 60ms apart; Undo glides back |
| Dragging a slider | Instant everywhere (photo, plan, value) |
| Play / pause icon | Cross-fade + scale 0.9 to 1, 120ms |
| Track change | Artwork and title cross-fade `--ctl-art-fade` |
| Progress and upload bars | `transform: scaleX`, linear |
| New Library tiles | Fade + rise 8px, 400ms, once |
| Reorder | Others shift 200ms; keyboard moves instant |
| Drop overlay | Fade 160ms |
| Toasts | As v1 |
| Buttons | Scale 0.99 on press, 0.25s (BRAND 7B); hover only under `(hover: hover) and (pointer: fine)` |

Icons: Phosphor regular, added to `icons.svg`: `play`, `pause`, `skip-back`, `skip-forward`, `shuffle`, `repeat`, `repeat-once`, `speaker-x`, `headphones`, `upload-simple`, `pencil-simple`, `trash`, `dots-six-vertical` (drag handle), `bell`, `music-notes`, `film-strip`, `image`, `playlist`, `map-trifold`, `plus`, `magnifying-glass`, `dots-three`, `spotify-logo`.

Never: looping decoration (no equaliser bars, no pulsing dots), bounce, blur, animated filters. Video previews are content, not decoration.

**Reduced motion:** everything instant, cross-fades kept at 120ms opacity only, video previews show posters until played by hand, Library tile hover does not auto-play.

## 13. Phone (375)

- Banner (short text), top bar, content, mini player (when playing), bottom tabs (5) with safe area.
- Overview: the 3D model full width (turned 90 degrees, one finger tilts and turns, two zoom), or the transposed plan as the fallback, then numbers and Playing. Room sheet at peek.
- Rooms: one column cards (photo 3:2 full width).
- Music: zone list first as a horizontal row of zone chips (artwork 32 + name) above the player; player stacks: artwork `min(72vw, 280px)` centred, title, artist, scrub, transport, volume, Listen here, Change music; queue below. Source picker is a full sheet.
- Screens: one column; panel is a full sheet.
- Library: grid 2 across (`minmax(150px, 1fr)`); filters scroll sideways in one row; Upload in the top bar as an icon button; tray as a sheet; no drag and drop needed (file picker, which on iOS offers Files and Photos).
- Touch targets 44px, inputs 16px, no page-level sideways scroll.

## 14. Accessibility

- AA everywhere: only the v1 contrast pairs plus `--ctl-chip-bg` (11.9 over a white frame) for text. DEMO chip `--ctl-demo` on `--ctl-surface` 8.6.
- Plan rooms are links with full accessible names; the plan has a visually-hidden heading and the Rooms tab is the full non-visual equivalent.
- Players: buttons with labels that change ("Play Lounge zone" / "Pause Lounge zone"); scrub and volume are native ranges with `aria-valuetext`; track changes announced once via the polite live region ("Now playing Low Light in Lounge zone"), not every second.
- Drag and drop always has a keyboard path (handle + arrows, or "Move up" / "Move down" in the row menu) and a picker path for uploads.
- Upload tray is `role="status"` for the summary; each failure is text on its row, not colour.
- Panels and sheets: focus moves in, trapped where modal, Esc closes, focus returns.
- Video previews have no sound and pause off screen; nothing autoplays with sound anywhere. Listen here starts audio only on a click.
- No information by colour alone; every state has a word.

## 15. Acceptance checklist

1. Six tabs on desktop (Overview, Rooms, Music, Screens, Schedule, Library), five on phone with More; each control has one home, other places link to it.
2. DEMO banner with the new text on every page; Reset demo resets pretend state and leaves Library files and playlists untouched; DEMO chips on each simulated group, none in the Library.
3. Overview is the 3D model of section 4.0 (top view start, drag to tilt and turn, zoom, Top view button, calm floor tints, gold hover outline, labels, tap opens the panel) with the 2D floor plan of section 4.1 as the fallback (the real ground floor lighting plan: saunas, shower and cold plunge, relaxing zone, changing room, hallway, kitchenette, massage, gym, the Entrance with its curved wall and fish tank); each room lit by brightness and warmth; tapping a room opens its panel beside the plan (desktop) or a peek sheet (phone) and the plan re-lights live.
4. Phone plan is the transposed version, every controllable room at least 56px on its short side.
5. Room cards use the real photo; moving Light or Warmth visibly re-lights it (night, lamps, pool, warm, cool layers), Off shows a silhouette and "Off"; only opacity changes; lamps maps exist for every room photo.
6. Scene chips open the scene editor (4.3); Save scene and Apply now are separate; Apply glides the photos and the plan room by room over about 2s; Undo works; reduced motion is instant. Tapping any room anywhere on the Overview opens its Rooms panel; Back goes to the previous tab once and never loops (4.2).
7. Room panel: photo, light, climate, music trim and link, screen thumbnail and link; no source or content choosers inside it.
8. Music: five zones, edit rooms, Group all / Ungroup, Mute all with Undo; player with artwork, title, artist, source, scrub, shuffle, repeat (three states), previous, play/pause, next, volume, queue with drag and keyboard reorder.
9. Library source plays real uploaded tracks and playlists; Listen here plays the real file in this browser; without it, position and track changes follow real durations silently.
10. Spotify: Connect flow ends "Connected (demo)", Disconnect works, six sample playlists with typographic covers, Listen here disabled on Spotify.
11. Screens: six screens with live previews (real video, image, playlist, slides); at most 3 videos playing; panel with transport, loop, power, Slides / Library chooser, This screen / All screens, optional schedule shown on the Schedule tab.
12. Library uploads are real: picker, drag and drop overlay, tray with per-file progress, two at a time, cancel and retry, waveform, poster, duration and dimensions captured; limits from 10.3 enforced in the browser and on the server with the listed messages.
13. Library grid and list, filters, search, rename, tags, multi-select, delete with "used in" warning and fallbacks.
14. Playlists: create (Music or Screens), rename, add items, reorder by drag and keyboard, image timings, delete playlist keeps files.
15. Library writes are POST, Admin level and up, CSRF, change history; files private with signed URLs; pretend state never reaches the server.
16. Empty states as section 11; error copy as 10.3; no exclamation marks.
17. Motion as section 12, nothing on load, no looping decoration; reduced motion as stated.
18. Contrast and keyboard: focus ring on every control, ranges with `aria-valuetext`, live region announces track changes once.
19. Phone 375: bottom tabs with safe area, sheets with drag, mini player above tabs, 44px targets, 16px inputs, no sideways page scroll.
20. Screenshots at 375 and 1440 for review: Overview (room selected), Rooms (one room Off, one dimmed), Music (Library playing, Spotify connected), Screens with a panel open, Library grid with the upload tray and drop overlay, a Playlist view, and Schedule.
