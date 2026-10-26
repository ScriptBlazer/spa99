# Large screens (4K, 32 inch)

Designer brief, 2026-10-26. Owner's note: "the site looks too spacious and weird on a 4K 32-inch monitor. Don't break the CSS for other screens, because on most screens it looks perfect."

Scope: one new stylesheet. It only applies above 1920 CSS px wide. At 1920 and below, every page stays pixel-identical.

## 1. What goes wrong, and why

The whole system is in `rem` and stops growing at 1440:

- `--container-max: 90rem` (1440px). The header, every text group and every grid sit inside it.
- The fluid values all reach their caps at about 1440: `--text-hero` (8vw + 1rem, capped at 8rem by 1400), `--text-2xl`, `--section-y` (11vw, capped at 10rem by 1455), `--page-margin` (4rem), `--gutter` (2rem). Above 1440 nothing grows.
- Full-bleed things do keep growing: hero videos and pictures, `100svh` scenes, the edge-bleed frames (`--bleed`), the espresso and cream backgrounds.

So at 3840x2160 (4K at 100%, a common 32 inch setup) the page is a 1440px column, 37% of the screen width, with 16px body text and a 72px header, set inside a 3840x2160 photograph. Measured in the screenshots:

| Viewport | Content column | Share of width | What it feels like |
|---|---|---|---|
| 1440x900 | 1440 | 100% | Baseline, right |
| 1920x1080 | 1440 | 75% | Right ("most screens") |
| 2560x1440 | 1440 | 56% | Starting to look small |
| 3008x1692 | 1440 | 48% | Small, lots of empty space |
| 3840x2160 | 1440 | 37% | Tiny text, gaps, "weird" |

What you see at 3840:
1. **Home hero**: "Beyond Luxury." and the buttons look like a caption in the middle of the photo. The left-hand darkening sits at the screen edge, far from the words.
2. **Header**: 72px tall, a small logo and 16px links in a strip in the middle of the screen. Nothing lines up with the full-bleed media.
3. **Memberships**: the three cards and the choice column sit in the middle, a third of the screen wide, with about 700px of empty cream above and below. Card text is tiny.
4. **The spa**: the edge-bleed frames (dry sauna, gym) run out to the screen edge and become huge next to the small text. The page reads as large photos with captions.
5. **Register / Gold apply / Journey**: still usable, but the panels sit in the middle and the cream texture fills most of the screen.

Nothing is broken (no overflow, no stretched cards, line lengths are fine because `--measure` is in rem). It is a **scale** problem: the content does not grow with the screen, the media does.

## 2. Options considered

| Option | Result | Verdict |
|---|---|---|
| A. Widen `--container-max` above 1920 | Wider column, same small type, longer lines. Cards spread out. Lots of selectors to retune. | No |
| B. Raise the clamp() caps (type, spacing) above 1920 | Many tokens to touch, proportions drift page by page, the header and cards do not follow | No |
| C. CSS `zoom` on `html` | Scales px too, but Chrome's standard zoom also multiplies `vh`/`svh`, which breaks the 100svh scenes and the pinned opener | No |
| **D. Scale the root font size above 1920** | Every rem value (type, spacing, container, header, cards, gaps) grows together. The 1920 composition is kept exactly. vw/svh media stays as it is. One rule. | **Yes** |

Why D works so cleanly here: almost every size in `tokens.css` and the page CSS is in `rem` or is a clamp() whose cap is in rem. Media queries use `em`, which always means the browser default 16px, so no breakpoint moves.

## 3. The fix

### 3.1 New file: `common/static/common/css/wide.css`

Imported last in `common/static/common/css/app.css` (after `memberships.css`):

```css
@import "wide.css";
```

Contents:

```css
/* Large screens (docs/design/LARGE-SCREENS.md). Above 1920 CSS px the root size grows with the screen,
   so the whole page keeps its 1920 proportions. Nothing here applies at 1920 or below. */
@media (min-width: 120.0625em) {
  html {
    /* 16px at 1920 wide (no jump), 21.3px at 2560, 25.1px at 3008, 32px at 3840.
       Capped by height (16px at 960 tall) so short, very wide windows (21:9, 32:9) do not overflow.
       Never smaller than the reader's own default. */
    font-size: max(100%, min(100vw / 120, 100vh / 60));
  }
  :root {
    /* Proposed, large screens: keep corners in proportion. Same 6px and 12px at 16px root. */
    --radius-sm: 0.375rem;
    --radius-md: 0.75rem;
  }
  /* Proposed, large screens: the swan texture keeps its density (200 x 240px at 16px root). */
  .register::before {
    -webkit-mask-size: 12.5rem 15rem;
    mask-size: 12.5rem 15rem;
  }
  .type-tile { background-size: 12.5rem 15rem; }
}
```

The values, and why:

- **Threshold `120.0625em` (just above 1920px).** The evidence: 1920 already looks right (75% column) and is the most common big screen. 2560 is where it starts to look small. Starting just above 1920 means 1920 and everything below are untouched.
- **`100vw / 120`.** 1920 / 120 = 16px, so the size is continuous at the threshold: 1921px gives 16.008px, no visible step. Above that the page scales in exact proportion to the 1920 layout. A 16:9 4K screen becomes exactly the 1920x1080 composition at 2x. The column stays at 75% of the width on every 16:9 screen.
- **`100vh / 60`.** 16px at 960px tall, which is about the real browser viewport on a 1080p screen once the toolbar is taken off. On a 4K screen (about 2030px tall in a browser) the cap is 33.8px, so the width rule (32px) wins. On a 3440x1440 ultrawide the height wins (about 22–24px), so the 100svh scenes, the tier cards (`--tier-h`) and the hero still fit vertically.
- **`max(100%, …)`.** If someone has set a larger default text size in the browser, we never make it smaller.
- **Browser zoom still works.** A 4K user at 150% browser zoom gets a 2560 CSS px viewport, so the rule follows the zoom on its own.

Resulting root size (rendered with the rule applied):

| Viewport | Root | Column (90rem) |
|---|---|---|
| 1920x1080 and below | 16px (rule not applied) | 1440 |
| 2560x1440 | 21.33px | 1920 (75%) |
| 3008x1692 | 25.07px | 2256 (75%) |
| 3440x1440 (21:9) | 24px (height-capped) | 2160 (63%) |
| 3840x2160 | 32px | 2880 (75%) |

### 3.2 Tokens

Nothing changes in `tokens.css`. Proposed additions for `docs/BRAND.md` (Layout), clearly marked:

- *Proposed, large screens:* "Above 1920 CSS px the root size grows with the viewport (`min(100vw / 120, 100vh / 60)`, never below the reader's default). Layouts are designed once, up to 1920. Sizes are in rem, so they scale; only hairlines, shadows and motion distances stay in px."
- *Proposed, large screens:* `--radius-sm` and `--radius-md` become `0.375rem` / `0.75rem` above 1920 only (same pixels at 1920 and below).

### 3.3 Files and selectors to touch

| File | Change |
|---|---|
| `common/static/common/css/wide.css` | New, as above |
| `common/static/common/css/app.css` | Add `@import "wide.css";` as the last line |
| `docs/BRAND.md` | The two proposed lines above (after approval) |

Do **not** put the rule in `tokens.css` or `base.css`. `tokens.css` is also loaded by System and Control, and `base.css` is imported by `office.css`. Those are working screens, where a big monitor should give more room, not bigger type. `app.css` is loaded by the public site, My Spa 99 (`member_base.html` loads `app.css` plus `member.css`), the 500 page, and `base_bare.html` through `common/_assets.html`. That bare shell is also used for the Office and Control sign-in pages. Scaling a sign-in form is harmless, and it fits the site.

Nothing else needs to change. Checked:
- `--bleed` and `scenes.css:366` use `100vw - var(--container-max)`. The container is in rem, so they follow.
- `--gc-w: min(40rem, 44vw)` and the Gold hero `min(42rem, 46vw)` scale, and the WebGL canvas sizes from CSS.
- No JS reads px layout sizes. Breakpoints in JS (`matchMedia('(min-width: 64em)')`) are em, so they do not move. GSAP ScrollTrigger refreshes on resize as it already does.
- Images: the `sizes` attributes are almost all in vw, so they still ask for the right file. Four are in rem (`4.5rem`, `12rem`, `20rem`, `2.5rem`: small thumbnails and glyphs). Rem in `sizes` is measured against the browser default, so at 3840 those ask for half-size sources. They are small, so this is low priority. Follow-up only if they look soft: add a `(min-width: 120.0625em) calc(Xrem * 2)` entry in front.

## 4. Verify "nothing changed at 1920 and below"

I prototyped the rule by injecting it with Playwright on the running dev server and compared the DOM geometry with and without it.

Method (repeat after the real change):
1. On each page, in each viewport, record every element under `body`: tag, `getBoundingClientRect()` (x, y, width, height to 0.01px), computed `font-size`, `padding`, `margin`.
2. Turn the rule on (or compare the branch before and after the change), record again, and diff the two.
3. Pages: `/`, `/the-spa/`, `/memberships/`, `/gold-card/`, `/visit/`, `/register/`, `/journey/`, `/gold-card/apply/`, plus `/account/` signed in.
4. Viewports: 375x812, 1440x900, 1920x1080, 1920x950. All must show **0 differing elements**.

My result: 0 differing elements on all 8 pages, at all 4 sizes (375, 1440, 1920x1080, 1920x950). Root stays at 16px.

Pixel screenshot diffs back this up where a page renders the same twice in a row (register and visit came out byte-identical). Memberships is not a reliable pixel test: it differs from itself between two plain renders with no rule applied (something on the page changes between loads). Use the geometry diff as the gate.

Then look at the large screens: 2560x1440, 3008x1692, 3840x2160 and 3440x1440. Expect the 1920 composition, larger, with no vertical overflow in the hero, the memberships stage or the Continue bar.

Note: in this sandbox Chromium only starts with `--single-process --no-zygote` and one browser per viewport.

## 5. After the change: what to expect at 3840

- The home hero matches the 1920 layout: "Beyond Luxury." is a statement again and sits on the darkened side of the picture.
- The header is 144px tall, with links in proportion, lined up with the content column.
- Memberships fills the screen like at 1920: cards about 576px wide, comfortable text, no sea of cream.
- On the spa page the edge-bleed frames and the text are back in proportion.
- Hairlines (1px) and shadows stay in px, so they look slightly finer. That is fine and fits the quiet look.
