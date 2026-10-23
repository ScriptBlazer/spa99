# Forms, round 4: Tailor your membership and the Gold application

Owner decisions: `docs/PROJECT.md`, the four rows dated 2026-10-23 about the journey and Gold. Motion mode 7B (restrained). Brand rules in `docs/BRAND.md` win. The flow, the data and the endpoints stay the same. No new steps.

Screenshots: the sandbox blocked localhost:8000, so nothing is in `.private/shots/forms-r4/` yet. The frontend agent takes the 375 and 1440 shots listed in section 6 after building.

Files: `common/static/common/css/journey.css`, `components.css` (tiles, segmented), `base.css` (focus), `common/static/common/js/journey.js`, `choices.js`, `gold-apply.js`, `content/seed.py`, `journey/seed.py`. Seeds only create rows, so copy changes need a data migration (or editing in Control) as well as the seed edit.

---

## 1. Step screens (Your time, What draws you, Company, About you, Gold screen 1)

### 1.1 Layout

**Phone (under 64em).** One column. The heading, then the lead, then the questions. The action bar stays sticky (as now).

**Desktop (64em and up): an editorial split.** The heading sits on the left and the choices on the right, so the big type gets room and the choices never sit under a 12-column-wide heading.
- `.screen` becomes a 12-column grid inside `.flow-container` (drop the 8-column `.flow-col` offset for question screens; the result keeps its own grid).
- `.screen-head`: columns 1 to 4, `position: sticky; top: calc(var(--header-h) + var(--space-6)); align-self: start`.
- `.screen-body` and `.action-bar`: columns 6 to 12.
- `.screen` padding-top: `var(--space-7)` at desktop, `var(--space-6)` on phone.

### 1.2 Type
| Element | Now | Round 4 |
|---|---|---|
| `.screen-title` (h1) | `--text-xl` | `--text-2xl` (36px on phone, 64px at 1440), `font-weight: 400` on dark, `max-width: var(--measure-display)`, `line-height: var(--leading-tight)` |
| `.screen-head .lead` | margin `--space-2` | margin-top `--space-4`, `max-width: 22rem`, colour `--s-muted` |
| Legend | `--text-lg` 500 | unchanged (Figtree `--text-lg` 500) |
| `.question-help` (the hint) | `--text-sm` muted | unchanged size, `margin-top: var(--space-1)`. This is where "Choose at least one." lives |
| Space between questions | `--space-6` | `--space-6` on phone, `--space-7` on desktop. The first question gets `margin-top: 0` on desktop, so it lines up with the heading |

### 1.3 Choice cards (`.tile`)
The current tile reads like a default form field. Make it quieter at rest and clearer once chosen.

| State | Spec |
|---|---|
| Rest | `background: var(--s-raised)` (espresso-raised); `border: 1px solid var(--color-hairline-inverse)`; `border-radius: var(--radius-md)`; `min-height: 4.5rem`; padding `var(--space-4)`. The label is Figtree 500 `--text-base` (`--text-lg` from 64em); the part in brackets is already split out as `.tile-sub` (for example "5 to 9am"). It goes on its own line in `--s-muted` `--text-sm`. |
| Mark | 1.25rem, centred vertically on the right (`top: 50%; translate: 0 -50%`), `border: 1px solid var(--s-muted)`. Square with a 4px radius for multi, round for single. |
| Hover (fine pointer) | Border becomes `var(--color-control-line)`. Keep the existing scale of 1.01. |
| Press | The existing scale of 0.99, `--duration-press`. |
| Chosen | `border-color: var(--color-gold)` plus `box-shadow: inset 0 0 0 1px var(--color-gold)` (2px of gold in total). Background `linear-gradient(var(--color-chosen-wash), var(--color-chosen-wash)), var(--s-raised)`. The mark fills gold with the espresso check (single: a gold dot). It changes **instantly**: only `transform` has a transition. Cream text on the washed surface is about 8.2:1. |
| Keyboard focus | Unchanged: `.tile:has(input:focus-visible)` 2px `--s-focus` (gold) ring, offset 3px. |

**Facility image tiles:** the same chosen ring goes on the whole tile (border plus inset, as above) and the mark stays as it is. Unchosen photos are never dimmed. Phone: 2 columns. Desktop: 4 columns, so the 8 facilities sit in 2 rows of 4 inside columns 6 to 12.

**Time tiles:** 2 columns on all widths (at 375 each tile is about 159px wide, so "Early morning" fits on one line).

