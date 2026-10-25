# Spa 99 — Brand

Source: `Spa 99 Branding.pdf` (8 pages, 2026) and the `01 Branding` folder in OneDrive.

## 1. Essence

- Brand line: **Beyond Luxury**. Badge line: "Your Comfort, Our Passion".
- Feeling: warm, quiet, unmistakably premium. Editorial elegance, modern restraint.
- It should feel like walking into the spa: lots of space, one idea per screen, big editorial type, slow soft motion.
- A men's spa. No spa clichés: no candles, stones, flowers-in-water, women in towels.

## 2. The mark

- A swan shaped from the letter S, with 99 in its body acting as feathers.
- Lockups: stacked (swan over "SPA 99"), horizontal (swan + "SPA 99"), swan + "Beyond Luxury", circular badge.
- Light and dark versions exist. Use vector (SVG from the PDF/AI files) on the web, never a stretched PNG.
- Swan pattern (repeating S-swans) for backgrounds and texture, gold on espresso or espresso on gold.

## 3. Colour

| Token | Name | Hex | Use |
|---|---|---|---|
| `--color-cream` | Spa Cream | `#F5F2D8` | Main light background |
| `--color-gold` | Swan Gold | `#E5AC6E` | Mark, accents, highlights on dark |
| `--color-caramel` | Caramel | `#BB8855` | Secondary accent, lines, large text only |
| `--color-espresso` | Espresso | `#492E21` | Main text, dark backgrounds |

**Contrast (WCAG AA = 4.5 for body text, 3.0 for large text):**

| Pair | Ratio | Verdict |
|---|---|---|
| Espresso on Cream | 10.95 | Any text |
| Cream on Espresso | 10.95 | Any text |
| Gold on Espresso | 6.17 | Any text |
| Caramel on Espresso | 3.99 | Large text and UI only |
| Caramel on Cream | 2.75 | Decoration only, never text |
| Gold on Cream | 1.78 | Decoration only, never text |

Derived tints (designer may add, mark as derived): e.g. a slightly lighter cream for cards, espresso at reduced opacity for borders.

## 4. Typography

| Role | Font | Notes |
|---|---|---|
| Headlines, statements | **Signika** (Google Fonts) | Letter spacing −0.025em. Brand guide: lowercase tracking −25 |
| Body, UI, wayfinding, forms | **Figtree** (Google Fonts) | Replaces JUST Sans (no web licence). Letter spacing −0.01em |

- Self-host both (no Google Fonts calls from the browser).
- Big editorial type for headlines. Comfortable reading size for body (min 16px on mobile).

## 5. Imagery

- Current images are AI renders (Gemini, Aug 2026) in `01 Branding/Assets`: towels, robes, saunas, lockers, totes, bottle, slippers, gym, reception, pool.
- Warm wood, travertine, low warm light. Branded items with the gold swan.
- Do not use asset 07 (towel with stones) or anything cliché.
- New renders can be generated with fal.ai in the same look.
- Real photography to replace renders later.

## 6. Copy tone

- Short, calm, confident. No hype, no exclamation marks.
- Speaks to a man as a guest, not a customer. "Your evening", not "Book now!!".
- Anything that collects information feels like choosing, not filling in a form.

## 7. Motion

Two modes, one feeling (slow, soft, never bouncy):

- **Immersive** (7A): the marketing pages (Home, The spa, Memberships, Gold Card, Book, Visit us). Scroll-told scenes with GSAP. Full spec: `docs/design/IMMERSIVE.md`.
- **Restrained** (7B): everything that collects information or is a tool: the journey, register interest, sign in, password reset, account, the Gold application, error pages and Control. CSS and the one shared reveal script, no animation library.

Shared everywhere:
- **Easing:** `cubic-bezier(0.22, 1, 0.36, 1)` (`--ease-soft`; in GSAP `CustomEase` named `soft`). Scroll-scrubbed motion uses linear easing, because the scroll is the easing.
- Only `transform` and `opacity` animate (plus SVG stroke drawing on the swan). Never `width`, `height`, `top`, `left`, animated `clip-path` or filters.
- No bounce, no rotation, no blur transitions, no sideways travel of text, no sound. One exception to rotation: the 3D Gold Card object may rotate (decision log 2026-10-22; text never rotates and never lives in WebGL).
- Hover motion only under `(hover: hover) and (pointer: fine)`.

