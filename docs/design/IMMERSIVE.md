# Spa 99: immersive marketing pages

For the frontend agent. This replaces the layout and motion parts of `docs/design/BRIEF.md` for the **marketing pages only** (Home, The spa, Memberships, Gold Card, Book, Visit us). Everything else in the brief stays: palette, type, tokens, components, copy tone, and the journey, forms, sign up, sign in, account, Gold application and Control screens. `docs/BRAND.md` wins on any conflict; its section 7 now holds both the restrained rules (forms) and the immersive rules (this page).

Hero video concepts and prompts: `docs/design/HERO-VIDEO.md`.

---

## 1. Concept

**One visit, told in scenes.** Each page is a short film you scroll through: the street goes dark, water moves, a door opens, you walk room to room, and the light settles. Every screen holds one idea and is complete on its own; the motion between screens is what makes it feel alive.

Three rules that make it Spa 99 and not a template:
1. **Slow and continuous, never bouncy.** Scroll drives motion (scrub), so the guest is always in control and nothing plays at him. Load animations are few and soft.
2. **Big quiet type over warm dark images.** Signika at hero size, short lines, cream on espresso. Gold only as light: the swan, a hairline, the primary button.
3. **Each screen fits the screen.** `100svh`, checked at 375×667 and 1440×800. Longer scrolls only where a scene is deliberately pinned and something changes the whole time.

Design read: premium hospitality marketing for men in London, Apple-style scroll storytelling with Aman-like restraint, Django templates + plain CSS + GSAP. Dials for marketing pages: variance 7, motion 7, density 2. Forms and journey stay at motion 3.

---

## 2. Global system

### 2.1 Scene anatomy

Every marketing section is a **scene**:

```html
<section class="scene scene--dark" data-scene="ritual" aria-labelledby="...">
  <div class="scene-stage"> ... </div>
</section>
```

- `.scene` is `min-height: 100svh` and never taller in the static layout. Content inside must fit 375×667 and 1440×800 (header included, it overlays).
- `data-scene` names the JS pattern (section 8). Pinned scenes get their extra length from ScrollTrigger (`pinSpacing`), never from CSS height.
- `--scene-pad-top: calc(var(--header-h) + var(--space-5))` so nothing hides under the fixed header. Bottom padding `--space-6` (phone `--space-5`), plus `env(safe-area-inset-bottom)`.
- Two layouts per scene, one markup:
  - **Static layout** (default CSS): no JS, reduced motion, or GSAP failed. Normal flow, everything visible, each scene one screen.
  - **Motion layout** (CSS under `html.motion`): stage layers stacked absolutely for pinning and cross-fades.

### 2.2 The `motion` switch

Extend the inline script in `common/templates/common/_head.html`:

```js
// adds .js always; adds .motion only when the visitor has not asked for reduced motion
var d=document.documentElement;d.classList.add("js");
var mq=matchMedia("(prefers-reduced-motion: reduce)");
if(!mq.matches&&d.dataset.page==="marketing")d.classList.add("motion");
setTimeout(function(){if(!d.dataset.scenes)d.classList.remove("motion")},4000);
```

- `<html data-page="marketing">` is set by the six marketing templates only (block in `base.html`). Journey, forms, account and Control never get `.motion` and never load GSAP.
- `scenes.js` sets `document.documentElement.dataset.scenes = "ready"` once GSAP is registered. If GSAP fails to load, the failsafe drops `.motion` after 4s and the static layout shows.
- `scenes.js` listens to `mq.addEventListener("change")`: on reduce, remove `.motion` and `ScrollTrigger.getAll().forEach(t => t.kill())` via `mm.revert()`, then `ScrollTrigger.refresh()`.

### 2.3 Header

| State | Look | When |
|---|---|---|
| Overlay | Transparent, cream lockup and links, no hairline | Pages whose first scene is dark (Home, The spa, Gold Card, Book) while the first scene is under it |
| Solid | `--color-header-solid` (espresso 88%) with `backdrop-filter: blur(16px) saturate(120%)`, 1px `--color-hairline-inverse` | After 64px of scroll, and always on pages that start cream (Memberships, Visit us) |
| Hidden | `transform: translateY(-100%)` | Scrolling down more than 8px past the first screen. Shows again on any upward scroll |

- Hide and show: `gsap.to(header, { yPercent: -100 / 0, duration: 0.45, ease: "soft" })`. Never hidden while the menu is open, while focus is inside the header, or within the first screen.
- Header becomes `position: fixed` on marketing pages (was sticky). `body[data-header="overlay"]` sets the transparent start. Height unchanged (`--header-h`).
- `prefers-reduced-motion`: always solid, never hides. `prefers-reduced-transparency`: solid espresso, no blur.
- Phone: same behaviour. The "Menu" sheet stays instant (BRAND 7, restrained).
- Journey, forms and account keep the reduced header exactly as built.

### 2.4 Page transitions

Cross-document View Transitions, no JS router:

```css
@view-transition { navigation: auto; }
.site-header { view-transition-name: site-header; }        /* the header does not flash */
::view-transition-old(root) { animation: 240ms var(--ease-soft) both vt-out; }
::view-transition-new(root) { animation: 480ms var(--ease-soft) 80ms both vt-in; }
@keyframes vt-out { to { opacity: 0; } }
@keyframes vt-in { from { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { @view-transition { navigation: none; } }
```

- Opacity only, no slide. Feels like the lights dimming between rooms. Browsers without support navigate normally.
- On arrival, each page's first scene plays its load reveal (section 2.6). No exit choreography beyond the fade.

### 2.5 Smooth scrolling (Lenis)

