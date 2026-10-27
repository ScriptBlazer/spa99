# Email builder: UI brief

For `docs/features/email-builder.md`. Screen: System > Emails > Mailings, New group send and Edit draft (`system/templates/system/emails_mailing_form.html`, `system-emails.js`, `system-emails.css`).

**Look:** System stays as it is (Moishe). Use only `--sys-*` tokens and the existing parts: `sys-panel`, `sys-row`, `sys-btn` (`sm`, `primary`, `link`), `sys-seg`, `sys-pop`, `sys-note`, `sys-error`, `sys-badge`, `se-group-card`, `se-editor`, `se-palette`. No new colours, no shadows on cards, no new type sizes. Nothing from the public brand look comes in here.

**Layout is unchanged.** Left: the write pane. Right: the live preview with Desktop/Phone. Bottom: the save bar (Save draft, Send me a test, Send). The parts list replaces the **Body** row inside the Message block. Order: Start from (new only), Who, Kind, count, Message (Name, Subject, Parts, Placeholders), When.

## 1. Start from (New group send only)

- First block in the write pane, above Who. `fieldset.se-block`, legend **Start from**. Two `se-group-card` radio cards side by side (stacked below 48em):
  - **Blank**: "An empty email with one paragraph."
  - **Booking is open**: "Service message to everyone registered: a heading, a short paragraph, a Book button and small print."
- The template words live in Python only. Choosing a card loads `?from=booking` (or `?from=blank`) and the server renders the form prefilled (parts, Kind = Service, Who = Everyone registered, subject).
- If nothing has been typed yet, it switches straight away. If something has, show an inline `sys-note warn` under the cards: "This replaces what you have written." with **Replace** (`sys-btn sm`) and **Keep mine** (`sys-btn sm link`). Keep mine puts the radio back. No browser confirm dialog.
- Not shown on Edit draft.

## 2. Parts list

- Heading row: `h3.se-label` **Parts**. From 25 parts, add `sys-muted` "25 of 30" on the right.
- Each part is an `li.se-part` in an `ol`: 1px `--sys-line` border, `--sys-radius`, padding `--sys-3`, gap `--sys-2` between cards. No shadow, no drag handle.
- **Card header** (one line, 32px): on the left the number in mono, then the type label in `--sys-fs-sm`, weight 600 ("2  Paragraph"). On the right, four `sys-btn sm` icon buttons, square, in this order: **Add below** (`plus`), **Move up**, **Move down**, **Remove**. Each has an aria-label with the place: "Move Paragraph 2 up", "Remove Paragraph 2", "Add a part below Paragraph 2". Move up is `disabled` on the first card, Move down on the last.
- **Proposed sprite additions** (`common/static/common/img/system-icons.svg`, Phosphor, same weight as the rest): `arrow-up`, `arrow-down`, `trash`.
- **Fields** sit under the header, label above field (the column is narrow), full width. Text fields show a counter "112 / 120" in `sys-muted` from 80% of the limit, `--sys-danger` when over.

| Part | Fields, label and hint |
|---|---|
| Heading | **Text**. No hint. |
| Paragraph | **Text** (`se-editor`, placeholders drawn, 5 rows, grows). Hint: "A blank line starts a new paragraph." |
| Button | **Label**, hint "Short, like Book your visit." **Link**, hint "A full address (https://...) or a page on the site, like /memberships/." |
| Image | See section 3. |
| Divider | No fields. One `sys-muted` line: "A thin line between sections." |
| Small print | **Text** (`se-editor`, 3 rows). Hint: "Shown small and grey, for terms or details." |

- **Placeholders** palette stays under the list. It inserts into the subject or the text part that last had focus (Heading, Paragraph, Small print, Button label). It hides while the focus is in a Link or alt text field.
- Under the palette, `sys-muted`: "The footer is added for you. News gets an unsubscribe link; Service messages say why it was sent."
- **Add part** at the bottom: `sys-btn` with `plus`, label **Add part**, `aria-haspopup="menu"`, `aria-expanded`. It opens a `sys-pop` menu (`role="menu"`, opens left-aligned and as wide as the button column, at least 260px). Six items, name plus a short `sys-muted` line:
  - **Heading**: "A section title"
  - **Paragraph**: "Body text"
  - **Button**: "A link people tap"
  - **Image**: "JPEG, PNG or GIF"
  - **Divider**: "A thin line"
  - **Small print**: "Terms or details"
- **Add below** opens the same menu, anchored to that card. The new part goes straight after the card.
- **Remove** works at once, with no confirm. The save bar note says "Paragraph 2 removed." with an **Undo** `sys-btn sm link`. Undo stays until the next change to the parts.
- **Old drafts** (body only) open as paragraph parts with a `sys-note` above the list: "This draft was one block of text. It is now split into paragraphs. Check the preview."

## 3. Image part