### 7A. Immersive (marketing pages)

- **Every section fits one screen on desktop** (`100svh`), complete on its own at 1440×800. On phone, a scene read in normal scroll (no pin) may run to two screens; nothing inside it may depend on a pin.
- **Scroll drives the story, with one short pin on Home (the hero shrinking into its frame) and the same short pin on The spa (the door shrinking into its frame):** image settle (scale 1.06 → 1), depth between image layers, the thread. Pins only where a whole sequence changes in place (The spa room walk). Scrub 0.4 desktop, 0.3 phone. No snapping on Home.
- **Headings rise line by line** from a mask (1.1s, 0.08s between lines), once. Body and actions fade up after them (0.9s, 16px).
- **The swan draws itself** (stroke, then the gold fill) on the Gold Card, Book and the Home Gold scene. Nowhere else. On Home the draw is time-based on enter (2.4s), not scrubbed.
- **Numbers count** only when they are small whole numbers that matter (visits a month, days ahead): 1.2s, once. Prices never animate.
- **Pointer light**: a soft gold glow follows the pointer on dark scenes, desktop with a fine pointer only.
- **Hero**: a looping muted video (6-10s, warm water, steam or light), or a living still (a 48s scale cycle and drifting steam) until the video exists. No Pause control (Moishe, 2026-10-23). Video loads after the page, never on Save-Data.
- **Text on photographs and video** is allowed on marketing scenes, always on the solid part of the legibility veil (`--color-veil`). Text groups sit vertically centred and left aligned, not at the bottom of the screen (IMMERSIVE section 0).
- **Header** overlays the first dark scene, turns solid after 64px, hides on scroll down and returns on scroll up.
- **Page changes** cross-fade (View Transitions, opacity only, 240ms out, 480ms in); the header stays put.
- **Smooth scrolling is off** (flag `data-smooth` on `<html>`, code kept for later).
- **Loops** slower than one cycle per 15s, paused when off screen or the tab is hidden.
- **Budget:** at most 75 KB gzip of motion JS on marketing pages, 60fps on a mid phone, LCP ≤ 2.5s (the hero poster).
- **Reduced motion** (and no JS): the static layout. Every scene a normal one-screen section, everything visible, final numbers, filled swans, poster instead of video, no pins, scrub, Lenis, glow, page transitions or steam; header always solid.

### 7B. Restrained (forms, journey, account, Gold application, errors, Control)

Smooth and restrained. Built with CSS and one small shared script (IntersectionObserver), no animation library. These pages never load GSAP.

**Easing:** always `cubic-bezier(0.22, 1, 0.36, 1)` (`--ease-soft`). Opacity 0 → 1.

**Entrances**
| Group | Trigger | Duration | Delay | Movement |
|---|---|---|---|---|
| Hero | On load | 0.8s | none | Rise 12px (8px on phone) |
| Section groups (heading + copy + actions together) | 15% of the group visible (0 if taller than the screen) | 1s | 0.1s after entering view | Rise 12px (8px on phone) |
| Card collections | Same as sections | 1s | 0.1s | Rise 12px (8px on phone) |
| Standalone images | Same as sections | 1s | 0.1s | Scale 0.98 → 1, no travel |

- Each group reveals once (no replay) and on its own, never scheduled from page load. Never reveal the whole page as one group.
- Animate a container or its groups, never both.
- Stagger only 2–4 sibling cards or visuals that show steps or progression: 0.1s apart in reading order. On phone, no stagger. Never stagger long lists, words, or copy with its actions.
- Not animated: navigation, sticky controls, backgrounds, dividers, long article text, footer legal/utility links.
- No blur, rotation, sideways travel, bounce or exit animations.