- Only when `(pointer: fine) and (hover: hover) and (prefers-reduced-motion: no-preference)` on marketing pages. Never on touch (native momentum is better and Lenis would fight it), never on journey or forms.
- `new Lenis({ lerp: 0.1, smoothWheel: true, syncTouch: false })`, wired to GSAP (section 8.2). `lenis.stop()` while the menu dialog or the modal is open; `lenis.start()` after.
- In-page anchor links (room index) use `lenis.scrollTo(target, { duration: 1.2 })` when Lenis is on, native `scrollIntoView` otherwise.
- Ship it behind a flag (`data-smooth="on"` on `<html>`) so it can be switched off without a deploy of new JS. Open question 3.

### 2.6 Shared motion vocabulary

Use only these. Values are the immersive scale in BRAND section 7.

| Name | What it does | Used for |
|---|---|---|
| **Line rise** | SplitText lines in a mask, `yPercent: 105 → 0`, 1.1s, `soft`, 0.08s between lines | Every scene heading, on enter (once) or on load |
| **Word light** | SplitText words, `opacity 0.15 → 1`, scrubbed across the pin | One statement per page at most |
| **Settle** | Image `scale 1.12 → 1.0`, scrubbed while it crosses the screen or its pin segment | Every full-bleed image |
| **Cross-fade** | Next layer `opacity 0 → 1` over 35% of its segment while it settles; previous layer holds, then drops to 0 underneath | Pinned image sequences |
| **Window** | A full-bleed media wrapper shrinks into a framed window (counter-scaled, section 8.6) | Home hero, The spa door |
| **Draw** | Swan mark outline draws (DrawSVG), then the gold fill fades in | Gold Card, Book, Home Gold scene |
| **Count** | Small whole numbers count up once, 1.2s, `soft` | Visits per month, days ahead (never prices) |
| **Fade up** | `opacity 0 → 1`, `y 16 → 0`, 0.9s, `soft` | Body lines and actions after a heading |
| **Glow** | A soft gold light follows the pointer | Dark scenes on desktop only |

What never happens: bounce, rotation, horizontal slides of text, blur transitions, parallax on text, animated `clip-path`, `width`/`height`/`top`/`left`, anything on a timer that loops faster than 15s, autoplay sound.

---

## 3. Home

Chapters: espresso (hero, ritual, journey entry) → cream (memberships) → espresso (Gold, opening, footer). Two colour changes plus footer.

Total scroll at desktop: about 9.5 screens, of which 4.4 are pinned scenes.

### H1. Arrival (hero) - pinned, `+=90%` desktop, `+=70%` phone

**On screen (first paint):** full-bleed hero media under the header (overlay header). Bottom left over the legibility veil: "Beyond Luxury." in `--text-hero` (Signika 400 cream, BRIEF 3), lead "A private spa for men in North London. Opening January 2027.", primary gold "Find your membership" with arrow, quiet "See the spa". A small quiet "Pause" control bottom right (section 3.1).

**Media:** `<video>` slot with poster (markup in 3.1). Until a video exists, the living still: render **08** (`hero`) with slow settle and a steam layer (3.2).

**On load:** headline Line rise (2 lines max: "Beyond / Luxury." on phone, one line on desktop), lead and actions Fade up 0.3s after. Media fades from espresso `opacity 0 → 1` over 1.4s (prevents a hard poster pop).

**On scroll (scrubbed, ease none):**
| Progress | What moves |
|---|---|
| 0 → 0.3 | Headline, lead and actions: `opacity 1 → 0`, `y 0 → -32`. Veil eases off (`opacity 1 → 0.4`) |
| 0 → 0.75 | **Window**: media shrinks into the target window. Desktop: cols 8-12, top `--scene-pad-top`, bottom `--space-6` (a portrait window flush with the right margin). Phone: full width minus `--page-margin`, top 46% of the stage |
| 0 → 0.75 | Media inner zoom `1.0 → 1.08` so the water feels closer as the frame closes in |
| 0.35 → 1 | Statement "Heat, cold, quiet, and time that is yours." Word light. Desktop: cols 1-6, vertically centred, `--text-2xl`. Phone: under the window, `--text-xl` |
| 0.8 → 1 | Statement paragraph ("Two saunas, a cold plunge...") Fade up under it (desktop only; phone drops the paragraph to keep one screen) |

**End state** equals the old editorial split: words left, water in a portrait window right. Pin releases and the ritual scene arrives under it.

**Glow** on desktop over the whole scene.

**Reduced motion / static:** poster image full-bleed (no autoplay), headline, lead, actions bottom left. Statement becomes its own static espresso scene after it: words left, render 08 in a portrait window right (desktop), words then a 4:5 image (phone, image cropped to fit the remaining height, min 40svh).

### H2. The ritual - pinned, `+=200%` desktop and phone

Three rooms in order: heat, cold, rest.

**On screen:** one full-bleed image at a time, the veil bottom left, one caption in `--text-2xl` cream bottom left: "Heat, slowly." / "Then cold." / "Then nothing at all." A 3-segment gold hairline bottom right (desktop) or bottom full width (phone): each segment fills with `scaleX` as its room plays. Segments are not numbered. Quiet "See the spa" appears with the third caption.

**Images:** `dry-sauna` (14), **N2** cold plunge (interim: `door-white`, see open question 2), `relaxing-zone` (04). Focal points: dry-sauna 50% 45% (swan on glass), relaxing-zone 68% 50% (swan wall), door-white 50% 40%.

**On scroll:** timeline with labels `heat`, `cold`, `rest`, one segment each (`duration: 1`):
- Entering image: Cross-fade in the first 0.35 of its segment, Settle (`1.12 → 1`) across the whole segment.
- Leaving caption: lines `yPercent 0 → -105` in its mask in the last 0.2 of its segment. Entering caption: Line rise in the first 0.3 (scrubbed, not timed).
- Progress hairline segment: `scaleX 0 → 1` across its segment, `transform-origin: left`.

**Phone vs desktop:** identical sequence. Phone images use portrait crops via `object-position`; captions sit above the safe area.

**Reduced motion / static:** three stacked one-screen scenes, each an image (full-bleed, 100svh) with its caption on the veil. No progress line.

