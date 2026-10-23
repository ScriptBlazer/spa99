# Spa 99: Phase 1 design brief

> **Superseded in part (22 Oct 2026):** layout and motion for the marketing pages (sections 1 "What makes it feel expensive", 5.1 to 5.6 and 9) are replaced by `docs/design/IMMERSIVE.md`. Everything else here stands: palette, type, tokens, components, copy, the journey, forms, account, Gold application and Control.

For the frontend agent. Read with `docs/BRAND.md` (which wins on any conflict) and the feature docs. This is direction, layout, copy tone and tokens, not code. Every value below maps to a token in `common/static/common/css/tokens.css`; never write raw colours, sizes or timings in components.

Copy in this brief is sample copy. All of it lives in `content` and is edited in Control. Samples never use exclamation marks or em dashes.

---

## 1. Direction

**The idea: an evening visit.** The site moves the way a visit does: you come in from the dark street (espresso), step into warm light (cream), then settle back into the quiet (espresso). Each screen holds one thing: one image, one statement, or one choice.

**What makes it feel expensive**
- Space. Sections are tall, margins wide, and nothing sits closer to anything else than it must.
- Scale contrast. Very large Signika headlines next to small, calm Figtree text. Little in between.
- One image at a time, large, sharp-cornered, never in a carousel, never with text or badges laid on top.
- Gold used as light, not paint: the swan, a thin rule, a primary button on dark. Never a gold background behind text on cream.
- Slow, soft entrances (BRAND section 7) and instant, precise responses to touch.
- Plain words. Short sentences. The reader is a guest.

**What we avoid**
- Spa clichés: candles, stones, pebbles, orchids, petals in water, bamboo, women, towels on faces. No people's faces at all in Phase 1.
- Template tells: three equal feature cards, an uppercase label above every heading, numbered section labels, icon rows, gradients, glows, glass blur on content, stock smiles, carousels, scroll cues, counters.
- Hype: "elevate", "unwind in style", "exclusive offer", urgency, exclamation marks.
- Fake function: no button that does nothing. Not-ready things say so, beautifully.

**Design read.** Premium hospitality site for men in North London, editorial and quiet, plain CSS + one IntersectionObserver script, brand palette and fonts fixed by `BRAND.md`. Dials: variance 6, motion 3, density 2 on the site; density 6 in Control.

---

## 2. Layout system

### Breakpoints
Design at three widths, build mobile first with two `min-width` queries (CSS variables cannot be used in media queries, so these are constants):

| Name | Query | Design canvas |
|---|---|---|
| Phone | base | 375px |
| Tablet | `min-width: 48em` (768px) | 768px |
| Desktop | `min-width: 64em` (1024px) | 1440px |

At 1024px and above the desktop nav appears. Above 1440px the layout stops growing (`--container-max`) and margins widen.

### Grid
- Phone: 4 columns. Tablet: 8. Desktop: 12.
- Column gap: `--gutter` (20px phone, grows to 32px).
- Outer margin: `--page-margin` (20px phone, about 34px tablet, 64px at 1440).
- Content max width: `--container-max` (1440px including margins).
- Reading width: `--measure` (34rem, about 60 characters). Body copy never runs wider.
- Headline width: `--measure-display` (14ch). Display headlines break by meaning, not by container.
- Use CSS Grid with named areas per section. Every multi-column section states its phone layout explicitly (always one column).

### Spacing rhythm
The space scale (`--space-1` to `--space-8`) is unchanged. Usage:

| Gap | Token |
|---|---|
| Label to field, icon to text | `--space-2` |
| Between fields in a group, between tiles | `--space-3` |
| Heading to body | `--space-4` |
| Body to actions | `--space-5` |
| Between groups inside a section | `--space-6` |
| Section top and bottom padding | `--section-y` (6rem phone, 10rem desktop) |
| Hero top padding (below header) | `--space-6` phone, `--space-7` desktop (never more) |

### Dark and light
- **Espresso** (`--color-bg-inverse`): arrival and night. The hero of every marketing page, the header, the journey questions, the whole Gold world, the footer.
- **Cream** (`--color-bg`): the default reading surface. Most content sections, forms, the journey result, the account page.
- **Alternation rule.** A page is a few "chapters", not stripes. Consecutive sections of the same colour join into one chapter. A page changes colour at most four times including the footer. The change is a hard edge or a full-bleed photograph; never a gradient.
- **Raised surfaces** (derived): `--color-cream-raised` for fields, tiles and cards on cream; `--color-espresso-raised` for tiles and panels on espresso.
- **Swan pattern** (SVG, repeating S-swans) is the only texture. Gold strokes at 8% opacity on espresso, used at most once per page (journey entry, Gold panel, Book). Never behind body text on cream.

### Shape
One documented rule, applied everywhere:
- Controls (buttons, fields, segmented control, checkboxes): `--radius-sm` (6px).
- Surfaces (tiles, cards, panels, modal): `--radius-md` (12px).
- Photography: square corners (0). Always.
- No pills, no circles except the radio dot and the badge lockup.

### Header height and stacking
- `--header-h`: 64px phone, 72px desktop.
- Layers (z-index): header 10, sticky journey action bar 20, mobile menu 30, modal 40, messages 50. Nothing else gets a z-index.

---

## 3. Type

### Fonts
- **Signika** (variable, self-hosted, weights 300-600 subset): headlines, statements, prices and big numbers. Sentence case always, never uppercase. Tracking `--tracking-display`.
- **Figtree** (variable, self-hosted, 400-600): everything else. Tracking `--tracking-body`.
- `font-display: swap`, preload the two woff2 files, `size-adjust` fallbacks to avoid layout shift.
- Numbers: `font-variant-numeric: tabular-nums` on prices, tables and stats.

### Scale

| Role | Token | 375px | 1440px | Font / weight | Leading |
|---|---|---|---|---|---|
| Display (hero headline) | `--text-hero` | 48px | 128px | Signika 500 | `--leading-display` 1.0 |
| Heading 1 (page/section statement) | `--text-2xl` | 36px | 64px | Signika 500 | `--leading-tight` 1.1 |
| Heading 2 (group, card title, journey screen title) | `--text-xl` | 24px | 36px | Signika 500 | `--leading-tight` 1.1 |
| Lead (intro line under a heading) | `--text-lg` | 20px | 20px | Figtree 400 | `--leading-snug` 1.4 |
| Body | `--text-base` | 16px | 17px* | Figtree 400 | `--leading-body` 1.6 |
| Small (helper, feedback, legal, meta) | `--text-sm` | 14px | 14px | Figtree 400 | 1.5 |
| Label (rare, see below) | `--text-sm` | 14px | 14px | Figtree 600, uppercase, `--tracking-label` | 1.2 |
| Price (plan) | `--text-2xl` | 36px | 64px | Signika 400, tabular | 1.0 |
| Price (small, other tiers) | `--text-xl` | 24px | 36px | Signika 400, tabular | 1.0 |
| Stat number (Control) | `--text-xl` | 24px | 36px | Signika 500, tabular | 1.0 |

