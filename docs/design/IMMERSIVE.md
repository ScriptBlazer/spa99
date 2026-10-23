# Spa 99: immersive marketing pages

For the frontend agent. This replaces the layout and motion parts of `docs/design/BRIEF.md` for the **marketing pages only** (Home, The spa, Memberships, Gold Card, Book, Visit us). Everything else in the brief stays: palette, type, tokens, components, copy tone, and the journey, forms, sign up, sign in, account, Gold application and Control screens. `docs/BRAND.md` wins on any conflict; its section 7 now holds both the restrained rules (forms) and the immersive rules (this page).

Hero video concepts and prompts: `docs/design/HERO-VIDEO.md`.

---

## 0. Revision 2026-10-22 (Moishe's review of Home): text in the middle, one size smaller

Moishe: with every heading and button at the bottom of each screen, the sections still feel too big and odd. This revision wins over every "bottom left" placement below (H1, H2, S1, S2, G1, V2 and the sauna walk caption).

- **Placement:** the text group (heading, line, actions) sits **vertically centred, left aligned**, at the optical centre (centre of the area under the header, nudged up by `--space-4`). Never pinned to the bottom. Actions sit directly under the line (`--space-5` gap), never pushed to the screen edge.
- **Desktop:** text in cols 1-6. **Phone:** full width inside `--page-margin`, same vertical centring.
- **Type one step down on marketing scenes:** `--text-hero` becomes `clamp(2.75rem, 5vw + 1rem, 6rem)` (44px phone, about 88px at 1440), `--text-2xl` becomes `clamp(2rem, 2.5vw + 1rem, 3rem)` (32px phone, 48px desktop). Leads stay `--text-lg`.
- **Veil follows the text:** desktop uses `.veil--left` with the solid part widened to cover cols 1-6 (solid to about 45%, clear by about 75%). Phone uses a centred band veil (solid behind the text block, fading out above and below) plus a light overall veil. Measure cream on the veil over the brightest pixels under the text: at least 4.5:1 for body text, 3:1 for headings. If an image fails, darken the veil, never move the text back down.
- **Progress lines and small controls** (ritual hairline, phone room hairline, hero Pause) stay at the bottom; they are not text groups.
- **Window end state (H1):** unchanged, words left and the window right, now vertically centred together.
- BRAND 7A "never above the lower 30%" is replaced by "always on the solid part of the veil".

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

**On screen (first paint):** full-bleed hero media under the header (overlay header). Vertically centred, left aligned, over the legibility veil (section 0): "Beyond Luxury." in `--text-hero` (Signika 400 cream, BRIEF 3), lead "A private spa for men in North London. Opening January 2027.", primary gold "Find your membership" with arrow, quiet "See the spa". A small quiet "Pause" control bottom right (section 3.1).

**Media:** `<video>` slot with poster (markup in 3.1). Until a video exists, the living still: render **08** (`hero`) with slow settle and a steam layer (3.2). On desktop with a capable GPU and no video, the living still is the WebGL water pass instead (section 14.1); phones keep the CSS living still.

**On load:** headline Line rise (2 lines max: "Beyond / Luxury." on phone, one line on desktop), lead and actions Fade up 0.3s after. Media fades from espresso `opacity 0 → 1` over 1.4s (prevents a hard poster pop).

**On scroll (scrubbed, ease none):**
| Progress | What moves |
|---|---|
| 0 → 0.3 | Headline, lead and actions: `opacity 1 → 0`, `y 0 → -32`. Veil eases off (`opacity 1 → 0.4`) |
| 0 → 0.75 | **Window**: media shrinks into the target window. Desktop: cols 8-12, centred vertically with the words, inset `--space-4` top and bottom of the stage area (a portrait window flush with the right margin). Phone: full width minus `--page-margin`, 40svh tall, window and statement centred together as a pair |
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

### S2. The rooms - pinned, `+=70%` per room after the first (8 rooms: `+=490%`; `+=630%` when the dry sauna walk runs)

The core of the page. Eight facilities in visiting order (from `visible_facilities()`, hidden ones drop out and the pin shortens automatically: `(n - 1) * 70%`).