### H3. Find your membership - one screen, not pinned

**On screen:** espresso with the swan pattern. Heading "Which membership suits you?" (`--text-2xl`), line "A few taps. Under two minutes.", the real first journey question ("When would you come?", four tiles 2×2) and primary "Find your membership". Same function as built (`home-entry.js`).

**Motion:** heading Line rise on enter (`start: "top 70%"`, once). Swan pattern layer (a pseudo-element 120% tall) moves `yPercent 0 → -8` scrubbed across the scene's whole pass, so the texture drifts like steam. The tiles follow BRAND 7 restrained rules: they arrive as one group with the heading, selection is instant, no stagger.

**Fit check (375×667):** header 64 + heading 2 lines 80 + line 26 + legend 28 + tiles 2×(64+16) + button 52 + gaps 4×24 ≈ 506. Fits with `--space-5` to spare.

**Reduced motion / static:** same layout, no drift, heading visible.

### H4. Memberships, briefly - one screen, not pinned

**On screen:** cream. Desktop 5/7: left (cols 1-5) heading "Three memberships. One single visit." `--text-2xl` and quiet "Compare memberships". Right (cols 7-12) three rows: name in `--text-xl`, character muted, the visit count as a large Signika number ("6", "8", "Unlimited") with "visits a month" small beside it, price "£299 a month, ex VAT" with "£358.80 inc VAT" under. Single visit as one small line. Phone: heading, three compact rows, single visit line, link.

**Motion:** heading Line rise. Rows Fade up with 0.1s stagger (desktop only, it is a progression of tiers). The visit numbers **Count** from 0 when the row enters (`start: "top 85%"`, once). "Unlimited" does not count. Prices never animate.

**Reduced motion / static:** everything visible, final numbers.

### H5. The Gold Card - pinned, `+=60%` desktop, `+=40%` phone

**On screen:** espresso. The swan mark large (desktop 46svh tall, cols 7-11; phone 34svh, centred top). Text desktop cols 1-5 bottom-aligned, phone below the swan: "The Gold Card." `--text-2xl` cream, "For people in property. Free, by application.", quiet "About the Gold Card".

**On scroll:** **Draw** scrubbed across 0 → 0.7 of the pin: outline draws path by path (body, then the two 9 curls, then the head), gold fill fades in over 0.55 → 0.8, outline fades out over 0.7 → 0.9. Heading Line rise at 0.5 (scrubbed). Body and link Fade up at 0.7.

When **N6** (Gold card render) exists, it replaces nothing: it appears as a 4:5 image in a second step on the Gold Card page, not here. Home keeps the drawn swan.

**Glow** on desktop, centred on the pointer, brighter over the swan (`--color-glow`).

**Reduced motion / static:** filled swan, text, link. One screen.

### H6. Opening - one screen, not pinned

**On screen:** espresso. "January 2027." in `--text-hero` cream (Signika 400), "99 Vale Road, London N4." `--text-lg`, primary gold "Register interest". The footer follows directly (same espresso chapter).

**Motion:** headline Line rise on enter, then line and action Fade up. Nothing else: the quiet end of the visit.

**Reduced motion / static:** the same, visible.

---

## 4. The spa: walking through the rooms

### S1. The door - pinned, `+=100%`

**On screen at start:** espresso. "The spa." in `--text-hero` cream, left aligned, vertically centred. In the centre of the stage a thin vertical line of warm light: the `door-gold` (09) image inside a Window wrapper scaled to `scaleX 0.04, scaleY 0.72`.

**On scroll:**
| Progress | What moves |
|---|---|
| 0 → 0.7 | Door opens: wrapper `scaleX 0.04 → 1`, `scaleY 0.72 → 1` (counter-scaled child, so the image is never stretched). Image Settle `1.15 → 1` |
| 0 → 0.4 | "The spa." `opacity 1 → 0`, `y 0 → -24` |
| 0.55 → 1 | Veil rises bottom left; lead "Eight spaces, one quiet visit." Line rise in `--text-2xl` |

Phone: same, the light line is 6% wide.

**Reduced motion / static:** door-gold full-bleed with veil, "The spa." and the lead bottom left. One screen.

### S2. The rooms - pinned, `+=70%` per room after the first (8 rooms: `+=490%`)

The core of the page. Eight facilities in visiting order (from `visible_facilities()`, hidden ones drop out and the pin shortens automatically: `(n - 1) * 70%`).

**Markup:** an ordered list of `<article>` items (image, `<h2>` name, line) stacked absolutely inside the stage. Screen readers get a normal list; nothing is `aria-hidden`.

**On screen:** one room at a time, full-bleed image, veil bottom left, room name in `--text-2xl` (Signika 500 cream), its line in `--text-lg` under it.
- **Desktop index:** a vertical list of all room names at the left edge, centred vertically, Figtree `--text-base`; all names cream (muted inverse would drop to about 3.9:1 on the veil over bright stone, so it is not used here); the current one is Figtree 600 with a 1px gold hairline 24px wide before it (grows with `scaleX`). Each name is a link to its point in the pin (8.4). The index sits inside the solid part of `.veil--left`.
- **Phone:** no index. Bottom: an 8-segment hairline (gold fill) above the name. Room name and line bottom left above it.

**On scroll per room (segment `duration: 1`, label = facility slug):**
- Image: Cross-fade in first 0.35, Settle `1.15 → 1.0` across the segment (the "walking forward" feel). Previous image keeps settling to `0.97` under it, then `opacity 0` once covered.
- Name and line: leaving lines `yPercent -105` in the last 0.2 of the previous segment; entering Line rise over 0.15 → 0.45.
- Index and hairline update from the timeline label (`onUpdate` reads `tl.currentLabel()`; set `aria-current="true"` on the current index link).
- **Desktop snap** to labels (8.4). Phone: no snap (fights native momentum).

