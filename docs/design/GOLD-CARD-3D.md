# Spa 99: the Gold Card in 3D

Status: spec, 2026-10-22. Owner: design. Builds on `docs/design/IMMERSIVE.md` (sections 6, 8.7, 10, 14) and `docs/design/IMMERSIVE-R2.md` section 8 (R6). Decision log: PROJECT.md 2026-10-22 "Gold Card: a 3D floating gold card".

Moishe: "For the gold card itself create a 3D floating gold card. The card rotates or something on scroll and it has reflections, something luxury."

## 0. In one screen

- One object: a real metal membership card, soft warm gold, the swan polished into a brushed face, "SPA 99" and "GOLD" engraved small. No name, no number.
- It floats (one breath every 18s) and turns slowly as the section passes: -25° to +25°.
- The swan Moishe loved still draws itself, now **on the card face**: a fine light-gold line traces the swan while the face is still in shade, the line becomes polished metal, then a band of light sweeps across the swan and the edge catches the light as the card leaves.
- Three tiers, same pose and timing everywhere: **three.js** on capable desktops, a **CSS 3D card** (layered divs) on phones and everything else, a **rendered still** under reduced motion and without JS.
- Home Gold section (R6) and the Gold Card page hero (G1). No pin anywhere.
- Rule overrides (decision log): the card may rotate (BRAND 7 "no rotation" lifted for this object only). Text never rotates and never lives in WebGL. Animation gate: rare, marketing, purpose "explanation and delight": the card is the product.

---

## 1. The object

### 1.1 Geometry (model units = millimetres)

| Part | Spec |
|---|---|
| Outline | ISO ID-1: **85.6 × 54 mm**, corner radius **3.18 mm** |
| Thickness | **0.8 mm**, edge rounded: bevel 0.18 mm, 3 segments, so the edge reads as one soft bright line when lit |
| Body | `ExtrudeGeometry` from a rounded-rect `Shape` (`depth 0.44`, `bevelThickness 0.18`, `bevelSize 0.18`, `bevelSegments 3`, `curveSegments 10`), centred on z. Uses the **edge** material for both groups |
| Front face | `ShapeGeometry` of the same outline inset by the bevel, at `z = +0.401`, **face** material. UVs remapped to 0..1 across the card (shape coords / size) |
| Back face | Same, rotated π about Y, at `z = -0.401`, **back** material |
| Budget | about 2,500 triangles, **3 meshes, 3 draw calls** |

### 1.2 The face (front)

Layout on the 85.6 × 54 face (origin top left):

| Element | Position and size | How it is made |
|---|---|---|
| Swan | Centred horizontally; top 8 mm, height **32 mm** (about 60% of the card height). Paths from `common/_mark_draw.html` (viewBox `-2 -2 330 484`) | **Raised and polished**: height map plus a smoother patch in the roughness map (see 1.4) |
| "SPA 99" | Bottom left, 6 mm from the left and bottom edges, Signika 600, cap height 2.4 mm, tracking 0.06em | **Engraved** (debossed): height map, slightly rougher than the field |
| "GOLD" | Bottom right, 6 mm from the right and bottom edges, Figtree 500, uppercase, cap height 1.6 mm, tracking 0.24em | Engraved, same as "SPA 99" |

Nothing else on the face. No chip, no number, no name, no hologram.

### 1.3 The back

Darker bronze metal with a fine **swan pattern** (the S-swans of `swan-pattern.svg`, each 4 mm tall, 200:240 tile scaled to 10 × 12 mm), etched (height map only, no colour). One line centred low: "Beyond Luxury", Figtree 500, cap height 1.4 mm, tracking 0.2em, engraved. The back shows only on the Gold page hero (section 2.4) and at grazing angles.

### 1.4 Maps: generated at runtime from the real SVG paths

**Decision: no extruded swan geometry and no image download. Generate the swan, text and pattern as maps in a canvas at runtime from the same SVG paths the site already ships.** Reason: extruding 4 Bezier paths with `SVGLoader` adds a loader, about 6-10k triangles and aliasing on the polished edges; a normal map from the paths is sharper at this size, weighs 0 KB, and stays exact to the brand mark.

Steps (all in `requestIdleCallback`, one map per idle slot, never during scroll):