**Dry sauna walk:** on desktop with a capable GPU, the dry-sauna room (first in the list) is a scroll-driven 3D walk through the glass door to the top bench, three segments long instead of one. Phones, reduced motion and every other fallback keep render 14 as a normal one-segment room. Full spec: section 14.2.

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
common/static/common/vendor/three/  three.module.min.js (+ LICENSE, VERSION), only for section 14
common/static/common/js/webgl/      hero-water.js, sauna-walk.js (section 14), lazy-loaded by scenes.js
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
| Spa S2 rooms | number of rooms (the dry sauna walk counts 3, section 14.2) | 0.7 | 0.8 / 0.5 | desktop only, never inside the walk |
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
- **WebGL water pass** (section 14.1): on desktop with a capable GPU and no video, a canvas `.hero-gl` inside `.window-media` replaces the CSS living still and the `.hero-steam` layer. Same Pause control, same pausing rules.

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
| WebGL (three.js) | Never downloaded. CSS living still, render 14 | Home hero water pass (no video only) and the dry sauna walk, if the GPU gate passes (section 14) |

Tablet (48-64em) follows phone layouts with desktop video.

---

## 10. Performance budget

| Item | Budget |
|---|---|
| JS on marketing pages (gzip) | gsap 28 KB, ScrollTrigger 18 KB, SplitText 3.5 KB, DrawSVG 2.2 KB, CustomEase 3.6 KB, Lenis 5.4 KB (measured 2026-10-22: 60.7 KB), scenes.js ≤ 10 KB. **Total ≤ 75 KB.** Journey, forms, account: 0 KB of this |
| WebGL JS (gzip, counted separately, section 14.3) | three.js custom build ≤ 145 KB (measured r186.1: 143.5 KB), hero-water.js ≤ 4 KB, sauna-walk.js ≤ 10 KB. Downloaded only on Home and The spa, on desktop, after load and idle, when the gate passes. **New total for those visits: Home ≤ 224 KB, The spa ≤ 230 KB.** Phones, reduced motion and the other four pages stay ≤ 75 KB |
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

`prefers-reduced-motion: reduce` (and no JS, and GSAP failure) gives the **static layout**: every scene is a normal one-screen section, everything visible, final numbers, filled swans, no pins, no scrub, no Lenis, no glow, no page transitions, no autoplay video (poster only), no steam, no WebGL (three.js is never downloaded; the dry sauna is render 14), header always solid. The content and order are identical. Per scene fallbacks are listed under each scene above.

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
| `--duration-gl-in` | `1200ms` | WebGL canvas fade in over its fallback (hero and sauna walk) |

**WebGL palette (derived, decoration only, never for text).** Read by `hero-water.js` and `sauna-walk.js` with `getComputedStyle(document.documentElement)` so the 3D colours live in `tokens.css`, not in JS. All warm; nothing with a blue cast.

| Token | Value | Use |
|---|---|---|
| `--color-light-warm` | `#FFA957` | 2700K light: every point light in the sauna |
| `--color-led` | `#FFC48A` | LED strips (self-lit) behind the backrest and under the step |
| `--color-heater-glow` | `#FF8A3D` | The one low light inside the heater stones |
| `--color-aspen` | `#E3CCA6` | Bench seats, step and backrest slats |
| `--color-aspen-shade` | `#CDB48C` | Bench skirts (vertical boards under the seats) |
| `--color-cedar` | `#7E5236` | Walls and ceiling |
| `--color-walnut` | `#3B271B` | Door frame, bench end panels, heater rail |
| `--color-stone` | `#7A604C` | Split stone, lightest strip |
| `--color-stone-dark` | `#4A372B` | Split stone, darkest strip |
| `--color-floor-stone` | `#3A2B22` | Floor tiles and the shower area beyond the door |
| `--color-glass-bronze` | `rgb(107 74 48 / 0.28)` | Glass door |

The swan on the glass uses `--color-gold`; the hero steam uses `--color-cream`; the hero glint uses `--color-gold`.

GSAP uses `CustomEase.create('soft', '0.22,1,0.36,1')`, the same curve as `--ease-soft`.

---

## 13. Assets still needed