**Images:** dry-sauna (14), N1 wet sauna, N2 cold plunge, N3 showers, relaxing-zone (04), N4 massage room, gym (12), N5 kitchenette. Until N1-N5 exist, see open question 2. A room with no image shows a type-only frame: espresso-raised stage, the swan pattern at 8%, name in `--text-hero`. It reads as a deliberate typographic beat, not a hole.

**Reduced motion / static:** each room is its own one-screen scene in flow: image (desktop 3:2 within 70svh, phone 4:5 within 58svh), name, line. No index (anchors still work from the URL).

### S3. How a visit works - pinned, `+=150%`

**On screen:** `lockers` (20) full-bleed, veil heavier (`--color-veil` over the lower 70%). Centre left, one word at a time in `--text-hero`: "Book." / "Arrive." / "Stay." with its line under in `--text-lg`. Bottom: the hours summary from `hours_summary()` in `--text-sm` muted inverse ("Open 5am to 3am"), and a quiet link "Opening hours" to Visit us.

**On scroll:** lockers image Settle `1.1 → 1` across the whole pin (one slow push, no cross-fade). Words swap with the mask: leaving `yPercent -105`, entering Line rise, labels `book`, `arrive`, `stay`. Hours line is always visible.

**Reduced motion / static:** image full-bleed, the three steps stacked (`--text-2xl` words, lines), hours. Fits: 3 × (44 + 26) + gaps ≈ 290px.

### S4. Next - one screen

Cream. "Find the right way to visit." `--text-2xl`, primary "Find your membership", secondary "See memberships". Line rise, Fade up. Static: visible.

---

## 5. Memberships

### M1-M5. The stack - sticky cards, no extra pin length

Five full-screen cards that stack over each other: **Intro**, **Tier 1**, **Tier 2** (featured), **Tier 3**, **Single visit**. Stage background espresso.

**Intro card (cream):** "Memberships." `--text-hero`, lead "Choose when you come and how often.", then the three tier names as a typographic index (Signika `--text-xl`: "Tier 1, Daytime", "Tier 2, Any time", "Tier 3, Unlimited"), each a link to its card, plus quiet "Not sure? Find yours" (to the journey).

**Tier cards** (Tier 1 and 3 cream, Tier 2 espresso with "Recommended" label and gold primary, Single visit cream-raised):
- Desktop 12 col: name `--text-hero` cols 1-6 and character `--text-lg` muted under it; right cols 8-12: price (BRIEF price token), "a month, ex VAT", "£478.80 inc VAT", then three facts as large Signika numbers with a small label: visits ("8 visits a month" / "Unlimited"), booking window ("3 days ahead"), bookings at once ("2 at a time"), then the action.
- Phone: name `--text-2xl`, character, price, the three facts as one row of three numbers, action full width. Fit check 375×667: 64 + 44 + 26 + 60 + 40 + 72 + 52 + gaps 120 ≈ 478.

**Motion:** each card is `position: sticky; top: 0; height: 100svh` with `--radius-md` corners. As the next card arrives (its top from `bottom` to `top`), the current card scrubs to `scale 0.94` and its inner dim layer to `opacity 0.5` (5.A in `design-taste-frontend`, adapted: start `top top`). The arriving card's heading Line rises when it reaches 40% from the top; its numbers **Count** (visits and days only). Prices never animate.

**Reduced motion / static:** cards in normal flow, each one screen, no scaling. Same order.

### M6. Not sure - one screen

Espresso. "Not sure? Find yours." `--text-2xl`, primary "Find your membership". Swan pattern. Line rise. Static: visible.

### M7. The details - one screen when closed

Cream. `<details>` "Compare everything" (closed), the Gold line with link, the VAT note. Opening the comparison may make the scene taller than the screen: allowed, the guest asked for it. No animation inside the table (BRIEF 9 stands).

---

## 6. Gold Card

Espresso from top to bottom. A private room.

### G1. Hero - one screen, load animation only

**On screen:** desktop: text cols 1-6 bottom left ("The Gold Card." `--text-hero`, lead, primary "Apply"); the swan large on the right (cols 8-12, 60svh). Phone: swan top centre (28svh), then text. The swan is the hero image here; the N6 card render, when it exists, goes in G3, never behind the swan.

**On load:** **Draw** (timed, 2.4s, `soft`): outline paths with 0.25s offset, fill fades in from 1.6s, outline out from 2.0s. Heading Line rise from 0.4s, lead and action Fade up from 0.9s. **Glow** follows the pointer (desktop).

**Reduced motion / static:** filled swan, text. One screen.

### G2. Who it is for - pinned, `+=100%`

**On screen:** "Who it is for." `--text-2xl` top left; the six roles in Signika `--text-xl`, two columns desktop, one column phone; the muted line "Not in property? You're still welcome to apply." at the bottom.

**On scroll:** roles light up one by one: each role `opacity 0.2 → 1` in sequence across the pin (scrubbed, `stagger: 0.5` inside a timeline of length 6). The heading is visible from the start (Line rise on enter). Muted line Fade up at the end.

**Fit (375×667):** 64 + 44 + 6 × 58 (some roles wrap to 2 lines) + 48 ≈ 504.

**Reduced motion / static:** all roles at full opacity.

### G3. What it holds - one screen

**On screen:** two groups ("Your visits", "Beyond the spa") side by side desktop, stacked phone; a 1px gold rule above each group. With N6 available: desktop 5/7, N6 (4:5) left with Settle, groups right; phone: groups only (N6 dropped to keep one screen).

**Motion:** gold rules draw `scaleX 0 → 1` from the left (1.2s, `soft`) on enter, group lines Fade up as a group after. Settle on N6 scrubbed.

### G4. How it works - one screen

**On screen:** three steps. Desktop: three columns joined by one gold hairline running behind the step words. Phone: one column with the hairline running vertically on the left.

**Motion:** the hairline draws (`scaleX` desktop / `scaleY` phone) scrubbed while the scene crosses from `top 70%` to `center center`; each step word Line rises as the line reaches it (scrubbed positions 0, 0.5, 1). Stagger allowed: a progression.