**Interaction feedback** (separate from entrances)
- Buttons and clickable cards without their own feedback: scale 1.01 on hover, 0.99 on press, 0.25s, same easing.
- Tall selectable cards (the Memberships key cards) lift instead of scale, because scaling a tall card blurs its type: 4px up on hover (`--tier-hover-lift`), 2px up on press. The selected card sits up (`--tier-lift`, 8px from 64em); its colour and check change instantly, the lift eases over `--duration-tier` (0.6s). Off under reduced motion.
- The selected Memberships card also lights its room (veil off, photo settles 1.03 to 1, 1.2s) and casts a warm pool on the cream (600ms with the lift). The colour, check, inlay and gold numeral still change instantly.
- The one-off sheen: the selected Memberships card gets one band of light across it on selection (`--color-sheen`, 1.6s, once, CSS only). Same family as the Gold Card sheen. Not on hover, never looping, off under reduced motion; the band is not text, so the ban on sideways travel of text does not apply.
- If scale is already used on that element, use opacity 0.9 on hover and 0.8 on press instead.
- Inline links and non-interactive elements don't scale. Scaled elements must never clip.

**Reduced motion** (`prefers-reduced-motion: reduce`): everything is visible immediately, with no movement or sequencing.

**Journey screens:** the next part fades and rises in the same way; a choice is acknowledged instantly (no animation delay on the selected state).

**On marketing pages**, the parts that are really small forms (the journey entry tiles on Home) follow 7B inside their immersive scene: they arrive as one group, selection is instant, no stagger. Interaction feedback (buttons scale 1.01 / 0.99) is the same in both modes.

**Visual consistency:** forms and journey use the same type scale, colours, header and page transition as the marketing pages, so moving from a scene into the journey feels like the same building, just quieter.

## Components: accents

Never a one-sided accent (left/right stripe, inset side shadow, or a ::before bar). Use no border with a soft shadow, a tinted background, or a full hairline. Selected/active states use background tint, weight or an icon.

## 8. CSS tokens

Kept in sync with `common/static/common/css/tokens.css`. Brand values are the four colours, the two fonts and the type/space scale. Everything commented "derived" was added by the designer (Phase 1 design brief, `docs/design/BRIEF.md` section 11, which lists every contrast ratio). Nothing in the starting set was changed or removed.