1. Hero video (HERO-VIDEO.md), landscape and portrait, plus posters.
2. Steam-on-black overlay (HERO-VIDEO.md, section 4).
3. Renders N1-N6 (BRIEF section 10), now more important: the room walk and the cold scene depend on them. N2 first.
4. A 16:9 outpainted version of render 08 for the desktop living still (the current file is portrait, 1367 px wide, so it is soft and tightly cropped full-bleed at 1440). fal.ai outpaint, same grade.
5. `_mark_draw.html` (the mark as fill + line groups), from the existing mark paths.
6. `hero-water-mask.webp` for the WebGL water pass (section 14.1): 480×270 greyscale, aligned pixel for pixel to the 16:9 render 08 (item 4), white on the water sheet, black elsewhere, 12px soft edge, ≤ 8 KB. Painted by hand over the 16:9 still. The water pass cannot ship before items 4 and 6 exist.

---

## 14. Three.js moments

Two moments only, both on desktop: the water on the Home hero and a walk into the dry sauna on The spa. Everything else stays GSAP and DOM. Both are decoration on top of a complete page: if three.js never loads, nothing is missing.

Rules that still hold: slow, no bounce, no camera roll, text never rotates and never lives in WebGL (all copy stays DOM, over the veil), DOM moves by `transform` and `opacity` only, warm light only, no people.

### 14.0 The gate (one function, run once, synchronously)

```js
function webglGate() {
  const html = document.documentElement;
  if (html.dataset.webgl === 'off') return false;                       // kill switch, like data-smooth
  if (!matchMedia('(min-width: 64em)').matches) return false;           // phones and tablets: never
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  if (navigator.connection?.saveData || matchMedia('(prefers-reduced-data: reduce)').matches) return false;
  if ((navigator.deviceMemory ?? 8) < 4 || (navigator.hardwareConcurrency ?? 8) < 4) return false;
  const gl = document.createElement('canvas').getContext('webgl2', { failIfMajorPerformanceCaveat: true });
  if (!gl) return false;                                                 // no WebGL2, or software rendering
  gl.getExtension('WEBGL_lose_context')?.loseContext();
  return true;
}
```

- `<html data-webgl="on">` is set from a Django setting (default on), so either moment can be switched off without a deploy of new JS.
- The gate runs before any pinned timeline is built, because the sauna walk changes the S2 pin length. The pin length never changes after it is built (no layout shift).
- `(pointer: fine)` is not required: a large touch screen at 64em or wider with a real GPU gets the moments too. Lenis and Glow keep their own fine-pointer rule.

### 14.1 Home hero: the water pass

**Decision: a shader pass over the still, not a steam-only layer.** The still already has cheap CSS steam; the one thing a still cannot do is move its water. The pass makes the water sheet on render 08 ripple and catch light, and draws the steam in the same shader, so the CSS `.hero-steam` blend layer is switched off and the site still has one blend.

**When it runs:**

| Situation | Hero shows |
|---|---|
| Reduced motion, no JS, GSAP failed | Poster only (static layout) |
| A hero video exists and may play (8.11) | The video. three.js is not downloaded on Home |
| Save-Data, phone or tablet (< 64em), gate fails | CSS living still (8.11) |
| Desktop, gate passes, no video, assets 4 and 6 exist | **WebGL water pass** |
| The pass fails later (watchdog, context lost) | Cross-fade back to the CSS living still within 1.2s |

When the video arrives, it wins and the pass switches off: two kinds of moving water on one hero would look fake and doubles the GPU cost. Moishe can change this (report, question 1).

**Layers inside `.window-media`, bottom to top:** `video` (unused on this path) → `.hero-still` (the `<img>`, still the LCP element) → `.hero-gl` (the canvas, created by JS) → `.hero-steam` (hidden on this path). The veil and the text sit above `.window`, as now.

**Window shrink (8.6):** the canvas is a child of `.window-media`, so the counter-scaled frame crops it exactly like the image. Its drawing buffer follows the layout box of `.window-media` (`ResizeObserver` content box, which ignores transforms), so the shrink never resizes the canvas. The scroll zoom `1.0 → 1.08` (H1, 0 → 0.75) targets `.hero-gl` with the same tween values as the image. The 48s living cycle (`1.0 → 1.06`) runs inside the shader (`uZoom`), so it never fights the scroll zoom on the same element.