### G5. Apply - one screen

Gold panel (BRIEF 4.9) centred, swan 48px drawn small on enter (1.2s), heading, line, primary "Apply for the Gold Card". The footer follows.

---

## 7. Book and Visit us

### B1. Booking opens soon - one screen

Espresso, swan pattern drifting (the H3 pattern drift, here on a 60s CSS loop `translateY 0 → -4%`, alternate, paused under reduced motion). Swan 64px **Draw** on load (1.6s), "Booking opens soon." `--text-2xl` Line rise, line, "January 2027" Signika `--text-xl` gold, primary "Register interest" (or "Your account"), quiet "See the spa".

### B2. How booking will work - one screen

Cream. Heading "How booking will work." Three columns desktop / three rows phone: tier name, then the booking window as a big Signika number with "days ahead" ("1", "3", "7" from plan data). Numbers **Count** on enter; columns Fade up with 0.1s stagger (progression). Static: final numbers.

### V1. Visit us - one screen

Cream. "Visit us." `--text-2xl`; address as a statement in `--text-hero` on two lines ("99 Vale Road" / "London N4 1PR"); email as a large quiet link; hours as the two-column list; getting-here slot if filled. Desktop 7/5: address left, hours and email right. Phone: stacked; hours list in `--text-sm` to fit.

**Motion:** address Line rise (two lines, 0.08s apart), the rest Fade up as one group.

### V2. Arrival - pinned, `+=80%`

**On screen:** `door-white` (10) full-bleed, veil bottom left, one line from content (`visit.arrival`, open question 6) in `--text-2xl`, or nothing if empty.

**On scroll:** a slow walk up to the door: image `scale 1.0 → 1.18` across the pin (the only scene that pushes in rather than settles), veil `0.6 → 1`, line Line rise at 0.4. Footer follows.

**Reduced motion / static:** image full-bleed, line on the veil.

---

## 8. Implementation: exact GSAP patterns

### 8.1 Files and loading

```
common/static/common/vendor/gsap/   gsap.min.js, ScrollTrigger.min.js, SplitText.min.js,
                                    DrawSVGPlugin.min.js, CustomEase.min.js   (from npm gsap@3.13.x dist/, with its LICENSE)
common/static/common/vendor/lenis/  lenis.min.js (+ LICENSE)
common/static/common/js/scenes.js   one ES module: setup + a registry of scene patterns keyed by data-scene
common/static/common/css/scenes.css motion layouts (all rules under html.motion), veil, glow, video
```

- GSAP is free for commercial use including all plugins since 3.13 (GreenSock "no charge" licence). Self-host, no CDN.
- Marketing templates add `{% block scripts %}` with the vendor files as classic `<script defer>` (UMD, they attach `window.gsap`) followed by `<script type="module" src="scenes.js">` (modules run after deferred scripts, in order). Page modules that already exist (`home-entry.js`, `compare.js`) stay.
- `reveal.js` keeps working on marketing pages for anything not inside a scene; do not put `data-reveal` inside a `data-scene` element (one system per element).

### 8.2 Setup (top of `scenes.js`)

```js
const { gsap, ScrollTrigger, SplitText, DrawSVGPlugin, CustomEase } = window;
gsap.registerPlugin(ScrollTrigger, SplitText, DrawSVGPlugin, CustomEase);
CustomEase.create('soft', '0.22,1,0.36,1');          // = --ease-soft
gsap.defaults({ ease: 'soft', duration: 1.1 });
ScrollTrigger.config({ ignoreMobileResize: true });   // address bar show/hide does not re-layout pins
const root = document.documentElement;

const mm = gsap.matchMedia();
mm.add({
  motion: '(prefers-reduced-motion: no-preference)',
  desktop: '(min-width: 64em)',
  fine: '(pointer: fine) and (hover: hover)',
}, (ctx) => {
  const { motion, desktop, fine } = ctx.conditions;
  if (!motion) return;                                // static layout, nothing created
  if (fine && root.dataset.smooth === 'on') startLenis();
  document.querySelectorAll('[data-scene]').forEach((el) => SCENES[el.dataset.scene]?.(el, { desktop, fine }));
  initHeader();
  if (fine) initGlow();
  return () => stopLenis();                           // gsap reverts tweens, triggers and splits made inside
});

document.fonts.ready.then(() => ScrollTrigger.refresh());  // line breaks and pin positions after Signika loads
root.dataset.scenes = 'ready';

function startLenis() {
  lenis = new Lenis({ lerp: 0.1, smoothWheel: true, syncTouch: false });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add(tick); gsap.ticker.lagSmoothing(0);
}
const tick = (t) => lenis.raf(t * 1000);
```

- Every scene function creates its tweens and triggers inside the `mm.add` callback, so a switch to reduced motion or a breakpoint change reverts them cleanly.
- Images inside pinned scenes are `loading="eager"` only for the first scene; others lazy, and call `ScrollTrigger.refresh()` once on `window.load`.

### 8.3 Line rise and word light (SplitText)

```js
function lineRise(el, opts = {}) {
  return SplitText.create(el, {
    type: 'lines', mask: 'lines', autoSplit: true,     // re-splits on resize and font load
    onSplit: (self) => gsap.from(self.lines, {
      yPercent: 105, duration: 1.1, stagger: 0.08, ease: 'soft',
      scrollTrigger: opts.trigger === false ? undefined
        : { trigger: el, start: 'top 80%', once: true },
      delay: opts.delay || 0,
    }),
  });
}

function wordLight(el, timeline, at, span) {          // inside a pinned timeline
  const split = SplitText.create(el, { type: 'words' });
  timeline.fromTo(split.words, { opacity: 0.15 }, { opacity: 1, ease: 'none', stagger: span / split.words.length, duration: span / 4 }, at);
}
```