**Segmented (How often?, How large?):** keep it, at `min-height: var(--control-h)`. The chosen segment is filled gold with espresso text (as now). The outer border becomes `1px solid var(--color-control-line)`, so the group reads as one control (3.09:1 on espresso).

### 1.4 Company (the screen Moishe wants lifted)
Three tall tiles with a quiet visual cue made from the swan glyph (the existing `.mark-glyph`, a CSS mask; no new artwork).
- Phone: stacked, each tile `min-height: 5.5rem`. The glyphs sit on the left (fixed 3rem column), then the label and sub.
- Desktop: 3 columns, each tile `min-height: var(--tile-tall-h)`. Glyphs at the top, label and sub at the bottom (`justify-content: space-between`, column direction).
- The label is Signika `--text-xl` 400, tracking `--tracking-display` (the word "Alone" carries it). The sub ("Time to myself.") is in `--s-muted` `--text-base`.
- Glyphs are chosen by option value, `aria-hidden`, width 1.25rem, gap `--space-1`:
  - `alone`: one gold swan.
  - `sometimes`: one gold swan and one in `--color-control-line`.
  - `often`: two gold swans.
  - Any other value added in Control gets no glyph, and the tile still works.
- Chosen state as in 1.3.

### 1.5 "At least one" and the inactive Continue
Applies to `time` (screen 1) and `facilities` (screen 2). `frequency` stays optional. Screens 3 and 4 keep "Skip this part".
- Data: give the question a minimum (backend: a `min_choices` field on `Question`, default 0, seeded 1 for `time` and `facilities`, editable in Control, sent in `/journey/state/`). The page reads `q.min_choices`. Do not hard-code the two keys. **Manager: this needs a decision-log row, because it overrides "Always skippable" for these two questions.**
- The hint (`.question-help`, id `hint-<key>`) reads **"Choose at least one."**
- While a required question on the screen has fewer than its minimum: the primary button reads **"Continue"** (never "Skip this part" on these screens) and carries `aria-disabled="true"` and `aria-describedby="hint-<key>"`. Use `aria-disabled`, **not** `disabled`, so the button stays focusable and the reason is announced.
- Inactive look: `background: transparent; border-color: var(--color-control-line); color: var(--s-muted)`, with no arrow icon. Muted-inverse on espresso is 6.50:1, so it is readable but clearly not ready. No opacity trick.
- Pressing or activating it while inactive does not navigate. Instead:
  - The hint gets `data-state="nudge"`: colour `--s-text`, weight 500. The colour changes instantly. No shake and no sideways movement.
  - A visually hidden `aria-live="polite"` node on the screen says "Choose at least one to continue."
  - If the question is off screen, scroll its legend into view (`block: 'center'`; `behavior: 'smooth'` unless reduced motion).
  - Focus stays on the button.
- Ticking a tile: the button switches to the gold primary with its arrow **instantly**, and `aria-disabled` and `aria-describedby` are removed. The nudge state clears. Unticking everything puts the inactive state back.
- Back is always available.

### 1.6 Progress
Keep the 2px line under the header (gold on espresso, `--s-hair` track). The fill transition becomes `transform var(--duration-slow) var(--ease-soft)` (700ms). The `aria-valuetext` stays as it is.

### 1.7 Motion (exact)
| What | How |
|---|---|
| New screen | The whole `.screen` is one group, `data-reveal="hero"`: opacity 0 to 1, rise `var(--rise)` (8px phone, 12px from 48em), `--duration-hero` 800ms, `--ease-soft`, no delay. No exit animation (the old screen is replaced). No stagger on tiles. |
| Choosing | Instant colour, border and mark. Press scale 0.99 over `--duration-press` (250ms). |
| Follow-up appears (Property follow-ups, "Other" text, Gold property questions) | Opacity 0 to 1 and rise `var(--rise)`, `--duration-slow` 700ms, `--ease-soft`, using `@starting-style` (CSS below). Hiding is instant. |
| Continue becomes active | Instant. |
| Progress fill | 700ms `--ease-soft`. |

```css
/* Follow-ups rise in only after the screen has settled (JS sets data-live on .screen-body two frames after render),
   so a screen that opens with a follow-up already visible does not animate twice. */
@media (prefers-reduced-motion: no-preference) {
  [data-live] .sub-question { transition: opacity var(--duration-slow) var(--ease-soft), transform var(--duration-slow) var(--ease-soft); }
  @starting-style { [data-live] .sub-question { opacity: 0; transform: translateY(var(--rise)); } }
}
```