```css
/* Brand tokens (docs/BRAND.md section 8). Components use these, never raw values.
   Anything marked "Derived" is not a brand colour/value; see docs/design/BRIEF.md section 11 for contrast. */
:root {
  /* Colour */
  --color-cream: #F5F2D8;
  --color-gold: #E5AC6E;
  --color-caramel: #BB8855;
  --color-espresso: #492E21;

  --color-bg: var(--color-cream);
  --color-text: var(--color-espresso);
  --color-bg-inverse: var(--color-espresso);
  --color-text-inverse: var(--color-cream);
  --color-accent: var(--color-gold);       /* on dark only for text */
  --color-line: var(--color-caramel);
  /* Derived (not brand colours): a deep red for destructive actions, a translucent espresso behind modals. */
  --color-danger: #8B1E1E;                 /* 8.07 on cream; not for text on espresso */
  --color-overlay: rgb(73 46 33 / 0.6);

  /* Derived surfaces and text (design brief) */
  --color-cream-raised: #FBF9EC;           /* espresso text 11.71 */
  --color-espresso-raised: #553729;        /* cream 9.45, gold 5.32, caramel 3.44 */
  --color-text-muted: #745F4F;             /* 5.32 on cream, 5.69 on cream-raised */
  --color-text-muted-inverse: #C5BBA5;     /* 6.50 on espresso, 5.61 on espresso-raised */
  --color-control-line: #8E7C6A;           /* field/tile borders: 3.54 cream, 3.79 cream-raised, 3.09 espresso; not on espresso-raised */
  --color-hairline: rgb(73 46 33 / 0.14);  /* decoration only */
  --color-hairline-inverse: rgb(245 242 216 / 0.14); /* decoration only */
  --color-danger-inverse: #F4B09E;         /* error text on espresso, 6.81 */
  --color-focus: var(--color-espresso);
  --color-focus-inverse: var(--color-gold);
  --color-pattern: rgb(229 172 110 / 0.08); /* swan pattern on espresso */
  /* Derived chart colours for Control (light background, >= 3:1 on cream-raised) */
  --color-chart-1: var(--color-espresso);  /* 11.71 */
  --color-chart-2: #A0703F;                /* caramel deep, 4.07 */
  --color-chart-3: #745F4F;                /* 5.69, always with a hatch pattern */

  /* Type */
  --font-display: "Signika", system-ui, sans-serif;
  --font-body: "Figtree", system-ui, sans-serif;
  --tracking-display: -0.025em;
  --tracking-body: -0.01em;
  --tracking-label: 0.08em;                /* derived: small uppercase labels only */

  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-body: 1rem;                       /* derived: may become 1.0625rem at desktop */
  --text-lg: 1.25rem;
  --text-xl: clamp(1.5rem, 2vw + 1rem, 2.25rem);
  --text-2xl: clamp(2.25rem, 4vw + 1rem, 4rem);      /* journey, forms, account, legal. Marketing pages override, see below */
  --text-hero: clamp(3rem, 8vw + 1rem, 8rem);

  --leading-display: 1;
  --leading-tight: 1.1;
  --leading-snug: 1.4;
  --leading-body: 1.6;

  /* Space */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 1rem;
  --space-4: 1.5rem;
  --space-5: 2.5rem;
  --space-6: 4rem;
  --space-7: 6rem;
  --space-8: 10rem;

  /* Layout (derived) */
  --container-max: 90rem;                  /* 1440px including margins */
  --page-margin: clamp(1.25rem, 4.4vw, 4rem);
  --gutter: clamp(1.25rem, 2.2vw, 2rem);
  --measure: 34rem;
  --measure-display: 14ch;
  --section-y: clamp(6rem, 11vw, 10rem);
  --header-h: 4rem;
  --control-h: 3.25rem;                    /* 52px buttons and fields */
  --control-h-compact: 2.5rem;             /* 40px, Control only */
  --tile-min-h: 4.5rem;

  /* Shape */
  --radius-sm: 6px;                        /* controls */
  --radius-md: 12px;                       /* surfaces; photography is always square */
  --shadow-raised: 0 24px 60px -24px rgb(73 46 33 / 0.35); /* derived: modal only */

  /* Motion */
  --ease-soft: cubic-bezier(0.22, 1, 0.36, 1);
  --duration-slow: 700ms;
  --duration-base: 400ms;
  /* BRAND section 7 timings (derived names, values from the spec) */
  --duration-hero: 800ms;
  --duration-reveal: 1000ms;
  --delay-reveal: 100ms;
  --stagger: 100ms;
  --duration-press: 250ms;
  --rise: 8px;

  /* Immersive marketing pages (docs/design/IMMERSIVE.md section 12). Derived, not brand colours. */
  --color-veil: rgb(73 46 33 / 0.82);          /* derived: solid part of the legibility veil; cream on it >= 6.5:1 over the brightest render */
  --color-header-solid: rgb(73 46 33 / 0.88);  /* derived: fixed header after scroll, with blur */
  --color-glow: rgb(229 172 110 / 0.16);       /* derived: pointer light centre, decoration only */
  --scene-h: 100svh;                           /* derived */
  --scene-pad-top: calc(var(--header-h) + var(--space-5)); /* derived: clears the fixed header */
  --duration-line: 1100ms;                     /* derived: line rise */
  --stagger-line: 80ms;                        /* derived: between lines of one heading */
  --duration-page: 480ms;                      /* derived: page transition in (out is 240ms) */
  /* Home round 2 (docs/design/IMMERSIVE-R2.md section 7). Derived, decoration only. */
  --color-frame-tint: rgb(73 46 33 / 0.14);    /* derived: resting tint inside every frame on dark scenes */
  --color-thread: rgb(229 172 110 / 0.45);     /* derived: the thread (gold) on espresso */
  --color-thread-light: rgb(187 136 85 / 0.6); /* derived: the thread (caramel) on cream */
  --frame-gap: var(--space-6);                 /* derived: minimum espresso between two frames */
  --bleed: calc(var(--page-margin) + max(0px, (100vw - var(--container-max)) / 2)); /* derived: content edge to screen edge, for edge-bleed frames */
  /* Memberships round 2, the key cards (docs/design/MEMBERSHIPS-R2.md section 7). Derived, decoration only; shadows are warm (espresso), never black. */
  --shadow-tier: 0 1px 1px rgb(73 46 33 / 0.04), 0 6px 12px -4px rgb(73 46 33 / 0.06), 0 24px 44px -20px rgb(73 46 33 / 0.14); /* derived: a tier card at rest */
  --shadow-tier-hover: 0 2px 2px rgb(73 46 33 / 0.05), 0 12px 20px -6px rgb(73 46 33 / 0.08), 0 36px 64px -24px rgb(73 46 33 / 0.20); /* derived */
  --shadow-tier-selected: 0 2px 3px rgb(73 46 33 / 0.10), 0 16px 28px -10px rgb(73 46 33 / 0.20), 0 52px 88px -30px rgb(73 46 33 / 0.38); /* derived */
  --shadow-bar: 0 -10px 28px -18px rgb(73 46 33 / 0.22); /* derived: the sticky tag on phone */
  --color-tier-edge: rgb(73 46 33 / 0.07);     /* derived: 1px edge of a cream tier card (decoration) */
  --color-tier-edge-gold: rgb(229 172 110 / 0.55); /* derived: 1px edge of the selected tier card */
  --color-sheen: rgb(245 242 216 / 0.10);      /* derived: the one band of light across the selected card */
  --tier-w: 18rem;                             /* derived: a tier card */
  --tier-h: clamp(33rem, 100svh - 15rem, 37.5rem); /* derived */
  --tier-gap: 2.5rem;                          /* derived */
  --tier-tag-w: 18rem;                         /* derived: the tag column */
  --tier-num-size: 3.5rem;                     /* derived: the visits numeral; 4.5rem from 64em */
  --tier-lift: 0px;                            /* derived: how far the selected card sits up; -8px from 64em */
  --tier-hover-lift: -4px;                     /* derived */
  --duration-tier: 600ms;                      /* derived: the selected card's rise */
  /* Memberships round 3 (docs/design/MEMBERSHIPS-R3.md section 4). Proposed, round 3: derived, decoration only. */
  --color-pool: rgb(229 172 110 / 0.35);       /* proposed, round 3: warm light pool on the cream under the selected card */
  --color-room-veil: rgb(251 249 236 / 0.24);  /* proposed, round 3: cream veil over an unselected card's picture */
  --duration-ack: 240ms;                       /* proposed, round 3: the tag's acknowledgement fade */
  /* Forms round 4 (docs/design/FORMS-ROUND4.md section 5). Proposed, round 4. */
  --color-chosen-wash: var(--color-pattern);   /* proposed, round 4: alias, no new colour. Gold at 8% over a chosen tile; decoration only */
  --tile-tall-h: 11rem;                        /* proposed, round 4: Company tiles from 64em */
  --tile-compact-h: 3.5rem;                    /* derived, round 4: industry tiles (no sub line) */
  --tile-large-h: 5.5rem;                      /* derived, round 4: Company tiles on a phone */
  --tile-mark-room: 2rem;                      /* derived, round 4: room for the tile's mark at the right */
  --glyph-col-w: 3rem;                         /* derived, round 4: the swan glyph column in a Company tile */
  --measure-lead: 22rem;                       /* derived, round 4: the lead under a screen heading */
  --signin-w: 26rem;                           /* derived (round 3): the sign-in form column */
  --control-h-label: 3.75rem;                  /* derived (round 4): a field with its label inside (60px) */
  --color-field-well: var(--color-cream);      /* derived (round 4): alias, no new colour. The filled field on the raised cream panel */
  --register-photo-h: clamp(10rem, 100svh - var(--header-h) - 28rem, 24rem); /* derived (round 4): the register stage picture, desktop */
  --panel-overlap: var(--space-5);             /* derived (round 4): how far the cream panel rises over the espresso stage, below 64em */
  --tracking-engraved: 0.2em;                  /* derived (round 3): the engraved brand line on the Gold panel; the "Launching" label used it in round 5, now --tracking-launch */
  --tracking-launch: 0.3em;                    /* derived (2026-10-23): the "Launching" label (Home opening band, register caption): all caps, --text-base, weight 600 */
  --bar-h: 4.5rem;                             /* derived: Continue bar; 4rem from 64em */
  /* The Gold Card (docs/design/GOLD-CARD-3D.md 7.3). Derived, decoration only: the metal of one object. Brand gold is hue 31 degrees; nothing here goes brass (45+). */
  --color-gold-metal: #D9A46C;                 /* derived: card base metal (hue 31) */
  --color-gold-light: #F3D2A2;                 /* derived: polished highlight, the drawn line (hue 36) */
  --color-gold-shade: #A9763F;                 /* derived: card edge and gradient ends (hue 31) */
  --color-gold-deep: #5A3A26;                  /* derived: the back of the card (hue 23) */
  --color-led: #FFE8C8;                        /* derived: warm LED white, the key and rim light of the 3D studio */
  --gc-w: min(86vw, 24rem);                    /* derived: card width (phone); desktop below */
  --gc-tilt-max: 6deg;                         /* derived: pointer tilt cap */
  /* The spa page (docs/design/SPA-PAGE.md 7.3). Derived. */
  --chip-h: 2.75rem;                           /* derived: a link chip, 44px tap target */
  --pill-h: 2rem;                              /* derived: a static pill */
  --frame-h-feature: min(68svh, 34rem);        /* derived: max height of a feature frame, desktop */
  --tile-w-phone: 72vw;                        /* derived: a tile in the phone scroll row */
  --ratio-tile: 3 / 4;                         /* derived */
  /* Feedback: toasts and the one modal (docs/design/FEEDBACK.md section 4). */
  --shadow-toast: 0 2px 4px rgb(73 46 33 / 0.12), 0 12px 32px -12px rgb(73 46 33 / 0.45); /* approved 2026-10-25, FEEDBACK: toasts only */
  --color-overlay-soft: rgb(73 46 33 / 0.32);  /* approved 2026-10-25, FEEDBACK: modal backdrop, with 4px blur; same value as --office-overlay */
  --toast-w: 22.5rem;                          /* approved 2026-10-25, FEEDBACK: toast width from 64em */
  --modal-w: 26.25rem;                         /* approved 2026-10-25, FEEDBACK: the one modal */
}

@media (min-width: 48em) {
  :root { --rise: 12px; }
}

@media (min-width: 64em) {
  :root { --header-h: 4.5rem; --gc-w: min(40rem, 44vw); }
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-slow: 0ms;
    --duration-base: 0ms;
    --duration-hero: 0ms;
    --duration-reveal: 0ms;
    --delay-reveal: 0ms;
    --stagger: 0ms;
    --duration-press: 0ms;
    --rise: 0px;
  }
}
```