- SplitText 3.13 adds `aria-label` to the split element and `aria-hidden` to the pieces, so headings still read as one string.
- For scrubbed swaps inside a pin (ritual captions, room names, steps), split once and add the line tweens to the scene timeline with `ease: 'none'` at the positions in the storyboard, instead of a separate ScrollTrigger.

### 8.4 Pinned scene timeline (ritual, rooms, steps, door, who)

```js
function pinnedScene(el, { segments, perSegment = 1, snap = false, scrub = 0.8 }) {
  const tl = gsap.timeline({
    defaults: { ease: 'none' },
    scrollTrigger: {
      trigger: el, start: 'top top',
      end: () => '+=' + (segments - 1) * perSegment * window.innerHeight,
      pin: true, pinSpacing: true,                     // pins the section; .scene-stage fills it
      scrub, anticipatePin: 1, invalidateOnRefresh: true,
      snap: snap ? { snapTo: 'labelsDirectional', duration: { min: 0.3, max: 0.8 }, delay: 0.08, ease: 'power1.inOut' } : false,
    },
  });
  return tl;
}
```

Per scene settings:

| Scene | segments | perSegment (viewport heights) | scrub desktop / phone | snap |
|---|---|---|---|---|
| Home H1 arrival | 2 | 0.9 desktop, 0.7 phone | 0.8 / 0.5 | no |
| Home H2 ritual | 3 | 1.0 | 0.8 / 0.5 | desktop only |
| Home H5 Gold | 2 | 0.6 desktop, 0.4 phone | 0.8 / 0.5 | no |
| Spa S1 door | 2 | 1.0 | 0.8 / 0.5 | no |
| Spa S2 rooms | number of rooms | 0.7 | 0.8 / 0.5 | desktop only |
| Spa S3 steps | 3 | 0.75 | 0.8 / 0.5 | desktop only |
| Gold G2 who | 2 | 1.0 | 0.8 / 0.5 | no |
| Visit V2 arrival | 2 | 0.8 | 0.8 / 0.5 | no |

Building a sequence (ritual and rooms):

```js
const items = gsap.utils.toArray('.scene-item', el);
gsap.set(items.slice(1), { autoAlpha: 0 });
items.forEach((item, i) => {
  const img = item.querySelector('.scene-media');
  const label = item.dataset.label;                  // 'heat', 'dry-sauna', ...
  tl.addLabel(label, i);                             // segment i starts at time i
  if (i > 0) tl.to(item, { autoAlpha: 1, duration: 0.35 }, i - 0.35);  // cross-fade ends exactly on the label
  tl.fromTo(img, { scale: 1.15 }, { scale: 1, duration: 1 }, Math.max(0, i - 0.35));
  // caption out/in at the positions in sections 3 and 4
});
tl.to({}, { duration: 0.35 });                        // a short hold on the last room before the pin releases
```

- `autoAlpha` sets `visibility: hidden` at 0 so covered images stop painting.
- Room index links: `link.addEventListener('click', e => { e.preventDefault(); const st = tl.scrollTrigger; const y = st.start + (st.end - st.start) * (tl.labels[slug] / tl.duration()); lenis ? lenis.scrollTo(y) : scrollTo({ top: y, behavior: 'smooth' }); })`.

### 8.5 Sticky card stack (Memberships)

```js
const cards = gsap.utils.toArray('.plan-card', el);
cards.forEach((card, i) => {
  const next = cards[i + 1];
  if (!next) return;
  gsap.timeline({ scrollTrigger: { trigger: next, start: 'top bottom', end: 'top top', scrub: true } })
    .to(card, { scale: 0.94, ease: 'none' }, 0)
    .to(card.querySelector('.plan-card-dim'), { opacity: 0.5, ease: 'none' }, 0);
});
```

- Cards are CSS `position: sticky; top: 0; height: 100svh` under `html.motion` only (no GSAP pin, so phones keep native scroll). `transform-origin: 50% 0`.
- `.plan-card-dim` is an espresso layer inside the card (`opacity: 0`), so dimming is opacity, not filter.

### 8.6 Window and door (counter-scaled mask, transforms only)

Animated `clip-path` repaints every frame; this does the same with transforms. Markup: `.window` (overflow hidden, the frame) > `.window-media` (the image or video).

```js
function windowTo(el, target, tl, at, span) {
  const frame = el.querySelector('.window'), media = el.querySelector('.window-media');
  const p = { v: 0 };
  const setF = gsap.quickSetter(frame, 'css'), setM = gsap.quickSetter(media, 'css');
  const measure = () => {                              // target is an invisible element laid out by CSS
    const a = frame.getBoundingClientRect(), b = target.getBoundingClientRect();
    return { sx: b.width / a.width, sy: b.height / a.height, x: b.left - a.left, y: b.top - a.top };
  };
  let m = measure();
  ScrollTrigger.addEventListener('refreshInit', () => { gsap.set([frame, media], { clearProps: 'transform' }); m = measure(); });
  tl.to(p, { v: 1, duration: span, ease: 'none', onUpdate: () => {
    const sx = 1 + (m.sx - 1) * p.v, sy = 1 + (m.sy - 1) * p.v;
    setF({ x: m.x * p.v, y: m.y * p.v, scaleX: sx, scaleY: sy, transformOrigin: '0 0' });
    setM({ scaleX: 1 / sx, scaleY: 1 / sy, transformOrigin: '0 0' });   // child cancels the frame: a pure crop, never stretched
  } }, at);
}
```

- Home hero: target is `.hero-window-target`, placed by CSS in grid cols 8-12 (desktop) or the top 46% (phone).
- Spa door is the reverse (from a thin slit to full-bleed): start with `p.v = 1` at the slit and tween to 0, with the slit as the target. Centre origin: use `transformOrigin: '50% 50%'` on both and skip `x/y`.
- The media's own zoom (Settle) goes on an inner `<img>`/`<video>`, never on `.window-media`, so the two transforms do not fight.

### 8.7 Swan draw (DrawSVG)