**Reduced motion:** the tokens already go to 0. The `@starting-style` rule is inside `no-preference`. Everything appears at once, and the scroll-into-view uses `behavior: 'auto'`.

---

## 2. Result

### 2.1 The stray outline (exact CSS, `base.css`, straight after the `:focus-visible` rule)
Chrome treats the script's `h1.focus()` as `:focus-visible` on load and refresh (no pointer interaction yet), so `h1.result-tier[tabindex="-1"]` gets the 2px ring until the first click. `.screen-title` was already excluded; `.result-tier` was not.

```css
/* Elements focused by script (headings, sections) only to move the screen reader: never a visible ring.
   Controls keep their :focus-visible ring. */
[tabindex="-1"]:focus,
[tabindex="-1"]:focus-visible { outline: none; }
```
Keep `tabindex="-1"` and the `.focus({ preventScroll: true })` call exactly as they are. Then remove the now-redundant `.screen:focus, .screen-title:focus { outline: none; }` from `journey.css`.

### 2.2 "Start again"
- `.result-actions`: the primary "Register interest in Tier 1" first, then a quiet button **"Start again"** (`btn-quiet`, `min-height: 2.75rem`). On phone it sits on its own line under the full-width primary, left aligned.
- Behaviour: `POST /journey/restart/` (new session, old one kept), then question 1 with nothing ticked. This is the same code path as the existing `data-restart`. Use the `start_again` copy row and retire `change_answers`.

### 2.3 Reopening, and "See my last suggestion"
- **Arriving at bare `/journey/`** (header, Home tile, "Tailor your membership") with a **completed** session: open question 1 with the saved answers ticked. Never open the result.
- Arriving at bare `/journey/` with an unfinished session: resume where he was (unchanged, "Never lost").
- A refresh or Back on a specific screen URL, including the result URL, keeps that screen (unchanged).
- On question 1 only, when `state.session.completed` is true and he has not pressed Start again in this page: show a small link **"See my last suggestion"** directly under the lead (`margin-top: var(--space-4)`, `.small`, underlined text link, `min-height: 2.75rem`, `display: inline-flex; align-items: center`).
  - It is a real `<a href>` to the result URL. JS intercepts it and calls `go(resultStep)`. This recomputes from the current answers, which are the same unless he changed them.
  - On desktop it sits in the left (sticky) column under the lead.
- The existing quiet "Start again" at the foot of question 1 stays (it shows when answers exist).

---

## 3. Gold application, screen 1 "About you."

### 3.1 Order of questions
1. **What do you do?** (required, one tap). The options are the journey's `industry` options, read from `/journey/state/` (Property, Finance, Business owner, Law, Medical, Tech, Creative, Other), so Control edits apply to both flows. Tiles: 2 columns on phone, 4 on desktop, `min-height: 3.5rem`, no sub, single (round mark).
2. **Only when Property is chosen**, as `.sub-question` blocks directly under it:
   - **Your link to property** (required once shown): the six property links. **"None of these" is not shown here.**
   - **How large?** (optional, segmented): unchanged.
3. **Where?**: unchanged (everyone).
4. **Do you work with BML?**: unchanged (everyone).
5. **Company and role** (optional): unchanged.
6. **Referred by** (optional): unchanged.

### 3.2 Behaviour
- Prefill: a journey `industry` answer preselects the industry. A known property link (journey or signed-in prefill) preselects Property and the link.
- Saving the industry: keep it in the form (sessionStorage) **and** save it to the journey (`saveJourney('industry')`, the same pattern as the visit answers), so it is never asked twice.
- Switching away from Property hides the follow-ups instantly and keeps their values in sessionStorage (they come back if he switches back). On submit, a non-Property applicant sends `property_link: "none"` and no `size_range`, so the Gold rating keeps working (Low base, plus the BML, North London and referral points as before).
- **Backend dependency (manager):** `GoldApplication` has no industry field. Add `industry` (value and label), show "What you do" in Barry's email section 2 and in Control, and accept it in `POST /gold/apply/`.
- Error on Continue with no industry: focus the first industry tile and set the slot to **"Choose the one closest to what you do."** With Property chosen but no link: **"Choose your link to property."**
- Motion: the follow-ups use the section 1.7 follow-up reveal (700ms, rise `--rise`, `--ease-soft`, instant hide). On phone, after Property is tapped, scroll so the first follow-up's legend is in view if its top is below 75% of the viewport (`block: 'center'`, smooth unless reduced motion).
- Layout and tiles: as section 1 (desktop split, the same tile and chosen styles).

