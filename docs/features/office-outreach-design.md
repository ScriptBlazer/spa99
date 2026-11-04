# Office outreach: design brief

Spec: `docs/features/office-outreach.md`. Builds on `docs/design/OFFICE.md` and `docs/features/office-mobile.md`. Desktop = `min-width: 64em`, phone = below. Test at 320, 375, 414 and 1440.

Read: calm back office, warm paper surfaces, one action per moment. Notes should feel like paper left on a desk, not a widget.

## 0. Tokens

Existing only: `--color-cream`, `--color-espresso`, `--color-gold`, `--color-tier-edge`, `--color-danger`, `--office-surface`, `--office-sunken`, `--office-muted`, `--office-caramel-tint`, `--office-shadow-1/2/3`, `--office-radius(-lg)`, `--office-pill`, `--office-dur-lift`, `--office-dur-swap`, `--ease-soft`, `--radius-sm`, `--space-*`, `--text-*`, `--control-h`.

**Proposed additions** (Office only, in `office-tokens.css` under `.office`; list them in `docs/design/OFFICE.md` section 2 and the "Office tokens" line of `docs/BRAND.md`, marked proposed):

| Token | Value | Why |
|---|---|---|
| `--office-note` | `var(--color-cream)` | Alias, no new colour. The paper of a note. Espresso 10.95, `--office-muted` 5.81, danger 8.07 |
| `--office-note-tilt` | `0.6deg` | The most a note leans. `0deg` under reduced motion is not needed (it is static) |
| `--office-note-min-w` | `13rem` | Grid column minimum for the board |

New icons in `_icons.html` (same 24 grid, 1.5 stroke, `currentColor`; redraw the Phosphor regular glyph, do not import the library): `i-list-checks` (Phosphor ListChecks, the list), `i-note` (Note), `i-plus` (Plus), `i-x` (X), `i-paperclip` (Paperclip), `i-paper-plane` (PaperPlaneTilt, Send guide and Message).

## 1. Decision card: Send guide

Order in `.o-detail-rail .o-card[data-region=decision]` stays: badges, callouts, Decline, Approve and invite (primary), the 14 days line, "Open his account", then `.o-actions-more`.

- `.o-actions-more`: `display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2)`. Gold Decision card: **Send guide** (`btn btn-secondary`, `min-height: var(--control-h)`, icon `i-paper-plane` 1.125rem before the label), which shows in every status. There is no Respond button now: WhatsApp and Email are the two reach out buttons, and the old Respond link goes to one of them.
- Under it, a quiet row: **Add to Approach list** (section 3). Add note leaves this card.
- **No guide uploaded:** the button stays focusable with `aria-disabled="true"` and `aria-describedby="guide-hint"` (not `disabled`, so the hint is read). Look: `background: var(--office-sunken); color: var(--office-muted); box-shadow: none; cursor: not-allowed`; click does nothing. Hint below the row, full width: `<p class="o-hint-line" id="guide-hint">Upload the guide in System</p>`, `--text-sm`, `--office-muted`, `margin-top: var(--space-2)`. If the user can open System, "System" is a link to the guide setting.
- **Phone:** the decision bar (`.o-bar`) is unchanged. Send guide stays in the card, which sits after the application sections; same grid.

**Send guide dialog** (`dialog.fb-modal.o-dialog[data-gold-dialog=guide]`, same build as Respond, posted as a form, `data-problems`, duplicate guard via `data-working-text`):

- Title: "Send the guide to Daniel?" (first name).
- Body line (`fb-modal-body`): "To daniel@example.com, from hello@spa99.uk. His reply comes to the team."
- Attachment row `.o-attach`: `display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-radius: var(--office-radius); background: var(--office-sunken)`; `i-paperclip`, file name (weight 500, ellipsis), size right-aligned in `--office-muted` ("1.2 MB").
- Message: `fb-modal-textarea`, 6 rows, prefilled from template `gold_guide`, label "Message (you can change it)".
- If sent before: `<p class="o-sub">Last sent 2 Nov by Moishe.</p>` above the actions.
- Actions: **Cancel** (secondary) / **Send guide** (primary, working text "Sending").
- After: toast "Guide sent to Daniel." History line: label "Guide sent", meta as usual (time, who, Office), message kept.