The mark (`common/_mark.html`) is four filled paths. For drawing, render a variant `common/_mark_draw.html`: the same paths twice, a `.mark-fill` group (`fill: var(--color-gold)`, `opacity: 0` under `.motion`) and a `.mark-line` group (`fill: none; stroke: var(--color-gold); stroke-width: 1.25; vector-effect: non-scaling-stroke`). `aria-hidden="true"` as now.

```js
function drawSwan(svg, tl, at = 0, total = 2.4) {
  const lines = svg.querySelectorAll('.mark-line path');      // order: body, curl, curl, head
  tl.fromTo(lines, { drawSVG: '0%' }, { drawSVG: '100%', duration: total * 0.6, stagger: total * 0.1, ease: 'soft' }, at)
    .to(svg.querySelector('.mark-fill'), { opacity: 1, duration: total * 0.35 }, at + total * 0.65)
    .to(svg.querySelector('.mark-line'), { opacity: 0, duration: total * 0.25 }, at + total * 0.8);
}
```

- On load (Gold hero, Book, Gold apply panel): a plain timeline. Scrubbed (Home H5): the pinned timeline with `ease: 'none'` on the draw.
- Static: `.mark-fill` visible, `.mark-line` hidden.

### 8.8 Count

```js
function count(el) {                                  // el contains the final number as text
  const end = parseInt(el.textContent, 10);
  if (!Number.isFinite(end) || end > 99) return;      // whole numbers only; never prices
  el.setAttribute('aria-label', el.textContent);      // screen readers get the real value once
  const n = { v: 0 };
  ScrollTrigger.create({ trigger: el, start: 'top 85%', once: true, onEnter: () =>
    gsap.to(n, { v: end, duration: 1.2, ease: 'soft', snap: { v: 1 }, onUpdate: () => { el.textContent = n.v; } }) });
  el.textContent = '0';                               // only set after the trigger exists and el is below the fold
}
```

- `font-variant-numeric: tabular-nums` and `min-width: 2ch` on the number so nothing shifts.
- If the element is already in view on load (`ScrollTrigger.isInViewport(el)`), skip the count and leave the final number.

### 8.9 Glow (pointer light, desktop only)

```js
function initGlow() {
  document.querySelectorAll('[data-glow]').forEach((scene) => {
    const glow = scene.querySelector('.glow');
    const x = gsap.quickTo(glow, 'x', { duration: 0.8, ease: 'power3' });
    const y = gsap.quickTo(glow, 'y', { duration: 0.8, ease: 'power3' });
    scene.addEventListener('pointermove', (e) => { const r = scene.getBoundingClientRect(); x(e.clientX - r.left); y(e.clientY - r.top); });
    scene.addEventListener('pointerenter', () => gsap.to(glow, { opacity: 1, duration: 0.6 }));
    scene.addEventListener('pointerleave', () => gsap.to(glow, { opacity: 0, duration: 0.6 }));
  });
}
```

`.glow`: `position: absolute; left: 0; top: 0; width: 44vmax; aspect-ratio: 1; margin: -22vmax 0 0 -22vmax; border-radius: 50%; background: radial-gradient(closest-side, var(--color-glow), transparent); pointer-events: none; opacity: 0;`. Sits between media and text. Scenes with `data-glow`: Home H1, H5; Gold G1.

### 8.10 Header

```js
function initHeader() {
  const header = document.querySelector('.site-header');
  ScrollTrigger.create({ start: 64, end: 'max', toggleClass: { targets: header, className: 'is-solid' } });
  ScrollTrigger.create({ start: () => innerHeight, end: 'max', onUpdate: (self) => {
    if (header.contains(document.activeElement) || document.querySelector('[data-menu][open]')) return;
    gsap.to(header, { yPercent: self.direction === 1 ? -100 : 0, duration: 0.45, ease: 'soft', overwrite: true });
  } });
}
```

### 8.11 Hero media (video slot and living still)

Markup (Home H1; the same slot pattern can be reused on other dark heroes later):

```html
<div class="window" data-hero-media>
  <div class="window-media">
    <video class="hero-video" muted playsinline loop preload="none" poster="{{ hero_poster }}" aria-hidden="true"
           data-sources='[{"src":"{{ hero_av1 }}","type":"video/webm; codecs=av01.0.05M.08","media":"(min-width: 48em)"},
                          {"src":"{{ hero_mp4 }}","type":"video/mp4","media":"(min-width: 48em)"},
                          {"src":"{{ hero_av1_portrait }}","type":"video/webm; codecs=av01.0.05M.08","media":"(max-width: 47.99em)"},
                          {"src":"{{ hero_mp4_portrait }}","type":"video/mp4","media":"(max-width: 47.99em)"}]'></video>
    {% photo "hero" alt="" sizes="100vw" eager=True css_class="hero-still" %}   {# the living still; hidden once the video plays #}
    <div class="hero-steam" aria-hidden="true"></div>
  </div>
</div>
<button class="hero-pause btn-quiet" type="button" aria-pressed="false" data-hero-pause>Pause</button>
```

- The poster/still is the LCP element: preload it (as now) with `fetchpriority="high"`. The video gets its `<source>` elements from `data-sources` only after `load` and `requestIdleCallback`, so it never competes with first paint. Skip the video when `navigator.connection?.saveData`, under reduced motion, or when no video file exists (the template tag renders no `data-sources`).
- When the video fires `playing`, fade the still out (`opacity 0`, 1.2s). Pick the first source whose `media` matches and whose type `canPlayType` accepts.
- **Pause control** (WCAG 2.2.2, motion longer than 5s): quiet text button bottom right, "Pause"/"Play", 44px target. Pauses the video or the living still loop and the steam. Remember the choice in `sessionStorage`.
- **Living still** (until a video exists): `.hero-still img` loops `scale 1.0 → 1.06` over 24s, `yoyo`, `repeat: -1`, `sine.inOut` (one cycle per 48s, far below the 0.2Hz discomfort zone), plus `.hero-steam`: a steam-on-black WebP (asset to make, see HERO-VIDEO.md) at `mix-blend-mode: screen`, `opacity 0.28` desktop / `0.18` phone, drifting `xPercent -6 → 6` over 30s yoyo. The one blend layer on the site.
- Video and steam pause when the hero is out of view (`ScrollTrigger` `onToggle`), and on `visibilitychange`.