---

## 4. Copy (every changed string)

| Where | Key / place | Now | Round 4 |
|---|---|---|---|
| Journey, Your time | `Question time` help | Choose any that fit. | Choose at least one. |
| Journey, What draws you | `Question facilities` help | Choose as many as you like. | Choose at least one. |
| Journey, inactive Continue | live message (new, journey page copy `need_one`) | (none) | Choose at least one to continue. |
| Journey, screens 1 and 2 | primary button when nothing is chosen | Skip this part | Continue (inactive) |
| Journey, result | `change_answers` cta | Change my answers | (retired; use `start_again`: "Start again") |
| Journey, question 1 | new row `last_suggestion` cta | (none) | See my last suggestion |
| Gold, screen 1 | `screen_1` heading / body | Your property. / A few taps about your work in property. | About you. / A few taps, so we know you. |
| Gold, screen 1 | first question | (none) | What do you do? |
| Gold, screen 1 | required error, industry | Choose the one that fits, or "None of these". | Choose the one closest to what you do. |
| Gold, screen 1 | required error, property link | (as above) | Choose your link to property. |
| Gold, screen 2 | `screen_2` body | What you would use, so we know you. | What you would use at the spa. (avoids repeating "so we know you") |
| Gold, screen 3 | `screen_3` heading | You. | Your details. (avoids two "you" headings; body stays "So we can reply.") |

All British English, no exclamation marks. "Your link to property", "How large?", "Where?" and "Do you work with BML?" are unchanged.

## 5. Tokens (proposed, round 4; add to `tokens.css` and `docs/BRAND.md` section 8)
```css
--color-chosen-wash: var(--color-pattern);   /* proposed, round 4: alias, no new colour. Gold at 8% over a chosen tile; decoration only */
--tile-tall-h: 11rem;                        /* proposed, round 4: Company tiles from 64em */
```
Everything else uses existing tokens: `--text-2xl`, `--rise`, `--duration-hero`, `--duration-slow`, `--duration-press`, `--ease-soft`, `--color-control-line`, `--color-hairline-inverse`, `--s-muted`, `--radius-md`, `--space-*`.

## 6. Acceptance checks (375x812 and 1440x900; save to `.private/shots/forms-r4/`)
1. Your time at 375: the heading is about 36px, the time tiles are 2 columns with the sub on its own line, and the sticky bar shows an inactive "Continue" (outlined, muted, no arrow). At 1440: the heading is sticky on the left (columns 1 to 4) and the choices are on the right (columns 6 to 12).
2. Pressing the inactive Continue does not move on: the hint "Choose at least one." brightens, and VoiceOver or NVDA reads "Choose at least one to continue." Tab reaches the button, and it announces as dimmed or unavailable with the hint as its description.
3. Ticking one time makes the button gold with its arrow at once. Unticking makes it inactive again. Two or more times are allowed. "How often?" stays optional.
4. What draws you: the same behaviour. The chosen photo tile has the gold ring and check, with no dimming of the others. 4 per row at 1440, 2 per row at 375.
5. Company: 3 tall tiles side by side at 1440, stacked at 375, with Signika labels and the swan glyphs (1 gold; 1 gold + 1 line colour; 2 gold).
6. About you (journey): tapping Property makes the follow-ups rise in over 700ms. Changing to Finance hides them instantly.
7. Result: no outline round "Tier 1." on load, on refresh, or after pressing Back to it. Tab still shows rings on the buttons and links. The screen reader still starts at the tier heading.
8. Result: "Start again" sits next to the primary at 1440 and under it at 375. It clears the answers and opens question 1 with nothing ticked.
9. With a completed journey, opening `/journey/` from the header shows question 1 with the earlier answers ticked and "See my last suggestion" under the lead. The link opens the result. On other screens the link is absent.
10. Gold `/gold-card/apply/`: "About you." / "A few taps, so we know you." The first question is "What do you do?" with 8 tiles (4 per row at 1440, 2 per row at 375). Property reveals "Your link to property" (no "None of these") and "How large?". Any other choice shows neither. Where, BML, company and role, and referred by are always shown.
11. A Gold application from a non-Property applicant submits and is rated (Low, plus any BML, location or referral points). A Property owner with 10-49 units is still rated High.
12. Reduced motion on: no rises or fades, follow-ups appear at once, the progress line jumps.
13. AA: cream text on a chosen tile is about 8.2:1, inactive Continue text is 6.50:1, and the control borders are 3.09:1 on espresso.
