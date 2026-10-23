# Spa 99: Register interest (round 4)

For the frontend agent. Date 2026-10-23. Owner (PROJECT.md, 2026-10-23): the form is neat but dated, "looks like a doctor's prescription". Keep the colours; make it modern and premium, with more elements and a background. Same fields, same flow, same endpoints, same field names and order (autofill, analytics). `docs/BRAND.md` wins on any conflict. Motion is BRAND **7B (restrained)**: CSS and `reveal.js`, no GSAP.

Design read: the arrival desk. Sign-in is the members' entrance (form left, lockers right, all espresso). Register is its sibling, mirrored: an espresso **stage** on the left with the reception photograph melting into espresso, the heading and **your membership** card; the form on the right on a **raised cream panel** over a faint swan pattern. Same building, different room. Dials: variance 6, motion 3, density 3.

Screenshots: the sandbox blocks localhost, so this brief is written from the code. The frontend agent takes the shots in section 9.

Files: `users/templates/users/register.html`, `register_sent.html`, `verify_confirm.html`, `common/static/common/css/pages.css` (the `register interest` block), `components.css` (only if a rule is shared), `common/static/common/js/register.js`, `tokens.css` (section 8).

---

## 1. Why it reads as a prescription today

1. A cream page with two plain columns and nothing else: no picture, no texture, no depth.
2. Five big Signika legends (`--text-xl`) stacked down the page with boxed fields under each: it reads like a printed form with headed sections.
3. The plan is a small grey panel above a grey segmented bar, the most important choice looks like a setting.
4. The consents are bare checkboxes with long lines of text.
5. Nothing connects it to the sign-in page the owner likes.

What stays: every field, the honeypot, live validation (`validate.js`, `data-live-validate`, `data-check-email-url`), the DOB three-field script, the password checklist and strength meter, the plan radios (`name="plan"`, `form="register-form"`), the button label and working text, all error and hint wording.

---

## 2. Layout

