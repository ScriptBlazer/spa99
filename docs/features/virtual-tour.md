# Feature: Virtual tour

Branch `feature/virtual-tour`. Decisions: PROJECT.md, 2026-10-23 rows on the virtual tour. `docs/BRAND.md` wins on look and tokens.

## What it is

A page, **Virtual tour** at `/tour/`, where a visitor stands inside Spa 99's rooms and looks around. The rooms are 3D models we build ourselves in three.js (no fal, no external tour service). Fun, calm and premium: it should feel like walking through the real place at night, not a game.

## Rooms (first set)

1. Lounge: the wide reef tank flush in travertine, the long bench with sage pillows, green wall, gold ceiling cove.
2. Dry sauna: pale aspen benches, curved ceiling light line, heater, glass door with the swan.
3. Wet sauna: travertine steam room, curved bench, soft animated steam.
4. Relaxing zone: cushioned loungers with bolsters and throws, travertine walls with LED lines, moss panels, the backlit swan logo.
5. Gym: dark room, smoked oak, the gold lockup on the wall, a few machines.

More rooms only after these five feel good.

## How it works

- Look around: drag (mouse or touch), arrow keys, or tilt on a phone (gyroscope, only after the visitor allows it).
- Move: tap a soft gold marker in a doorway to glide to the next room. A small room list lets you jump straight to any room.
- Each room has one short line of text (from the content rows, editable in the admin) and links back to that room on The spa.
- Look: matched to the site's room photos (travertine, oak, warm 2700K light, lifted deep browns, never pure black). The logo is the real SVG mark used as a texture, never redrawn.
- Motion: a slow settle on arrival, gentle steam and water caustics. No auto-spin.

## Rules

- three.js self-hosted (as for the Gold Card). Loaded only on `/tour/`.
- Performance: the first room loads fast (target under 3 s on a mid phone); other rooms load on demand. Textures compressed, low poly with baked lighting where possible.
- Fallback: reduced motion, no WebGL or Save-Data shows each room's photo with its text and the same room list. Nothing breaks without JavaScript.
- Accessible: room list and markers reachable by keyboard, each room announced by name, no motion that can't be avoided.
- Links: "Virtual tour" in the menu next to The spa, and "Take the tour" on each toured room on The spa (deep link `/tour/<room>/`).
- No new database models expected: room order and names reuse `Facility`; per-room tour text as content rows.

## Acceptance checks

- `/tour/` opens in the lounge; `/tour/<room>/` opens that room; unknown rooms are a 404.
- Look-around works with mouse, touch, keyboard and phone tilt; moving between rooms works by markers and by the list.
- Fallback mode shows photos and text with no WebGL loaded.
- Looks like the site's photos side by side (reviewed against the room pictures at 375 and 1440).
- First room under 3 s on a throttled mid phone profile; no console errors.

## Built: server side (2026-10-23)

- Routes (`pages`): `/tour/` (lounge), `/tour/<slug>/` for `gym`, `kitchenette`, `massage-room`, `dry-sauna`, `wet-sauna`, `relaxing-zone`; `/tour/lounge/` 301s to `/tour/`; anything else is a 404. The list and order live in `TOUR_ROOMS` in `pages/services.py` (slug, fallback name, photo alt, photo focus): adding a room is one line. A room whose Facility is hidden leaves the tour (404, dropped from the list); the lounge has no Facility so it is always in.
- Template `pages/tour.html` is the full fallback (photo, h1, line, spa link, room list). Hooks for the 3D script: `#tour` (`data-room`), `#tour-stage`, `#tour-photo`, `#tour-caption`, `#tour-title`, `#tour-line`, `#tour-spa-link`, `#tour-rooms` (links carry `data-room-link`), `#tour-live`, hidden `#tour-logos` holding `#tour-mark`, `#tour-logo` and `#tour-logo-stacked` (inline gold stacked SVG, plus `data-src`), `{{ tour_config|json_script:"tour-config" }}`. The `{% block scripts %}` loads `tour/boot.js` (a module), which checks the gate and then loads three.js and the engine.
- Config JSON: `{current, rooms: [{slug, name, line, photo, alt, focus, spa_url, spa_label, tour_url, order}], copy: {intro, hint, hint_tilt, tilt: {heading, body, cta_label}}}`.
- Photo: the `room_<slug>` section image if set, else the manifest render named after the slug (1600 px WebP), else the brand placeholder.
- Content: page `tour` rows as in the brief, and `spa` row `tour_link` (cta_label "Take the tour") created by seed and `backfill_site_data` (create-if-missing only).
- Menu: "Virtual tour" after The spa (header, menu, footer); "Take the tour" link on every toured room on The spa except the lounge (not on that page); `/tour/` is in the sitemap. The tour's CSS, fallback included, is in `common/css/tour.css`.
- Titles are "{Room}, virtual tour | Spa 99" (set server side for each room).

## Built: frontend (2026-10-23)