1. **Mask** (face 1024 × 646, back 512 × 323, single canvas reused): for each `.mark-line path` in the mount's own DOM swan, `ctx.setTransform(faceMatrix × pathMatrix)` then `ctx.fill(new Path2D(path.getAttribute('d')))` in white on black. Text with `ctx.fillText` after `document.fonts.load('600 40px Signika')` and `('500 20px Figtree')` resolve. Pattern: tile the swan path on the back mask.
2. **Height**: two-pass box blur in JS on the mask (radius 2 px, a JS blur, not `ctx.filter`, which Safari does not support everywhere). Swan positive (raised), text and pattern negative (engraved).
3. **Normal map** from the height with a Sobel pass, strength 2.0 for the swan and text, 1.2 for the pattern. `uniform float` scaled through `normalScale` so relief can grow from 0 to 1 in the motion (section 2).
4. **Roughness map** (green channel, three's convention): field 0.32, swan 0.16 (polished), engraved text 0.42. A hairline brush on the field: horizontal 1 px streaks of random brightness ±0.03, so highlights stretch like brushed metal.
5. **Draw map** (emissive, face size): starts black; redrawn while the line draws (section 2.2).

GPU memory: face normal + roughness + draw at 1024 × 646 RGBA (2.6 MB each), back normal + roughness 512 × 323, environment about 1.5 MB. **Total ≤ 12 MB.**

### 1.5 Materials (three.js `MeshPhysicalMaterial`)

Colours come from tokens via `getComputedStyle` (section 7), never hard-coded in JS.

| Material | Settings |
|---|---|
| **Face** | `color --color-gold-metal`, `metalness 1`, `roughness 1` (scaled by the map: field 0.32, swan 0.16), `anisotropy 0.55`, `anisotropyRotation 0` (brushed horizontally), `clearcoat 0.35`, `clearcoatRoughness 0.12`, `normalMap`, `roughnessMap`, `emissive --color-gold-light`, `emissiveMap` = draw map, `emissiveIntensity` 0 at rest, `envMapIntensity 1` |
| **Edge** | `color --color-gold-metal`, `metalness 1`, `roughness 0.2` (polished edge catches a clean line), `clearcoat 0` |
| **Back** | `color --color-gold-deep`, `metalness 1`, `roughness 0.45`, `normalMap`, `roughnessMap`, `clearcoat 0.2` |

If `anisotropy` is unsupported (it is in three r153+, so only a build error would remove it), drop it; nothing else changes.

**Never yellow-brassy.** The brand gold is hue 31°. Brass reads at 45° and up. Use `NeutralToneMapping` (Khronos PBR Neutral, keeps hue; ACES pushes gold towards yellow and orange), `toneMappingExposure 1.0`, `outputColorSpace SRGBColorSpace`. Acceptance check 7.

### 1.6 Light: a warm studio, built in code

> **Update 2026-10-23 (Moishe):** on Home the card looked too shiny at every point of the scroll, as if a bright light was always on it. The light is now set per page (`LOOK` in `gold-card-3d.js`, keyed by `data-gold-card`). **Home:** studio walls 0.55 (was 0.9), exposure 0.9, and the reflections and key light dim and brighten with the turn (cosine, bright every 36°, brightest near 2°, at most 45% dimmer: mid at rest, darker near -16° and 20°, never black), so the gold reads as metal with shadow and highlight. **Gold Card page hero:** unchanged (walls 0.9, exposure 1, no dimming). The CSS card tier is unchanged.

**Environment, 0 KB download.** A tiny procedural studio scene rendered once to a PMREM (`PMREMGenerator.fromScene(studio, 0.02)`, 256 px cube), then the studio scene and generator are disposed. Not `RoomEnvironment` (cool white, and an addon import); ours is warm and sized for a card.

| Studio part (inside a 10 × 6 × 10 box) | Colour (token) | Brightness | Position | Job |
|---|---|---|---|---|
| Room walls (`BackSide`) | `--color-espresso` × 0.5 | dark | | Dark field so the face reads deep in shade |
| Key softbox, 4 × 1.4 | `--color-led` | × 5 | above left, in front `(-2.5, 2.4, 3)` | Main soft reflection on the face |
| **Sheen strip**, 0.3 × 5 vertical | `--color-cream` | × 9 | in front `(0, 0, 4.5)` | The band of light that sweeps across the swan |
| Rim strip, 0.15 × 4 | `--color-led` | × 8 | right, slightly behind `(4, 0.5, -1)` | Makes the bevel edge glint as the card turns right |
| Floor bounce, 8 × 8 | `--color-caramel` | × 0.6 | below | Warm underside, keeps the gold from going grey |

The **sheen sweep** is the scene's `environmentRotation.y` (three r162+) animated with scroll, so the strip's reflection travels across the face without any extra light. One **DirectionalLight** (`--color-led`, intensity 1.4) adds a tight anisotropic highlight; it travels with the sweep and nudges with the pointer. No shadows, no post-processing, no bloom.

Background transparent (`alpha: true`, clear alpha 0): the espresso section and the DOM glow show through.

### 1.7 Camera

`PerspectiveCamera` fov **20°** (a long product lens: little distortion, calm), distance set so the card at rest is **72% of the canvas width**. The canvas is larger than the card (aspect 4:3) so rotation, tilt and float never clip a corner.

---

## 2. Motion

All values in one proxy object, `gc = { p, draw, relief, sheen, ry, rx }`, driven by GSAP in `scenes.js`. The three.js module and the CSS card both read the same proxy, so the two tiers are always in the same pose (cross-fade safe). Scroll-scrubbed tweens use `ease: 'none'` (the scroll is the easing); time-based ones use `soft`.

### 2.1 Idle float (always, both tiers)

| Motion | Value | Cycle |
|---|---|---|
| Bob | translateY ±1.6% of the card height (about ±6 px at 1440) | **18s**, sine |
| Drift roll | rotateZ ±0.6° | **23s**, sine (out of step with the bob, so it never visibly repeats) |
| Pool light under the card | opacity 0.7 to 1, in step with the bob (card up, pool fainter) | 18s |

Paused when the section is off screen and when the tab is hidden (BRAND 7A loop rule).

### 2.2 Home: the scroll, frame by frame

ScrollTrigger on the Gold section, `start: 'top 85%'`, `end: 'bottom 15%'`, `scrub 0.5` desktop, `0.3` phone. **No pin** (Home keeps its one hero pin; Moishe finds slow pins tiring). At 1440 × 800 the 85svh section travels about 1.5 screens through this range, so the whole story plays at normal scroll speed.

| p | Card (ry, rx) | Swan | Light | What you see |
|---|---|---|---|---|
| **0.00** | -25°, 8° | Nothing drawn, relief 0 | Face turned away from the key: dark bronze | The card rises into view, in shade, edge just visible |
| **0.05 to 0.30** | -25° → -14°, 8° → 5° | **The line draws**: body, curl, curl, head, stagger 0.025 each, same proportions as `drawSwan()` (8.7). Light gold line (`--color-gold-light`), 0.35 mm wide, emissive 1.0 | Still in shade, so the line glows clearly | The swan drawing itself, as Moishe loved, now on metal |
| **0.30 to 0.42** | -14° → -8° | Relief 0 → 1, swan roughness eases to polished | Key reflection starts to reach the left of the face | The drawing turns into raised, polished metal |
| **0.36 to 0.45** | | Emissive 1.0 → 0 (the line hands over to the metal, like fill and outline in 8.7) | | |
| **0.45 to 0.75** | -8° → +12°, 3° → -2° (square to camera at p 0.58) | Full relief | **The sheen**: `environmentRotation.y` -60° → +60°; the cream strip crosses the face left to right. It reaches the swan at **p 0.60**: the polished swan flashes brighter than the brushed field around it | The luxury moment: the card faces you as the light crosses the swan |
| **0.75 to 1.00** | +12° → +25°, -2° → -6° | | The rim strip catches the right-hand bevel (peak at p 0.9) | A single bright line runs along the edge as the card leaves |

Scrolling back reverses everything, the line included (same as today's scrubbed swan).

**Text on the left** (unchanged from R6): heading Line rise on enter (`top 75%`), body and link Fade up, pills Fade up 0.06s apart. The text does not move with the card.

### 2.3 Pointer tilt (desktop, fine pointer only)

`(hover: hover) and (pointer: fine)`. Pointer position inside the section maps to an added rotateX/rotateY of **max 6°** (and the DirectionalLight shifts with it by up to 10°, so the highlight slides). Damped follow: each frame `v += (target - v) * 0.06` (about 0.6s to settle, no overshoot). Returns to 0 over the same damping on `pointerleave`. Added on top of the scroll pose. CSS tier on desktop gets the same tilt.

### 2.4 Gold Card page hero (G1)

G1 becomes: text cols 1 to 6 (unchanged words), the card cols 7 to 12 instead of the free swan and the photo. Phone: card on top (82vw wide), then text. One screen. **No pin.**

**On load (time-based, `soft`):**

| t | Card | Swan | Light |
|---|---|---|---|
| 0 to 1.2s | Fades in (opacity 0 → 1) at -25°, 8°, rising 16px | | Shade |
| 0.3 to 2.7s | | Line draws (the 2.4s Draw of section 6, same proportions) | |
| 2.4 to 3.0s | | Relief 0 → 1, line fades | |
| 3.0 to 4.6s | -25° → -12°, 8° → 3° | | One sheen sweep across the swan (peak at 3.8s) |

Heading Line rise from 0.4s, lead and action Fade up from 0.9s (as G1 today).

**On scroll** (`start: 'top top'`, `end: 'bottom top'`, scrub 0.5 / 0.3): ry -12° → **+168°**, a slow half turn that shows the back (bronze, swan pattern, "Beyond Luxury") just as the hero leaves; the card also drifts up 8% slower than the page (depth). The turn crosses 90° (edge-on) at about 55% of the scroll, where the rim strip lights the whole edge. This is the only place the back shows (open question for Moishe, see the report).

### 2.5 CSS tier: the same story

The CSS card uses the real DOM swan (`_mark_draw.html`) on its face, so the line draw is the existing `drawSwan()` with DrawSVG, scrubbed on the same trigger. Light-gold line on the shaded face, then the polished fill fades in and the line fades out at the same p values as 2.2. Sheen is a moving gradient band (section 4).

---

## 3. Placement and size

### 3.1 Home Gold section (R6 → R6b)

Target (decision log): about **85% of a screen at 1440**, card on the visual half, text and pills on the other.

| | Desktop (≥ 64em) | Phone |
|---|---|---|
| Section | `min-height: 85svh`, content vertically centred, `padding-block: var(--space-6)` | Content height |
| Text | cols 1 to 5, as now (heading one step up, body, pills, quiet link) | Below the card |
| Card mount | cols 7 to 12, bleeding right to `--bleed` is not needed (the card floats, it is not a frame). Mount aspect 4:3, width `min(46rem, 50vw)` | Full container width, aspect 4:3 |
| Card at rest | **`min(40rem, 44vw)` wide** (640 px at 1440, so 404 px tall: about half the screen, matching "swan about half the screen tall") | `min(86vw, 24rem)` wide |

The free-standing swan (`.gold-swan`) is replaced by the card. The swan draw lives on the card.

Behind the card: the existing `.glow` (pointer light) and a new `.gc-pool`, a soft warm ellipse under the card (`radial-gradient` of `--color-glow`, 70% of the card width, 18% of its height, 12% below it): the gold card throwing a little warm light on the espresso. Static gradient, only its opacity moves.

### 3.2 Gold Card page hero (G1)

As 2.4. The `photo "gold-card"` placeholder in `gold.html` goes; the hero image is the card. The Gold page must load the immersive stack (gsap, ScrollTrigger, SplitText, CustomEase, DrawSVG, `scenes.js`) like Home; today it uses `data-reveal` only. G2 to G5 keep their current build for now.

---

## 4. Fallbacks

### 4.1 Who gets what

| Visitor | Tier |
|---|---|
| Passes `webglGate()` (IMMERSIVE 14.0: ≥ 64em, motion allowed, no Save-Data, ≥ 4 GB and ≥ 4 cores, WebGL2 without a performance caveat, `data-webgl` not `off`) | three.js, over the CSS card |
| Everyone else with JS and motion (all phones, tablets, weaker laptops, gate failed, three.js still loading or failed, context lost) | **CSS 3D card** |
| `prefers-reduced-motion`, no JS, GSAP failed (no `html.motion`) | **Still image** |

The CSS card is always in the markup under the canvas. three.js is a layer on top, never a replacement: if it never arrives, nothing is missing.

### 4.2 The CSS 3D card (most people see this; make it good)

```
.gold-card            perspective container (perspective: 1600px desktop, 1100px phone; perspective-origin 50% 45%)
  .gc-pool            warm light under the card
  .gc-float           idle bob and roll (CSS keyframes, 18s / 23s)
    .gc-card          transform-style: preserve-3d; rotateX/rotateY set by GSAP directly on this element
      .gc-edge × 4    the thickness: four copies of the outline at translateZ(-0.5px, -1px, -1.5px, -2px),
                      --color-gold-shade, same radius. Turned, they read as a solid metal edge
      .gc-back        rotateY(180deg) translateZ(2px), backface-visibility: hidden;
                      --color-gold-deep with swan-pattern.svg at 10% opacity, "Beyond Luxury"
      .gc-front       translateZ(0.5px), backface-visibility: hidden
        .gc-metal     base gradient (static): linear-gradient(118deg, --color-gold-shade 0%, --color-gold-metal 28%,
                      --color-gold-light 48%, --color-gold-metal 66%, --color-gold-shade 100%)
                      + brushed hairlines: repeating-linear-gradient(0deg, rgb(255 255 255 / 0.04) 0 1px, transparent 1px 3px)
        .gc-swan      _mark_draw.html: .mark-fill uses a linearGradient (gold-light → gold-metal → gold-light) = polished;
                      a static second copy offset 0.6px in espresso at 0.25 = the raised edge shadow;
                      .mark-line stroke --color-gold-light, 1.5px, non-scaling
        .gc-text      "SPA 99" and "GOLD" as aria-hidden spans, espresso at 0.45 (reads as engraving)
        .gc-shade     espresso layer, opacity driven from the pose: 0.55 at ry -25°, 0 near 0°, 0.25 at +25° (fake light falloff)
        .gc-sheen     a band 40% of the card wide: linear-gradient(105deg, transparent, rgb(245 242 216 / 0.38) 50%, transparent),
                      translateX -130% → 130% (transform only), clipped by .gc-front (overflow: hidden, radius)
```

- Card radius `calc(var(--gc-w) * 0.0371)` (3.18 / 85.6), aspect `85.6 / 54`.
- Motion: the same proxy and p table as 2.2. Phone uses ±18° instead of ±25° and rx 5° → -4° (a small screen reads smaller angles as larger).
- No `mix-blend-mode` (the page budget allows one blend layer and the hero may use it), no `filter`, no animated gradients: only `transform` on `.gc-card`, `.gc-float`, `.gc-sheen` and `opacity` on `.gc-shade`, `.gc-pool`, swan groups.
- `will-change: transform` on `.gc-card` and `.gc-sheen` only while the section is in view.
- Pointer tilt on desktop (fine pointer) as 2.3, when this tier is the one showing.
- No device-orientation tilt (needs a permission prompt; not worth it).

### 4.3 The still (reduced motion, no JS)

A render of the three.js card, exported once, at pose **p 0.62** (square to camera, the sheen just past the swan, full relief, no line), on the section espresso `#492E21` (so JPG works and it matches the section exactly).

How to produce it:
1. In local dev with `?gc-export=1` (honoured only when `settings.DEBUG`; the template sets `data-gc-export`), `gold-card-3d.js` renders that pose at 2560 × 1920 with `preserveDrawingBuffer`, background espresso, DPR 1, and downloads `gold-card-master.png`.
2. Run it through the existing image pipeline (IMMERSIVE-R2 5.3) to `content/static/content/img/gold-card-480.webp/.jpg`, `-800`, `-1280`, and add `gold-card` to the image manifest (the name `gold.html` already asks for).
3. Budget: 1280w WebP ≤ 70 KB, 800w ≤ 40 KB, 480w ≤ 20 KB.

Shown with `{% photo "gold-card" alt="" %}` inside the mount, only in the static layout (`html:not(.motion)`). With motion it is `display: none` and, being lazy, never downloaded. Static layout: card image on the right (desktop) or top (phone), text and pills, everything visible. Until the export exists, the static layout shows the CSS card unmoved at ry -8°, full relief, fill visible.

---

## 5. Performance

| Item | Budget / rule |
|---|---|
| three.js | The same vendored custom build as IMMERSIVE 14.3, entry extended with: `MeshPhysicalMaterial`, `PMREMGenerator`, `ExtrudeGeometry`, `ShapeGeometry`, `Shape`, `DirectionalLight`, `BackSide`, `NeutralToneMapping`. Re-measure after the build; cap **≤ 155 KB gzip** (was 145) |
| `gold-card-3d.js` | **≤ 9 KB gzip** |
| CSS card motion | In `scenes.js` (one shared `goldCard()` helper, about 1.5 KB); `scenes.js` stays ≤ 10 KB, Home motion JS ≤ 75 KB |
| Home on a capable desktop | 73 + 155 + 9 ≈ **237 KB** gzip, of which 164 KB load only near the Gold section. Phones: unchanged, three.js never requested |
| When it loads | Never in `<head>`, never preloaded. After `load` + idle, and only when the mount is within **two screens** (IntersectionObserver `rootMargin: 200% 0px`). Gold page: after `load` + idle (the card is in the hero). Build in separate idle slots: maps, then PMREM, then `renderer.compile()` and one frame |
| Hand-over | When ready, the canvas fades in over the CSS card (`--duration-gl-in`, 1.2s); same proxy, so the poses match and it may happen in view |
| Renderer | `antialias: true`, `alpha: true`, `powerPreference: 'high-performance'`, pixel ratio `min(devicePixelRatio, 1.5)`, dropped to 1 if three frames exceed 20 ms |
| Render loop | One `gsap.ticker` callback. Renders only while the mount is in view (IntersectionObserver). Full rate while the pose changes (scroll, pointer, load sequence); **30 fps** when only the idle float moves. Stops on `visibilitychange` hidden and off screen |
| Geometry | ≤ 3,000 triangles, 3 draw calls, 6 textures, GPU memory ≤ 12 MB |
| Frame | GPU ≤ 3 ms per frame at 1440 × 800; draw-map redraws (canvas + upload) only while `0 < draw < 1` and the value changed |
| Dispose | IMMERSIVE 14.3 contract: idempotent; ticker, observers, listeners, every geometry, material, texture and the PMREM target, `renderer.dispose()`, `forceContextLoss()`, canvas removed, CSS card visible. One WebGL context per page at most |

---

## 6. Accessibility

- The whole mount is decorative: `aria-hidden="true"` on `.gold-card`, the canvas and the still (`alt=""`). Nothing focusable inside. The heading, body and pills carry the meaning ("For people in property. Free, by application.").
- No flashing: the sheen is one band, scrubbed and smoothed (`scrub 0.5`), covering at most 30% of the face at a time, so even fast scroll up and down cannot produce more than one bright change a second over a large area. No pulsing, no glitter, no animated grain.
- Reduced motion: the still, no float, no tilt, no draw (filled swan). Switching it on while on the page reverts to the static layout and disposes the renderer (matchMedia cleanup).
- Text contrast unchanged (cream and gold on espresso, BRAND 3). The card is never behind text.

---

## 7. Files, hooks and tokens

### 7.1 Files

| File | What |
|---|---|
| `common/templates/common/_gold_card.html` | The mount: CSS card layers, the face swan (`include "common/_mark_draw.html"`), the back, the still. Params: `still_sizes`, `variant` (`home` or `hero`) |
| `common/static/common/js/gold-card-3d.js` | The three.js module. Contract of IMMERSIVE 14.3: `export function create(mount, { gsap, ScrollTrigger, tokens, card })` returns `{ ready, start, stop, dispose }`; `card` is the shared `gc` proxy |
| `common/static/common/js/scenes.js` | `goldCard(mount, opts)` helper (proxy, timelines, CSS card writes, idle float pause, pointer tilt); `SCENES.gold` updated (Home); `SCENES['gold-hero']` new (Gold page); the `[data-webgl]` loader of 14.3 with the near-viewport condition |
| `common/static/common/css/scenes.css` | `.gold-card` and `.gc-*` rules, Home R6b layout, G1 layout |
| `tools/three/entry.js` | Extra exports listed in section 5 |
| `pages/templates/pages/home.html`, `pages/templates/pages/gold.html` | Include `_gold_card.html` in place of `.gold-swan` and the hero photo; Gold page loads the immersive scripts |
| `content/static/content/img/gold-card-*.webp/.jpg` | The still (4.3) |

### 7.2 Markup hooks

```html
<!-- Home: inside <section class="scene gold-scene on-dark" data-scene="gold" data-glow ...> -->
<div class="gold-card gold-card--home" data-gold-card
     data-webgl="gold-card" data-webgl-src="{% static 'common/js/gold-card-3d.js' %}" aria-hidden="true"> ... </div>

<!-- Gold page: <section class="gold-hero on-dark" data-scene="gold-hero" data-glow ...> with .gold-card--hero -->
```

`data-gold-card` marks the mount for `goldCard()`; `data-webgl="gold-card"` joins the 14.3 loader. CSS classes: `.gold-card`, `.gold-card--home`, `.gold-card--hero`, `.gc-pool`, `.gc-float`, `.gc-card`, `.gc-edge`, `.gc-front`, `.gc-metal`, `.gc-swan`, `.gc-text`, `.gc-shade`, `.gc-sheen`, `.gc-back`, `.gc-still`, `.gc-canvas`.

### 7.3 Tokens (proposed, derived, decoration only: add to `tokens.css` and BRAND section 8)

| Token | Value | Hue | Use |
|---|---|---|---|
| `--color-gold-metal` | `#D9A46C` | 31° | Card base metal (three.js `color`, CSS gradient mid stops). A touch deeper than `--color-gold` so reflections lift it to brand gold |
| `--color-gold-light` | `#F3D2A2` | 36° | Polished highlight, the drawn line, the emissive colour |
| `--color-gold-shade` | `#A9763F` | 31° | CSS card edge layers and gradient ends |
| `--color-gold-deep` | `#5A3A26` | 23° | The back |
| `--gc-w` | `min(40rem, 44vw)` desktop, `min(86vw, 24rem)` phone | | Card width |
| `--duration-gc-float` | `18s` | | Idle bob cycle |
| `--duration-gc-roll` | `23s` | | Idle roll cycle |
| `--gc-tilt-max` | `6deg` | | Pointer tilt cap |

Reused: `--color-led` (key and rim light), `--color-cream` (sheen strip), `--color-caramel` (floor bounce), `--color-espresso` (studio walls, still background), `--color-glow` (pool), `--duration-gl-in`, `--ease-soft` / `soft`.

### 7.4 Doc amendments

- IMMERSIVE 14 intro: "Two moments only" becomes three: the hero water (parked), the sauna walks, the Gold Card. Rules unchanged (text never in WebGL, warm light only, no camera roll).
- BRAND 7 "no rotation": except the Gold Card object (decision log). BRAND 7A "The swan draws itself": on the Gold Card face on Home and G1.
- IMMERSIVE 6 G1 and G3: the card replaces the swan in the hero; G3 drops the N6 render.

---

### 7.5 Contrast pass (2026-10-23, Moishe: "the card has become much more flat")

**Finding.** No regression from the three.js rebuild: three is 0.186.1 before and after (0c6377e, f779f88 only added exports to `tools/three/entry.js`; PMREM, NeutralToneMapping, environment rotation and per-material `envMapIntensity` are the same code). The Gold Card page parameters were also unchanged since the approved commit 22df2e8; Home (020ccb4) only got its own darker `LOOK`. The flatness is in the approved design itself: since fb580c7 the studio was built to be "never black" (walls 0.9, big side, overhead and behind fills, strip only 3.5, face `envMapIntensity` 0.5, key light 0.6), so every angle met a mid-bright panel and the highlight had little to stand out from.
**Change.** All studio values are one `LOOK` block at the top of `gold-card-3d.js`, per page. Dark parts: walls 0.2 (Home 0.12), floor 0.12, side, overhead and behind fills x0.55 (Home x0.4): deep bronze, not black. Highlights: key softbox 5, sheen strip 14, rim 12 (were 1.5, 3.5, 5). Reflection strength face and edge 0.95, back 0.85; key light 0.4. Home is still darker and moodier (and keeps the turn dimming, now 35%) but with the same strong peaks. The CSS card tier and the still are unchanged. three.js is not downgraded or changed.
**Retune, same day (the first pass was too dark and muddy: a 0.2-wide strip is too thin to survive the face roughness, and nothing broad lit the face).** `LOOK` now has a broad soft warm panel behind the camera (`panel` 0.9, Home 0.7), walls 0.4 (Home 0.28), a wide hot strip (`stripW` 1.1, `strip` 7), key 4, rim 8, relief x1.3 (`bump`). Tune `panel` for how gold the face reads, `strip` and `stripW` for the travelling highlight, `wall`/`floor` for the dark angles.
**Third pass, same day (Moishe: "still very dull, needs to be more reflective and more dark").** Polished mirror gold in a dark studio, no broad fill: walls 0.07 (Home 0.05), floor 0.05, fills 0.2; three defined bright softboxes in front (left high `boxL` 9, right `boxR` 8, tall centre `strip` 11, width 0.9) that the face reflects in turn across the hero rotation; face roughness map x`rough` 0.5 (field about 0.1, swan 0.05), clearcoat 0.9 at roughness 0.05, anisotropy 0.3, relief x1.4. Home: same, a touch darker (boxes 8/7/10, exposure 0.95, mood 0.35). The broad `panel` is gone. Tune `boxL/boxR/strip` for how bright and where the reflections are, `rough` for how mirror-like, `wall/floor/fill` for the darks.

**Tune** (in `LOOK`): `wall`, `floor`, `fill` for the darkness of the shadows; `strip`, `key`, `rim` for how bright and crisp the highlights are; `face` for overall reflection strength; `exposure`; Home `mood`. If the face goes black at some angle raise `wall` to 0.3; if the highlight clips to white lower `strip` to 9.

## 8. Acceptance checks

Frontend, before review; reviewer repeats 1, 3, 4, 7, 9 with screenshots at 375 and 1440.

1. **Story.** At 1440 × 800, scrolling the Home Gold section at normal speed shows, in order: card in shade, the swan line drawing, the line becoming raised metal, one light band crossing the swan with the card square to the camera, the edge glinting as it leaves. Scrolling back reverses it. Same on the CSS tier (WebGL off with `data-webgl="off"`) and at 375 px.
2. **Pose match.** Toggling the canvas opacity at p 0.2, 0.6 and 0.9 shows the CSS card and the canvas within 2° of each other; the 1.2s cross-fade never shows a jump.
3. **Size.** Home Gold section 680 ± 40 px tall at 1440 × 800; card 640 px wide, about 404 px tall; text, pills and link visible without scrolling inside the section. At 375: card about 322 px wide, no horizontal scroll, nothing clipped at ±18°.
4. **Fallbacks never blank.** 375 px (no three.js or `gold-card-3d.js` request in the network panel), reduced motion (still image, or the unmoved CSS card until the export exists), no JS, `data-webgl="off"`, WebGL disabled, forced `WEBGL_lose_context` (CSS card back within one frame).
5. **Loading.** On Home, no three.js request until the Gold section is within two screens; build and compile finish before it is in view on an M1 Air; no long task over 50 ms during scroll.
6. **Frame rate.** 60 fps scrolling the section on an M1 Air and ≥ 50 fps on an Intel integrated-graphics laptop (three.js); 60 fps on a 2021 iPhone and a mid Android (CSS tier). GPU ≤ 3 ms per frame. Idle in view drops to 30 fps; off screen and hidden tab do zero frames.
7. **Colour.** In a 1440 screenshot at p 0.3, 0.6, 0.9: card face pixels with saturation over 0.25 have hue between **24° and 38°** (brand gold 31°; nothing brass-yellow), no pixel with blue above red, highlights reach `--color-gold-light`/cream, never pure white over more than the sheen band.
8. **Detail.** At 1440, the swan's outline is crisp (no stair-stepping on the relief), "SPA 99" and "GOLD" are legible as engraving, the bevel shows as one bright line at p 0.9, the back's pattern is visible on the Gold page turn. No name, no number on the card.
9. **Calm.** No bounce, no overshoot on pointer tilt (max 6°), float cycle 18s and roll 23s measured, text never rotates or moves with the card, no flashing on fast scroll up and down (one bright pass per direction).
10. **Clean revert.** Turning on reduced motion or resizing below 64em while on the page removes the canvas, `renderer.info.memory` geometries and textures read 0 after `dispose()`, and the static or CSS layout is correct. Never more than one WebGL context per page.
11. **Budget.** `three.module.min.js` ≤ 155 KB gzip, `gold-card-3d.js` ≤ 9 KB, `scenes.js` ≤ 10 KB, Home motion JS on phones ≤ 75 KB, still 1280w ≤ 70 KB. Lighthouse mobile ≥ 90 unchanged; LCP on Home is still the hero image, on the Gold page the heading.
12. **Accessibility.** The mount and everything in it are `aria-hidden`; axe shows no new issues; tab order skips the card.

### 7.6 Retune by eye (2026-10-23, coordinator, real WebGL render)

The flat look came from the bright strip sitting straight behind the camera, so the face mirrored it at every angle. The lights now stand off-axis (left high, right low, strip up-right), a broad soft `base` panel behind the viewer keeps the resting face warm gold, clearcoat is 0.4 and relief `bump` 2.0, so the swan stands out and the highlight sweeps as the card turns. Note for checks: the canvas fades in over `--duration-gl-in`; in a hidden/throttled browser the fade never finishes and screenshots show the CSS card underneath, so force `canvas { opacity: 1 }` to judge the 3D card.