**Texture source:** the already decoded `<img class="hero-still">` (`new THREE.Texture(img)` after `img.decode()`), so the still is not downloaded twice. The mask is `data-mask-src` on `.hero-gl`. Both textures use `colorSpace = NoColorSpace` and the material is a `ShaderMaterial` without the colour-space chunk: the still's pixels pass through unchanged, so the first frame matches the `<img>` exactly.

**Fragment shader (load-bearing, keep the numbers):**

```glsl
precision highp float;
uniform sampler2D uImage, uMask;
uniform vec2 uCover, uFocal;        // object-fit: cover and object-position of the <img>, in uv (y up)
uniform float uTime, uAmp, uZoom, uSteam;
uniform vec3 uSteamTint, uGlint;    // --color-cream, --color-gold as 0..1 sRGB
varying vec2 vUv;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p), u = f * f * (3. - 2. * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + 1.), u.x), u.y); }
float fbm(vec2 p){ float v = 0., a = .5; for (int i = 0; i < 3; i++) { v += a * noise(p); p *= 2.03; a *= .5; } return v; }
void main(){
  vec2 uv = (vUv - uFocal) * uCover / uZoom + uFocal;               // same crop as the <img>, living zoom on the focal point
  float m = texture2D(uMask, uv).r;                                   // 1 on the water sheet
  vec2 flow = vec2(uv.x * 38., uv.y * 6. + uTime * .35);              // fine vertical ripples, falling slowly
  vec2 d = (vec2(noise(flow), noise(flow + 17.3)) - .5) * vec2(.0022, .0010) * m * uAmp;
  vec3 c = texture2D(uImage, uv + d).rgb;
  c += m * uAmp * pow(noise(flow * vec2(1., 2.) + 5.), 8.) * .06 * uGlint;           // a faint gold glint on the water
  vec2 s = vUv * vec2(2.2, 1.4) + vec2(.15 * sin(uTime * .021), -uTime * .009);       // steam rises, drifts sideways over 300s
  float zone = smoothstep(.38, .62, vUv.y) * (1. - smoothstep(.88, 1., vUv.y)) * smoothstep(.18, .34, vUv.x);
  float steam = smoothstep(.45, .85, fbm(s)) * zone * uSteam * uAmp;
  c = 1. - (1. - c) * (1. - uSteamTint * steam);                      // screen blend, in the shader
  gl_FragColor = vec4(c, 1.);
}
```

- `uCover`: `r = viewAspect / imageAspect; uCover = r > 1 ? [1, 1 / r] : [r, 1]`. `uFocal` = the image's `object-position` (x, `1 - y`).
- `uZoom = 1 + 0.03 * (1 - cos(2π · t / 48))`: the same 48s cycle as the CSS living still.
- `uSteam = 0.16`. The `zone` keeps steam out of the lower 38% and the left 18%, where text sits on the veil, so hero text contrast is unchanged.
- Displacement is at most about 2 CSS px at 1440 wide. The ripples are continuous water, not a loop; the only cyclic parts (zoom 48s, steam drift 300s) are far slower than 15s.
- `uAmp` ramps `0 → 1` over 2.4s after the canvas fades in, so the fade shows no jump.

**Start:** after `load` + `requestIdleCallback` (timeout 2000ms) and `img.decode()`: dynamic import, build, `renderer.compile()`, render one frame with `uAmp = 0`, then fade `.hero-gl` `opacity 0 → 1` over `--duration-gl-in` (1.2s, `soft`) and `.hero-steam` `1 → 0` over the same time (then kill its drift tween). If Pause is stored in `sessionStorage`, nothing is downloaded until the guest presses Play.

**Running:**
- Renderer: `antialias: false` (a full-screen image pass gains nothing), `alpha: false`, `powerPreference: 'low-power'`, pixel ratio `min(devicePixelRatio, 1.5)`.
- Cadence: 30 fps (the water is slow; this halves GPU and battery cost). One callback on `gsap.ticker`, rendering when 33ms have passed. No second `requestAnimationFrame` loop on the page.
- `uTime` advances only while running, with a capped step (`min(dt, 1/15 s)`), so it never jumps after a pause or a hidden tab.
- Budget per frame: GPU ≤ 2ms, main thread ≤ 0.5ms at 1440×800.