Files: `common/static/common/js/tour/{boot,engine,kit,textures}.js`, `tour/rooms/<slug>.js`, `common/css/tour.css`, vendored three rebuilt with the tour's classes (`tools/three/entry.js`), `pages_tags.tour_modules` (slug to hashed static URL of every room module that exists, as `#tour-modules`). A room is "in 3D" simply by having a file in `rooms/`; rooms without one open their photo page (normal navigation) from markers and the list.

### Room module contract

`rooms/<slug>.js` provides a named function `build(scene, ctx)` (async) and takes no module statements: everything arrives in `ctx`. Full text at the top of `tour/engine.js`; summary:

- `scene`: a fresh `THREE.Scene` (background espresso, `environmentIntensity` 0.5).
- `ctx`: `THREE`; `K` (kit bound to the scene: `std basic glow` materials, `box plane put rbox sector` baked geometry merged per material, `led glowPlane shadow vista`, `inst`, `light hemi` in the brief's units, `flush()` once at the end); `T` (textures: `travertine oak planks slats moss quilting rings reef caustics fish`, `shared('halo'|'shadow'|'puff'|'ray')`, `tex mix rgba tok rng`); `tier` ('high' | 'mobile' | 'low'); `S` (1024 or 512); `reefSize`; `env(wallToken)` (warm PMREM, disposed with the room); `logo(kind, {normal, halo})` (kind 'mark' or 'stacked'; canvases from the page's own SVG, `alpha` is for `alphaMap`); `idle()` (await between heavy generators).
- Return `{ view: {pos:[x,y,z], yaw, pitch}, markers: [{to, at:[x,y,z]}], exposure?, arrive?: {pos, yaw, pitch, ms, input}, ambient?, update?(dt, t), tier?(name), dispose?() }`. Degrees; yaw from north (-z), positive turns right. `ambient: true` means the room animates (30 fps at rest); otherwise it renders on demand.
- The engine disposes every geometry, material, texture and env target in the scene; current plus previous room stay in memory.
- Budget per room: 50 draw calls, 80k triangles, 4 point lights (3 mobile), 8 textures of your own (shared ones are free). `K.light(..., optional)` returns null on non-high tiers.
- Do not write the two keywords that start a module statement, followed by a space, inside a comment: Django's static hashing matches them across lines (it broke `collectstatic` once).
- Adding a room: drop `rooms/<slug>.js`; its slug must be in `TOUR_ROOMS`. Markers to it from other rooms then work with no engine change.

## Round 2: kitchenette and massage room (2026-10-23)
- `TOUR_ROOMS` order (superseded 2026-10-25, see the door chain below): lounge, gym, kitchenette, massage-room, dry-sauna, wet-sauna, relaxing-zone. Routes `/tour/kitchenette/` and `/tour/massage-room/` work like the others; The spa shows "Take the tour" for them from the Facility rows (kitchenette as a tile, massage room as the gym's companion, whose template now also shows the link).
- Content rows `room_kitchenette` and `room_massage_room` are in the seed and created if missing by `backfill_site_data` (never overwritten). Photos: none yet (a `room_<slug>` section image, or a manifest render named `kitchenette` / `massage-room`, fills the no-WebGL fallback).
- Modules: `rooms/kitchenette.js` (about 3 KB gzip) and `rooms/massage-room.js` (about 3.8 KB gzip, ambient fireplace). Doorway graph: gym to kitchenette to massage room, then dry sauna (left) and wet sauna (right); the lounge's relaxing zone is unchanged. Details in `docs/design/VIRTUAL-TOUR.md` 2.7.
- Room sizes after round 2 (gzip -9, KB): lounge 6.3, dry sauna 5.2, gym 4.9, wet sauna 4.2, massage room 3.8, relaxing zone 3.2, kitchenette 3.0 (budget 6.5 per room, VIRTUAL-TOUR 4.2).

## Door chain (2026-10-25, Moishe: the doors follow the real plan, `control/plan.py`)
`TOUR_ROOMS` order (room list, URLs, `order` field): lounge, gym, massage-room, kitchenette, relaxing-zone, wet-sauna, dry-sauna. Every 3D door matches one chain, and the room list and prefetch (markers) follow it. Rooms keep their look; only doorways changed.
- Lounge: on to the gym (corridor in the west wall beside reception). No door to the relaxing zone (east wall is plain now; the relaxing zone is far deeper).
- Gym: back to the lounge (south), on to the massage room (north passage).
- Massage room: back to the gym (east wall), on to the kitchenette (west wall); south wall plain.
- Kitchenette: back to the massage room (east wall), on to the relaxing zone (west wall, new); south wall plain.
- Relaxing zone: back to the kitchenette (south), wet sauna (north wall, left as you face deeper), dry sauna (north wall, right).
- Wet sauna and dry sauna: back to the relaxing zone only (the glass door).
The no-WebGL photo page has no door links of its own: it shows the room list in the same order, so it matches the 3D chain.