\* Body can stay at 16px everywhere; 17px at desktop is optional via `--text-body` if it reads better in the browser.

**Rules**
- Signika 500 on espresso can look heavy: use 400 for cream-on-espresso display text above 64px.
- Headlines end with a full stop when they are a statement ("Beyond Luxury.", "The spa."). Questions end with a question mark.
- Uppercase labels: at most one per three sections, and never above a heading as decoration. Allowed for: form group names in Control, the plan "Recommended" marker, table headers.
- Body text is never Gold or Caramel on cream (BRAND contrast table). Secondary text uses `--color-text-muted` (5.32 on cream) or `--color-text-muted-inverse` (6.50 on espresso).
- Links inside text: underlined, 1px, offset 0.25em, same colour as text. Hover thickens to 2px. No colour change.

---

## 4. Components

Every component exists once in `common` and is reused by the site, the journey and Control.

### 4.1 Header and navigation
**Desktop (≥1024px)**: sticky, solid `--color-bg-inverse`, height `--header-h`, 1px `--color-hairline-inverse` bottom line.
- Left: horizontal lockup (gold swan + "SPA 99" in cream), SVG, 28px tall. Links home.
- Centre-right, one line: The spa · Memberships · Gold Card · Book · Visit us. Figtree 500 `--text-base`, `--space-5` apart. Current page: 1px cream underline 6px below text.
- Right: "Sign in" (quiet) or "Account" when signed in; primary button (gold, small, 40px tall) "Find your membership". Hidden on journey pages.
- Not animated. No shrink on scroll, no colour change.

**Phone and tablet (<1024px)**: same bar, 64px. Left: swan + "SPA 99". Right: the word "Menu" (Figtree 500, 44px tap area), no hamburger icon.
- Menu opens a full-screen espresso sheet instantly (no animation, per BRAND 7). Top: same bar with "Close". Links stacked in Signika `--text-xl`, `--space-4` apart. Then a primary button "Find your membership" full width, then "Sign in" quiet. Bottom: address and email in `--text-sm` muted inverse.
- Focus is trapped in the sheet; Escape and "Close" return focus to "Menu". Body scroll locked.

**Journey and Gold application**: reduced header: lockup left (links home), "Leave" quiet link right. Everything is saved, so leaving is safe; no confirm dialog.

### 4.2 Buttons
Height 52px (`--control-h`), padding 0 `--space-5`, `--radius-sm`, Figtree 500 `--text-base`, sentence case, label on one line (max three words for primary). Full width on phone when it is the main action of a screen; auto width otherwise.

| Variant | On cream | On espresso | Use |
|---|---|---|---|
| Primary | Espresso fill, cream text (10.95) | Gold fill, espresso text (6.17) | One per screen. The next step. |
| Secondary | 1px espresso border, espresso text, transparent | 1px cream border, cream text | An alternative next step. |
| Quiet | Text only, underlined, espresso | Text only, underlined, cream | Back, skip, change, sign in. |
| Danger | `--color-danger` fill, cream text (8.07) | Not used on espresso | Delete account (in the modal only). |

- Hover (only `@media (hover: hover) and (pointer: fine)`): scale 1.01. Press: scale 0.99. `--duration-press`, `--ease-soft`. Quiet buttons do not scale.
- Focus: 2px outline, offset 3px. Espresso outline on cream, gold outline on espresso (`--color-focus` / `--color-focus-inverse`).
- Working: on click the button disables at once, its label becomes the working label from content ("One moment", "Sending", "Saving") and `aria-busy="true"`. No spinner. Width is locked so nothing jumps.
- Disabled: 40% opacity. Avoid disabled buttons where possible; explain instead.
- Trailing arrow: only on the journey "Continue" and on "Find your membership". Phosphor Light `arrow-right`, 20px, from an SVG sprite. No other icons in buttons.

### 4.3 Choice tiles
The heart of "choosing, not filling in". Real `<input type="radio">` or `<input type="checkbox">` inside a `<label>`, visually hidden input, the label is the tile.

- Min height 64px (`--tile-min-h`), padding `--space-4`, `--radius-md`.
- Content: label Figtree 500 `--text-base`; optional second line `--text-sm` muted ("5 to 9am").
- On espresso: `--color-espresso-raised` fill, 1px `--color-hairline-inverse` border, cream text.
- On cream: `--color-cream-raised` fill, 1px `--color-control-line` border, espresso text.
- **Selected** (instant, no transition, BRAND 7):
  - On espresso: 2px gold border (drawn with inset box-shadow so the layout does not move), gold marker top-right.
  - On cream: 2px espresso border, espresso marker. (Gold is not used on cream: 1.78 fails non-text contrast.)
  - Marker: single choice = 18px ring with filled dot; multi choice = 18px rounded square with a check. Unselected tiles show the empty marker, so single and multi are distinguishable before tapping.
- Hover: scale 1.01, press 0.99 (BRAND 7). Focus: 2px focus outline around the tile.
- **Image tiles** (facilities): image 4:5 on top (square corners inside the rounded tile, clipped), label under it. Selected adds the border and marker over the image's top-right corner on a small espresso disc for contrast.
- Grid: phone 2 columns for short labels, 1 column for labels with a second line; tablet 2-3; desktop 4. Equal heights per row.
- A fieldset with a `<legend>` (the question) wraps every group. Multi groups say "Choose any that fit" in the helper line.

### 4.4 Segmented control
For ordered single choices (how often, size ranges, yes/no, tier picker).
- One joined bar, 52px tall, `--radius-sm` outer corners, 1px `--color-control-line` (cream) or `--color-hairline-inverse` (espresso) dividers.
- Selected segment: fills espresso with cream text (on cream) or gold with espresso text (on espresso). Instant.
- Up to 4 segments in one row on phone if every label fits 10 characters; otherwise it wraps to a 2×2 joined block (still one control). Labels are kept short in content ("Now and then", "Weekly", "2-3 a week", "Most days").
- Built as a radio group: arrow keys move, Space selects.

### 4.5 Text field with live feedback
- Label above (Figtree 500 `--text-sm`), never placeholder-as-label. Optional "(optional)" in muted text after the label.
- Field 52px tall (`--control-h`), `--radius-sm`, padding 0 `--space-3`, `--text-base` (16px minimum so iOS does not zoom).
- On cream: `--color-cream-raised` fill, 1px `--color-control-line` border (3.54).
- On espresso: transparent fill, 1px `--color-control-line` border (3.09), cream text. (Never on espresso-raised: 2.67.)
- Focus: border becomes 2px `--color-text` (or cream on espresso) via inset shadow, plus the focus outline.
- Feedback line under the field, `--text-sm`, 20px min height reserved so nothing jumps, `aria-live="polite"`:

| State | When | Looks |
|---|---|---|
| Hint | Before typing | Muted text ("We'll send a link to confirm it.") |
| Checking | Debounced server check running (email) | Muted "Checking" |
| Good | Rule met while typing | Small check (Phosphor Light) + muted text ("Looks right"). Border unchanged. |
| Needs attention | Only after the field loses focus, or on submit | `--color-danger` text with a small warning icon, border 2px danger. Wording calm: "That date makes you under 18. Spa 99 is for 18 and over." |
| Already registered | Email exists | Neutral, not an error: "You already have an account. Sign in" (link) |