**Pause control (same button as 8.11):** Pause stops the ticker callback; the canvas keeps its last frame; no GPU work while paused. Play resumes from the same `uTime`. Same label swap, `aria-pressed` and `sessionStorage` key as the video.

**Off screen and hidden:** a `ScrollTrigger` on the hero (`onToggle`) stops it when the hero leaves the viewport and starts it again on return; `visibilitychange` stops it while the tab is hidden.

**Watchdog and failure:** after 3s of running, if the median `gsap.ticker.deltaRatio()` over the last 90 ticks is above 1.35 (the page is under about 45 fps), cross-fade back to the CSS living still and dispose. Same on `webglcontextlost`. Never retry in the same page view.

### 14.2 The spa: the dry sauna walk

**Decision: inside S2, as the dry-sauna room, not its own scene.** It is the first room in the visiting order, it keeps its place in the index and the list for screen readers, and the next room (wet sauna) arrives with the normal S2 cross-fade, so the handover needs no new pattern. The story becomes: the spa door opens (S1), you stand at the sauna's glass door, it opens, you walk in to the stone wall and sit on the top bench, then the wet sauna fades in.

**Geometry: procedural, as in the concept file (Concept B), no GLB.** The room is boxes, planes and instanced slats. Building it costs about 10 KB of JS against a GLB of 300 KB or more plus a loader, and the palette stays in tokens. Use the concept's dimensions and coordinates (metres, `x` east, `z` south, `y` up): inner room `xL -1.4625 … xR 1.4625`, `zB -2.172 … zF 2.172`, ceiling 2.10; glass door 0.70 wide in the east wall, `z -0.834 … -0.134` (centre `-0.484`); heater centred on the north wall at `(0, 0, -1.697)`; two-tier bench across the south wall (upper seat 0.60 deep at 0.936, step 0.54 deep at 0.466).

**Markup (the dry-sauna `<article>` in S2):**

```html
<article class="scene-item" data-label="dry-sauna" data-walk>
  {% photo "dry-sauna" alt="..." css_class="scene-media" %}   {# render 14: the fallback and the screen-reader image #}
  <div class="walk-gl" data-webgl="sauna-walk" data-webgl-src="{% static 'common/js/webgl/sauna-walk.js' %}" aria-hidden="true"></div>
  <h2>...</h2><p>...</p>
</article>
```

**Pin length:** when the gate passes, the item has a span of 3 segments instead of 1. Eight rooms: `(7 + 3 - 1) × 70% = +=630%` (was 490%). The walk alone is 2.1 screens of scroll. Labels sit at cumulative spans:

```js
const span = (item) => (glOn && desktop && item.hasAttribute('data-walk')) ? 3 : 1;
let t = 0;
items.forEach((item) => { tl.addLabel(item.dataset.label, t); /* cross-fade, settle, captions as 8.4, with duration span(item) */ t += span(item); });
// end: '+=' + (t - 1) * 0.7 * innerHeight   (replaces (segments - 1))
const walk = { w: 0 };                                     // read by sauna-walk.js every tick
if (glOn && desktop) tl.fromTo(walk, { w: 0 }, { w: 3, duration: 3, ease: 'none' }, 0);
```

Snap (desktop) must never move the camera: inside the walk, return the value unchanged.

```js
snapTo: (v, st) => v < (3 - 0.35) / tl.duration() ? v
  : ScrollTrigger.snapDirectional(Object.values(tl.labels).map((l) => l / tl.duration()))(v, st.direction),
```

**Storyboard (walk time `w`, 0 → 3; scrubbed, ease none; scroll is the easing):**

| w | Camera | Also |
|---|---|---|
| 0 → 0.15 | Hold at A, outside the glass door, the gold swan centred | Name and line already visible (first room, Line rise on enter as 8.4) |
| 0.15 → 0.6 | Starts moving towards B | Door leaf opens `0° → 90°` outwards, hinge on the south jamb |
| 0.15 → 2.4 | A → B → C → D along the curves below | Grazing light on the stone, LEDs on, nothing flickers |
| 2.4 → 2.65 | Hold at D, seated on the top bench | Quiet hold |
| 2.65 → 3.0 | Hold | Wet sauna Cross-fades in over the canvas (normal S2, 0.35 before its label). Name and line leave in 2.8 → 3.0 |