### 8.12 Legibility veil

Text over photography and video always sits on the veil:

```css
.veil { position: absolute; inset: 0; pointer-events: none;
  background: linear-gradient(to top, var(--color-veil) 0%, var(--color-veil) 22%, rgb(73 46 33 / 0) 62%); }
.veil--left { background: linear-gradient(to right, var(--color-veil) 0%, var(--color-veil) 18%, rgb(73 46 33 / 0) 58%); } /* desktop index + captions */
```

Text is placed inside the solid part of the veil (bottom 22% / left 18%). Worst case (brightest travertine under it) cream on the veil measures 6.5:1, so body text passes AA. Do not place text above the 30% line on any image.

---

## 9. Phone vs desktop

| | Phone (< 64em) | Desktop (≥ 64em) |
|---|---|---|
| Scenes | Same scenes, same order, same pins | Same |
| Pin lengths | Shorter where listed (H1, H5) | As listed |
| Scrub smoothing | 0.5 (closer to the finger) | 0.8 |
| Snap | Never | Ritual, rooms, steps |
| Lenis | Never | On if flag is on |
| Glow | Never | Dark scenes |
| Hero video | Portrait 720×1280 file | Landscape 1920×1080 file |
| Room index | 8-segment hairline + current name | Vertical name list, clickable |
| Statement paragraph in H1 | Dropped | Shown |
| Text scale | `--text-hero` 48px, `--text-2xl` 36px | 128px, 64px |
| Type over images | Bottom veil only | Bottom or left veil |
| Header | Overlay, hides on scroll down | Same |

Tablet (48-64em) follows phone layouts with desktop video.

---

## 10. Performance budget

| Item | Budget |
|---|---|
| JS on marketing pages (gzip) | gsap 28 KB, ScrollTrigger 18 KB, SplitText 7 KB, DrawSVG 3 KB, CustomEase 3 KB, Lenis 5 KB, scenes.js ≤ 10 KB. **Total ≤ 75 KB.** Journey, forms, account: 0 KB of this |
| Hero video, landscape | 1920×1080, 24 fps, 8 s, no audio track. AV1 WebM ≤ 1.6 MB; H.264 MP4 (High, CRF ~23, `+faststart`) ≤ 2.5 MB |
| Hero video, portrait | 720×1280, same length. AV1 ≤ 0.8 MB; H.264 ≤ 1.2 MB |
| Poster / still | Landscape 1920 WebP ≤ 160 KB; portrait 900 WebP ≤ 90 KB |
| Steam overlay | 1600×900 WebP on black ≤ 60 KB |
| Full-bleed scene images | WebP at 800 / 1600 / 2400 widths, `sizes="100vw"`; 2400w ≤ 380 KB, 1600w ≤ 200 KB, 800w ≤ 90 KB. Lazy except the first scene |
| Images inside pins | Preload the next image of a sequence when the previous one is half way (`img.decode()` in the timeline `onUpdate` once) so cross-fades never show an empty frame |
| Fonts | Unchanged (two variable woff2, preloaded) |
| Core Web Vitals (mid phone, 4G) | LCP ≤ 2.5 s (the poster), CLS ≤ 0.05, INP ≤ 200 ms. Lighthouse mobile performance ≥ 90 |
| Frame rate | 60 fps on a 2021 iPhone and a mid Android in Chrome: only `transform` and `opacity` animate; one blend layer (steam); `backdrop-filter` only on the fixed header; no `filter` animations; `will-change: transform` only on the active pinned layers, removed after |

---

## 11. Reduced motion summary

`prefers-reduced-motion: reduce` (and no JS, and GSAP failure) gives the **static layout**: every scene is a normal one-screen section, everything visible, final numbers, filled swans, no pins, no scrub, no Lenis, no glow, no page transitions, no autoplay video (poster only), no steam, header always solid. The content and order are identical. Per scene fallbacks are listed under each scene above.

---

## 12. Token additions (proposed, derived; add to `tokens.css` and BRAND section 8)

| Token | Value | Use |
|---|---|---|
| `--color-veil` | `rgb(73 46 33 / 0.82)` | Solid part of the legibility veil. Cream text on it ≥ 6.5:1 over the brightest render |
| `--color-header-solid` | `rgb(73 46 33 / 0.88)` | Fixed header after scroll (with blur). Solid espresso under reduced transparency |
| `--color-glow` | `rgb(229 172 110 / 0.16)` | Pointer light centre. Decoration only |
| `--scene-h` | `100svh` | Scene height |
| `--scene-pad-top` | `calc(var(--header-h) + var(--space-5))` | Clears the fixed header |
| `--duration-line` | `1100ms` | Line rise |
| `--stagger-line` | `80ms` | Between lines of one heading |
| `--duration-page` | `480ms` | Page transition in (out is 240ms) |

GSAP uses `CustomEase.create('soft', '0.22,1,0.36,1')`, the same curve as `--ease-soft`.

---

## 13. Assets still needed

1. Hero video (HERO-VIDEO.md), landscape and portrait, plus posters.
2. Steam-on-black overlay (HERO-VIDEO.md, section 4).
3. Renders N1-N6 (BRIEF section 10), now more important: the room walk and the cold scene depend on them. N2 first.
4. A 16:9 outpainted version of render 08 for the desktop living still (the current file is portrait, 1367 px wide, so it is soft and tightly cropped full-bleed at 1440). fal.ai outpaint, same grade.
5. `_mark_draw.html` (the mark as fill + line groups), from the existing mark paths.