## 2. Sticky notes (lead, person and Gold application pages)

Notes belong to the person, matched by email, so one board shows the same notes on the lead page, the person page and his Gold application. The lead page renders `person.html`, so it gets the board with no extra template. A note added on any of the three appears on the others.

### Desktop board (`section.o-notes`, first child of `.o-detail-main`)

Sits above the application sections (Gold) and above the profile (lead and person), so it is the first thing read. Not a card: notes lie straight on the page background.

- Head `.o-notes-head`: `display: flex; align-items: baseline; gap: var(--space-2)`. `h2.o-h3` "Notes", count in `--office-muted` ("3"), then **Add note** pushed right (`btn btn-secondary btn-sm`, `i-plus`). Only for people who may add.
- Grid `.o-notes-grid`: `display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--office-note-min-w), 1fr)); gap: var(--space-3); margin-top: var(--space-3)`. Newest first.
- **How many:** the 3 newest (one row at 1440). If there are more, `.o-notes-all` under the grid: `o-quiet` button "Show all 7" / "Show fewer", `aria-expanded`, reveals the rest in place (no reload).
- Note `.o-note` (`<article>`):
  - `background: var(--office-note); border-radius: var(--radius-sm)` (paper corners, smaller than cards on purpose); `box-shadow: inset 0 0 0 1px var(--color-tier-edge), var(--office-shadow-1)`; `padding: var(--space-3); min-height: 8rem; display: grid; grid-template-rows: 1fr auto; gap: var(--space-3)`.
  - Lean: `nth-child(3n+1)` rotate `calc(var(--office-note-tilt) * -1)`, `3n+2` `calc(var(--office-note-tilt) * 0.6)`, `3n` `calc(var(--office-note-tilt) * -0.3)`. Never more than 0.6deg.
  - Text `.o-note-text`: `--text-base`, espresso, `line-height: var(--leading-snug)`, `overflow-wrap: break-word`, line breaks kept, clamp 6 lines; a longer note gets `o-quiet` "Read all" which removes the clamp.
  - Foot `.o-note-meta`: "Moishe, 3 Nov" (first name, `|dm`; time on `title`), `--text-sm`, `--office-muted`.
  - Hover and focus-within: `transform: rotate(0) translateY(-2px); box-shadow: inset 0 0 0 1px var(--color-tier-edge), var(--office-shadow-2)`, transition `transform, box-shadow var(--office-dur-lift) var(--ease-soft)` inside `prefers-reduced-motion: no-preference`.
  - No tape, pin, stripe or coloured edge (BRAND: no one-sided accents). No yellow.
- **Delete** `.o-note-x`: top right, `position: absolute; top: var(--space-1); right: var(--space-1)`, 2rem circle (2.75rem under `pointer: coarse`), `i-x` 1rem, `--office-muted`, hover background `var(--office-sunken)`. `aria-label="Delete note by Moishe, 3 Nov"`. Hidden with `opacity: 0` until `.o-note:hover` or `:focus-within` (fade `--office-dur-lift`); `@media (hover: none) { opacity: 1 }`. Only for permitted users.
  - Confirm: the shared `data-confirm data-confirm-danger` modal. Title "Delete this note?", body "It leaves the board. The history keeps a copy.", buttons **Keep** / **Delete note**.
  - On delete: the note fades to 0 and `scale(0.96)` over `--office-dur-swap`, then the board partial swaps in (HTMX). Toast "Note deleted."
- **Add note** (inline, not a dialog): clicking inserts a blank composer note as the first cell, `.o-note.o-note--draft` (no tilt, `outline: 2px solid var(--color-espresso); outline-offset: 2px` while focused). Inside: `<label class="sr-only">Note</label>`, textarea with no border or fill, `rows=4`, `maxlength=1000`, placeholder "Write a note"; counter "940 of 1000" only from 900 characters; actions row **Cancel** (`o-quiet`) and **Add note** (`btn btn-primary btn-sm`, working text "Saving"). Ctrl or Cmd + Enter saves, Escape cancels. Focus moves into the textarea; after saving, focus goes to the new note.
- **Empty state:** head stays, then `<p class="o-empty-line">No notes yet.</p>` (for people who cannot add: hide the whole board when empty).