Camera poses (position → target, vertical field of view):

| Pose | Where | Position | Target | FOV |
|---|---|---|---|---|
| A | In the shower area, facing the glass door | `(2.55, 1.55, -0.484)` | `(1.46, 1.40, -0.484)` | 46° |
| B | On the threshold, turning to the stone | `(1.62, 1.55, -0.484)` | `(0.20, 1.15, -1.45)` | 54° |
| C | In the room, stone wall and heater ahead | `(0.75, 1.52, 0.05)` | `(0.00, 1.00, -1.85)` | 56° |
| D | Seated, top bench, facing the stone | `(0.45, 1.66, 1.85)` | `(0.00, 0.95, -1.75)` | 58° |

- Position and target are two `CatmullRomCurve3` (`'centripetal'`) through A-D. `u = clamp((w - 0.15) / 2.25, 0, 1)`; use `getPointAt(u)` (arc length, so speed is even). FOV interpolates linearly with `u`.
- `camera.up` stays `(0, 1, 0)`: no roll, ever. No pointer look-around: scroll is the only control.
- The camera crosses the door plane at about `w 0.8`, after the door is fully open.

**Text:** the S2 caption only (room name `--text-2xl`, its line `--text-lg`), bottom left inside the solid part of the veil, and the desktop index (`.veil--left`) as for every room. No extra copy, no labels in 3D, no text in the canvas. The veil sits above the canvas exactly as above an image. Keep the bright stone grazing light in the upper right of every frame (the poses above do this), never under the caption.

**Materials and light (Spa 99 palette, section 12 tokens):**