- **Password**: show/hide toggle inside the field (quiet text "Show"/"Hide", 44px target). Under it a checklist that ticks live: "At least 10 characters", "Not a common password", "Not your name or email". Unmet items: empty ring, muted. Met: check, espresso. A 4-segment strength line (2px tall, segments fill espresso) under the checklist, with a word ("Fair", "Strong"). No red until submit.
- **Date of birth**: three short numeric fields (Day, Month, Year) in one row, `inputmode="numeric"`, auto-advance after 2/2/4 digits, one shared feedback line. No date picker.
- **Mobile**: `type="tel"`, UK hint "07…", normalised on blur.

### 4.6 Checkbox (agreements)
24px box, `--radius-sm` minus 2px, 1px control-line border; checked = espresso fill with cream check. Label text to the right in `--text-base`, links inside underlined. Whole row is the tap target (min 44px).

### 4.7 Progress indicator (journey)
- A 2px line across the full width of the journey content area, directly under the reduced header. Track: `--color-hairline-inverse`. Fill: gold, grown with `transform: scaleX()` from the left, `--duration-base`, `--ease-soft`.
- Beside the screen title, the screen's own name only ("Your time"). Never "Step 2 of 5" and never numbers.
- `role="progressbar"` with `aria-valuetext="Your time, part 1 of 4"` for screen readers only.

### 4.8 Plan row (memberships)
Plans are shown as an editorial "menu" of full-width rows, not three cards.
- Row layout desktop (12 col): name and character (cols 1-4: "Tier 2" in `--text-2xl`, "Any time" in `--text-lg` muted), price (cols 5-7: "£399" price token, "a month, ex VAT" small muted, "£478.80 inc VAT" small muted), what's included (cols 8-10: 3-4 short lines), action (cols 11-12, aligned bottom).
- Phone: one column, same order, action full width.
- Tier rows on cream are separated by `--space-6` and a single 1px `--color-hairline` above each row (not below).
- The featured tier (Tier 2, set in Control) is an espresso block on the cream page, `--radius-md`, padding `--space-6`, gold primary action, and a "Recommended" label (uppercase label style, gold on espresso). The only gold on the page apart from the swan.
- Single visit sits below as a smaller row (Signika `--text-xl` name and price).
- All values come from `plans`. If a plan is hidden in Control, its row disappears; no gaps.

### 4.9 Gold panel
Used on the journey result (High potential) and as the Gold teaser.
- Espresso fill, `--radius-md`, swan pattern at 8% gold behind, 1px gold rule along the top edge inset by `--space-5`.
- Small gold swan mark (32px), heading Signika `--text-xl` cream, one or two lines of body cream, primary gold button.
- Never more than one Gold panel on a screen.

### 4.10 Coming soon block
For Book and account placeholders. Must look finished.
- **Large (Book page)**: centred column on espresso with the swan pattern, swan mark 48px gold, heading `--text-2xl` cream, one sentence muted inverse, the opening month in Signika `--text-xl` gold ("January 2027"), one real action (Register interest, or Account if signed in).
- **Small (account)**: a cream-raised panel, `--radius-md`, 1px hairline. Title Signika `--text-xl` ("Visits"), one muted line ("Opens January 2027"). No buttons, no zero counters, no greyed fake data.

### 4.11 Footer
Espresso, padding `--section-y` top, `--space-6` bottom.
- Desktop 12 col: left (cols 1-5) the swan + "Beyond Luxury" lockup (gold) and one line "A private spa for men. Part of BML Group."; middle (cols 7-9) site links; right (cols 10-12) "99 Vale Road, London N4 1PR", "hello@spa99.uk", opening hours summary from data.
- Bottom line (`--text-sm`, muted inverse): "Men only. 18 and over." · Privacy · Terms · © 2026 Spa 99. Not animated.
- Phone: one column in the same order, lockup first.

### 4.12 Messages
Django messages and HTMX responses use one component.
- Inline banner at the top of the main content (below the header), full container width, `--color-cream-raised` on cream pages / `--color-espresso-raised` on espresso, `--radius-md`, a 2px left rule: espresso (info, success) or danger (error).
- Text `--text-base`, one sentence. Optional single action link. Close button ("Dismiss", quiet).
- `role="status"` (or `role="alert"` for errors). Enters with opacity only, `--duration-base`. Does not auto-dismiss.
- Sample: "Your email is confirmed. Welcome to Spa 99." / "We couldn't save that. Please try again."

### 4.13 Modal
One shared modal (`common/js/modal.js`).
- `<dialog>`, max width 30rem, cream fill, `--radius-md`, padding `--space-5`, `--shadow-raised`, backdrop `--color-overlay`.
- Phone: bottom sheet, full width, top corners `--radius-md`, safe-area padding.
- Heading Signika `--text-xl`, one paragraph, actions right-aligned (desktop) or stacked full width (phone), primary/danger last.
- Enter: opacity 0 → 1 and rise 8px, `--duration-base`, `--ease-soft`. Exit: instant (BRAND 7: no exit animations).
- Focus moves to the heading; Escape closes; focus returns to the trigger.

---

## 5. Pages

Image numbers refer to the contact sheet (section 9). "New: N#" refers to the new renders list.

### 5.1 Home
| # | Section | Surface | Content |
|---|---|---|---|
| 1 | Hero | Espresso | Desktop: 7/5 split. Left: display headline, lead, actions. Right: image **08** (travertine water wall), portrait, full height of the hero, square corners, flush to the right edge of the viewport. Phone: headline, lead and actions fill the first screen (`min-height: 100dvh` minus header), image 08 full-bleed 4:5 directly below. |
| 2 | Statement | Cream | One sentence in `--text-2xl`, left aligned at cols 2-9, then one short paragraph at `--measure`. No image. |
| 3 | Three scenes | Cream (same chapter) | Image **14** full-bleed 16:9 with a caption line under it; then two images offset (desktop: New **N2** cols 1-7, image **04** cols 9-12 starting `--space-7` lower). Captions under each image, never on it. Phone: three images stacked full-bleed, 4:5. Quiet link "See the spa". |
| 4 | Find your membership | Espresso, swan pattern | Heading, one line, then the real first journey question ("When would you come?" tiles). Tapping a tile saves the answer and opens the journey on screen 1 with it selected. Below: primary "Find your membership". |
| 5 | Memberships, briefly | Cream | Heading and a compact three-row list (name, one-line character, price ex VAT with inc VAT under it), single visit as one quiet line, link "Compare memberships". Not the full plan rows. |
| 6 | Gold Card | Espresso | Desktop 5/7: image New **N6** (Gold card on walnut) left, text right. Phone: image then text. |
| 7 | Opening | Espresso (same chapter, continues into the footer) | "January 2027." in `--text-2xl` gold, address line, primary "Register interest". |

