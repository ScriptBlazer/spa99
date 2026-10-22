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

- Slow, soft: fades and gentle rises, 400 to 800ms, ease-out.
- Respect `prefers-reduced-motion`: no movement, instant changes.

## 8. CSS tokens (starting set)

```css
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
  /* Derived, not brand colours */
  --color-danger: #8B1E1E;                 /* destructive actions */
  --color-overlay: rgb(73 46 33 / 0.6);    /* espresso at 60%, behind modals */

  /* Type */
  --font-display: "Signika", system-ui, sans-serif;
  --font-body: "Figtree", system-ui, sans-serif;
  --tracking-display: -0.025em;
  --tracking-body: -0.01em;

  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.25rem;
  --text-xl: clamp(1.5rem, 2vw + 1rem, 2.25rem);
  --text-2xl: clamp(2.25rem, 4vw + 1rem, 4rem);
  --text-hero: clamp(3rem, 8vw + 1rem, 8rem);

  /* Space */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 1rem;
  --space-4: 1.5rem;
  --space-5: 2.5rem;
  --space-6: 4rem;
  --space-7: 6rem;
  --space-8: 10rem;

  /* Shape */
  --radius-sm: 6px;
  --radius-md: 12px;

  /* Motion */
  --ease-soft: cubic-bezier(0.22, 1, 0.36, 1);
  --duration-slow: 700ms;
  --duration-base: 400ms;
}

@media (prefers-reduced-motion: reduce) {
  :root { --duration-slow: 0ms; --duration-base: 0ms; }
}
```

The designer refines these per task. Frontend uses only tokens, never raw values.