### Phone

- Board hidden below 64em. On all three pages, in the page header under the badges: `.o-notes-open` (`btn btn-secondary btn-sm`, `min-height: 2.75rem`, `i-note`) "Notes" plus the count in a pill (`--office-sunken` background, `--office-text-xs` weight 600); no pill when 0.
- Sheet `dialog.o-sheet.o-notesheet` (existing sheet: `85dvh`, scroll, `modal-in`). Head "Notes" and **Add note** right. The composer opens at the top of the list. Notes are full width, stacked with `gap: var(--space-2)`, no tilt, delete x always visible. All notes shown (no "Show all"). Close: backdrop, Escape, a **Done** button sticky at the bottom (same as "Show results").

### History wording

- Gold history (`_gold_history.html`): label "Note deleted", meta "3 Nov 14:20 · Moishe · Office", the note text in `.o-tl-msg`. (The meta already names the person, which reads as "Note deleted by Moishe".)
- Lead and person timeline (`_timeline.html`, one line, no meta who): label "Note deleted by Moishe", detail = the note text clamped to 3 lines.
- Because one board shows on all three pages, write the deleted line to the person's timeline (lead or account) and, if he has a Gold application, to its history too, so every board that lost the note explains why.
- Adding a note writes no history line. Old "Note added" lines disappear once copied.

## 3. Approach list (outreach)

Title everywhere = `outreach_list_name` from System, or "Approach list" while empty. Below, "Approach list" means that name.

### Rail and More sheet

- Rail item after Leads: `i-list-checks`, label = the name (ellipsis at rail width; System help text: "Short is best, up to 20 characters"). Shown when `office_can.can_see_all`.
- Phone: `data-nav-overflow`, so it lives in the More sheet (row: icon, label, chevron), first row, above Analytics. Add the section to the More `is-current` check.

### The page

- Header title = the name. Under it one quiet line `.o-sub`: "People to approach, newest first."
- Filter: `.o-seg` with two items, **Open 4** / **Done 12** (counts in `--office-muted`), left of the total line. On phone the same two chips sit in the bar (no filter sheet, two options do not need one). Search only if the list passes 50 (not now).
- Desktop: `.o-card.o-tablecard > table.o-list.o-list--outreach`. Columns:
  1. **Name** `c-name`: name (link to the source page via `.o-rowlink`), email under it (`o-cell-sub`).
  2. **Mobile** `c-contact`: number or empty.
  3. **From** `c-from`: pill `o-badge o-badge--type` "Lead", "Person" or "Gold".
  4. **Reason** `c-reason`: `--text-sm`, 2-line clamp, empty when none.
  5. **Added** `c-added`: "Moishe, 3 Nov". In Done: **Done** `c-done` "Barry, 4 Nov" replaces it.
  6. **Actions** `c-action`, right aligned: **Mark done** (`btn btn-secondary btn-sm`, `i-check`) and **Remove** (`o-quiet`). Done rows: Remove only.
- Phone card (office-mobile anatomy): title line name, second line email, badges line From pill, reason as `o-sub` (2 lines), meta line "Added by Moishe" with the date last, then an actions row `.o-row-actions` (`display: grid; grid-template-columns: 1fr auto; gap: var(--space-2); margin-top: var(--space-3)`): **Mark done** full width (`min-height: 2.75rem`), **Remove** quiet. Exception to "one target per card", noted: the row link covers only the title and email (`.o-row-main { position: relative }`).
- Mark done: no confirm; the row fades out (`--office-dur-swap`), counts update, toast "Marked done." Remove: `data-confirm` "Take Daniel off the list?", body "Nothing is sent to him.", **Keep** / **Remove** (not danger red; nothing is lost).
- Empty: Open "Nobody to approach. Add people from a lead, person or Gold application." Done "Nothing marked done yet."