**Virtual tour tokens** (VIRTUAL-TOUR 7.2, added 2026-10-23; the four brand colours are untouched, everything below is derived and decoration only, never text; sage and moss are outside the brand hues and live inside the lounge only; the tank colours (water, deep water, coral) live in the lounge room code, not as tokens):

```css
/* Virtual tour (docs/design/VIRTUAL-TOUR.md 7.2). Derived, decoration only, never text. The WebGL palette (IMMERSIVE 12) is read by the 3D script with getComputedStyle. */
:root {
  --color-light-warm: #FFA957;                 /* derived: 2700K, every point light */
  --color-led-warm: #FFC48A;                   /* derived: self-lit LED strips, downlights, halos (--color-led stays the Gold Card's) */
  --color-heater-glow: #FF8A3D;                /* derived: the low light in the heater stones */
  --color-aspen: #E3CCA6;                      /* derived: sauna bench seats and slats */
  --color-aspen-shade: #CDB48C;                /* derived: bench skirts */
  --color-cedar: #7E5236;                      /* derived: sauna walls and ceiling */
  --color-walnut: #3B271B;                     /* derived: frames, bench ends, gym panels */
  --color-stone: #7A604C;                      /* derived: heater stones, light */
  --color-stone-dark: #4A372B;                 /* derived: heater stones, dark */
  --color-floor-stone: #3A2B22;                /* derived: sauna floor */
  --color-glass-bronze: rgb(107 74 48 / 0.28); /* derived: bronze glass */
  --color-travertine: #E4D2B1;                 /* derived: cream 70% + caramel 30% */
  --color-travertine-vein: #CCA87C;            /* derived: cream 30% + caramel 70%; also the wet sauna fog */
  --color-iron: #2C1C14;                       /* derived: espresso at 60%; the darkest value anywhere */
  --color-sage: #A3A98A;                       /* derived, outside the brand hues: lounge pillows */
  --color-moss: #5F6B3C;                       /* derived, outside the brand hues: green wall, moss discs */
  --tour-caption-w: 26rem;                     /* derived: caption width */
  --tour-ring: 1.75rem;                        /* derived: marker ring (the tap target stays 2.75rem) */
  --ease-glide: cubic-bezier(0.65, 0, 0.35, 1); /* proposed: camera travel toward a doorway only */
  --duration-glide-fade: 700ms;                /* derived: room cross-fade */
  --duration-settle: 1400ms;                   /* derived: arrival settle */
  --duration-gl-in: 1200ms;                    /* derived: the canvas fading in */
  --duration-tour-fade: 300ms;                 /* derived: marker and hint fade */
  --duration-tour-quick: 200ms;                /* derived: markers leaving */
  --duration-tour-tap: 120ms;                  /* derived: ring press colour */
  --duration-tour-pulse: 1600ms;               /* derived: the one marker pulse */
  --duration-tour-wait: 8s;                    /* derived: the waiting line; matches the 8 s give-up in engine.js */
}
```