Copy samples
- Hero headline: "Beyond Luxury."
- Hero lead: "A private spa for men in North London. Opening January 2027."
- Hero actions: primary "Find your membership", quiet "See the spa".
- Statement: "Heat, cold, quiet, and time that is yours." Paragraph: "Two saunas, a cold plunge, a gym and a room to do nothing in. Come early, come late, stay as long as you like."
- Scene captions: "Heat, slowly." / "Then cold." / "Then nothing at all."
- Journey entry heading: "Which membership suits you?" Line: "A few taps. Under two minutes."
- Memberships heading: "Three memberships. One single visit."
- Gold heading: "The Gold Card." Body: "For people in property. Free, by application." Link: "About the Gold Card".
- Opening: "January 2027." / "99 Vale Road, London N4."

### 5.2 The spa
| # | Section | Surface | Content |
|---|---|---|---|
| 1 | Intro | Espresso | Heading and lead left (cols 1-6), image **09** (frosted door, gold swan) right, square, cols 7-12. Phone: text then image 1:1 full-bleed. |
| 2 | The rooms | Cream | Desktop: a sticky index on the left (cols 1-3) listing the facilities in Figtree `--text-base`; the current one is espresso with a 1px underline, others muted. Right (cols 5-12): each facility is one image (3:2) with its name in `--text-xl` and one line under. The index tracks scroll via the shared IntersectionObserver (state only, not animation) and each name is an anchor link. Phone: no index; each facility stacked: image 4:5 full-bleed, name, line, `--space-7` between. |
| 3 | How a visit works | Espresso | Three steps across (desktop), stacked (phone). Each: one word in `--text-2xl` and one line. Image **20** (lockers) full-bleed below the steps at 21:9 desktop, 4:5 phone. Then hours from data in `--text-sm`. |
| 4 | Next | Cream | Heading, primary "Find your membership", secondary "See memberships". |

Facilities in visiting order, image and line:

| Facility | Image | Line |
|---|---|---|
| Dry sauna | **14** | "Cedar and dry heat. Stay as long as it feels right." |
| Wet sauna | New **N1** | "Soft steam and warm stone benches." |
| Cold plunge | New **N2** | "Still, cold water. A minute is enough." |
| Showers | New **N3** (detail **06** optional inset) | "Rain showers, good towels, everything you need." |
| Relaxing zone | **04** | "Loungers, low light and nothing to do." |
| Massage room | New **N4** | "A quiet room for a massage, by appointment." |
| Gym | **12** | "Free weights and machines, never crowded." |
| Kitchenette | New **N5** | "Tea, coffee and somewhere to sit after." |

Copy samples
- Intro heading: "The spa." Lead: "Eight spaces, one quiet visit."
- Steps: "Book." "Choose a time that suits you." / "Arrive." "A towel, robe and slippers are waiting." / "Stay." "As long as you like, until closing."
- Do not promise face entry or wristbands (Phase 4).

### 5.3 Memberships
| # | Section | Surface | Content |
|---|---|---|---|
| 1 | Intro | Cream | Heading and lead. No image; the rows are the content. Hairline under. |
| 2 | Plan rows | Cream | Tier 1, Tier 2 (featured espresso block), Tier 3, then Single visit (section 4.8). Each row's action: "Register interest" (primary on the featured row, secondary on others, quiet on single visit). It opens sign-up with that plan selected. |
| 3 | Not sure | Cream-raised band, `--radius-md`, inside the container | "Not sure? Find yours." with a primary "Find your membership". |
| 4 | Compare everything | Cream | `<details>` "Compare everything" closed by default. Desktop: table (plans as columns, features as rows, featured column tinted cream-raised). Phone: segmented control (Tier 1 / Tier 2 / Tier 3 / Single) switching one column of feature rows. All from `plans`. |
| 5 | Gold line | Cream | One line: "There is also the Gold Card, for people in property." Link "About the Gold Card". |
| 6 | VAT note | Cream | `--text-sm` muted: "Prices exclude VAT at 20%. Prices including VAT are shown under each price." (rate from settings) |

Copy samples
- Heading: "Memberships." Lead: "Choose when you come and how often. Change tier whenever you need to." (Confirm tier-change wording with Moishe before launch.)
- Characters: Tier 1 "Daytime", Tier 2 "Any time", Tier 3 "Unlimited", Single visit "One visit".
- Included lines (Tier 2): "8 visits a month" / "Evenings and late nights" / "Book up to 3 days ahead" / "2 bookings at a time".
- Featured label: "Recommended".

### 5.4 Gold Card
The only page that stays espresso from top to bottom. It should feel like a private room.

