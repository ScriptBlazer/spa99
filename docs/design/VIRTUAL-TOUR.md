# Spa 99: the virtual tour

Status: brief, 2026-10-23. Owner: design. Feature: `docs/features/virtual-tour.md`. Decisions: PROJECT.md 2026-10-23 (own page `/tour/`, no fal, rooms built in three.js). Builds on `docs/design/IMMERSIVE.md` 12 and 14 (WebGL palette, loader pattern, kill switch) and `docs/design/GOLD-CARD-3D.md` (canvas maps from the page's own SVG paths, warm PMREM, dispose contract). `docs/BRAND.md` wins.

Look reference per room: `.private/fal-renders/{lounge,dry-sauna,wet-sauna,relaxing-zone,gym,kitchenette,massage-room}.png` (1400 px copies in `.private/shots/tour/ref-*.jpg`).

## 0. In one screen

- You stand in a room at night. Drag (or tilt, once you allow it) to look around. A soft gold marker sits in each doorway; tap it and you glide through to the next room. A small room list jumps anywhere.
- One idea per screen: the room fills the screen, its name and one line sit low on the left, the list low on the right (below the line on a phone). Nothing else.
- Calm, not a game: no auto-spin, no head bob, no zoom, no sound, no labels in 3D, no text in WebGL (the logo is the logo, drawn from its SVG).
- Every room is its own URL and its own server-rendered page (`/tour/`, `/tour/<room>/`). Without WebGL, with reduced motion, Save-Data or no JS, the same page shows the room's photo instead of the canvas. Nothing else changes.
- Rooms: Lounge, Dry sauna, Wet sauna, Relaxing zone, Gym. Order fixed in that order.

Design read: a quiet first-person walk-through for men considering a membership; warm, dark-lifted, editorial. Motion is user-led only.

---

## 1. Page layout

`html[data-page="marketing"]` type scale. Page does not scroll in 3D mode (`overflow: hidden` on `body.tour-3d`); it may scroll in fallback only if the caption plus list overflow at 375 x 667 (they should not).

### 1.1 Layers (bottom to top)

| Layer | What | Notes |
|---|---|---|
| `.tour-stage` | `position: fixed; inset: 0; height: var(--scene-h)` espresso background | Holds the canvas (3D) or the photo (fallback) |
| `.tour-canvas` | the three.js canvas, full stage | `touch-action: none`, `tabindex="0"`, `role="img"`, `aria-label` "3D view of the {room}. Use the arrow keys to look around." |
| `.tour-snap` | a 2D canvas the same size, used only for the cross-fade (3.2) | `aria-hidden`, `pointer-events: none` |
| `.tour-veil` | two gradients: top `--color-veil` to transparent over `calc(var(--header-h) + 3rem)`; bottom transparent to `--color-veil` | Bottom gradient: transparent at 52% height, solid from 78% down (desktop); transparent at 40%, solid from 64% down (phone). Text only on the solid part |
| `.tour-markers` | DOM buttons projected from 3D (1.4) | Above the veil so they stay crisp |
| `.tour-ui` | caption, room list, hint, tilt chip | |
| Header | the existing header, on-dark, transparent over the top veil. It never hides (no scroll) and does not turn solid | Menu gets "Virtual tour" after The spa |

### 1.2 Desktop, 1440 x 800

```
+--------------------------------------------------------------------------+
| SPA 99      The spa  Virtual tour  Memberships  Gold Card  Book  Visit   |  header 72px over top veil
|                                                                          |
|                                (room, full bleed)                        |
|                     (o) Dry sauna        <- doorway marker               |
|                                                                          |
|                        [ grab icon  Drag to look around ]   <- hint      |
|                                                                          |
| VIRTUAL TOUR                                                             |
| Lounge                                                                   |
| The reef, the long bench and no reason to hurry.                         |
| See it on The spa  ->          Lounge  Dry sauna  Wet sauna  Relaxing zone  Gym |
+--------------------------------------------------------------------------+
```

- Caption: left edge `--page-margin`, bottom `--space-6`. Max width `--tour-caption-w` (26rem).
  - Label: `intro.heading` "Virtual tour", Figtree 500, `--text-sm`, uppercase, `--tracking-engraved`, `--color-gold`. The page's only small-caps label.
  - Room name: `<h1>`, Signika, `--text-2xl` (48px), `--leading-tight`, cream.
  - Line: Figtree `--text-lg`, `--color-text-muted-inverse`, max 2 lines.
  - Link: "See it on The spa" with the `arrow-right` icon, `btn-quiet` on dark, 44px tall. Goes to `/the-spa/#<slug>` (lounge: `/the-spa/`). This is also the exit; no separate close button (one intent, one control).
- Room list: `<nav aria-label="Rooms">`, right edge `--page-margin`, its baseline on the caption link's baseline. Five links in a row, gap `--space-4`, Figtree `--text-base`, `--color-text-muted-inverse`, each 44px tall. Current room: cream, a 1px `--color-gold` line 6px under the word, `aria-current="page"`. Hover (fine pointer): cream, 0.25s `--ease-soft`. No numbers, no dots.
- Hint: centred horizontally, top at 62% of the stage. Pill `--color-veil`, `--radius-sm`, padding `--space-2 --space-3`, Phosphor `hand-grabbing` (20px, gold) plus "Drag to look around." cream `--text-sm`.

### 1.3 Phone, 375 x 812 (check 375 x 667 too)

```
+-----------------------------+
| SPA 99               Menu   |  header 64px
|                    [ Tilt ] |  tilt chip (only where tilt exists)
|                             |
|        (room, full bleed)   |
|      (o)                    |
|     Wet sauna               |  marker label always shown on touch
|  [ Drag to look around ]    |  hint at 45% height
|                             |
| VIRTUAL TOUR                |
| Dry sauna                   |
| Pale wood, low light and a  |
| slow, dry heat.             |
| See it on The spa ->        |
| [Lounge][Dry sauna][Wet s.. |  chip row, scrolls sideways
+-----------------------------+   + safe-area inset
```

- Caption left `--page-margin`, name `--text-2xl` (32px), line `--text-base`. Caption block sits directly above the list, gap `--space-3`.
- Room list becomes one row of chips (the spa page link chip: `--chip-h` 44px, `--radius-sm`, 1px `--color-hairline-inverse` border, cream text). Horizontal scroll with `scroll-snap-type: x proximity`, `scroll-padding-inline: var(--page-margin)`, the current chip scrolled into view on load and on room change (no smooth scroll under reduced motion; that case is fallback anyway). Current chip: 1px `--color-gold` border, cream text, `aria-current="page"`.
- Bottom padding: `calc(var(--space-3) + env(safe-area-inset-bottom))`.
- Caption plus list is about 280px tall at 375 wide, leaving about 460px of clear room between header and veil. At 375 x 667 the line may clamp to 2 lines; never hide the name or the list.

### 1.4 Doorway markers

- A `<button class="tour-marker">` per doorway, absolutely positioned each frame from the doorway's 3D anchor (centre of the opening at 1.1 m height, so it reads as something in the door, below eye level).
- Look: a 44 x 44 tap target; inside, a `--tour-ring` (28px) disc of `--color-veil` with a 1.5px `--color-gold` ring and a 6px gold dot. Gold on espresso 6.17:1, so it reads over pale travertine too.
- Label: the destination name, Figtree `--text-sm`, cream on a `--color-veil` pill, 8px below the ring. Shown on hover and focus with a fine pointer; always shown on touch.
- `aria-label`: "Walk to the {room, lowercase}" ("Walk to the dry sauna").
- Hidden (opacity 0 over 200ms, `visibility: hidden`, out of the tab order) when the anchor is behind the camera, off screen or more than 70 degrees from the view centre. Tab order keeps all markers of the room: focusing a hidden one turns the view to face it (keyboard turn, 3.4) and then shows it.
- Arrival: each visible marker's halo pulses once (a ring scales 1 to 1.6 while fading 0.5 to 0, 1.6s `--ease-soft`), 400ms after the settle ends. No looping pulse. Hover: ring scale 1.06, 0.25s.
- Press: the ring fills gold for 120ms (acknowledgement), then the glide starts.
- The doorway itself also invites: beyond each opening, a plane lit in the next room's main colour (travertine, cedar or oak) with a warm `--color-light-warm` glow, so the eye is drawn to it before the marker.

### 1.5 Look-around hint

- Shown 1.2s after the first arrival of the session, fades in 800ms; fades out (300ms) on the first drag, key or tilt, or after 7s. Once per session (`sessionStorage`). Never on later rooms.
- Text by input (content rows): fine pointer "Drag to look around."; touch "Drag to look around."; touch with tilt on "Tilt or drag to look around.". Keyboard users get the canvas `aria-label`.

### 1.6 Tilt (gyroscope), and the iOS permission

Tilt is never on by default and never asked for on load.

- Shown only where `DeviceOrientationEvent` exists and the primary pointer is coarse. A chip top right under the header (`--space-3` from the header and the edge): Phosphor `device-rotate` icon plus "Tilt" (`hint_touch.cta_label`), `aria-pressed="false"`.
- Tap on iOS (`typeof DeviceOrientationEvent.requestPermission === 'function'`): call `requestPermission()` inside the tap handler (it must be a user gesture; it needs HTTPS, so test on the live or a tunnel URL).
  - `granted`: tilt on, chip `aria-pressed="true"` with a gold border, the hint (if still showing) changes to "Tilt or drag to look around.". The view does not jump: the current yaw and pitch become the zero of the device orientation.
  - `denied` or error: the chip goes away for the session, and the hint shows "Tilt is off in your settings. Drag to look around." for 4s. Never ask again in this session.
- Tap on Android and others: no prompt; it toggles straight on. If no `deviceorientation` event arrives within 1s, remove the chip quietly.
- Tap again: tilt off, the view holds where it is. Drag always works and adds to tilt (it shifts the yaw offset).
- Re-zero on `screen.orientation` change.

---

## 2. The rooms

### 2.0 Conventions for all rooms

- Units metres. Origin at the room's floor centre. x east (right on the plan), y up, z south. "North" = looking along -z. Yaw is measured from north, positive = turning right (that is `rotation.y` negative in three.js). Pitch positive = up.
- Eye height **1.6 m**. Pitch clamp -40 to +35 degrees. No roll. No moving the standing spot except by glides.
- Vertical FOV: **60 degrees** when the stage is landscape (aspect at least 1), **75 degrees** when aspect is 0.6 or less, linear in between. Phones see a narrower slice; that is what drag and tilt are for. Never wider (fish-eye looks cheap).
- Geometry: `BoxGeometry`, `PlaneGeometry`, `CylinderGeometry` (open arcs for curves and vaults), `CircleGeometry`, `ExtrudeGeometry` from `Shape` (benches, sofa, lounger frames, rounded pillows), `InstancedMesh` for anything repeated (slats, boards, dumbbells, stones, fish). Merge static meshes that share a material.
- Materials: `MeshStandardMaterial` (not Physical) for everything; `MeshBasicMaterial` for self-lit LED strips, downlight discs and the far doorway glow; one `ShaderMaterial` each for caustics and steam. Colours come from tokens via `getComputedStyle`, never hard-coded (section 7).
- "Contact shadow": a plane just above the floor under every bench, lounger, sofa and machine with a canvas radial gradient in `--color-espresso`, opacity 0.35 to 0.5, `depthWrite: false`. Walls get a baked "AO" band: the wall texture is darkened 18% toward the floor over 0.3 m and 10% toward the ceiling over 0.2 m when the canvas texture is generated.
- Lockup on the relaxing zone and gym walls = the **stacked** logo (swan above "SPA 99"): `common/static/common/img/logo-stacked-gold.svg` (and `logo-stacked-espresso.svg`), added 2026-10-23 from Moishe's brand PDFs. Use its paths for the mask instead of the horizontal `_logo.html`.
- Logo: never redrawn. The swan and the lockup are drawn into a canvas mask from the SVG paths already in the page (include `common/_mark.html` and `common/_logo.html` inside the tour template, hidden, the way `_gold_card.html` carries its swan), then used as `alphaMap` (and a normal map from the mask, as in GOLD-CARD-3D 1.4) on a plane 2 cm off the wall. Canvas 1024 tall (desktop), 512 (phone).
- Canvas textures (all generated at runtime, 0 KB download, in idle slots of 50ms or less): travertine (horizontal veins, 2 seeds: wall and floor), oak grain (caramel and walnut variants), boards and slats (the concept's `planks` generator), reef backdrop, caustics tile, moss, quilting, fish atlas, steam puff, halo (radial gradient), contact shadow, logo masks. Sizes: 1024 desktop, 512 phone; `SRGBColorSpace` for colour maps, `NoColorSpace` for masks and normals.

### 2.1 Lounge (`/tour/`)

Reference: lounge.png. The wide reef tank flush in travertine, the long bench with sage pillows running into a curved sofa, the green wall, the gold ceiling cove. At night: the photo's daylit window becomes a frosted glass panel glowing softly from the corridor beyond (it is also the doorway to the dry sauna).

**Shell:** 7.2 w x 6.0 d x 3.0 h (x -3.6..3.6, z -3.0..3.0). Dropped ceiling at 2.75 except the cove.

| Object | Build | Material |
|---|---|---|
| Tank wall (north) | A travertine slab 4.8 w x 3.0 h x 0.25 d proud of the wall, x -3.4..1.4, made of 4 boxes around the opening | Travertine, veins horizontal, roughness 0.55 |
| Reef tank | Opening **3.4 w x 1.5 h**, bottom at 0.55, centre x -1.0. Behind it a box 0.6 deep: back plane with the reef texture (layered coral silhouettes, rock, sea grass; 2048 x 1024 desktop, 1024 x 512 phone), floor plane (sand), water tint. Front glass: one plane, roughness 0.05, metalness 0, opacity 0.12, env reflection only | Reef back and floor: `MeshBasicMaterial` with the caustics shader on top (2.6). Water `--color-reef-water` |
| Bench plinth | 3.6 w x 0.42 h x 0.70 d box in front of the tank, x -2.8..0.8, z -2.4. LED strip under the lip: 3.6 x 0.02 at y 0.03, plus a halo plane on the floor | Travertine; LED `--color-led-warm` |
| Bench cushion | 3.5 x 0.10 x 0.62 on the plinth (extruded rounded rect, bevel 0.03) | `--color-cream-raised`, roughness 0.9 |
| Sage pillows | 6, each 0.50 x 0.40 x 0.14 rounded (extrude, bevel 0.05), leaning back 15 degrees against the glass, 0.55 apart | `--color-sage`, roughness 0.95 |
| Curved sofa | Continues from the bench end: an annulus sector extruded 0.42 high (r 1.5 to 2.3, 70 degrees, centre (2.2, 0, -1.0)), seat cushion 0.12 on top, back 0.75 high on the outer edge | `--color-cream-raised` |
| Coffee table and rug | Cylinder top r 0.45 x 0.04 at 0.40; base cylinder r 0.30. Rug: circle r 1.1 at y 0.005 with fine ring grooves (canvas) | Top travertine; base `--color-caramel` oak; rug `--color-cream` |
| Green wall | 0.55 w x 2.6 h panel at x 1.7, against the north wall | Moss texture, `--color-moss`, roughness 1 |
| Gold cove | Open cylinder arc r 3.4, 110 degrees, 0.30 tall, its centre over the sofa (1.0, 2.75, -0.2); underside a ShapeGeometry sector at y 3.0; an LED line along the inner lip | Gold leaf: `--color-gold-metal`, metalness 0.8, roughness 0.35; LED `--color-led-warm` |
| Pendant | Torus r 0.35, tube 0.015 at y 2.2 over the table | `MeshBasicMaterial` `--color-led-warm` |
| Fluted panelling | East wall, 0 to 1.0 m, slats texture | `--color-caramel` oak |
| Sconce | East wall at 1.7 m, z 1.2: a 0.06 x 0.30 cylinder, self-lit | `--color-led-warm` |
| Floor | Large tiles 1.2 x 0.6 | Travertine (floor seed), roughness 0.45 |

**Light (2700K):** Hemisphere sky `--color-led` ground `--color-caramel`, 0.7. Points (colour `--color-light-warm` unless said): cove (1.0, 2.6, -0.4) i 6 d 6; sconce (3.4, 1.7, 1.2) i 2 d 3; tank spill (-1.0, 1.2, -2.5) colour `--color-cream` i 1.2 d 3 (the blue stays inside the tank; the room is never lit blue). Mobile tier drops the sconce light (the self-lit sconce stays).

**Camera:** stands at (1.6, 1.6, 2.0). Initial look: at the tank centre, yaw -29 degrees (left of north), pitch -4. This is the photo's composition.

**Doorways:**
| Where | Opening | Leads to |
|---|---|---|
| East wall, the frosted glass panel's door leaf, z -1.2 | 1.0 w x 2.2 h | Dry sauna |
| West wall, x -3.6, z 1.8 | 1.2 w x 2.3 h open passage | Relaxing zone |
| South wall, x 1.2, z 3.0 (behind you at arrival) | 1.0 w x 2.2 h | Gym |

**Animated:** fish and caustics (2.6).

**Correction, 2026-10-23 (Moishe, after seeing the first build): the lounge layout.** Standing at the tank: to the RIGHT is more lounge seating (curved sofa, two armchairs, coffee table, rug; the east wall is a frosted window and fluted panelling, no sauna door). To the LEFT is reception: a curved cream stone desk with the backlit gold stacked lockup on its front, under the gold ceiling cove (the cove moved from the sofa to reception). Past reception, in the west wall of a longer shell (10.6 w x 6.0 d, x -7..3.6), are the three ways on, each an open doorway 1.0 x 2.2 with the next room's colour beyond: dry sauna (z -1.9), relaxing zone (z 0), gym (z 1.9). This replaces the Doorways table and the east, west and south doors above; the tank, bench, pillows, green wall, lights and camera (1.6, 1.6, 2.0, yaw -29) are unchanged. Markers sit at (-6.95, 1.1, z). Built in `rooms/lounge.js`.

### 2.2 Dry sauna (`/tour/dry-sauna/`)

Reference: dry-sauna.png. Plan from the old concept (`dry-sauna-concepts.html`, room GF07): interior **2.93 w x 4.34 d x 2.10 h** (x -1.46..1.46, z -2.17..2.17). Glass front on the south side.

| Object | Build | Material |
|---|---|---|
| Walls, ceiling | Planes; vertical boards on walls, ceiling boards along the length (concept `planks`, 0.09 boards) | `--color-cedar`, roughness 0.8 |
| Benches | L along the west and north walls. Lower seat at 0.45 (0.60 deep), upper at 0.90 (0.60 deep, against the wall). Seats as one `InstancedMesh` of slats 0.09 wide, 0.012 gaps; skirts as vertical boards; backrest slats on the wall from 0.95 to 1.40 above the upper bench | Seats and backrest `--color-aspen`; skirts `--color-aspen-shade`; bench ends `--color-walnut` |
| LED lines | Under each seat lip, and one along the west and north walls at 1.75 (the light line in the photo), each with a halo plane | `--color-led-warm` |
| Heater | East wall near the north corner, centre (1.0, 0, -1.4): oak frame 0.60 x 0.75 x 0.50 (boxes), steel tray on top, 80 instanced stones | Frame `--color-caramel`; tray `--color-walnut` metalness 0.4 roughness 0.5; stones `--color-stone` to `--color-stone-dark` |
| Glass front | South wall: fixed panel x -1.46..0.55, door opening x 0.55..1.25 (door leaf open flat against the inside east wall), frame | Glass `--color-glass-bronze`, roughness 0.05, `depthWrite: false`; frame `--color-walnut` |
| Swan on the glass | On the fixed panel, 0.95 m tall, centre at 1.25 m, x -0.45. Drawn from the mark paths, on the **outside** face only (one-sided, facing the corridor) so it is never seen mirrored | `MeshBasicMaterial`, `--color-cream` at 0.85 (frosted etch, as in the photo) |
| Floor | Aspen duckboard slats over `--color-floor-stone` | |
| Downlights | 2 self-lit discs r 0.04 in the ceiling | `--color-led-warm` |

**Light:** Hemisphere sky `--color-led` ground `--color-floor-stone`, 0.5. Points `--color-light-warm`: backrest wash (-1.2, 1.7, 0.6) and (-0.2, 1.7, -1.9), i 2.5 d 2.6; under the lower bench (-0.6, 0.35, 0) i 1.2 d 2 (dropped on mobile); heater (1.0, 0.85, -1.4) `--color-heater-glow` i 0.8 d 1.4.

**Camera:** standing spot (0.75, 1.6, 1.30), just inside the door. Initial look: yaw -25, pitch -10, down the benches toward the north-west corner.

**Arrival (this room only):** the settle starts in the corridor, 1.4 m outside the glass (0.75, 1.6, 3.55), looking north, so the cross-fade lands on the photo's view (swan on the glass, benches beyond); it then glides 2.25 m in through the open door to the standing spot while turning to the initial look, **2400ms** `--ease-soft`. Input is accepted after 1200ms (it takes over the settle smoothly).

**Doorways:** the glass door (x 0.9, z 2.17) leads to **Wet sauna** (the door opens onto the wet corridor). The way back is the room list.

### 2.3 Wet sauna (`/tour/wet-sauna/`)

Reference: wet-sauna.png. Travertine steam room, barrel vault, curved L bench with light underneath, the gold swan on the back wall, a bronze-framed glass door.

**Shell:** 2.4 w x 3.2 d (x -1.2..1.2, z -1.6..1.6). Walls to 2.25, then a barrel vault: half open cylinder r 1.2 along z, scaled y 0.55 (crown at 2.91), `BackSide`. North wall: a plane plus the half-ellipse `ShapeGeometry` above 2.25.

| Object | Build | Material |
|---|---|---|
| Walls, vault, floor | As above; slab joints drawn into the texture every 1.2 m | Travertine (wall seed) roughness 0.55; vault 0.6; floor travertine roughness 0.30 (wet) |
| Curved bench | L along the north and west walls: ExtrudeGeometry of the L outline with a 0.6 m inner corner radius and a rounded nose (bevel 0.04), extruded up to seat height 0.45, depth 0.55; a slab back 0.45 high behind the seat; the west arm ends in a rounded column (cylinder r 0.28) | Travertine, roughness 0.35 |
| Bench light | A self-lit strip 0.02 high just under the seat nose, following the L, plus halo planes on the floor | `--color-led-warm` |
| Swan | Back wall centre, 0.45 m tall, centre at 1.55 m. Mark mask as alpha plus normal map, 1 cm proud | `--color-gold-metal`, metalness 0.9, roughness 0.3 |
| Glass door | East wall, z 0.6..1.4 (0.8 w x 2.1 h), bronze frame and a bar handle | Glass `--color-glass-bronze`; frame and handle `--color-gold-shade`, metalness 0.8, roughness 0.4 |
| Downlights | 4 self-lit discs in the vault: (0, 2.85, -0.6), (-0.55, 2.7, 0.3), (0.55, 2.7, 0.3), (0, 2.85, 0.9), each with a faint additive cone (opacity 0.05) visible in the steam | `--color-led-warm` |

**Light:** Hemisphere sky `--color-led` ground `--color-caramel`, 0.6. Points `--color-light-warm`: three under the vault downlights (0, 2.6, -0.6), (-0.55, 2.5, 0.3), (0.55, 2.5, 0.3), i 2 d 3; bench glow (-0.4, 0.30, -0.9) i 1.5 d 1.5 (mobile: emissive only). `FogExp2`, colour = travertine shadow (`--color-travertine-vein`), density 0.06 (this room only).

**Camera:** (0.45, 1.6, 1.05), near the door. Initial look: yaw -6, pitch -6, at the swan wall.

**Doorways:** the glass door (x 1.2, z 1.0) leads to **Relaxing zone**.

**Animated:** steam (2.6).

### 2.4 Relaxing zone (`/tour/relaxing-zone/`)

Reference: relaxing-zone.png (the new one: thick cushioned loungers with bolsters and folded throws). Travertine walls with vertical LED lines, round moss panels on an oak pilaster, a coffered ceiling with a light cove, the backlit lockup.

**Shell:** 3.6 w x 8.0 d x 2.7 h (x -1.8..1.8, z -4.0..4.0). Coffer: inner ceiling raised to 2.85 over x -1.2..1.2, z -3.4..3.4, LED line along its edge.

| Object | Build | Material |
|---|---|---|
| Walls | Travertine panels 1.2 wide (joints in the texture). East wall: self-lit vertical LED lines 0.015 wide, full height, every 2.4 m, with halo planes | Travertine roughness 0.6; LED `--color-led-warm` |
| Oak pilaster and moss | West wall, z -2.8..-0.6: a 0.25 deep oak slab; three moss discs (circles r 0.30, 0.28, 0.26) at 1.4 m, z -2.4, -1.7, -1.0, each in a thin oak ring | Oak `--color-caramel` grain; moss `--color-moss` |
| Lockup | East wall, centre (1.78, 1.9, -0.6), 1.1 m tall. Lockup mask as alpha plus normal, 2 cm proud; behind it a halo plane (blurred mask, additive) | `--color-gold-metal` metalness 0.85 roughness 0.35; halo `--color-light-warm` at 0.5 |
| Loungers | 6, one every 1.15 m along z from -3.0 to 2.75, centred x 0.6, each turned 15 degrees toward the west wall. Side frames: ExtrudeGeometry of an S-curve profile (seat 0.40 high, back rising to 0.85, foot dipping to 0.30), 0.04 thick, two per lounger. Pad: the same curve offset, 0.12 thick, 0.62 wide, tufting texture. Bolster: cylinder r 0.10 x 0.60 at the head. Throw: folded block 0.45 x 0.06 x 0.30 on the pad | Frames `--color-caramel` oak; pad and bolster `--color-cream-raised` roughness 0.9; throw `--color-caramel` roughness 1 |
| Floor | Large travertine tiles, slightly glossy | Travertine floor seed roughness 0.35 |
| Downlights | 6 self-lit discs in the coffer | `--color-led-warm` |

**Light:** Hemisphere sky `--color-led` ground `--color-caramel`, 0.55. Points `--color-light-warm`: coffer (0, 2.55, -1.5) and (0, 2.55, 2.0), i 3 d 5; lockup backlight (1.55, 1.9, -0.6) i 1.5 d 2.

**Camera:** (-0.6, 1.6, 3.4), at the south end. Initial look: yaw 10, pitch -8, down the row of loungers with the lockup in the right third.

**Doorways:**
| Where | Leads to |
|---|---|
| South wall, x 0, z 4.0 (behind you) | Lounge |
| West wall, x -1.8, z -3.4 (far end, left) | Gym |

### 2.5 Gym (`/tour/gym/`)

Reference: gym.png. Dark room, smoked oak panel wall with the gold lockup, mirrors, a ceiling cove, dark oak floor, a few machines. Dark but lifted: never black.

**Shell:** 7.0 w x 6.0 d x 2.8 h (x -3.5..3.5, z -3.0..3.0). Dropped ceiling with an LED cove 0.4 in from the walls.

| Object | Build | Material |
|---|---|---|
| Oak panel wall | West wall, z -2.2..1.2: three tall panels (boxes, 3 mm reveals), 2.6 h | `--color-walnut` with oak grain, roughness 0.6 |
| Lockup | On the middle panel, centre (-3.48, 1.55, -0.5), 1.3 m tall, 1.5 cm proud | `--color-gold-metal` metalness 0.9 roughness 0.3 |
| Mirrors | North wall 1.0 to 2.4 m, full width, three panels with 6 mm joints. Not real reflections: glossy dark glass that picks up the room's PMREM | `--color-walnut`, metalness 1, roughness 0.08 |
| Floor | Planks 0.18 wide, random lengths | `--color-walnut` grain lifted 10%, roughness 0.5 |
| Dumbbell rack and bench | Rack (boxes) at (-0.5, 0, -2.4) with 10 instanced dumbbells (cylinder bar plus two heads); flat bench (boxes plus padded top) at (0, 0, -1.4) | Frames `--color-iron`; pad `--color-espresso` roughness 0.6 |
| Cable tower | At (2.6, 0, -1.6): two uprights 2.3 h, top beam, 4 pulleys (cylinders), weight stack box, cables (thin cylinders) | `--color-iron`, metalness 0.6, roughness 0.45 |
| Cove and downlights | LED line in the cove, 6 self-lit discs | `--color-led-warm` |

**Light:** Hemisphere sky `--color-led` ground `--color-walnut`, 0.45. Points `--color-light-warm`: cove (0, 2.6, -1.0) and (0, 2.6, 1.8), i 4 d 6; lockup grazing (-2.6, 2.3, -0.5) i 2 d 2.5.

**Camera:** (1.5, 1.6, 2.2). Initial look: yaw -38, pitch -4, at the panel wall and lockup, machines in the right half.

**Doorways:**
| Where | Leads to |
|---|---|
| South wall, x 1.0, z 3.0 (behind you) | Lounge |
| East wall, x 3.5, z 0.8 | Relaxing zone |

### 2.6 Animated details

All ambient loops run at 30 fps, are paused when the tab is hidden, and are slower than one visible cycle per 15s where they cycle at all.

**Reef fish (lounge).** One `InstancedMesh` of side-view planes, 0.06 to 0.14 m long, from a 512 x 256 atlas of 6 silhouettes (reef colours, slightly desaturated and warm-graded). Counts: 24 high tier, 12 mobile, 6 low. Each fish swims a horizontal lane inside the tank (x range of the opening minus 0.1, y 0.65 to 1.95, depth 0.1 to 0.5 behind the glass) at 0.06 to 0.20 m/s, with a vertical sine bob of 0.02 to 0.04 m (period 4 to 7s) and a tail wobble by a 2-frame UV swap every 0.4s. At the lane end it turns by flipping scale.x over 600ms. Deeper fish are dimmer (multiply by 0.7 at 0.5 m depth). Nothing faces the camera; they are a picture in the wall, as in the photo.

**Caustics and rays (lounge).** `ShaderMaterial` on the reef back and floor: two copies of a 256 x 256 caustics tile (canvas, Voronoi-like cell edges) scrolling at 0.020 and -0.014 UV/s, multiplied, added at 0.25 strength over the base reef texture. Three additive light-ray planes from the top of the tank, opacity 0.06 to 0.12, drifting 4 cm sideways over 24s. Low tier: caustics frozen (still added, no scroll).

**Steam (wet sauna).** 8 high / 5 mobile / 3 low soft planes (256 x 256 canvas puff, `--color-cream`, normal blending, `depthWrite: false`, opacity 0.06 to 0.12), each facing the camera (billboard around y only), rising from bench height to 2.6 m at 0.03 m/s with 0.01 m/s drift and a slow spin of 2 degrees per second, fading in over the first 15% and out over the last 25% of its 40s life, then respawning. The fog density breathes 0.055 to 0.065 over 20s.

**Heat shimmer (dry sauna, optional, high tier only).** Skip in round 1. If added later: a 0.5 x 0.8 plane above the heater stones sampling a screen copy with a tiny sine offset (1 px at 1440). Off on mobile and low.

The relaxing zone and the gym have no ambient animation: render on demand only (3.6).

---


### 2.7 Round 2 notes (2026-10-23, Moishe)

**Doorway graph, round 2 (replaces the graph in 6.1 and the doorway tables above).** Chain: lounge, gym, kitchenette, massage room, then dry sauna (left) and wet sauna (right). Lounge to Gym (passage beside reception) and Relaxing zone (passage past the seating); Relaxing zone to Lounge; Gym to Lounge and Kitchenette; Kitchenette to Gym and Massage room; Massage room to Kitchenette, Dry sauna (left) and Wet sauna (right); Dry sauna to Massage room and Wet sauna; Wet sauna to Massage room and Dry sauna. The room list reaches any room.

- **Lounge.** Reception is now a half-round counter (radius 1.0 to 1.6, centre on the west wall at z 0.4) growing out of the west wall, which is plain behind it (the three doorways are gone). Gold cove and lockup follow the desk. Gym passage: north wall, x -5.6, 1.0 x 2.2, marker (-5.6, 1.1, -2.95). Relaxing-zone passage: east wall, z 2.0, past the seating (flutes stop short of it), marker (3.55, 1.1, 2.0). No sauna markers. Tank, seating and look unchanged.
- **Lounge correction (2026-10-23, Moishe; reference `docs/design/reference/tour/lounge-reception-corridor.jpg`; second pass the same day).** Supersedes the lounge bullet above for the desk and the gym passage. The desk keeps its curved end on the west wall (quarter ring, radius 1.0 to 1.6, centre (-7, 1.0)) and runs straight along the west wall to the south wall (x -6.0..-5.4, z 1.0..3.0): it sits in the south-west corner, the corner opposite the tank wall. The stacked gold Spa 99 lockup (dark iron inset, glow halo; no "BML SPA", no wall signage) is on the straight front, centred z 2.0. Gold cove centred (-5.0, 1.0). The way to the rooms is a long straight corridor in the SAME west wall as the desk, immediately to its right as you face it (north of it, between the desk and the tank-wall corner), opening at z -2.7..-1.1, 2.4 high, running 6 m west to x -13, parallel to the tank wall. It is not in the tank wall or the south wall (both plain). Corridor: travertine floor and walls, gold-leaf ceiling with warm LED cove lines both sides and LED lines at the floor, three gold fins at each jamb, a stone bench with cushion and a round plinth on the tank-side wall, two doors on that side and one opposite, a lit oak door at the far end, one warm point light (the lockup backlight light was dropped to stay inside the 4-light cap; the lockup is self-lit). Gym marker (-10, 1.1, -1.9), inside the corridor, 3 m in, with the lit end door behind it. First view: pos (2.9, 1.6, -0.8), yaw -97, pitch -5, arrive from (3.3, 1.6, -0.5): the corridor opening with the desk beside it, the tank wall running along the right; a short drag brings in the seating. Relaxing-zone passage, tank, seating and look unchanged. Not checked in a live browser (the sandbox could not serve or render WebGL); the module builds clean in a node smoke test.
- **Relaxing zone.** TV on the west wall at z 1.7, 1.44 x 0.81, centre y 1.4, slim `--color-iron` frame, screen a dark canvas with a faint warm diagonal sheen and a small warm glow, no picture, no text. The west doorway to the gym is removed; the only marker is the lounge.
- **Gym (2026-10-26, Moishe: much smaller).** Now only one treadmill (x 2.3, z -2.9) and one exercise bike (x 2.5, z -1.6) facing a wall screen (off) on a walnut panel on the east wall, a shorter night window to the south of it, and one dumbbell rack on a rubber mat on the west wall. The power rack, benches, kettlebells, plates, cable machine, rower and the other treadmills and bike are gone. Shell, mirrors, passage, markers and lights unchanged. The tour's fallback photo is `gym-tour` (`TOUR_PHOTO_NAMES` in `pages/services.py`); The spa keeps `gym`. Superseded entry below:
- **Gym (round 2).** Shell is now 7.0 x 8.0 (z -5..3). East: night window and, facing it, 3 treadmills (z -3.7, -2.55, -1.4), 2 bikes, a rower. West: oak panels with the lockup, a rubber zone with a 12-dumbbell rack (heads instanced), a power rack with a loaded barbell, 2 adjustable benches (one inclined), 8 kettlebells and 9 plates (instanced), and a cable machine at the north wall. North: mirrors with a short passage in the middle; its back wall has one door with a marker to the kitchenette. Markers: lounge (south), kitchenette (north). About 30 draw calls.
- **Kitchenette and massage room (added, 2026-10-23).** `TOUR_ROOMS` order is now lounge, gym, kitchenette, massage-room, dry-sauna, wet-sauna, relaxing-zone. Doorways: gym to kitchenette (south door, x -1.0) to massage room (east door, z -0.9); the massage room's south door goes back to the kitchenette, its west door (z -2.1, left) to the dry sauna and its east door (z -2.4, right) to the wet sauna. Kitchenette (4.4 x 5.0 x 2.7, look from `.private/fal-renders/kitchenette.png`): walnut counter with travertine top and splashback on the north wall, bronze built-in coffee machine and tap, one open oak shelf of 13 cream cups (instanced), the gold swan on the walnut panel above with an LED wash, cream fluted panelling low on the other walls, two low caramel boucle chairs round a round travertine table under a frosted pendant. Massage room (3.6 x 6.4 x 2.7, look from `massage-room.png`): oak slatted north wall with the gold swan, three cream-leather chairs with walnut sides along the east wall facing west with gaps (parts instanced), a stone chimney breast on the west wall with a flush linear fireplace (two additive flame layers scrolling slowly, a flickering floor glow and point light, 30 fps ambient) and a 75 inch dark TV above it, LED coves along both side walls. No fake facts: no amenity promises in the copy.

## 3. Motion

### 3.1 Tokens and curves

- `--ease-soft` `cubic-bezier(0.22, 1, 0.36, 1)` (GSAP `soft`) for arrivals, turns, fades and UI, as everywhere.
- **Proposed:** `--ease-glide` `cubic-bezier(0.65, 0, 0.35, 1)` (ease-in-out cubic) for the camera's travel toward a doorway only. Reason: travel starts from rest; a soft ease-out would lurch at the first frame. Nothing else uses it.
- No bounce, no overshoot, no camera roll, no FOV change.

### 3.2 Moving to a room (marker)

| t | What happens |
|---|---|
| 0 | Ring fills gold (120ms). Caption fades out (opacity 1 to 0, 240ms). Markers fade out (200ms). Input is ignored until arrival (the room list still works; a new request replaces the queued one) |
| 0 | **Turn** to face the doorway if more than 5 degrees off: duration 400ms + 3ms per degree, max 900ms, `--ease-soft`. Pitch eases to 0 |
| 40% of the turn | **Glide** toward the door: to 0.5 m before the door plane, at most 2.5 m of travel. Duration 700ms + 250ms per metre, max 1400ms, `--ease-glide` |
| glide end | **Snapshot**: right after the last outgoing render, `drawImage(webglCanvas)` onto `.tour-snap` (same frame, so no `preserveDrawingBuffer`), set it to opacity 1, swap to the new room's scene, camera at its arrival start (3.3) |
| + 0 | **Cross-fade**: `.tour-snap` opacity 1 to 0, **700ms** `--ease-soft`, while the new room settles underneath |
| + 350ms | New caption in: opacity 0 to 1 and rise 8px to 0, 800ms `--ease-soft`. The list's current item changes instantly (state, not animation). URL `history.pushState('/tour/<slug>/')`, `document.title` updated, `<h1>` text updated |
| settle end + 400ms | Markers fade in (300ms), halo pulse once (1.4) |

Typical total: about 2.3s from tap to stillness (2.9s worst case, plus 1s more for the dry sauna's walk-in).

If the next room is not built yet at glide end: hold on the snapshot, dim it toward espresso (an espresso layer 0 to 0.4 over 1200ms) and show a 1px `--color-gold` progress line (scaleX, linear) across the top of the caption area. When ready, continue as above. After 8s, give up: that room opens as its photo page (normal navigation).

### 3.3 Arrival settle

- Camera starts 0.9 m behind its standing spot (along the initial look, flattened) with pitch 3 degrees below the initial pitch, and glides to the spot and the initial look over **1400ms** `--ease-soft`. Dry sauna: 2.25 m, 2400ms (2.2).
- First load of the page: the stage is espresso with the caption already visible (text is the LCP). When the first frame is ready, the canvas fades in over `--duration-gl-in` (1200ms) and the settle runs at the same time. No photo poster under the canvas: a photo cross-fading into a 3D room shows every difference.
- Room list jump (not via a marker): no turn or glide. Snapshot, cross-fade 700ms, settle 1400ms.
- Back and forward buttons (`popstate`): same as a list jump.

### 3.4 Looking around

| Input | Mapping | Follow |
|---|---|---|
| Drag (mouse or touch) | 1:1 "grab the room": a drag across the full stage width turns the horizontal FOV; vertical likewise with the vertical FOV | Rendered view follows the target with `v += (t - v) * (1 - exp(-dt / 90ms))` |
| Release | Inertia from the last 80ms of velocity, decaying with a 250ms time constant, capped at 20 degrees of coast | |
| Arrow keys (canvas focused) | Left/Right 15 degrees yaw, Up/Down 8 degrees pitch per press, each a 500ms `--ease-soft` tween; holding repeats every 350ms | |
| Tilt | Device orientation as a quaternion (own 40-line helper; three no longer ships DeviceOrientationControls), relative to the pose when tilt was turned on, plus the drag yaw offset | Smoothed with a 120ms time constant |
| Focus a hidden marker (Tab) | Turn to face it, as the arrow-key tween, duration as the marker turn (3.2) | |

- Cursor: `grab`, `grabbing` while dragging (fine pointer). No custom cursor.
- No wheel or pinch zoom. Wheel does nothing (the page does not scroll either).

### 3.5 Idle

Nothing moves the camera on its own. No auto-spin, no "look here" nudges, no hint coming back. Only the ambient fish, caustics and steam keep living.

### 3.6 Render loop

One `requestAnimationFrame` loop (no GSAP needed on this page; tweens are small hand-written ones with the two curves, or GSAP core if already cached, not ScrollTrigger). It renders at full rate while input, a tween or a transition is active; at 30 fps when only ambient animation runs (lounge, wet sauna); not at all when nothing changes (relaxing zone, gym, dry sauna at rest). Stops on `visibilitychange` hidden.

---

## 4. Rendering look and performance

### 4.1 Look

| Setting | Value |
|---|---|
| Renderer | `WebGLRenderer({ antialias: true, powerPreference: 'high-performance', alpha: false })`, clear colour `--color-espresso` (never black) |
| Colour | `outputColorSpace = SRGBColorSpace`; colour textures `SRGBColorSpace` |
| Tone mapping | `NeutralToneMapping` (keeps the gold at hue 31, as for the Gold Card; ACES pushes it to orange) |
| Exposure | Lounge 1.0, Dry sauna 0.95, Wet sauna 1.05, Relaxing zone 1.0, Gym 1.15. Tune by eye side by side with the photo |
| Environment | Per room, a tiny warm studio box (walls in the room's main colour, one `--color-led` softbox overhead) rendered once to PMREM at 128 px, then disposed. Gives the gold, the glass, the mirrors and wet stone something warm to reflect. No HDR download |
| Shadows | No shadow maps. Contact-shadow planes and baked AO bands (2.0) |
| Glow | Halo planes (additive radial gradient) beside self-lit strips. No bloom |
| Post effects | None. No bloom, no SSAO, no depth of field, no film grain, no vignette in WebGL (the veil does the framing). Fog only in the wet sauna |
| Grade check | Mean luminance of the initial view within 12% of the reference photo; no pixel darker than `--color-iron`; outside the lounge tank, no pixel with blue above red |

### 4.2 Budget

| Item | High tier | Mobile tier |
|---|---|---|
| Frame rate | 60 fps while moving, 30 ambient | 60 target, 30 accepted; 30 ambient |
| Pixel ratio | `min(dpr, 2)` | `min(dpr, 1.5)` |
| Draw calls per room | 50 or fewer | 40 or fewer |
| Triangles per room | 80k or fewer | 40k or fewer |
| Point lights per room | 4 or fewer | 3 or fewer |
| Textures per room | 8 or fewer, largest 1024 (reef 2048 x 1024) | 8 or fewer, largest 512 (reef 1024 x 512) |
| GPU memory per room | 40 MB or less | 16 MB or less |
| Rooms held in memory | current, the previous one, and one warmed by hover or focus; older ones disposed (cap of three) | same |
| GPU time per frame at 1440 x 800 | 6 ms or less | |

**Tiers.** High: at least 64em, `deviceMemory` 4+ and `hardwareConcurrency` 4+. Mobile: everything else that passes the gate (4.4). Low (automatic): if the median frame over 2s exceeds 22 ms, drop pixel ratio to 1, fish to 6, steam to 3, freeze caustics, and stay low for the session.

**JS (gzip).**
| File | Cap |
|---|---|
| `vendor/three/three.module.min.js` | 165 KB (entry extended with `MeshStandardMaterial`, `CylinderGeometry`, `CircleGeometry`, `TorusGeometry`, `InstancedMesh`, `Object3D`, `PointLight`, `HemisphereLight`, `ShaderMaterial`, `FogExp2`, `Quaternion`, `AdditiveBlending`, `DoubleSide`; re-measure, update `VERSION`) |
| `common/js/tour.js` (renderer, input, markers, transitions, texture generators, logo masks) | 16 KB. Raised 2026-10-23 to 25 KB for `tour/engine.js` + `kit.js` + `textures.js` together (measured 24.8 KB gzip) |
| `common/js/tour-rooms/<slug>.js` (one per room) | 6 KB each. Raised 2026-10-23 to 6.5 KB (lounge is 6.0 KB) |
| First room total | 190 KB or less |
| Tour CSS | 6 KB |

**Loading.** three.js and `tour.js` only on `/tour/` pages, never in `<head>`, never preloaded, requested after `DOMContentLoaded` once the gate passes. The current room's module loads with them (hashed URL in a `data-room-src` attribute; dynamic `import()` is not rewritten by the static storage, IMMERSIVE 14.3). Texture generation runs in idle slots of 50ms or less, then `renderer.compile()`, then the first frame. After arrival plus idle, the neighbour rooms' modules are fetched (JS only). A room is built when its marker is hovered or focused (desktop) or at tap (touch), so the build overlaps the glide. First room: canvas visible within 3s on a throttled mid phone (Lighthouse mobile: slow 4G, 4x CPU).

**Dispose.** As GOLD-CARD-3D 5: idempotent; every geometry, material, texture, PMREM target, listener and observer; one WebGL context per page; `webglcontextlost` swaps to the photo of the current room at once.

### 4.3 Accessibility in 3D mode

- Each room change updates the `<h1>`, the title and a polite live region: "{Room}. {line}". Focus: after a marker, focus moves to the `<h1>` (`tabindex="-1"`); after a list link, focus stays on the list.
- Tab order: header, canvas, markers, caption link, room list, tilt chip.
- Focus ring: 2px `--color-focus-inverse` (gold), offset 3px, on everything including markers and the canvas.

### 4.4 The gate (this page's own)

3D runs when all are true: JS; `<html data-webgl>` is not `off`; not `prefers-reduced-motion: reduce`; not Save-Data or `prefers-reduced-data: reduce`; WebGL2 with `failIfMajorPerformanceCaveat: true`. Unlike IMMERSIVE 14.0, phones and tablets are allowed (this page is the experience), on the mobile tier.

---

## 5. Fallback (reduced motion, no WebGL, Save-Data, no JS, context lost)

Same page, same layout, same text, same list. Only the stage changes.

- The stage shows the room photo full bleed with `{% photo "<image>" alt=... sizes="100vw" eager=True %}` (LCP), object-position from the room's focus: lounge 28% 55%, dry-sauna 50% 55%, wet-sauna 50% 40% (portrait image), relaxing-zone 55% 60%, gym 40% 55%. A `room_<slug>` section image overrides it.
- The room list links are real links to `/tour/<slug>/` (they are in both modes; JS intercepts them in 3D). Page changes use the site's existing View Transition cross-fade.
- No markers, no hint, no tilt chip, no canvas, and three.js is never requested.
- Save-Data with motion allowed: the photo settles 1.04 to 1 over 1200ms `--ease-soft` once. Reduced motion: still.
- If reduced motion is switched on, or the context is lost, while in 3D: dispose, show the photo of the current room (no fade), keep the URL.

---

## 6. URLs and content

### 6.1 URLs

- `/tour/` is the Lounge (canonical). `/tour/lounge/` redirects 301 to `/tour/`.
- `/tour/<slug>/` for `dry-sauna`, `wet-sauna`, `relaxing-zone`, `gym` (the `Facility` slugs). The room must be in the tour list and its `Facility` must be visible; anything else is a 404 (including real facilities not in the tour, such as `cold-plunge`).
- Tour order and the list: `TOUR_ROOMS = ["lounge", "dry-sauna", "wet-sauna", "relaxing-zone", "gym"]` in code. Names come from `Facility.name`; the lounge is not a `Facility` today (see question 1), so its name comes from its content row.
- Doorway graph (superseded by 2.7, round 2): Lounge to Dry sauna, Relaxing zone, Gym; Dry sauna to Wet sauna; Wet sauna to Relaxing zone; Relaxing zone to Lounge, Gym; Gym to Lounge, Relaxing zone. It follows the ritual (heat, steam, rest); the list reaches any room.
- The spa: each toured room gets a "Take the tour" link to `/tour/<slug>/`. Header and menu: "Virtual tour" after The spa, `aria-current` on all `/tour/` pages.

### 6.2 Content rows (page `tour`)

Page: key `tour`, title "Virtual tour", meta description "Look around the lounge, the saunas, the relaxing zone and the gym at Spa 99, 99 Vale Road, London N4."

| Section key | heading | body | cta_label | cta_url |
|---|---|---|---|---|
| `intro` | Virtual tour | Look around the rooms, then walk through. (used in the canvas description) | | |
| `hint` | | Drag to look around. | | |
| `hint_tilt` | | Tilt or drag to look around. | | |
| `tilt` | | Tilt is off in your settings. Drag to look around. | Tilt | |
| `room_lounge` | Lounge | The reef, the long bench and no reason to hurry. | See it on The spa | /the-spa/ |
| `room_dry_sauna` | (blank = Facility name) | Pale wood, low light and a slow, dry heat. | See it on The spa | (blank = /the-spa/#dry-sauna) |
| `room_wet_sauna` | | Warm stone under soft steam. | See it on The spa | |
| `room_relaxing_zone` | | Lie back. Nothing here needs you. | See it on The spa | |
| `room_gym` | | Free weights and machines, in low warm light. | See it on The spa | |
| `room_kitchenette` | | A quiet corner for a warm drink and a low chair. | See it on The spa | |
| `room_massage_room` | | Slatted oak, soft light and a fire to settle beside. | See it on The spa | |

A blank room body falls back to `Facility.short_line`. A room section image overrides the fallback photo. Page `spa` gets `tour_link` with cta_label "Take the tour".

---

## 7. Copy and tokens

### 7.1 Copy (all strings)

British English, calm, no exclamation marks, no em dashes.

- Label: "Virtual tour". Menu: "Virtual tour". On The spa: "Take the tour".
- Room lines: as 6.2.
- Hints: "Drag to look around.", "Tilt or drag to look around.", "Tilt is off in your settings. Drag to look around."
- Tilt chip: "Tilt" (`aria-pressed`).
- Marker: visible "{Room}"; accessible "Walk to the {room}".
- Link: "See it on The spa".
- Canvas: "3D view of the {room}. Use the arrow keys to look around."
- Live region: "{Room}. {line}"
- `<title>`: "{Room}, virtual tour" plus the site's usual suffix.

### 7.2 Tokens

The four brand colours are untouched. Everything below is derived and decoration only (never text). Values marked "existing" are already in `tokens.css`; the WebGL palette from IMMERSIVE 12 is documented but **not yet in `tokens.css`**: add it with this round.

| Token | Value | Status and use |
|---|---|---|
| `--color-light-warm` | `#FFA957` | IMMERSIVE 12, add to tokens.css. Every point light (2700K) |
| `--color-led-warm` | `#FFC48A` | **Proposed** (IMMERSIVE 12's `--color-led` value, renamed: `--color-led` already exists as `#FFE8C8` for the Gold Card). Self-lit LED strips, downlights, halos |
| `--color-led` | `#FFE8C8` | Existing. Hemisphere sky, PMREM softbox |
| `--color-heater-glow` | `#FF8A3D` | IMMERSIVE 12, add. Heater stones |
| `--color-aspen`, `--color-aspen-shade`, `--color-cedar`, `--color-walnut`, `--color-stone`, `--color-stone-dark`, `--color-floor-stone`, `--color-glass-bronze` | as IMMERSIVE 12 | Add. Dry sauna, gym floor and panels |
| `--color-gold-metal`, `--color-gold-shade` | existing | Gold leaf, swan, lockups, bronze door frame |
| `--color-cream-raised` | existing | Upholstery |
| `--color-travertine` | `#E4D2B1` | **Proposed**: cream 70% + caramel 30%. Travertine base |
| `--color-travertine-vein` | `#CCA87C` | **Proposed**: cream 30% + caramel 70%. Veins, wet sauna fog |
| `--color-iron` | `#2C1C14` | **Proposed**: espresso at 60% brightness. Gym machines; the darkest value anywhere |
| `--color-sage` | `#A3A98A` | **Proposed, outside the brand hues** (question 4). Lounge pillows |
| `--color-moss` | `#5F6B3C` | **Proposed, outside the brand hues** (question 4). Green wall, moss discs |
| `--color-reef-water` | `#2E6E86` | **Proposed, outside the brand hues** (question 4). Inside the tank only |
| `--tour-caption-w` | `26rem` | Derived. Caption width |
| `--tour-ring` | `1.75rem` | Derived. Marker ring (tap target stays 2.75rem) |
| `--ease-glide` | `cubic-bezier(0.65, 0, 0.35, 1)` | **Proposed**. Camera travel only (3.1) |
| `--duration-glide-fade` | `700ms` | Derived. Room cross-fade |
| `--duration-settle` | `1400ms` | Derived. Arrival settle |

Icons: add Phosphor `hand-grabbing` and `device-rotate` (regular weight) to `icons.svg` (MIT, licence file already there).

---

## 8. Acceptance checks (375 x 812, 375 x 667 and 1440 x 800)

1. `/tour/` opens in the Lounge looking at the tank as in the photo; `/tour/gym/` opens the Gym; `/tour/lounge/` redirects to `/tour/`; `/tour/cold-plunge/` and `/tour/nowhere/` are 404.
2. Layout: caption bottom left on the solid veil, list bottom right (1440) or chip row (375), nothing overlapping the header, the name and list never clipped at 375 x 667, safe area respected on iPhone.
3. Look-around works by mouse drag, touch drag, arrow keys and (after the tap) tilt; pitch clamps; no roll; no zoom; the view never moves on its own.
4. iOS: no permission prompt on load; the prompt appears only after tapping Tilt; denying removes the chip and shows the one-line note; the view does not jump when tilt turns on.
5. Each marker glides through its doorway and lands in the right room with the cross-fade and settle at the specified timings (check at 2x slow-down in DevTools); the list jumps anywhere; back and forward work; the URL, title and `<h1>` follow.
6. Keyboard only: every marker and list item reachable; focusing a hidden marker turns the view to it; focus is visible (gold) on every control; a screen reader announces each new room.
7. Side by side with each reference photo at 1440: same materials and warmth, mean luminance within 12%, never black, no blue cast outside the tank; the gold reads as brand gold (hue near 31), not brass.
8. The swan on the dry sauna glass is never seen mirrored; every logo in the rooms comes from the SVG paths.
9. Reduced motion, Save-Data, `data-webgl="off"`, WebGL disabled and no JS: the photo page with the same text and list, and no request for three.js or `tour.js` in the network panel.
10. Performance: first room visible within 3s on Lighthouse mobile throttling; 60 fps while dragging on an M1 Air and an iPhone 12-class phone; no long task over 50ms after arrival; draw calls and triangles within 4.2 (`renderer.info`); JS sizes within caps; no console errors.
11. Leaving the page or switching to the photo mode disposes everything (`renderer.info.memory` 0); never more than one WebGL context.
12. Copy: every string from section 7.1, no exclamation marks, no em dashes.

**Doorway graph, round 3 (2026-10-25) supersedes round 2 above.** Chain from the real plan: lounge, gym, massage room, kitchenette, relaxing zone, then wet sauna (left) and dry sauna (right). See `docs/features/virtual-tour.md`, "Door chain".