**Marketing type scale** (one step down, IMMERSIVE section 0): under `html[data-page="marketing"]` in `tokens.css`, `--text-2xl: clamp(2rem, 2.5vw + 1rem, 3rem)` (32px phone, 48px desktop) and `--text-hero: clamp(2.75rem, 5vw + 1rem, 6rem)` (44px phone, about 88px at 1440). The journey, forms, account and legal pages keep the larger scale above.

**Immersive tokens** (`--color-veil`, `--color-header-solid`, `--color-glow`, `--scene-h`, `--scene-pad-top`, `--scene-centre-top`, `--scene-centre-bottom`, `--color-veil-soft`, `--duration-line`, `--stagger-line`, `--duration-page`, `--color-frame-tint`, `--color-thread`, `--color-thread-light`, `--frame-gap`, `--bleed`) are derived and now live in `tokens.css`. Values and contrast: `docs/design/IMMERSIVE.md` section 12.

**My Spa 99 tokens** (MEMBER.md 8, 2026-10-23, derived, in `tokens.css`): `--member-rail-w` (16rem), `--member-topbar-h` (3.5rem), `--member-tabbar-h` (4rem), `--member-content-max` (52rem), `--color-tabbar` (espresso at 96%).

The designer refines these per task. Frontend uses only tokens, never raw values. Breakpoints are constants (CSS variables can't be used in media queries): `48em` (tablet) and `64em` (desktop).

### Office tokens
The Office (staff back office) is light and has its own `--office-*` tokens, defined in `common/static/common/css/office-tokens.css` under `.office`, never in `tokens.css`. Spec and values: `docs/design/OFFICE.md`. `--office-toast-edge: rgb(73 46 33 / 0.08)` (approved 2026-10-25, FEEDBACK): the 1px edge of an Office toast, decoration only.

### Round 3 layout tokens (The spa, 2026-10-23, derived)
- `--mount-gap` 0.375rem (0.5rem from 48em): margin between a mount's gold line and its photo.
- `--mount-gap-sm` 0.375rem: the same gap on small mounts (the kit tiles); does not grow at 48em.
- `--band-h` min(62svh, 36rem): height of a full-bleed amenity band.
- `--opener-measure` 26rem: widest the opener words go.
- `--opener-pin` 0.35 (0.5 from 64em): opener pin length in screens (shortened 2026-10-23: one line in the hero).