### 2.1 Desktop 1440 x 800 (from 64em)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ header (solid espresso)                                                      │
├────────────────────────────────┬─────────────────────────────────────────────┤
│▓ reception photo (swan desk)  ▓│  cream page, faint swan pattern             │
│▓ bleeds off the LEFT edge,    ▓│   ╭───────────────────────────────────────╮ │
│▓ fades into espresso          ▓│   │ raised cream panel                    │ │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   │ ── Your name                          │ │
│ Register interest.             │   │ [First name    ] [Last name     ]     │ │
│ No payment now. We'll write    │   │ ── How we reach you                   │ │
│ before the doors open.         │   │ [Email                         ]      │ │
│ ╭────────────────────────────╮ │   │ [Mobile                        ]      │ │
│ │ YOUR MEMBERSHIP            │ │   │ ── Your password                      │ │
│ │ Tier 2            £89      │ │   │ ...  (panel scrolls, stage stays)     │ │
│ │ Character line    a month  │ │   │                                       │ │
│ │ ex VAT (£107 inc VAT)      │ │   │                                       │ │
│ │ [Tier 1] [Tier 2] [Tier 3] │ │   │                                       │ │
│ │ (swan) Your answers come   │ │   │                                       │ │
│ │        with you.           │ │   │                                       │ │
│ ╰────────────────────────────╯ │   ╰───────────────────────────────────────╯ │
└────────────────────────────────┴─────────────────────────────────────────────┘
```

- `.register` is the section (`.on-light`, cream). Grid 12 columns in `.container`.
- **Stage** (`.register-stage`, `.on-dark`): columns 1 to 5, bleeding off the left screen edge (`margin-left: calc(var(--bleed) * -1)`, `padding-left: var(--bleed)`), espresso, square corners (it is a room, not a frame). `position: sticky; top: var(--header-h); height: calc(100svh - var(--header-h)); align-self: start`. Flex column, `justify-content: flex-end`, padding `var(--space-5)` right and bottom.
  - Sticky only when the viewport is tall enough: `@media (min-width: 64em) and (min-height: 42em)`. Below 42em tall the stage is a normal block that scrolls with the page.
- **Photo** (`.register-photo`): absolutely positioned at the top of the stage, full stage width (to the screen edge), height `--register-photo-h` (section 8: 280px at 800 tall, 380 at 900). Picture `reception` (the swan desk; not used anywhere else on the site), focus `22% 72%` so the lit swan desk sits in the lower left. A gradient overlay (`.register-photo::after`): `linear-gradient(to bottom, transparent 35%, var(--color-espresso) 100%)`, so the photo melts into the stage. **No text ever sits on the photo**; the heading starts below its bottom edge, on solid espresso.
- **Stage content** (bottom aligned, max width `--signin-w` 26rem):
  | Part | Spec |
  |---|---|
  | h1 | "Register interest." Signika 500, `--text-2xl` (64px at 1440), cream, `line-height: var(--leading-tight)` |
  | Lead | `r.intro.body`. Figtree `--text-base`, `--color-text-muted-inverse` (6.50), margin-top `--space-2`, max width `--measure-lead` |
  | Membership card | margin-top `--space-5`. Section 4 |
- **Panel** (`.register-panel`): columns 7 to 12, max width 40rem, margin-block `var(--space-6)`. Background `--color-cream-raised`, 1px `--color-tier-edge`, `--radius-md`, `--shadow-tier` (warm, existing). Padding `var(--space-6)` (64px) at desktop. The form sits inside it.
- **Background texture** (`.register::before`): the swan pattern on the cream, behind the panel only (columns 6 to 12, full section height), as a mask so it takes espresso: `background: var(--color-espresso); -webkit-mask: url("../img/swan-pattern.svg") 0 0 / 200px 240px repeat; mask: same; opacity: 0.5` (the SVG is 8% alpha, so this is espresso at 4%: a texture you notice only on a second look). `pointer-events: none`, static, never animated, `z-index` below the panel.
- Fit: the stage at 800 tall is photo 280 + h1 70 + lead 52 + gap 40 + card about 250 + padding 40 = 732 against 728 available; the photo height token absorbs this (section 8). At 1280 x 720 the photo is 200px and everything still fits; under 42em tall the stage stops being sticky.

### 2.2 Tablet 48em to 64em

Stacked as the phone (2.3), with a 14rem photo band, the card at max width 30rem, the panel at max width 40rem, left aligned with the container. Name fields side by side.

### 2.3 Phone 375 x 667

```
 header 64
╭─────────────────────────────┐      photo band, bleeds LEFT, 10rem, right corners radiused
│ reception                    │
└─────────────────────────────┘
 Register interest.                   h1 36px, cream on espresso
 No payment now. We'll write
 before the doors open.
 ╭───────────────────────────╮
 │ YOUR MEMBERSHIP           │        card, section 4
 │ Tier 2              £89   │
 │ ...                       │
 │ [Tier 1][Tier 2][Tier 3]  │
 ╰───────────────────────────╯
 ╭───────────────────────────╮  ← cream panel rises 40px over the espresso
 │ ── Your name               │
 │ [First name             ]  │
 │ [Last name              ]  │
 │ ...                        │
