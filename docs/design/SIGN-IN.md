# Spa 99: Sign in (round 3)

For the frontend agent (one small backend item, section 6). Date 2026-10-23. Owner: the sign-in page is "very generic, very unimpressive" (PROJECT.md 2026-10-23). Make it feel like the rest of the site and keep it simple and fast. `docs/BRAND.md` wins on any conflict. Motion is BRAND **7B (restrained)**: CSS and the shared reveal script, no GSAP.

Design read: the members' entrance of a private club. Espresso room, one photograph of the swan lockers bleeding off the right edge, a short welcome in big type, two fields and a gold button. Dials: variance 6, motion 3, density 3.

Scope: the **public** sign-in (`users/login.html`, the `{% else %}` branch). The Spa 99 Control sign-in (the `{% if control %}` branch) does not change.

---

## 1. What is generic today (from the template and CSS)

1. A cream form floating at the top left of an empty cream page (`.auth`, `--measure` wide). Nothing says Spa 99 except the header.
2. No picture, no swan, no detail: it could be any website's login.
3. "Forgotten your password?" and "Register interest" are two loose lines under the button with equal weight.
4. The page is light while the header and most of the site are espresso, so it feels like a different building.

What stays: the heading "Welcome back.", the two fields, the Show toggle, live validation, the throttle message, the error messages, the button label "Sign in" and its working text "One moment", the links' targets, the field names (no analytics or autofill change).

---

## 2. Layout

### 2.1 Desktop 1440 x 800 (from 64em)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ header (solid espresso, as everywhere)                                       │
├──────────────────────────────────┬───────────────────────────────────────────┤
│                                  │╭──────────────────────────────────────────│
│   [swan, 40px gold]              ││                                          │
│                                  ││   the swan lockers (photo), bleeding     │
│   Welcome back.                  ││   off the right edge, inner corners      │
│   Sign in to your Spa 99         ││   radiused                               │
│   account.                       ││                                          │
│                                  ││                                          │
│   Email                          ││                                          │
│   [                        ]     ││                                          │
│   Password       Forgotten?      ││                                          │
│   [                   ] Show     ││                                          │
│                                  ││                                          │
│   [        Sign in         ]     │╰──────────────────────────────────────────│
│   ────────────────────────       │   ── Your own locker, every visit.        │
│   New here? Register interest    │                                           │
│                                  │                                           │
│   99 Vale Road, London N4 · Opening January 2027                             │
└──────────────────────────────────┴───────────────────────────────────────────┘
```

- The section is `.on-dark` (espresso), `min-height: calc(100svh - var(--header-h))`, `display: grid; align-items: center`, padding-block `--space-5`. The footer follows as on every page.
- Grid 12 columns (container as everywhere). **Form column: cols 1 to 5** (max width 26rem, 416px). **Picture: col 7 to the right screen edge** (`.frame--right`, inner corners `--radius-md`), height `min(76svh, 38rem)` (608 at 800 tall), vertically centred with the form.
- Picture: `lockers` (the owner likes it; the swan on every door, and "your own locker" is a fact of the visit, step 2 on The spa). Focus `70% 50%`. Content row override (section 6). `frame-tint` at 0.14 (the house tint on dark).
- Caption under the picture, aligned to its left edge: the standard `.frame-caption` (24px gold hairline, then "Your own locker, every visit." Figtree `--text-sm`, `--color-text-muted-inverse`). One line of editorial detail, not a heading.

**The form column, top to bottom:**

| Part | Spec |
|---|---|
| Swan | `common/_mark.html`, 2.5rem (40px) wide, `--color-gold`, `aria-hidden`. Static (the swan only draws on Gold, Book and Home) |
| h1 | "Welcome back." Signika 500, `--text-2xl` (64px at 1440; this page keeps the form scale), cream, margin-top `--space-4` |
| Lead | "Sign in to your Spa 99 account." Figtree `--text-base`, `--color-text-muted-inverse` (6.50:1), margin-top `--space-2` |
| Throttle / non-field error | Unchanged markup, on dark: `--color-danger-inverse` (6.81:1), margin-top `--space-4` |
| Fields | margin-top `--space-5`, gap `--space-4`. Existing `_field.html`. On dark: label Figtree 500 `--text-sm` cream; input `--control-h` (52px), transparent background, 1px `--color-control-line` border (3.09:1 on espresso, UI), `--radius-sm`, cream text 16px (no iOS zoom). Focus: border cream + 2px `--color-focus-inverse` (gold) outline, 3px offset. Error: `--color-danger-inverse` border and message |
| Forgotten password | Moves **onto the password label row**, right aligned: `.btn-quiet` `--text-sm`, cream, underline offset 3px, "Forgotten?" visually, full accessible name "Forgotten your password?" (`aria-label`). The label row is `display: flex; justify-content: space-between; align-items: baseline` |
| Sign in | `.btn.btn-primary.btn-block` on dark: gold background, espresso label (6.17:1), 52px, margin-top `--space-5`. Unchanged label and working text |
| Divider | 1px `--color-hairline-inverse`, margin-block `--space-5` |
| New here | "New here? Register interest" Figtree `--text-sm`: "New here?" muted inverse, "Register interest" cream `.btn-quiet` link (same target) |
| Address line | Pinned to the bottom of the column (`margin-top: auto` in a flex column that fills the section height minus padding), Figtree `--text-sm`, muted inverse: `{address_one_line}` + " · " + `{opening_text}` from Site settings, e.g. "99 Vale Road, London N4 1PR · Opening January 2027". One middle dot only. If either setting is empty, show the other alone |

Fit at 1440 x 800: header 72; section 728. Column: swan 46 + 24 + h1 64 + 8 + lead 26 + 40 + email 22 + 8 + 52 + 20 (feedback line) + 24 + password 22 + 8 + 52 + 20 + 40 + button 52 + 40 + 1 + 40... = about 650 with the "New here" line, address at the bottom: **fits in 728** with `--space-5` padding. At 1280 x 720 the address line drops into normal flow under "New here" (no pinning when the column is taller than the section).

### 2.2 Tablet 48em to 64em

Form column cols 1 to 7 (max 26rem). The picture becomes a band **above** the form, bleeding right, `--page-margin` on the left, height 12rem, caption under it. Then the form column.

### 2.3 Phone 375 x 667

```
 header 64