| Part | Build | Material |
|---|---|---|
| North wall, split stone | `InstancedMesh` of boxes: about 16 rows (7-18 cm tall), stones 15-45 cm wide, depth 2-25 mm random, about 200 instances | `MeshStandardMaterial`, instance colour random between `--color-stone-dark` and `--color-stone`, roughness 0.92, one 1024² canvas detail texture (concept's `stoneCv`, re-tinted warm) |
| Other walls and ceiling | Planes, 0.6 m boards (concept `planks`), ceiling boards vertical | `--color-cedar`, roughness 0.8 |
| Bench, step, backrest | Slats, skirts and the vertical backrest slats as one `InstancedMesh` per material | `--color-aspen` (seats, slats), `--color-aspen-shade` (skirts), roughness 0.7 |
| Bench ends, door frame, heater rail | Boxes and the concept's tube rail | `--color-walnut`, roughness 0.6 |
| Floor and shower area | Planes, 0.6 m tiles | `--color-floor-stone`, roughness 0.75 (the concept's grey slate is replaced: no cool greys) |
| Heater | Cylinder body, 24 instanced vertical bars (not wireframe), the concept's instanced stones | Body walnut-dark metal (`--color-walnut`, metalness 0.4, roughness 0.5); stones warm greys from `--color-stone-dark` |
| Glass door | One thin box | `--color-glass-bronze`, roughness 0.05, `transparent`, `depthWrite: false` |
| Swan on the glass (once) | A 512² `CanvasTexture`: the mark's path strings drawn with `Path2D`, filled `--color-gold`, on a plane 1 mm in front of the glass, 0.24 m tall, centre at 1.40 m | `MeshBasicMaterial`, `transparent`, opacity 0.9 |
| LED strips | Concept positions: under the step lip, top and bottom of the backrest | `MeshBasicMaterial`, `--color-led` |

Removed from the concept: bucket and ladle, the control panel and its blue screen, vents, labels, OrbitControls, the theme switcher.

Lights (three r155+ uses physical units: these are starting values in candela, tune by eye against render 14):

| Light | Colour | Intensity | Distance / decay | Position |
|---|---|---|---|---|
| Hemisphere | sky `--color-led`, ground `--color-floor-stone` | 0.6 | | |
| Backrest wash × 2 | `--color-light-warm` | 2.0 | 2.2 / 2 | `(±0.8, 1.40, 2.02)` |
| Under the step | `--color-light-warm` | 1.2 | 1.8 / 2 | `(0, 0.30, 0.93)` |
| Stone grazing × 2 | `--color-light-warm` | 3.0 | 2.4 / 2 | `(±0.9, 2.05, -2.05)` |
| Heater stones | `--color-heater-glow` | 0.8 | 1.4 / 2 | `(0, 0.75, -1.697)` |
| Shower area (behind A) | `--color-light-warm` | 1.0 | 3.0 / 2 | `(2.8, 1.9, -0.484)` |

- `outputColorSpace = SRGBColorSpace`, canvas textures `SRGBColorSpace`, `ACESFilmicToneMapping`, exposure 0.95. No shadow maps, no post-processing, no fog. Background `--color-espresso`.
- Grade check: the mean luminance of pose D is within ±10% of render 14, and no rendered pixel has blue above red.

**Budget:** ≤ 40,000 triangles, ≤ 40 draw calls, ≤ 6 textures (one 1024², the rest 512²), GPU memory ≤ 16 MB. Renderer `antialias: true`, `powerPreference: 'high-performance'`, pixel ratio `min(devicePixelRatio, 1.5)`, dropped to 1 if three rendered frames exceed 20ms. GPU ≤ 6ms per frame at 1440×800.

**Render on demand:** the room is static. A `gsap.ticker` callback renders only when `walk.w` changed since the last frame or the canvas was resized; a still scroll costs nothing. It stops completely once the wet sauna image is fully opaque (`w ≥ 3`) and starts again on scroll back. Build, `renderer.compile()` and one frame at pose A happen in idle time after `load`, long before S2 (the S1 door pin is above it).

**Handover and fallbacks:**
- The canvas fades in over render 14 (`--duration-gl-in`) only while S2 is not active. If it is not ready when the S2 pin starts, render 14 stays for this page view: the item keeps its span of 3 and the image Settles slowly `1.15 → 1` across all three segments. It may swap in later only when the guest is back above S2.
- Phone, tablet, reduced motion, Save-Data, the kill switch, a failed gate: render 14 as a normal one-segment room (S2 as written). three.js is not downloaded.
- Context lost or build error: render 14 shows again at once (canvas `opacity 0`, no fade), dispose.

### 14.3 Loading and the scenes.js pattern

**three.js file.** r186.1 is current (2026-10-22) and no longer ships minified files, and the full core plus module build is 196 KB gzip. So vendor one custom, tree-shaken build:

- `tools/three/entry.js` re-exports only what the two modules use (`WebGLRenderer`, `Scene`, `PerspectiveCamera`, `OrthographicCamera`, `Mesh`, `InstancedMesh`, `Group`, `BoxGeometry`, `PlaneGeometry`, `CylinderGeometry`, `IcosahedronGeometry`, `TubeGeometry`, `CatmullRomCurve3`, `Vector3`, `Color`, `Object3D`, `MeshStandardMaterial`, `MeshBasicMaterial`, `ShaderMaterial`, `Texture`, `CanvasTexture`, `TextureLoader`, `HemisphereLight`, `PointLight`, colour-space and tone-mapping constants) from `three@0.186.1`.
- Build once: `npx esbuild@0.28 tools/three/entry.js --bundle --minify --format=esm --legal-comments=eof --outfile=common/static/common/vendor/three/three.module.min.js`. Measured 143.5 KB gzip. Commit the output with three's `LICENSE` (MIT) and a `VERSION` file (`three 0.186.1, esbuild 0.28.2, entry tools/three/entry.js`). No build step at deploy.
- `hero-water.js` and `sauna-walk.js` import it statically (`import * as THREE from '../../vendor/three/three.module.min.js'`). `SpaStaticFilesStorage` already rewrites static module imports to hashed names. Dynamic `import()` is not rewritten, so scenes.js imports the modules by the hashed URL in `data-webgl-src` (`{% static %}` in the template).

**When it loads:** never in `<head>`, never preloaded. Only on Home and The spa, only when `webglGate()` passed, and on Home only when there is no video. Start after `window` `load` + `requestIdleCallback` (timeout 2000ms). Phones never request it.

**Module contract (both files):**

```js
export function create(mount, { gsap, ScrollTrigger, tokens, walk }) {
  // builds renderer, scene and canvas inside mount; returns:
  return { ready /* Promise, resolves after the first frame */, start() {}, stop() {}, dispose() {} };
}
```

`dispose()` is idempotent: removes its ticker callback, observers and listeners, disposes every geometry, material and texture, calls `renderer.dispose()` and `renderer.forceContextLoss()`, removes the canvas, and restores the fallback (`.hero-still` and `.hero-steam` visible on Home, render 14 visible on The spa).

**In scenes.js:** compute `const glOn = webglGate()` once at the top (before `mm.add`). Inside the `mm.add` callback, after the scenes are built, and only when `motion && desktop`:

```js
const disposers = [];
document.querySelectorAll('[data-webgl]').forEach((mount) => {
  if (!glOn || (mount.dataset.webgl === 'hero-water' && heroHasVideo)) return;
  let inst = null, dead = false;
  afterLoadIdle(() => import(mount.dataset.webglSrc)
    .then((m) => { if (dead) return; ctx.add(() => { inst = m.create(mount, { gsap, ScrollTrigger, tokens, walk }); }); })
    .catch(() => {}));                                   // the fallback is already on screen
  disposers.push(() => { dead = true; inst?.dispose(); });
});
return () => { disposers.forEach((d) => d()); stopLenis(); };
```

- `ctx.add` puts the tweens and ScrollTriggers created after the async import into the same matchMedia context, so a switch to reduced motion or below 64em reverts them, and the cleanup disposes the renderer.
- `heroHasVideo` is the 8.11 check (sources present, not Save-Data, a type can play).
- `walk` is the proxy object tweened in the S2 timeline (14.2); the hero ignores it.

### 14.4 Acceptance checks (frontend, before review)

1. **Frame rate.** Chrome Performance panel at 1440×800 on an M1 MacBook Air and on an Intel laptop with integrated graphics: scrolling H1 and S2 holds 60 fps on the M1 and ≥ 50 fps on the Intel; hero pass renders at a steady 30 fps; GPU per frame within budget (hero ≤ 2ms, walk ≤ 6ms); no long task over 50ms during scroll; build and compile happen before the scene is reached.
2. **No layout shift.** CLS ≤ 0.05 with WebGL on and off. Document height is identical right after `load` and after the WebGL moments are ready. A screenshot of the hero just before and just after the canvas fades in differs by no more than antialiasing (`uAmp = 0` first frame).
3. **Fallbacks visible, never blank.** Check each one shows its fallback with no empty frame: 375px (no three.js request in the network panel), reduced motion, `data-webgl="off"`, WebGL disabled in the browser, a hero video present (no three.js on Home), and a forced `WEBGL_lose_context` in the console (fallback back within 1.2s).
4. **Pause and hidden.** Pause stops all GPU work on Home (Performance panel shows no WebGL frames), survives a reload in the same session, the button is 44px and keyboard reachable. A hidden tab does no work; returning does not jump the water.
5. **Clean revert.** Toggling reduced motion while on the page, and resizing below 64em, removes the canvas, frees the context (`renderer.info.memory` geometries and textures at 0 after `dispose()`) and leaves the static layout correct. Visiting Home then The spa never holds more than one WebGL context.
6. **Contrast.** Caption text over the walk at `w` 0, 0.8, 1.5 and 2.4, and hero text over the water pass, measure ≥ 4.5:1 against the brightest pixel under the text box (cream on the veil). No steam inside the hero text zone.
7. **Look.** Warm only (no pixel with blue above red in the sauna; the hero still's colours unchanged at `uAmp = 0`). No camera roll, no text in WebGL, nothing flickers, no people. The swan appears once, on the glass door.
8. **Budget.** `three.module.min.js` ≤ 145 KB gzip, `hero-water.js` ≤ 4 KB, `sauna-walk.js` ≤ 10 KB. Lighthouse mobile ≥ 90 unchanged (phones do not download any of it). LCP is still the poster.