```

- The stage is a full-width espresso block (no sticky): padding-top `--space-4`, padding-bottom `calc(var(--space-6) + var(--panel-overlap))`.
- Photo band: 10rem tall, `.frame--left` (bleeds off the left edge, `--radius-md` on the right corners; the mirror of sign-in, whose band bleeds right), same gradient melt at its bottom 40%, focus `18% 78%`.
- h1 `--text-2xl` (36px), margin-top `--space-4`; lead; card margin-top `--space-4`.
- Panel: `margin-top: calc(var(--panel-overlap) * -1)` so it sits over the bottom of the espresso (layered), full container width, padding `var(--space-4)` (24px; inner width 287px at 375). Swan pattern texture behind it on the cream below the stage.
- First screen at 375 x 667: header 64 + 24 + 160 + 24 + 36 + 8 + 52 + 24 + card top (eyebrow, name, price) about 110 = 502, so heading, lead and the plan name and price are on the first screen. No horizontal scroll.
- `scroll-padding-top: calc(var(--header-h) + var(--space-4))` on the page so a focused field is never under the header.

---

## 3. Fields (inside the panel)

### 3.1 Groups

- Legends lose the prescription look: Signika 400, `--text-lg` (not `--text-xl`), espresso, preceded by a 24px caramel hairline (`::before`, 1px, `--color-line`, decoration only, the same motif as the sign-in caption). `display: flex; align-items: center; gap: var(--space-3)`.
- Space between groups `--space-5` phone, `--space-6` desktop (was `--space-6` everywhere with bigger legends). Inside a group, fields `gap: var(--space-4)`.
- No dividers between groups, no numbers, no "Step 1".

### 3.2 The field: a filled well with the label inside

Applies to every text-like input in the panel (name, email, mobile, password, the three DOB parts). Checkboxes are section 3.4.

| State | Spec |
|---|---|
| Rest | `min-height: var(--control-h-label)` (60px). Background `--color-cream` (a shade deeper than the panel, so it reads as a well). No side or top border; `border-bottom: 1px solid var(--color-control-line)` (3.54 on cream); radius `var(--radius-sm) var(--radius-sm) 0 0`. Input text Figtree 16px espresso, padding `1.5rem var(--space-3) 0.375rem` |
| Label | Stays a real `<label>`, always visible, positioned **inside** the well at the top left: `position: absolute; top: 0.5rem; left: var(--space-3); font-size: var(--text-sm); font-weight: 500; color: var(--color-text-muted)` (5.32 on cream), `pointer-events: none`. It never moves or shrinks (no floating-label animation, no `:placeholder-shown` tricks, autofill-safe). `.field` gets `position: relative`; the label is the first child, so it lands inside the input box |
| Placeholder | Only DOB has one (DD, MM, YYYY): `--color-text-muted`, on the text line under the label |
| Hover (fine pointer) | bottom border `--color-espresso` 1px. Instant |
| Focus | bottom edge 2px espresso (`box-shadow: inset 0 -2px 0 var(--color-espresso)`), label turns espresso. **Instant**, no transition (box-shadow is not a property we animate). This replaces the outline for these inputs (`outline: none` on `:focus-visible` inside `.register-panel .field`); the 2px espresso edge is 10.95 on cream, so it passes as the focus indicator |
| Valid | the existing "Looks right" feedback line with the check (unchanged) |
| Error | bottom edge 2px `--color-danger` (8.07 on cream), label `--color-danger`, feedback line in danger as today. Shows on leaving the field, as today |
| Show toggle | inside the well, right, vertically centred on the input line (`top: 0.75rem; bottom: 0`), `--text-sm` 500 espresso, underline offset 0.25em. Unchanged behaviour |

- Feedback line: unchanged markup and min-height (no layout shift), margin-top `--space-1`.
- Name pair: two columns from 48em (as now), stacked on phone.
- DOB: three wells (Day, Month, Year) with the labels inside, grid `1fr 1fr 1.6fr`, gap `--space-3`, max width 22rem. One shared feedback line under the group (as now).
- Password: the checklist becomes a wrapping row from 48em (`display: flex; flex-wrap: wrap; column-gap: var(--space-4)`), still the three items with their circles; stacked on phone. The strength bar stays 4 segments, 2px, under the well, `--color-hairline` empty and espresso filled.

### 3.3 Non-field error
At the top of the panel, `.form-error` as now, margin-bottom `--space-4`.

### 3.4 Consents ("Before you register"): choosing, not ticking

Each of the three `.check` labels becomes a choice row:
- `display: flex; gap: var(--space-3); padding: var(--space-3) var(--space-4); min-height: var(--tile-min-h)` (72px); background `--color-cream`; 1px `--color-hairline` border; `--radius-md`; `align-items: center`.
- The box: 1.5rem, 1px `--color-control-line` (3.54), `--radius-sm` minus 2px (as now). Checked: espresso fill, cream check; the row's border becomes `--color-espresso` 1px plus `box-shadow: inset 0 0 0 1px var(--color-espresso)` (2px total, the light version of the journey's chosen tile). Instant.
- Hover (fine pointer): border `--color-control-line`. No scale (a full-width row should not scale).
- Focus: the existing 2px espresso ring on the row via `.check:has(input:focus-visible)`, offset 3px.
- Error (men-only, privacy): row border `--color-danger` 2px; the feedback line under the row as now.
- Gap between rows `--space-3`. Links inside the text stay underlined espresso.

### 3.5 Submit

- `.btn.btn-primary.btn-block` (espresso, cream label, 10.95), full panel width at every size, `--control-h` 52px, margin-top `--space-6`. Label `{{ site_settings.wording }}`, working text "One moment" (unchanged).
- Under it, the sign-in foot pattern: 1px `--color-hairline` divider, margin-block `--space-5`, then "Already registered? Sign in": "Already registered?" muted, "Sign in" `.btn-quiet` espresso. Same target.

---

## 4. Your membership (the premium element)

The plan is the choice that matters, so it gets the one crafted object on the page: a membership card on the stage, family of the Gold panel and the Memberships key cards.

**Markup:** move the existing panel and picker into one `.plan-card` inside the stage. The radios keep `name="plan"` and `form="register-form"`; the `data-*` on each radio stay.

| Part | Spec |
|---|---|
| Card | Background `--color-espresso` with the swan pattern (`url("../img/swan-pattern.svg")`, gold at 8%, as `.gold-panel`); 1px `--color-tier-edge-gold`; `--radius-md`; padding `--space-4` phone, `--space-5` desktop. On espresso, not espresso-raised, so the chip borders keep 3.09 |
| Eyebrow | "Your membership", Figtree `--text-sm` 500, uppercase, `--tracking-label`, `--color-gold` (6.17). The only eyebrow on the page |
| Name row | `display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-3)`, margin-top `--space-3`. Left: plan name, Signika 400 `--text-xl`, cream. Right: price "£89", Signika 400 `--text-xl`, `--color-gold`, tabular numbers, with "a month" under it in `--text-sm` muted inverse, right aligned |
| Character | Under the name, Figtree `--text-sm`, muted inverse (6.50) |
| VAT | "ex VAT (£107 inc VAT)", `--text-sm` muted inverse, margin-top `--space-2` |
| Picker | margin-top `--space-4`, after a 1px `--color-hairline-inverse` line and `--space-4`. Chips in a wrapping row (`gap: var(--space-2)`), each the `.chip` shape: `min-height: var(--chip-h)` (44px), `--radius-md`, 1px `--color-control-line`, cream `--text-sm` 500. Chosen: gold fill, espresso text (6.17), gold border. Hover (fine pointer): border cream. Focus: `.chip:has(input:focus-visible)` 2px gold ring, offset 3px. The visually hidden legend stays |
| Journey note | Only when `from_journey`. Inside the card, last row, after a 1px `--color-hairline-inverse` line and `--space-3`: the swan glyph (`.mark-glyph`, 1rem wide, gold, `aria-hidden`) then "Your answers come with you." Figtree `--text-sm` cream. Flex, `gap: var(--space-2)`, `align-items: center` |
| Empty state | If no plan is checked: the name row, character and VAT are hidden and one line shows instead: "Choose one. You can change it later." (`--text-base`, cream). The picker always shows |

- **No JS:** the template renders the checked plan's name, character, price and VAT server-side (`{% with chosen=form.plan.value|default:selected_plan %}` and pick the matching card), so the card is correct before `register.js` runs. `register.js` then updates it on change as today, and toggles the empty state instead of hiding the whole card.
- Optional, recommended (one context variable, no new endpoint): pass `suggested_plan` (the slug the view already computes as `suggested`) to the template. When the chosen chip equals it, the eyebrow reads "Suggested by your answers" instead of "Your membership".

---

## 5. Motion (7B)

| What | How | Timing |
|---|---|---|
| Stage text (h1, lead, card) | One hero group, `data-reveal="hero"`: opacity 0 to 1, rise `--rise` (8px phone, 12px desktop), on load | `--duration-hero` 0.8s, `--ease-soft` |
| Photo | `data-reveal="hero-image"`: scale 0.98 to 1 and opacity 0 to 1, no travel | `--duration-reveal` 1s, delay `--delay-reveal` 0.1s |
| Panel | One group, `data-reveal` (taller than the screen, so it reveals as soon as any of it is in view): opacity and rise `--rise`. Fields inside never animate on their own | 1s, delay 0.1s |
| Plan change | The chip changes instantly. The card's text block (name row, character, VAT, eyebrow) fades from opacity 0 to 1 once (JS removes and re-adds `.is-changing`, or uses the Web Animations API on opacity only). Prices never count | `--duration-ack` 240ms, `--ease-soft` |
| Submit button | Hover scale 1.01, press 0.99, fine pointer only for hover | `--duration-press` 0.25s |
| Fields, consents, chips | No transitions on state. Focus, error, check and chosen states are instant | 0 |
| Feedback lines | Appear instantly, `aria-live="polite"` as now | 0 |
| Pattern, gradient melt | Static | |

No pointer glow, no parallax on the photo, no sticky-scroll effects beyond the stage staying put.

**Reduced motion / no JS:** everything visible on load, no rise, no scale, no plan fade (the tokens already go to 0; the plan fade must check `matchMedia('(prefers-reduced-motion: reduce)')` or use a token duration).

---

## 6. Check your email and Confirm your email

`register_sent.html` and `verify_confirm.html` move to the same split, so the person stays in the same room after pressing the button.

- Desktop: the stage (photo, melt) on the left as on register, but its bottom content is only a caption: 24px gold hairline + `site_settings.opening_text` (for example "Opening January 2027"), Figtree `--text-sm`, muted inverse; omit the caption if the setting is empty. The section is `min-height: calc(100svh - var(--header-h))`, and the panel (same raised cream panel, max width 32rem) is **vertically centred** in columns 7 to 12.
- Phone: the photo band and caption on espresso, then the panel overlapping by `--panel-overlap`.
- Panel content, check your email (copy unchanged): h1 `r.sent.heading` ("Check your email.") Signika 500 `--text-2xl`; lead with the address in bold; then the two quiet actions as a column (`gap: var(--space-3)`, each `.btn-quiet`, 44px tap height): "Send it again", "Wrong address? Change it"; the status line under them. The resend status is `role="status"` as now.
- Panel content, confirm your email (copy unchanged): h1 "Confirm your email.", lead, the full-width espresso button "Confirm my email" (working text "Confirming").
- After confirming, the person lands on Account with the message "Your email is confirmed." (unchanged; the Account page is out of scope).
- Motion: stage text hero group, photo hero-image, panel one group, as section 5.

---

## 7. Copy changes (British English, calm, no exclamation marks)

| Where | Now | Round 4 |
|---|---|---|
| h1 | `{{ site_settings.wording }}` | `{{ site_settings.wording }}.` (full stop, like the other page headings; the button keeps the plain wording) |
| Card eyebrow | none | "Your membership" (or "Suggested by your answers", section 4) |
| Card empty state | card hidden | "Choose one. You can change it later." |
| Photo alt | n/a | "The reception desk with the gold swan, and the corridor beyond" |
| Sent / confirm caption | none | `site_settings.opening_text` |

Everything else (legends, labels, hints, errors, consents, button, links, `r.intro.body`, `r.journey_note.body`) stays word for word.

---

## 8. Tokens

No new colours. Uses `--color-cream`, `--color-cream-raised`, `--color-espresso`, `--color-gold`, `--color-line`, `--color-text-muted`, `--color-text-muted-inverse`, `--color-control-line`, `--color-hairline`, `--color-hairline-inverse`, `--color-danger`, `--color-tier-edge`, `--color-tier-edge-gold`, `--shadow-tier`, `--radius-sm`, `--radius-md`, `--control-h`, `--tile-min-h`, `--chip-h`, `--signin-w`, `--measure-lead`, `--bleed`, `--tracking-label`, `--space-*`, `--ease-soft`, `--duration-hero`, `--duration-reveal`, `--delay-reveal`, `--duration-press`, `--duration-ack`, `--rise`.

Proposed, round 4 (add to `tokens.css` and BRAND section 8, marked derived):

```css
--control-h-label: 3.75rem;        /* proposed, round 4: a field with its label inside (60px) */
--color-field-well: var(--color-cream); /* proposed, round 4: alias, no new colour. The filled field on the raised cream panel; espresso text 10.95, muted label 5.32 */
--register-photo-h: clamp(10rem, 100svh - var(--header-h) - 28rem, 24rem); /* proposed, round 4: the stage photo, desktop (280px at 800 tall) */
--panel-overlap: var(--space-5);    /* proposed, round 4: how far the cream panel rises over the espresso stage, below 64em */
```

The swan pattern on cream uses the existing SVG as a mask on `--color-espresso` at opacity 0.5 (4% effective): decoration only, no token needed.

---

## 9. Acceptance checks

Shots in `.private/shots/register-r4/` at 375 x 667, 1024 x 768, 1280 x 720 and 1440 x 800: empty form, form with errors (submit empty), from the journey (note shows), no plan chosen, check your email, confirm your email.

1. 1440: espresso stage on the left bleeding off the screen edge, the reception photo melting into espresso with no text on it, h1, lead and the membership card fully visible; the raised cream panel on the right over a just-visible swan texture. Scrolling the form keeps the stage in place; the footer pushes it away at the end.
2. 1280 x 720: the stage still fits (photo shrinks); under 42em tall it scrolls normally and nothing is cut off.
3. 375: photo band bleeding left, h1, lead, plan name and price on the first screen; the panel visibly overlaps the espresso; no horizontal scroll; DOB fits on one row.
4. Fields: label inside every well and always visible, also after browser autofill; focus shows the 2px espresso edge instantly; errors show the danger edge, danger label and message, and the layout does not jump.
5. Plan: changing a chip updates name, character, price and VAT, with one 240ms fade; with JS off the card shows the preselected plan; `?plan=tier-3` preselects tier 3; with no plan the empty line shows.
6. Journey: arriving from a finished journey shows "Your answers come with you." inside the card; arriving directly does not.
7. Consents are 72px rows; clicking anywhere on the row toggles the box; the men-only and privacy errors mark the row.
8. Submit still posts to `/register/`, the honeypot is still off screen, the working state still shows "One moment", the email "already registered" check still offers sign-in.
9. Keyboard: tab order is chips, first name, last name, email, mobile, password, Show, day, month, year, the three consents, submit, Sign in; every control shows a visible focus indicator.
10. Contrast: muted label on the well 5.32; espresso on the well 10.95; field edge 3.54; gold eyebrow and price on espresso 6.17; chip border 3.09; chosen chip 6.17; danger 8.07. Nothing sits on `--color-espresso-raised`.
11. Reduced motion: everything visible at once, no rise, scale or plan fade.
12. No em dashes, no exclamation marks, no new colours, nothing animates except `transform` and `opacity`. Lighthouse accessibility 100, CLS under 0.1 (the photo box is sized before it loads).