| # | Section | Content |
|---|---|---|
| 1 | Hero | Desktop 6/6: text left, image New **N6** right (4:5). Phone: text, then image. Primary "Apply". |
| 2 | Who it's for | Heading, then the property roles as a two-column typographic list (desktop), one column (phone), Signika `--text-xl`, no bullets, `--space-4` apart. Then a muted line that anyone may apply. |
| 3 | What it holds | Perks from the Gold plan as grouped lines in two groups ("Your visits": unlimited, any time, 7 days ahead, 2 guests a month, first call from the waitlist; "Beyond the spa": each merch release, Leil Shishi when offered, BML members' events). One 1px gold rule above each group, not between lines. |
| 4 | How it works | Three steps (stagger allowed): "Apply." "A few minutes, mostly taps." / "We read it." "Each application is read personally." / "We'll be in touch." "If it's a fit, we'll invite you." |
| 5 | Apply | Gold panel (4.9) with "Apply for the Gold Card". |

Copy samples
- Hero heading: "The Gold Card." Lead: "For people who own, build and manage property. Free, by application."
- Who: "Owners and investors", "Developers", "Block, estate and portfolio managers", "People at property and management firms", "Agents and brokers", "Property lawyers". Muted line: "Not in property? You're still welcome to apply."
- Never name Barry on the site. Never show a potential rating to the applicant.

### 5.5 Book (placeholder)
Espresso, one screen tall, the large coming soon block (4.10).
- Heading: "Booking opens soon."
- Line: "When the doors open, you'll choose your time here."
- Gold line: "January 2027"
- Action: primary "Register interest" (or "Your account" when signed in). Quiet: "See the spa".
- Below, on cream, a short "How booking will work" with three lines taken from plan data ("Tier 1 books a day ahead. Tier 2, three days. Tier 3, a week."). Plain text, no fake calendar, no fake slots.

### 5.6 Visit us
| # | Section | Surface | Content |
|---|---|---|---|
| 1 | Address | Cream | Heading, then the address as a statement in Signika `--text-2xl` on two lines. Email as a large quiet link. Hours from data in a two-column definition list (`--text-base`). |
| 2 | Map | Cream | Static map image, full container width, 16:9 desktop, 4:5 phone, square corners. Rendered in brand colours (cream land, espresso-muted roads, a gold swan pin). Generated once from OpenStreetMap data with attribution under it in `--text-sm`. Link "Open in Maps" (plain `https://maps.apple.com/?q=...` and Google fallback, opened by the visitor; nothing loaded from them). |
| 3 | Arrival | Espresso | Image **10** (frosted door, white swan), 21:9 desktop, 4:5 phone. One line: "Ring once. We'll be expecting you." (Confirm arrival details.) |

Copy samples
- Heading: "Visit us."
- Address: "99 Vale Road" / "London N4 1PR"
- Getting here: leave a slot in content for nearest stations and parking; do not invent them.

### 5.7 Sign up (register interest), Sign in, Check your email
See section 7.

### 5.8 Account
Cream throughout. Container max 48rem for readability, left aligned on desktop.

| # | Section | Content |
|---|---|---|
| 0 | Verify banner (if unverified) | Message component: "Please confirm your email. We sent a link to daniel@example.com." Action "Send it again". |
| 1 | Greeting | Signika `--text-2xl`: "Good evening, Daniel." (morning before 12, afternoon before 6, evening otherwise, Europe/London). |
| 2 | Your interest | Cream-raised panel: "You're registered for Tier 2." with price line, quiet "Change" which reveals a segmented tier picker and "Save". |
| 3 | Coming soon | Three small coming soon panels in a row (desktop), stacked (phone): Visits, Bookings, Membership. Each "Opens January 2027". |
| 4 | Your account ID | The 8-character ID in Figtree 600 `--text-xl`, letter-spaced 0.08em, tabular, with a "Copy" quiet button (feedback: label becomes "Copied" for 2s). Line: "Share it with a member who wants to bring you as a guest." |
| 5 | Details | Name, email, mobile as read rows with "Edit" per row (inline edit in place via HTMX, same field component). "Change password" opens its own small form. |
| 6 | Privacy | Two quiet actions: "Download my data", "Delete my account" (opens modal: heading "Delete your account?", body "This removes your details and your interest. It can't be undone.", actions "Keep my account" (secondary) and "Delete" (danger)). |
| 7 | Sign out | Quiet link at the end. |

### 5.9 Error pages
Espresso, one screen tall, swan mark 48px gold, heading `--text-2xl`, one line, primary "Back to home". Reduced header. No illustrations, no jokes.
- 404: "This page isn't here." / "It may have moved. Everything else is where you left it."
- 500: "Something went wrong on our side." / "Please try again in a moment."
- 403: "This page is private." / "Sign in, or head back to the home page."
- 429: "That was a lot at once." / "Please wait a minute and try again."
- Privacy and Terms: cream, long-form text at `--measure`, Figtree body, headings `--text-xl`. Not animated.

---

## 6. The journey

### Shell
- URLs: one per screen (`/journey/your-time/`, `/journey/what-draws-you/`, `/journey/company/`, `/journey/about-you/`, `/journey/result/`). Screens load with HTMX and `hx-push-url`, so Back, refresh and closing all land on the right screen with answers shown (answers rendered server-side from the saved session).
- Question screens are espresso. The result is cream (arrival into light).
- Reduced header with "Leave". Progress line under it (4.7).
- Content column: phone full width; desktop cols 3-10 (about 760px), left aligned in that column.
- Screen title Signika `--text-xl` cream, one muted lead line. Each question is a fieldset: legend in Figtree 500 `--text-lg` cream, helper `--text-sm` muted inverse, then the control. `--space-6` between questions.
- **Action bar**: sticky at the bottom on phone (espresso with a hairline top, safe-area padding, z 20), inline after the last question on desktop. Left: quiet "Back" (not on screen 1). Right: primary gold. The primary reads "Continue" when anything on the screen is answered and "Skip this part" when nothing is. Skips are saved.
- Each question also has a quiet "Prefer not to say" link at the end of its helper line where it makes sense (industry, how heard). Tapping it marks the question skipped and dims the tiles slightly (still tappable).
- Saving: each tap is saved in the background. No saved indicator by default; if a save fails, retry silently up to 3 times, then show a message: "We couldn't save that just now. Your answers are safe on this page." The journey keeps working.
- Resume: returning on the same device opens the screen he was on. A quiet "Start again" link sits under the action bar on screen 1 when answers exist.
- Transition between screens: the new screen's content group fades and rises (BRAND 7, section group, 1s). The page scrolls to top instantly, focus moves to the screen title, the progress line grows.
- Conditional questions (screen 4) reveal below their parent as a group, same fade and rise, and the page does not jump the reader past them.

### Screen 1: Your time
- Title: "Your time." Lead: "When you'd come, and how often."
- Q1 "When would you come?" helper "Choose any that fit." Multi tiles, 2×2 (phone and desktop):
  - "Early morning" / "5 to 9am"
  - "Daytime" / "9am to 6pm"
  - "Evening" / "6 to 10pm"
  - "Late night" / "10pm to 3am"
- Q2 "How often?" Segmented, ascending: "Now and then" · "Weekly" · "2-3 a week" · "Most days".

### Screen 2: What draws you
- Title: "What draws you." Lead: "The parts of the spa you'd use."
- Q "What would you use?" helper "Choose as many as you like." Image tiles (4.3), 2 columns phone, 4 desktop, same images as The spa page:
  - Dry sauna (14) · Wet sauna (N1) · Cold plunge (N2) · Showers (N3) · Relaxing zone (04) · Gym (12) · Massage room (N4) · Kitchenette (N5)
- Image tiles load small (480px wide AVIF) and lazily.

### Screen 3: Company
- Title: "Company." Lead: "Some come alone. Some bring a friend."
- Q "Do you usually come alone?" Single tiles, one column, large (min height 80px):
  - "Alone" / "Time to myself."
  - "Sometimes with someone" / "A friend now and then."
  - "Often with someone" / "Most visits."

### Screen 4: About you
- Title: "About you." Lead: "Optional, and only to suggest the right fit."
- Q1 "What do you do?" Single tiles, 2 columns phone, 4 desktop: Property · Finance · Business owner · Law · Medical · Tech · Creative · Other. "Prefer not to say" link.
  - If **Other**: a short text field reveals ("In a few words", optional). Typed answer 1.
  - If **Property**: "Your link to property" reveals. Single tiles, 1 column phone, 2 desktop: Owner or investor · Developer · Manager (block, estate, portfolio) · At a property or management firm · Agent or broker · Property lawyer.
  - If **Law**: "Is it property law?" segmented Yes · No.
- Q2 "How did you hear about us?" Small single tiles in a wrapping row (height 44px, `--text-sm`): Instagram · A friend · BML · Walking past · Other. If Other: short text field ("Where?", optional). Typed answer 2.
- Primary reads "See my membership".

### Result
Cream. Desktop: 7/5 split when there is a Gold panel (result left, panel right, panel top aligned with the tier name); single column (cols 2-9) when not. Phone: one column.

Order:
1. Small line, muted: "Your membership"
2. Tier name in `--text-hero`: "Tier 2."
3. Price line: "£399 a month, ex VAT (£478.80 inc VAT)". Character: "Any time, 8 visits a month."
4. "Why it suits you", three lines in `--text-lg`, each preceded by a small caramel swan glyph (decoration only, `aria-hidden`), built from his answers and plan data:
   - "Evenings suit you, and Tier 2 is open until 3am."
   - "Two to three visits a week fits 8 a month."
   - "You can book up to 3 days ahead."
5. Primary "Register interest in Tier 2" (label from content, tier name inserted). Quiet "Change my answers" (back to screen 1).
6. **Gold, by potential:**
   - **High**: Gold panel (4.9). Heading "The Gold Card." Body "With your property background, you may be invited to hold the Gold Card. It's free, by application, and your answers come with you." Button "Apply for the Gold Card". Desktop: right column. Phone: directly after the primary action, before other tiers.
   - **Medium**: one line directly under the primary action, `--text-base`: "In property? You may be eligible for the Gold Card." followed by an inline link "Apply".
   - **Low / none**: nothing.
7. "Or choose another" heading `--text-xl`, then the other plans as compact rows (name, character, price, quiet "Choose Tier 1"). Choosing one opens sign-up with that tier (chosen differs from suggested; both are saved).

Reveal on arrival: the tier name, price and reasons are one group (hero timing, 0.8s); the Gold panel is its own group (section timing, 0.1s after it is in view). No count-up numbers, no confetti.

### Register interest (sign-up)
Cream. One calm screen, grouped.

- **Desktop**: 5/7 split. Left (sticky): "Register interest" `--text-2xl`, the chosen plan as a cream-raised panel (name, price, character) with a segmented tier picker under it ("Tier 1 · Tier 2 · Tier 3 · Single"), and one muted line: "No payment now. We'll write before the doors open." Right: the form.
- **Phone**: heading, plan panel with picker, then the form.
- Groups (each a fieldset with a `--text-xl` legend in Signika, `--space-6` apart):
  1. "Your name": First name, Last name (side by side from tablet).
  2. "How we reach you": Email (live format + already-registered check), Mobile.
  3. "Your password": Password with checklist and strength.
  4. "Date of birth": Day / Month / Year. Helper "Spa 99 is for 18 and over."
  5. "Before you register": checkbox "I understand Spa 99 is a men-only spa." (link "Our policy"); checkbox "Send me occasional news from Spa 99." (unticked); line "Read how we use your details in our privacy notice." (link).
- Submit: primary "Register interest", full width on phone. Under it: "Already registered? Sign in".
- If he came from the journey, a muted line under the plan panel: "Your answers come with you."
- Errors keep everything typed; the first problem field receives focus on submit and the page scrolls to it.
- **Check your email** (cream): heading "Check your email." Line "We've sent a link to daniel@example.com. It works for 24 hours." Quiet "Send it again" (becomes "Sent" with the time) and "Wrong address? Change it".
- **Sign in**: cream, one column at `--measure`. Heading "Welcome back." Email, password, primary "Sign in", quiet "Forgotten your password?", line "New here? Register interest".
- **Password reset** follows the same pattern ("Choose a new password.").

---

## 7. Gold application

Espresso throughout (the Gold world). Same shell as the journey: reduced header, progress line, one URL per screen, everything saved as it happens, Back and refresh safe. Journey answers are reused and never asked twice.

### Screen 1: Your property
- Title: "Your property." Lead: "A few taps about your work in property."
- "Your link to property" single tiles (pre-selected from the journey if given): Owner or investor · Developer · Manager · At a property or management firm · Agent or broker · Property lawyer · None of these.
- "How large?" segmented: "1-9" · "10-49" · "50-199" · "200+", helper "Units or properties". A quiet toggle under it: "Easier to give a portfolio value?" swaps the segments to value ranges (ranges from Control).
- "Where?" single tiles 2×2: North London · Rest of London · Rest of UK · Abroad.
- "Do you work with BML?" segmented: Yes · Not yet · No.
- "Company and role" text field (optional).
- "Referred by" text field (optional), helper "If someone suggested you apply."

### Screen 2: Your visits
- If the journey was done: an espresso-raised summary panel: "From your earlier answers" then four short lines ("Evenings and late nights", "2-3 a week", "Dry sauna, cold plunge, gym", "Sometimes with someone"), quiet "Change" opens the controls inline. Continue is primary.
- If not: the short version, same controls as journey screens 1-3 on one screen (times, how often, facilities as text tiles without images, company).

### Screen 3: You
- Title: "You." Lead: "So we can reply."
- First name, Last name, Email, Mobile (field on espresso, 4.5). No password, no date of birth (no account).
- "Anything else?" optional textarea (4 rows, grows), helper "Optional."
- Privacy line and marketing opt-in checkbox as in sign-up.
- Primary "Send application".

### Sent
- Swan mark, heading "Thank you." Line "Your application is with us. We'll be in touch personally." Reference in `--text-sm` muted ("Reference G-4K7P"). Quiet "Back to home".
- No rating, no timeline promise.

---

## 8. Spa 99 Control

**Feel**: the back office of the same building. Calm, dense, fast, branded in its frame, neutral in its data. Light theme.

### Frame
- **Sidebar** (desktop ≥1024px): 248px, espresso, full height. Top: swan + "Control" (Signika, cream). Sections as a list, Figtree 500 `--text-sm`, 40px rows, muted inverse; current item cream with a 2px gold bar on its left. Bottom: signed-in name, role, "Sign out".
- **Phone/tablet**: espresso top bar with "Menu" opening the same list as a full-height sheet.
- **Content**: `--color-cream-raised` page background (lighter than the site, easier for long sessions), padding `--space-5`, max width none for tables, 48rem for forms.
- **Page header**: title Signika `--text-xl`, optional one-line description muted, actions right (primary espresso).

### Density
- Control uses `--control-h-compact` (40px) for buttons and fields, `--space-3` gaps. Tap targets stay at least 40px.
- Type: Figtree `--text-sm` for tables and forms, `--text-base` for detail views. Signika only for page titles and stat numbers.

### Tables
- Full width, no outer box. Header row: label style (uppercase, `--tracking-label`, muted), sticky under the page header.
- Rows 44px, 1px `--color-hairline` between rows (acceptable here: this is data), hover row cream (`--color-bg`).
- Numbers right aligned, tabular. Dates "22 Oct 2026, 18:40" (Europe/London).
- Row click opens the detail (whole row is a link, with a real link on the first cell for keyboard).
- Empty state: a sentence and the action, e.g. "No Gold applications yet. They'll appear here as they arrive."
- Loading (HTMX): rows keep their height; the table dims to 60% opacity while loading. No spinners.

### Filters
- A single filter bar above the table: search field, segmented controls for short sets (e.g. Potential: All · High · Medium · Low), compact selects for longer sets, date range as two date fields with presets ("7 days", "30 days", "All time").
- Filters are in the URL (shareable, back-safe). "Clear" quiet link appears only when a filter is set.

### Status and potential
Text first, colour second, never colour alone.

| Value | Look |
|---|---|
| Potential High | Gold fill, espresso text (6.17), `--radius-sm` |
| Potential Medium | 1px `--color-chart-2` border, espresso text |
| Potential Low | Muted text, no box |
| Status New | Espresso fill, cream text |
| Status Contacted | 1px espresso border |
| Status Approved | Gold fill, espresso text |
| Status Declined | Muted text, no box |
| Email not sent | `--color-danger` text with warning icon and "Resend" |

### Detail views
- Two columns on desktop: main content (sections as on Barry's email: Personal, Property profile, What the site collected) and a right rail (status picker, notes, history).
- History: a quiet list "22 Oct 2026, 18:40 · Moishe changed price from £399 to £419" with before/after.
- Editing: same field components; Save is primary, "Saved" appears in the page header for 3s. Unsaved changes warn on leave (modal).
- Reordering (questions, options, plans): drag handle plus "Move up / Move down" buttons for keyboard. Hidden items show muted with "Hidden" and stay listed.
- Journey preview: opens the real journey in a phone-sized frame (375px) beside the editor.

### Dashboard and charts
- Top row: 4 stat tiles (cream fill on cream-raised, `--radius-md`, padding `--space-4`): label `--text-sm` muted, number Signika `--text-xl`, comparison line `--text-sm` ("+12 this week"). Tiles: Registrations, Journeys started, Completed, Gold applications.
- Charts: inline SVG rendered server-side (no chart library, no third parties). Direct labels on bars instead of legends where possible.
- Palette on light backgrounds (each at least 3:1 against `--color-cream-raised` for graphics):
  - `--color-chart-1` espresso (11.7): the main series.
  - `--color-chart-2` caramel deep `#A0703F` (4.07): the second series.
  - `--color-chart-3` muted `#745F4F` (5.69): the third series, always with a pattern (diagonal hatch) to separate it from chart-1.
  - Gold and Caramel never used for chart marks on light backgrounds (1.90 and 2.94).
  - Gridlines `--color-hairline`. Axis text `--text-sm` muted.
- Funnel: horizontal bars, one per step, chart-1, with count and drop-off % at the end of each bar. Demand by time: 4 vertical bars. Facilities: horizontal bars sorted by interest. Tier mix: grouped bars, suggested (chart-1) vs chosen (chart-2). Trend: line chart, chart-1 registrations, chart-2 Gold applications, dots on the last point only.
- Every chart has a "View as table" toggle (accessibility and export).
- Charts don't animate.

### Sign-in to Control
Espresso screen, swan mark, "Spa 99 Control" in Signika `--text-xl`, email, password, primary gold "Sign in".

---

## 9. Motion

All of BRAND section 7 applies. One shared script (`common/static/common/js/reveal.js` or inside `app.js`) adds `data-reveal` groups; CSS does the rest. Groups use `--duration-reveal`, `--delay-reveal`, `--rise` (8px phone, 12px from 48em). Hero uses `--duration-hero`. Reduced motion: every group visible immediately.

| Page | Revealed as one group | Stagger (0.1s, desktop and tablet only) | Not animated |
|---|---|---|---|
| Home | Hero text + actions (hero timing); hero image 08 as a standalone image (scale 0.98 → 1, hero timing). Statement. Journey entry (heading + tiles + button). Memberships list. Gold teaser text; Gold image standalone. Opening. | The three scenes (heat, cold, rest is a progression): 14, then N2, then 04. | Header, swan pattern, footer. |
| The spa | Intro text; intro image standalone. Each facility (image + name + line) as its own group as it scrolls in. Steps block. Next. | The three steps (Book, Arrive, Stay). | Sticky index (state change only, no motion). |
| Memberships | Intro. Each plan row its own group. Not-sure band. Comparison table appears with its `<details>` (no animation). | None (rows are a list, not a progression). | VAT note, table contents. |
| Gold Card | Hero text; hero image standalone. Who list as one group. Each perk group. Apply panel. | The three "How it works" steps. | Pattern. |
| Book | The coming soon block as one group (hero timing). | None. | |
| Visit us | Address block. Map standalone image. Arrival image standalone. | None. | |
| Account | Nothing on load except messages (opacity only). | None. | Everything else (it's a tool). |
| Journey | Each screen's content as one group on arrival. Conditional follow-up questions as their own group when they appear. Result: tier + reasons (hero timing), Gold panel (own group). | None. Tiles never stagger. | Header, progress line (it grows, but is not a reveal), action bar, selected states (instant). |
| Gold application | As journey. | None. | As journey. |
| Control | Nothing. Modal and messages only. | None. | Everything. |
| Error pages | The block as one group (hero timing). | None. | |

Interaction feedback (BRAND 7): buttons and tiles scale 1.01 hover / 0.99 press with `--duration-press`. Plan rows are not clickable as a whole (the button is), so they don't scale. Image tiles already scale, so their image does not zoom on hover.

---

## 10. Images

### Treatment (all renders)
- One grade for everything: warm white balance, blacks lifted to a deep brown (never pure black), greens desaturated by about 30% so plants sit inside the palette, no vignette, no added grain.
- Remove or crop out any candle, pebble, flower or stray prop.
- Export AVIF and WebP, widths 480 / 960 / 1600 / 2400, `srcset` + `sizes`, `width`/`height` set, lazy except the hero (preloaded, `fetchpriority="high"`). Phone crops via `<picture>` art direction where noted.
- `alt` text describes the room plainly ("Dry sauna with cedar benches and a glass door etched with the swan"). Decorative crops get empty alt.

### Keep

| # | What | Use | Crop and notes |
|---|---|---|---|
| 04 | Relaxing zone, loungers, travertine, swan on wall | Home scene 3, The spa, journey tile | Wide 2.36:1. Desktop 3:2 centred on loungers and swan; phone 4:5 on the swan wall. |
| 06 | Soap bottles on travertine basin | Optional inset with Showers | Crop out the olive branch. Small use only. |
| 08 | Backlit travertine water wall with carved swan | Home hero | Portrait. Crop the right edge to remove the lounger with the candle (keep the wall and plant on the left). Phone 4:5 centred on the swan. |
| 09 | Frosted glass door, gold swan | The spa intro | Square. Phone 1:1, desktop 1:1. |
| 10 | Frosted glass door, white swan | Visit us arrival | Desktop 21:9 band centred on the swan; phone 4:5. Near-duplicate of 09; never on the same page. |
| 12 | Dark gym, swan wall panel | Gym (The spa, journey tile) | 4:3 source. 3:2 desktop, 4:5 phone on the swan panel. |
| 14 | Wood sauna, swan on glass, steam | Dry sauna, Home scene 1, journey tile | Sauna heater stones are functional and stay; no decorative stones added. 16:9 home, 3:2 spa, 4:5 phone. |
| 20 | Wood lockers with swans, bench | How a visit works | 21:9 desktop band, 4:5 phone. |
| 13 | Swan slippers on travertine | Optional detail for "Arrive" | Small, 1:1. |
| 11 | Espresso tote bags | Optional, Gold "each merch release" | Small, 1:1. Not in Phase 1 unless Moishe wants merch shown. |

### Don't use

| # | Why |
|---|---|
| 01 | Instagram mockup, not a photo. |
| 07 | Towel with stones (cliché, excluded by BRAND). |
| 02, 03 | Towel and robe hanging: fine as objects but close to cliché, and 03 is low resolution (768px wide). Hold in reserve. |
| 05 | Bottles: merch, not Phase 1. |
| 15 | Fluorescent-lit gym and yoga mat: wrong light, off-brand. |
| 16 | Yellow wall, plastic chair: off-palette. |
| 17 | Reception: pebble planter, moss wall, office chair, pink cast. Off-brand. |
| 18 | Pool with mosaic swan: Spa 99 has a cold plunge, not a pool. It would mislead. |
| 19 | Duplicate of 11. |
| 21-26 | Logo renders. Use the vector mark instead. |

### New renders (6)
Generate with fal.ai at 3:2 landscape (2400×1600) and 4:5 portrait (1600×2000) for each. Same look as 04, 08, 12, 14. Every prompt ends with the shared style block and negative prompt.

**Shared style block** (append to each):
> Photorealistic interior photograph for a men's luxury spa in London called Spa 99. Warm walnut wood, honed travertine stone, brushed brass details, low warm indirect light from concealed LED strips, quiet and calm, generous negative space, shot on a 35mm lens at eye level, soft shadows, warm white balance, muted earthy palette of cream, caramel, espresso brown and soft gold. The Spa 99 mark appears once, subtly: a minimal gold line-drawn swan formed from the letter S with two small 9-shaped curls as feathers, engraved or inlaid, never as a sign with text other than "SPA 99".

**Negative prompt** (use for all):
> people, faces, hands, women, candles, pebbles, stacked stones, flowers, petals, orchids, bamboo, incense, fruit bowls, text, watermark, logos other than the swan, neon, cool blue light, fluorescent light, clutter, fisheye, oversaturated greens.

| ID | Subject | Prompt (before the shared style block) |
|---|---|---|
| N1 | Wet sauna (steam room) | "A small steam room clad entirely in honed travertine, a long travertine bench along the back wall, soft steam drifting at knee height, warm light grazing the stone from a concealed strip under the bench, a clear glass door on the right edge of frame, the gold swan inlaid in the wall above the bench." |
| N2 | Cold plunge | "A single rectangular cold plunge pool for one or two people, sunk into a dark travertine floor, three steps leading in, perfectly still clear water with a faint cool tint against the warm room, a brushed brass grab rail, a folded white towel on a walnut stool beside it, the gold swan engraved small on the stone edge." |
| N3 | Showers | "A row of three open rain showers separated by walnut slatted screens, travertine walls and floor, brushed brass ceiling rain heads and simple brass controls, water falling from one shower only, a gold swan etched on a frosted glass panel at the end of the row." |
| N4 | Massage room | "A calm massage room with one walnut massage table dressed in a plain cream cover, a neatly folded towel at its foot, a travertine wall with a low warm light slot, a single walnut stool and a small brass hook with a cream robe, the gold swan carved small on the wall behind the table." |
| N5 | Kitchenette | "A small private kitchenette and lounge corner with a walnut counter and a travertine top, a brushed brass tap, two plain cream ceramic cups and a ceramic teapot on the counter, two low leather armchairs in espresso brown facing each other, warm pendant light, the gold swan inlaid in the walnut panel above the counter." |
| N6 | Gold Card | "Close-up still life of a single metal membership card in brushed soft gold, with a minimal debossed swan line mark formed from the letter S and the small words SPA 99, lying at an angle on a dark walnut surface beside a folded espresso-brown leather wallet, one warm light from the side, shallow depth of field." (Square crop also needed, 2000×2000.) |

Also needed, not renders:
- Static brand map for Visit us (from OpenStreetMap, recoloured; attribution kept).
- Open Graph image (1200×630): image 08 cropped left, espresso panel right with the swan and "Beyond Luxury" lockup. Composed from vector, not generated.
- Swan pattern and all marks as SVG from the brand PDF/AI files.

---

## 11. Tokens

Starting set is `docs/BRAND.md` section 8; the additions below are marked there and in `tokens.css`. Nothing existing was changed or removed.

### Derived colours (with contrast)

| Token | Value | Checked against | Ratio | Use |
|---|---|---|---|---|
| `--color-cream-raised` | `#FBF9EC` | Espresso text | 11.71 | Fields, tiles, panels on cream; Control background |
| `--color-espresso-raised` | `#553729` | Cream / Gold / Caramel text | 9.45 / 5.32 / 3.44 | Tiles, panels, messages on espresso |
| `--color-text-muted` | `#745F4F` | Cream / Cream-raised | 5.32 / 5.69 | Secondary text on light |
| `--color-text-muted-inverse` | `#C5BBA5` | Espresso / Espresso-raised | 6.50 / 5.61 | Secondary text on dark |
| `--color-control-line` | `#8E7C6A` | Cream / Cream-raised / Espresso | 3.54 / 3.79 / 3.09 | Field and tile borders (non-text 3:1). Not on espresso-raised (2.67). |
| `--color-hairline` | espresso at 14% | n/a | decoration | Dividers on light |
| `--color-hairline-inverse` | cream at 14% | n/a | decoration | Dividers on dark |
| `--color-danger-inverse` | `#F4B09E` | Espresso | 6.81 | Error text on dark (journey, Gold application) |
| `--color-focus` / `--color-focus-inverse` | espresso / gold | Cream / Espresso | 10.95 / 6.17 | Focus outlines |
| `--color-chart-1` | espresso | Cream-raised | 11.71 | Control charts |
| `--color-chart-2` | `#A0703F` (caramel deep) | Cream-raised | 4.07 | Control charts |
| `--color-chart-3` | `#745F4F` | Cream-raised | 5.69 | Control charts, with hatch |
| `--color-pattern` | gold at 8% | n/a | decoration | Swan pattern on espresso |

Existing `--color-danger` `#8B1E1E`: 8.07 on cream, 8.63 on cream-raised. Not for text on espresso.

### Type, layout, shape, motion additions
`--leading-display`, `--leading-tight`, `--leading-snug`, `--leading-body`, `--tracking-label`, `--text-body`, `--measure`, `--measure-display`, `--container-max`, `--page-margin`, `--gutter`, `--section-y`, `--header-h`, `--control-h`, `--control-h-compact`, `--tile-min-h`, `--shadow-raised`, `--duration-hero` (800ms), `--duration-reveal` (1000ms), `--delay-reveal` (100ms), `--stagger` (100ms), `--duration-press` (250ms), `--rise` (8px, 12px from 48em).

`--duration-slow` and `--duration-base` stay for existing components; the BRAND 7 entrance timings use the new named tokens, which match the spec exactly.

---

## 12. Open points for Moishe
1. Home hero image: 08 (travertine water wall, warm and still) or a new wide entrance render.
2. Show merch (totes, bottles) anywhere in Phase 1, or hold it.
3. Visit us: arrival wording, nearest stations and parking need real details.
4. "Change tier whenever you need to": confirm it's true before it's written.