- **Empty:** a drop zone `.se-drop`, 1px dashed `--sys-control` border, `--sys-radius`, min-height 112px, centred text: "Drag an image here or **Choose a file**". The real `input type=file accept="image/jpeg,image/png,image/gif"` sits inside a label styled `sys-btn sm`, so it is keyboard-usable. Hint under it: "JPEG, PNG or GIF, up to 2 MB. Shown full width." While a file is dragged over it: border `--sys-accent`, background `--sys-selected`.
- **Check first in the browser** (type and size), then upload as soon as a file is chosen. The server's answer wins.
- **Uploading:** the zone is replaced by the file name, a 4px progress bar (`--sys-accent` on `--sys-subtle`), "Uploading 64%" (`role="status"`), and **Cancel** (`sys-btn sm link`). Send and Send me a test stay `aria-disabled` while an upload runs. The bar note says "Wait for the image to finish uploading."
- **Done:** a thumbnail (max 120px tall, `object-fit: contain` on `--sys-subtle`, its alt set to the alt text field), the file name and size in `sys-muted`, and **Replace** (`sys-btn sm`). The preview refreshes.
- **Errors** (`sys-error`, `role="alert"`, under the zone; the zone stays usable):
  - "This file is over 2 MB. Choose a smaller one."
  - "Use a JPEG, PNG or GIF."
  - "The upload did not finish. Check the connection and try again." with **Try again**.
- **Alt text** (required): label **Describe the image**, hint "Read aloud to people who can't see it, and shown when images are off." Error if empty: "Describe the image in a few words."
- **Link** (optional): label **Link** with `<small>Optional</small>`, hint "Where a tap on the image goes." Same link rule and error as Button.

## 4. Errors

- The contract returns errors per part index, from saving and from the preview. Map them onto the card: `.se-part.invalid` gets a 2px `--sys-danger` left border (inset, so nothing shifts), and each field gets its own `sys-error` under it with `aria-invalid` and `aria-describedby`.
- Whole-part errors go under the card header, for example "Add text or remove this part."
- List-level error under the Parts heading: "Add something besides a divider. A heading, paragraph, button, image or small print."
- Above the list, when any part has errors: a `sys-note error` "2 parts need a fix." with links that jump to and focus each card ("Paragraph 3", "Button 5"). Register these with the existing `data-problem` summary so the save bar behaves as it does now.
- Link error: "Use a full address starting https://, or a site page starting /." Over the limit: "Keep this under 120 characters." (use that part's limit).
- An error clears on that field's next input, as `sys-row` does today.

## 5. Keyboard, focus, announcements

- One polite live region for the list (`role="status"`, visually hidden).
- **Add:** focus moves to the new part's first field. A Divider has none, so focus goes to the card (`tabindex="-1"`, `aria-labelledby` its header). Announce "Heading added, part 3 of 6."
- **Move:** focus stays on the button that was pressed. If that button is now disabled (the part reached the top or bottom), focus moves to the other move button. Announce "Paragraph moved to part 2."
- **Remove:** focus goes to the previous card. If the first part was removed, it goes to the new first card; if the list is empty, to **Add part**. Announce "Paragraph removed."
- **Menu:** Arrow keys move between items, Home/End jump, Enter adds, Esc closes and returns focus to the button that opened it. A click outside closes it.
- Tab order inside a card: header buttons, then fields.

## 6. Motion

- **New card:** fades in (opacity 0 to 1, 160ms, ease-out), with its background fading from `--sys-selected` to `--sys-surface` over 700ms so it is clear where it landed.
- **Move:** both swapped cards slide to their new places (FLIP translateY, 180ms, `cubic-bezier(.2,.8,.2,1)`). The moved card gets the same highlight fade.
- **Remove:** instant.
- **Reduced motion:** no sliding. Keep only the highlight fade (`system.css` already limits motion to opacity and colour).

## 7. 375px

- Keep today's rule below 64em: one column, with the **Write / Preview** switch at the top. The preview stays behind that switch, not under the form.
- Start from cards stack. Card header buttons become 36px squares. The type label shortens with an ellipsis if needed, and the buttons never wrap. All inputs use 16px text so iOS does not zoom.
- The Add part menu opens full width of the column, above the button when there is no room below.
- The drop zone text reads "**Choose an image**" (no drag on touch). The hint stays.
- The save bar wraps as it does today.

## 8. Empty and full

- **Empty** (every part removed; Blank starts with one empty Paragraph): in place of the list, a 1px dashed `--sys-line` box, padding `--sys-5`, `sys-muted` "No parts yet. Add a heading, paragraph or button to begin.", with **Add part** under it. The preview note reads "Add a part to see the preview." Send and Send me a test are `aria-disabled`.
- **Full** (30 parts): **Add part** and every **Add below** are `disabled`. Under the list, `sys-muted`: "30 parts is the most one email can hold. Remove one to add another." The "30 of 30" count turns `--sys-warn`.