┌───────────────────────────────╮   picture band, bleeds right, 9rem (144), inner corners radiused
│ lockers                        │
└───────────────────────────────╯
 ── Your own locker, every visit.     (caption, --text-sm)
 [swan 32]
 Welcome back.                        h1 36px
 Sign in to your Spa 99 account.
 Email
 [                              ]
 Password              Forgotten?
 [                         ] Show
 [          Sign in             ]
 ───────────────────────────────
 New here? Register interest
 99 Vale Road, London N4 1PR
 Opening January 2027
```

- Section padding-top `--space-4`; picture band 9rem tall, left edge at the page margin, bleeding off the right edge, focus `70% 50%`.
- Caption `--space-3` under it. Swan 2rem, `--space-5` under the caption. h1 `--text-2xl` (36px on phone), lead.
- Fields as desktop, full width. Button full width.
- Address line on two lines (no dot): address, then opening text.
- First screen at 375 x 667: header 64 + 24 + 144 + 12 + 20 + 40 + 32 + 16 + 36 + 8 + 24 + 32 + email field 102 + 24 = 598: **the email field is on the first screen**; the password and button are one short scroll (the keyboard covers them anyway once typing).
- `scroll-padding-top: calc(var(--header-h) + var(--space-4))` so focusing a field never hides its label under the header.

---

## 3. Motion (7B)

| What | How | Timing |
|---|---|---|
| Swan, h1, lead | Hero group: opacity 0 to 1, rise `--rise` (8px phone, 12px desktop), on load | `--duration-hero` (0.8s), `--ease-soft` |
| Form (fields, button, links) | Same group as the hero (it is above the fold; one group, never field by field) | same, no stagger |
| Picture | Scale 0.98 to 1 + opacity 0 to 1, no travel, on load | `--duration-reveal` (1s), delay `--delay-reveal` (0.1s) |
| Caption, address line | Fade (opacity only) with the picture | 1s |
| Button | Hover scale 1.01, press 0.99 (BRAND 7B), fine pointer only for hover | `--duration-press` (0.25s) |
| Show toggle, links | No motion; underline thickens on hover (existing `.btn-quiet`) | |
| Errors | Appear instantly (no animation), `aria-live="polite"` as today | 0 |

No pointer glow (this is a tool page). No page-load delay on the form: it must be usable at first paint even if the reveal has not run (the reveal only starts at opacity 0 under `html.motion`, and `reveal.js` is already on the page).

**Reduced motion / no JS:** everything visible at once, no scale, no rise.

---

## 4. Accessibility

- One `<h1>`. The swan and the picture caption are decorative to the form: swan `aria-hidden`; picture `alt="Wooden lockers, each with the swan carved in its door"`.
- Contrast: cream on espresso 10.95; muted inverse 6.50; gold button label (espresso on gold) 6.17; field borders 3.09 (UI); focus ring gold on espresso 6.17; danger inverse 6.81. The form never sits on `--color-espresso-raised` (field borders would drop to 2.67).
- Tab order: Email, Password, Show, Forgotten?, Sign in, Register interest. "Forgotten?" comes after Show, so the password field and its toggle stay together.
- `autocomplete="email"` and `autocomplete="current-password"` on the inputs (check the form widget attrs; add if missing). No autofocus.
- The page works without JS (plain POST form).

---

## 5. Performance

- One picture, `loading="eager"` on desktop (it is above the fold), `sizes="(min-width: 64em) 50vw, 100vw"`, built sizes 800/1600 only. No video, no GSAP, no three.js. Total added weight: the picture (about 120 KB at 1600 WebP).
- The form must be interactive at first paint; LCP is the h1 or the picture, under 2.0s.

---

## 6. Data (backend, small)

- New content page `signin` (seed, create only when missing): row `intro` heading "Welcome back.", body "Sign in to your Spa 99 account.", image (upload, optional, overrides `lockers`); row `caption` body "Your own locker, every visit.".
- The view passes `page_content "signin"` (or the template loads it with the tag, as other pages do). If the rows are missing, the template falls back to the words above.
- Address and opening text come from Site settings (`address_one_line`, `opening_text`), already used by the footer and Home.

---

## 7. Classes and tokens

New in `pages.css` (replace `.auth` and `.auth-inner` for the public sign-in only; keep the old classes for the other account pages until they get the same treatment):

| Class | What |
|---|---|
| `.signin` | The section: `.on-dark`, grid, min-height, centring |
| `.signin-form` | The column, `max-width: var(--opener-measure)` (26rem, SPA-OPENER token) or `26rem` if that token is not in yet |
| `.signin-frame` | The picture: reuses `.frame.frame--right` + `.frame-media` + `.frame-tint` |
| `.field-head` | Label row with the "Forgotten?" link |
| `.signin-foot` | Divider, "New here", address line |

No new colour tokens. Uses `--color-gold`, `--color-text-muted-inverse`, `--color-control-line`, `--color-hairline-inverse`, `--color-focus-inverse`, `--color-danger-inverse`, `--radius-md`, `--radius-sm`, `--control-h`, `--space-*`, `--ease-soft`, `--duration-hero`, `--duration-reveal`, `--delay-reveal`, `--rise`.

Optional, recommended (owner question): the same shell for **Forgotten password**, **Reset password** and **Check your email** pages (one picture, the same column), so the whole account entrance feels like one place. Register interest is a longer form and keeps its own layout.

---

## 8. Acceptance checks (screenshots `.private/shots/signin/` at 375 x 667, 1024 x 768, 1440 x 800; plus error and throttled states)

1. 1440: espresso page, the lockers picture bleeding off the right edge with radiused inner corners, form column on the left, everything (including the address line) visible without scrolling; nothing touches the header.
2. 375: the picture band, caption, swan, heading and the email field on the first screen; no horizontal scroll.
3. Wrong password: the non-field error shows in `--color-danger-inverse` above the fields; focus moves nowhere unexpectedly; the layout does not jump more than the message height.
4. Throttled: the message shows, the form still renders.
5. Keyboard only: Tab order as section 4; visible gold focus ring on every control; Enter submits.
6. Contrast: every text pair as section 4 (check with the browser's contrast tool on the real page).
7. Reduced motion: no rise or scale; everything visible on load.
8. Control's sign-in (control host) is unchanged.
9. Lighthouse accessibility 100, no layout shift from the picture (its box is sized before it loads).