### Add to list (lead, person, Gold pages)

- Gold: a quiet full-width row in the Decision card under Send guide: `o-quiet` button with `i-list-checks`, "Add to Approach list".
- Person and lead: in the new **Reach out** rail card (section 4), second button: `btn btn-secondary btn-block`, `i-list-checks`, "Add to Approach list".
- Opens a small `fb-modal.o-dialog[data-dialog=outreach]`: title "Add Daniel to the Approach list?", reason chips (choosing first): "High potential", "Asked to talk", "Big business" (`.o-chip`, tapping one fills the field, tap again clears), then `fb-modal-field` "Reason (optional)", textarea 2 rows, `maxlength=200`. Actions **Cancel** / **Add to list** (primary). Toast "Added to the Approach list."
- **Already on the list:** the button is replaced by a state row `.o-onlist`: `i-check`, "On the Approach list", `--text-sm` meta "Moishe, 3 Nov", and `o-quiet` link "View" to the page. If the entry is done: "Approached 4 Nov by Barry", no link button. A second add (race) returns the same state with toast "Already on the Approach list."
- Row action on lists: not in this round (no cheap spot without a hover menu).

## 4. Email (lead, person and Gold pages)

- New first card in `.o-detail-rail`: `section.o-card[data-person-reach]`, `h2.o-h3` "Reach out". Buttons stacked, `gap: var(--space-2)`: **WhatsApp** and **Email** (`btn btn-block`, one primary, `.o-email-btn`), then Add to Approach list. Phone: card order right after the header (`order: 1`). Read-only users: card hidden.
- Dialog `fb-modal.o-dialog[data-dialog=email]` (the lead page's Correct the email dialog is `data-dialog=correct-email`):
  - Title "Email Daniel" (name, else the email).
  - Body "From <his name and address>. His reply goes to <that address>. Kept in his timeline."
  - Unsubscribed: `.o-warn` above the field, `i-warning` 1rem inline: "Unsubscribed from news. This is a one-to-one message, so it still goes."
  - Field "Message", 6 rows, `required minlength=5 maxlength=2000`.
  - Actions **Cancel** / **Send email** (working text "Sending").
- Toast "Your email is on its way." Timeline: label "Email sent by Moishe", detail = text clamped to 3 lines.

## 5. Leads: the Show filter goes

- Remove the Show `fieldset` (Not registered / Registered / All) from `leads.html` and `leads_show` from System > Defaults. Old `?show=` links are ignored.
- Filter order after: Last seen, Potential, Industry, Heard about us, Sort by, chips. Desktop: Potential moves up beside Last seen in the bar; phone sheet follows the same order.
- Summary tiles: "Leads" stays; "Went on to register" stays as a conversion figure if the snapshot still has it (otherwise the grid drops to two columns, `repeat(2, 1fr)`); Hot leads line becomes "High potential" (they are all unregistered now).
- Status column: Registered pill no longer appears; Applied and Gold stay.

## Motion summary

All CSS, all on `--ease-soft`: note lift `--office-dur-lift`, delete x fade `--office-dur-lift`, note and row exits `--office-dur-swap`, dialogs and sheets the existing `modal-in`. All durations are 0 under reduced motion (tokens already do this). Nothing loops.

## Copy checklist

Send guide, Upload the guide in System, Notes, Add note, Write a note, Show all 7, Show fewer, Read all, No notes yet., Delete this note?, It leaves the board. The history keeps a copy., Keep, Delete note, Note deleted, Note deleted by X, Guide sent, Add to Approach list, On the Approach list, Mark done, Remove, Reach out, Message, Send message, Unsubscribed from news. No exclamation marks, no em dashes.

# Round 2 (2026-11-03)

Spec: `docs/features/office-outreach.md` R1 to R7. Same breakpoints (desktop `min-width: 64em`). **No new tokens**: everything below uses existing ones. New icons only (same 24 grid, 1.5 stroke, `currentColor`, added to `_icons.html`):
`i-arrow-up` `<path d="M12 19V5.5M7 10.5l5-5 5 5"/>` (one arrow, rotated for descending), `i-archive` `<rect x="3" y="4.5" width="18" height="4.5" rx="1.5"/><path d="M4.5 9v9a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V9M10 13h4"/>`, `i-trash` `<path d="M4 6.5h16M9.5 6.5v-2h5v2M6.5 6.5l.8 12.2a1.5 1.5 0 0 0 1.5 1.3h6.4a1.5 1.5 0 0 0 1.5-1.3l.8-12.2M10 10.5v6M14 10.5v6"/>`.

## R1. Sortable headers

**Markup** (every `table.o-list` in Leads, Registered, Gold, Approach list, Invited, Chats; a shared include `_th_sort.html` with key, label, `num`):
`<th scope="col" class="is-sortable" aria-sort="descending"><a class="o-sort" href="?{kept params}&sort=last_seen&dir=asc" data-sort>Last seen<svg class="o-icon o-sort-icon" aria-hidden="true"><use href="#i-arrow-up"/></svg></a></th>`
- A link, not a button: it works with no JS, keeps every filter, and the existing list swap (HTMX, `aria-busy` fade on `.o-tablecard`) takes it over. The head re-renders with the rows so `aria-sort` stays true. Page resets to 1.
- `aria-sort` (`ascending` / `descending`) only on the sorted column; no attribute elsewhere.
- **First click** uses the column's natural order: text A to Z, dates newest first, numbers and potential highest first. **Second click** reverses.
- Non-sortable headers (Wants, Status badges, answers, Actions) stay plain text, exactly as now. No cursor, no hover.

**Look** (`office-lists.css`):
- `.o-sort`: `display: inline-flex; align-items: center; gap: 0.25rem; height: 100%; min-height: 2.75rem; color: inherit; text-decoration: none; font: inherit; letter-spacing: inherit; cursor: pointer`. It inherits the head style (xs, 600, uppercase, `--office-muted`).
- `.o-sort-icon`: `width: 0.875rem; height: 0.875rem; stroke-width: 2` (1.5 is too thin at this size). **Always rendered** with `opacity: 0` on unsorted columns, so the label never shifts and the Leads `%` widths hold.
- Hover (`hover: hover` and `pointer: fine`): `color: var(--office-text)`, the arrow fades to `opacity: 0.45` showing the order a click gives. Transition `color, opacity var(--office-dur-lift) var(--ease-soft)`.
- **Active** (`th[aria-sort]`): `color: var(--office-text)` (10.13 on sunken), arrow `opacity: 1`; `th[aria-sort="descending"] .o-sort-icon { rotate: 180deg }`. No fill change, no underline (no one-sided accents).
- Focus: `.o-sort:focus-visible { outline: 2px solid var(--office-text); outline-offset: -2px; border-radius: var(--radius-sm) }` (inset: Leads heads clip overflow).
- `th.num .o-sort { flex-direction: row-reverse }`: the arrow sits left so the label lines up with the right-aligned numbers.
- Screen readers: `aria-sort` on the `th` is enough; no extra hidden text.

**Phone** (no heads, rows are cards): a **Sort** group, the same `sort` and `dir` params.
- Lists with a filter sheet (Leads, Registered, Gold, Invited): last group in the sheet, `.o-filter-group--sort`, hidden at 64em and up (the heads do it there; keep it in the form so filter changes keep the order). Two rows of pill radios (the existing `.o-sheet .o-seg` chip look):
  - "Sort by": the list's sortable keys, e.g. Leads: Last seen, First seen, Name, Potential, Visits.
  - "Order": two pills whose labels follow the field (`data-asc` / `data-desc` on the option): "Newest first / Oldest first", "A to Z / Z to A", "Highest first / Lowest first". No JS: "Ascending / Descending".
- Lists without a sheet (Approach list, Chats): a quiet button at the end of the total line, `o-quiet o-sortbtn`, `i-arrow-up` 1rem, "Sort: Added" (the active field). It opens a small `dialog.o-sheet[data-sort-sheet]` with the same two groups and **Show results**.
- Leads: the old "Sort by" select goes; its System default stays the default order.

## R2. Registered and Best fit

- Nav rail, phone tab bar, `<title>`, `h1`, caption ("People who have registered" stays as the caption), empty states and dashboard tiles: "People" becomes **Registered**. Icon `i-people` stays. "Registered" at `--office-text-xs` is about 62px, inside a 75px tab at 375 (5 tabs); the existing ellipsis covers 320.
- The Registered list's date column keeps the label "Registered"; it reads as "Registered 3 Nov" in the card meta.
- Approach list subtitle: "People to approach." ("newest first" is wrong once sorted).
- Analytics "People" columns are counts, not the section: leave them; flag to the lead if the acceptance test catches them.
- Leads "Suggested" becomes **Best fit** (head, CSV, filter label "Best fit"). Shorter, so no width change; update the width comments in `office-leads.css`.

## R3. Wrapping and Read more

**One rule** in `office.css` (shared Office base):
```css
.o-card, .o-rows dd, .o-sub, .o-tl, .o-tl-msg, .o-history, .o-callout, .o-dialog, .o-row td { min-width: 0; overflow-wrap: anywhere; }
.o-list .c-name, .o-list .o-rowname { overflow-wrap: break-word; }   /* names break at spaces first, not mid-word */
```
- `anywhere` on free text (reasons, messages, history, emails); names keep `break-word`. Desktop tables already scroll inside `.o-tablecard` as a last resort.
- Emails: a `|soft_email` filter inserts `<wbr>` after `@` and before each `.`, so long addresses break at sensible points first.

**Clamp** (generalise the note clamp; `.o-clamp` in `office.css`, toggle JS generalised from the note "Read all" code in `office-tools.js`):
- `.o-clamp:not([data-open]) { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: var(--lines, 3); line-clamp: var(--lines, 3); overflow: hidden }`.
- Toggle `button.o-quiet.o-clamp-more` "Read more" / "Show less", `aria-expanded`, `hidden` until JS finds `scrollHeight > clientHeight`. No JS: no clamp (`html:not(.js) .o-clamp { display: block }`).
- Where: Approach list reason `--lines: 2` (table and card); lead timeline detail, Gold history `.o-tl-msg`, archive reason `--lines: 3`. In table rows the button sits above the row link (`position: relative; z-index: 1`).
- Reason field (Add to list dialog): `maxlength=300`. Counter "270 of 300" from 270 characters, `--text-sm`, muted; at 300 it reads "300 of 300, that is the most" in `--office-danger`. Pasted text over 300 is refused by the server with the same line.

## R4. Delete a Gold application (Admin and up)

- **Where:** the very end of `.o-detail-main`, after History. Not in the Decision card, not in the phone bar. `div.o-endzone`: `margin-top: var(--space-6); padding-top: var(--space-4); border-top: 1px solid var(--color-control-line)` (a full-width rule, not an accent).
  - `button.o-quiet.o-quiet--danger` with `i-trash` 1rem: "Delete application". Colour `--office-danger` (8.15). One line under it, `--text-sm`, muted: "For tests and junk. Notes stay with his email."
  - Phone: same spot, last thing on the page, above the decision bar's padding.
- **Confirm:** the shared `data-confirm data-confirm-danger` modal.
  - Title "Delete G-1234?"
  - Body "This removes the application and its history. It cannot be undone."
  - Buttons **Keep** / **Delete application** (danger, working text "Deleting").
- After: back to the Gold list, toast "G-1234 deleted." Nothing else changes on screen.

## R5. Approach list: Open / Registered / Done

- `.o-seg` with `--n: 3`, `min-width: 21rem` on desktop: **Open 4** / **Registered 2** / **Done 12** (counts `.o-seg-count`, muted). Phone: full width; below 24em the items drop to `--text-sm` and `padding-inline: var(--space-1)`.
- Tag: the existing `o-badge o-badge--st-registered` (sunken, espresso, 10.13), text "Registered 4 Nov" (`|dm`, full date and time on `title`).
  - Desktop: on the name line after the name, `margin-left: var(--space-2)`, vertical-align middle.
  - Phone: in the badges line, after the From pill.
  - Shown in Registered, and in Done when he had registered by then.
- In Registered the name links to his account page, not the lead. **Mark done** and **Remove** work as in Open.
- Empty: Registered "Nobody on the list has registered yet."

## R6. Archived leads

**Archive on the lead page:** last item of the rail, after Reach out: `button.o-quiet` with `i-archive`, "Archive lead". Phone: end of the page (same as Gold delete, not red).
- Dialog `fb-modal.o-dialog[data-dialog=archive]`: title "Archive Daniel?" (name, else the email). Body "He leaves Leads and the counts. If the next-morning email has not gone, it will not go. You can move him back." Reason chips (choosing first): "Test", "Duplicate", "Not a fit"; then "Reason (optional)", 1-row input, `maxlength=120`. **Cancel** / **Archive** (primary, not danger: nothing is lost). Toast "Lead archived."
- **Archived state** on the lead page: header badge `o-badge o-badge--archived` (`background: var(--office-sunken); color: var(--office-muted)`, 5.38; `i-archive` 0.875rem) "Archived 4 Nov". The rail row becomes an `.o-onlist`-style state: `i-archive`, "Archived by Moishe, 4 Nov", reason under it (clamp 3), and **Move back** (`btn btn-secondary btn-sm`). Reach out stays.
- **Row action:** not on the main Leads table (no free column, no hover menus). Move back is a row action in the Archived view.

**Archived view** (`/leads/?archived=1`, a filter, same page):
- Reached by a quiet link at the end of the total line: `o-quiet` "Archived 3" (count muted; hidden at 0). Desktop and phone alike.
- In the view: summary tiles and filters hide (search and sort stay). Total line "3 archived leads" and `o-quiet` with `i-chevron-left` "Back to Leads". `h1` (sr-only) "Archived leads".
- Columns: Lead, Best fit, Potential, Reason (clamp 2), Archived ("Moishe, 4 Nov", sortable), Action **Move back** (`btn btn-secondary btn-sm`). No confirm; the row fades (`.o-row.is-leaving`), toast "Moved back to Leads."
- Phone card: name and email, badges, reason, meta "Archived by Moishe, 4 Nov", then Move back full width (`.o-row-actions`, as the Approach list).
- Timeline: "Archived by Moishe" (detail: the reason) and "Moved back by Moishe".

## R7. Next-morning email

**System > Settings**, new `sys-group` after Launch, heading "Next-morning email to new leads":
1. "Automatic emails sender name", placeholder "Barry Lobenstein".
2. "Automatic emails sender address", placeholder "barry@spa99.uk". Help: "Must be an @spa99.uk address. Replies come here." (domain read from the sending domain). Error: "Use an address ending in @spa99.uk."
3. Switch "Send the next-morning email to new leads", off. Help: "10:00 London time, at least 8 hours after he gives his email. Once per address." Turning it on with no address: "Add a sender address first." Add it to `risky_fields` (it emails real people).
4. A link row: "Edit the email" to `system_email_edit lead_next_morning`.
- Emails > Automatic: a row "Next-morning email to new leads", Sent when "10:00 the morning after a new lead", plus `sys-badge` "Off" while the switch is off.

**Lead timeline** (`kind="auto_email"`, never styled as an error; only a bounce is red):
- "Next-morning email sent", detail "From Barry Lobenstein".
- "Next-morning email skipped", detail one of: "Archived", "Already registered", "Unsubscribed", "Address bounced before", "Switched off".
- Optional, quiet: while due, the Reach out card shows one muted line "Next-morning email at 10:00 tomorrow".

## Round 2 copy

Best fit, Registered, Sort by, Order, Newest first, Oldest first, A to Z, Z to A, Highest first, Lowest first, Sort: Added, Read more, Show less, 300 of 300, that is the most, Delete application, Delete G-1234?, This removes the application and its history. It cannot be undone., G-1234 deleted., Registered 4 Nov, Archive lead, Archive Daniel?, Lead archived., Archived 3, Back to Leads, Move back, Moved back to Leads., Archived by X, Moved back by X, Next-morning email sent, Next-morning email skipped, Edit the email. No exclamation marks, no em dashes.
