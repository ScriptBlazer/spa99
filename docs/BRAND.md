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

Smooth and restrained. Built with CSS and one small shared script (IntersectionObserver), no animation library.

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
- If scale is already used on that element, use opacity 0.9 on hover and 0.8 on press instead.
- Inline links and non-interactive elements don't scale. Scaled elements must never clip.

**Reduced motion** (`prefers-reduced-motion: reduce`): everything is visible immediately, with no movement or sequencing.

**Journey screens:** the next part fades and rises in the same way; a choice is acknowledged instantly (no animation delay on the selected state).

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
  --text-2xl: clamp(2.25rem, 4vw + 1rem, 4rem);
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
  --tile-min-h: 4rem;

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
}

@media (min-width: 48em) {
  :root { --rise: 12px; }
}

@media (min-width: 64em) {
  :root { --header-h: 4.5rem; }
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

The designer refines these per task. Frontend uses only tokens, never raw values. Breakpoints are constants (CSS variables can't be used in media queries): `48em` (tablet) and `64em` (desktop).
