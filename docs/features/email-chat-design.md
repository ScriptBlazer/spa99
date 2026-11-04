# Email chat, the reach out buttons and WhatsApp round 2: design brief
Spec: `docs/features/office-email-chat.md` ("Mini Outlook", "Built"), `docs/features/whatsapp.md` ("Round 2", "Mobile optional", "Built, round 2"). Sister brief: `docs/features/whatsapp-design.md`. Builds on `docs/design/OFFICE.md`. `docs/BRAND.md` wins. Desktop = `min-width: 64em`, phone = below. Test at 320, 375, 414 and 1440, and on a real iPhone: keyboard, microphone and safe areas cannot be judged in emulation.

- **Design read.** WhatsApp is a wall you talk across. Email is paper you read. Same building, same list and same shell, but here a subject, a sender, full-width sheets and words instead of ticks. Dials: variance 2, motion 2, density 5.
- **Not rendered.** The sandbox refused Chromium (Playwright's headless shell exits on launch with SIGTRAP; Chrome cannot create its profile lock). Every size below is calculated from the CSS, and text widths are estimates. Contrast ratios are computed from the hex values. Section 9 lists what to judge at the first screenshots.

## 0. Tokens
**Proposed additions** (Office only, `office-tokens.css` under `.office`; copy into `OFFICE.md` section 2 and the "Office tokens" line of `BRAND.md`, marked proposed). **No new colour.**

| Token | Value | Use |
|---|---|---|
| `--office-em-list-w` | `clamp(21rem, 28vw, 26rem)` | Thread list. Wider than WhatsApp's: subject lines need it. 403px at 1440 |
| `--office-em-read-max` | `48rem` | Longest message sheet |

Reused: `--office-page`, `--office-surface`, `--office-sunken`, `--office-row-alt`, `--office-muted`, `--office-gold-text`, `--office-danger`, `--office-caramel-tint`, `--office-wa-out`, `--office-wa-inset`, `--office-wa-avatar`, `--office-shadow-1/2/3`, `--office-shadow-scrolled`, `--office-radius(-lg)`, `--office-pill`, `--office-text-xs`, `--office-dur-swap`, `--ease-soft`, `--radius-sm`, `--color-control-line`, `--color-veil`, `--chat-text`, `--chat-heading`, `--control-h`, `--control-h-compact`, `--space-*`, `--text-*`.

**Colours that travel in an email** are raw hex, because mail clients have no variables, like the Email layout tokens in `BRAND.md`. Each one is an existing value. See section 3.

- **New CSS file:** `office-email.css`, imported after `office-whatsapp.css`. Classes `o-em-*`. Reuse `.o-wa-search`, `.o-wa-chips`, `.o-chip`, `.o-wa-time`, `.o-wa-note`, `.o-wa-pill`, `.o-wa-blank`, `.o-wa-lightbox`, `.o-badge-count`. Set `.o-em p { max-width: none }`, or the site-wide 34rem measure narrows every line.
- **New icons** in `_icons.html` (24 grid, 1.5 stroke, `currentColor`, redrawn from Phosphor regular): `i-address-book` (Leads), `i-text-b`, `i-text-italic`, `i-text-underline`, `i-text-strikethrough`, `i-text-a-underline`, `i-highlighter`, `i-list-bullets`, `i-list-numbers`, `i-link`, `i-quotes`, `i-image`, `i-reply` (`arrow-bend-up-left`), `i-smiley`, `i-microphone`, `i-video`. `i-more`, `i-paperclip`, `i-trash`, `i-tick`, `i-ticks`, `i-clock`, `i-warning`, `i-arrow-clockwise`, `i-download`, `i-file-pdf`, `i-plus`, `i-x` exist.
- **Naming.** "WhatsApp" and "Email" are the sections. "Assistant" is the AI. In staff copy: a WhatsApp conversation is a chat, an email conversation is a thread.

## 1. Reach out buttons
One partial per channel: `_wa_button.html` (rewritten) and new `_email_button.html`, wrapped in `.o-channels`. **Key on `whatsapp.state`, not on `configured`.** Keep the hooks `data-wa-button`, `data-whatsapp-open`, `data-add-mobile`.

**Layout, both sizes:** `.o-channels { display: grid; gap: var(--space-2); grid-column: 1 / -1 }`. Always stacked, one channel a row. "Open WhatsApp chat" with icon and count needs about 215px and half of a 335px card is 163px, so side by side cannot work. Each row is `.o-channel`: the button, then any line under it (`.o-hint-line`, `--text-sm`, `--office-muted`, centred, 5.88 or more). WhatsApp first, Email second. "Add to list" follows at full width.

**Plainly different:** the channel's own icon and its name in every label. No green; the brand does not need WhatsApp's colour, and the word does the work.

**One primary at most.** Lead and person: WhatsApp is primary when he can be sent to on it (`state` is `chat` or `ready`, `can_edit`, not `opted_out`), otherwise Email is primary when it can send, otherwise none. Gold: both secondary, always, so Approve stays the one primary. Pass `secondary=True` in both Gold branches.

### WhatsApp

| Condition | Button | Line under it | Does |
|---|---|---|---|
| `chat`, can edit | **Open WhatsApp chat**, gold count pushed right | | `contact_url` |
| `ready` | **Start WhatsApp chat** | None. The label replaces "No messages yet." | `contact_url`, picker open |
| `opted_out` true (state `chat` or `ready`) | **Open WhatsApp chat**, secondary | He replied STOP. | Opens the history |
| `chat`, view-only staff | **Open WhatsApp chat**, secondary, with count | | Reads the chat |
| `view_only` | **No WhatsApp chat yet**, off | View only. | Nothing. A dead "Start" would invite a click he may not make |
| `unconfigured`, `has_chat` | **Open WhatsApp chat**, secondary | `reason`: WhatsApp is not set up yet. | `thread_url`, history. The thread's `unconfigured` slot explains the rest |
| `unconfigured`, no chat | **Start WhatsApp chat**, off | `reason`: WhatsApp is not set up yet. | Nothing |
| `no_mobile`, `can_add_number` | None | **Clickable** greyed line, see below | Add a mobile dialog |
| `no_mobile`, `can_add_number`, Gold page | None | **Clickable** greyed line, as on a lead or person (staff can add a number everywhere, 2026-11-04) | Add a mobile dialog (mobile only, no first name field) |
| `no_mobile`, view-only staff | None | Static greyed line: No mobile on file. | Nothing. He cannot add one, so he is not told to |

### Email

| Condition | Button | Line under it | Does |
|---|---|---|---|
| `start`, `can_send` | **Start email** | | `open_url` (New email) |
| `open`, `can_send` | **Open email thread**, gold count | `o-quiet` link: New email (`new_email_url`). With `thread_count` over 1: "3 threads. This opens the latest." before it | `open_url` |
| `open`, view-only staff | **Open email thread**, secondary | | Reads the thread |
| `start`, view-only staff | **No email yet**, off | View only. | Nothing |
| `suppressed`, `start` | **Start email**, off | `reason` | Nothing |
| `suppressed`, `open` | **Open email thread**, secondary | `reason` | Reads the thread |
| No `email` on file | **Start email**, off | No email on file. | Nothing |
| `replies_to_mailbox` (adds to any of these that can send) | No change | Replies go to the hello@ mailbox. | |

When both channels are off for view-only staff, "View only." shows once, under the last. Use `open_url`, never `latest_thread_url`: on Gold it carries `?gold=`, which is what marks the application Contacted.

### The details
- **Off button:** `btn btn-secondary btn-block o-btn-off`, `aria-disabled="true"`, `aria-describedby` its line, a `button` that does nothing, still focusable so a screen reader hears why. **Fix first:** `.btn[aria-disabled="true"]` sets `opacity: 0.4` and `.o-btn-off` does not undo it, so the label computes at 1.82. Add `opacity: 1` to `.office .btn.o-btn-off`: muted on sunken is then 5.38. This also repairs the off Send guide.
- **Clickable greyed line:** `button.o-quiet.o-channel-add`, `data-dialog-open="mobile"`, `data-add-mobile`, `aria-haspopup="dialog"`. `i-whatsapp` 1rem, then the words, `--text-sm`, `--office-muted`, underlined at offset 0.2em. The underline is what separates it from the static line; the static line never has one. Espresso on hover (fine pointer). Target 2.25rem, 2.75rem under `pointer: coarse`. It sits directly under the email button.
- **After saving a number** the card swaps from the server as today, and shows **Start WhatsApp chat** as primary, with Email dropping to secondary. Move focus to the new button.
- **Gold page.** Take the channels out of the `office_can.can_edit` block, or view-only staff lose sight of a live thread. New order in the rail: Approve (`.o-actions-rail`), `.o-channels`, then `.o-actions-more` holding Send guide alone (its `:only-child` rule makes it full width). The phone decision bar does not change.
- **Lead and person.** Remove the guard at the top of `_person_tools.html` (`whatsapp.can_edit or whatsapp.has_chat or outreach.can_add`). As written, a reader with only an email thread loses the card. The card now always shows: nothing vanishes. The Add a mobile dialog stays behind its own guard.

## 2. The Email tab
`section = "email"` (already set by the views). In this section `.o-main { padding: 0; max-width: none }` and the document does not scroll, as WhatsApp. **No wall and no swan pattern anywhere in Email.** That one absence, with the words and the full-width sheets, is most of what makes it read as email.

### Frame
- **Desktop:** the `.o-wa` frame with `--office-wa-list-w: var(--office-em-list-w)`. At 1440: rail 248, list 403, margin 24, reading pane 765. Nothing chosen: `.o-wa-blank` on `--office-page`, mark, pill "Choose an email."
- **Phone:** list at `/email/` with the normal shell. Thread at `/email/<id>/` with `data-office-detail data-em-thread`: header and tabs hide. Same keyboard handling as WhatsApp: `--wa-vh`, `--wa-top` and `data-keyboard` from `visualViewport`. Share that script, do not fork it. Back is `.o-back`, `aria-label="Back to email"`, and keeps the list's scroll.
- **New email** in the shell header's right side through the `header_range` block: `btn btn-primary btn-sm`, `i-plus`, "New email", both sizes, only with `can_send`. Espresso on the one thing this screen starts. No floating button: it would cover rows.
- **Shell title:** add `section == "email"` to the header title chain in `base.html`. **`whatsapp` is missing from that chain too**, so the WhatsApp header has a swan and no title today. Add both.

### List
**Head:** `.o-wa-search`, placeholder "Search name, address or subject". Chips **All**, **Unread**, **Sent with no reply**, `flex-wrap: wrap`: about 304px wide, so they sit on one line at 375 and wrap at 320. `?filter=unread`, `?filter=noreply`, `?q=` with a 250ms debounce. With `replies_to_mailbox`, `.o-wa-note` above the rows: "Replies go to the hello@ mailbox for now, not here."

**Row** `a.o-em-row`: no avatar. Avatars say chat, and three lines of words say email. It also gives back 64px of a 375 screen. `display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.125rem var(--space-2); min-height: 5.25rem; padding: var(--space-2) var(--space-3); border-radius: var(--office-radius)`. Margin 0 `--space-2`. Hover `--office-row-alt`, selected `--office-sunken`. No rules between rows.

| Line | Left | Right |
|---|---|---|
| 1 | Person, 600 `--text-base`, ellipsis. The address when `has_name` is false. Then quiet `Gold` badge when `gold` | Time, `.o-wa-time`, same format as WhatsApp |
| 2 | Subject, 500 `--text-sm`, espresso, ellipsis, `dir="auto"` | `i-paperclip` 1rem muted when `has_attachment`, `aria-label="Has a file"` |
| 3 | Preview, `--text-sm` muted, ellipsis. Ours starts with "You: " | Gold `.o-badge-count` when `unread` |

- **Unread:** person and subject 600, time espresso 600, count. No dot, no stripe.
- **Ours, not delivered:** line 3 reads `i-warning` and "Bounced" or "Not sent", `--office-danger`, in place of the preview.
- **No "No reply" badge on rows.** The server sets `no_reply` the moment we send, so every row we just wrote would carry it. "You: " already says it, and the chip finds them.
- **Empty:** all, "No email yet. Write one, or start from a lead." Search, "No email matches that." Unread, "Nothing unread." No reply, "Everyone has replied."
- **Loading:** server rendered, HTMX gets the rows. Dim to 0.5 only after 300ms. A row moving to the top does not animate.

### Thread
Grid `auto minmax(0, 1fr) auto`, as WhatsApp: head, scroller, foot.

**Head** `.o-em-head`: 3.5rem phone, 4.5rem desktop, `--office-page`, `--office-shadow-scrolled`. Name 600 `--text-base`, address `--text-sm` muted, selectable. Desktop: `o-badge--type` pills to his page at the right ("Lead", "Registered", "Gold"). Phone: the name block is the link, with a chevron. Reuse the markup from `_thread.html`.

**Scroller** `.o-em-scroll`: `--office-page`, `overflow-y: auto; overscroll-behavior: contain`. Padding 0 on phone, `--space-4` on desktop. Content `max-width: var(--office-em-read-max)`, left aligned.

**Subject** `h1.o-em-subject`: first thing in the scroller, Signika 500, `--text-lg` phone, `--chat-heading` desktop, `--tracking-display`, `line-height: var(--leading-tight)`, `dir="auto"`, wraps freely. Padding `--space-3` on phone. It scrolls away, the head stays. A later message with `shows_subject` shows its own subject in its header.

**Message** `article.o-em-msg`: one sheet, always full width. His and ours sit in the same column, never left and right. `--office-surface`, `--office-radius`, `--office-shadow-1`, padding `--space-3` phone, `--space-4` desktop, `margin-top: var(--space-2)`. Phone: radius 0, edge to edge, tone separates them.

**Header**, a `button` when the message can collapse:

| Part | Style |
|---|---|
| Disc 2.5rem | `.o-wa-avatar--sm`. His: initials on `--office-sunken`, gold fill if Gold. Ours: staff initials on `--office-wa-out` (9.74). The same gold tint means "us" in both channels: that is the family link |
| Sender | `from_name` or `author`, 600 `--text-base`. Ours: "Moishe, Spa 99" |
| Address | Line under, `--text-sm` muted, selectable: `from_address`. Ours: "To daniel@example.com" |
| Time | `.o-wa-time`, right. Full date and time on `title` |
| Collapsed extras | `i-paperclip` beside the time. Preview under the name in one muted line, in place of the address |

**Collapsing.** Open on arrival: the newest message, any unread, any bounced or failed. The rest collapse to a 3.5rem row. Spam stays collapsed even when newest. Three or more collapsed in a row fold further into one `o-quiet` row, "Show 6 earlier emails". `has_older`: a row at the top, "Show earlier emails", loading `older_url` on click only, with the place held by adding the height difference to `scrollTop`.

**Where it opens.** At the top of the first unread message, or else the top of the newest. **Not the bottom of the pane:** a long email must be read from its start. This is the opposite of chat.

**The sender differs** (`from_other`): directly under the header, `--office-caramel-tint`, `--office-radius`, `--text-sm` espresso (10.25), `i-warning`: "Sent from daniel.w@outlook.com, not daniel@example.com. Check it is him before sharing anything." Replies still go to the thread address, and the composer says so.

**Delivery state, ours:** words in the header's second row, not bare ticks: this is email, and words fit it. `--office-text-xs` muted, with the existing icon. Status text changes instantly.

| `status` | Icon | Words |
|---|---|---|
| `queued` | `i-clock` | Sending |
| `sent` | `i-tick` | Sent |
| `delivered` | `i-ticks` | Delivered |
| `bounced` | `i-warning`, danger | `error.reason`, then `o-quiet` "Check his address" to `thread.page_url`. Never retried |
| `failed` | `i-warning`, danger | `error.reason`, then `o-quiet` "Try again", `i-arrow-clockwise`, when `error.can_retry` (POST `retry_url`) |

Bounced and failed: a row at the foot of the sheet, `--text-sm`, `--office-danger` (8.98), open by default. No read state exists: never imply one.

**Spam** (`spam`): quiet pill "Marked as spam" beside the time, always visible. Opened: `--office-caramel-tint` note, "Flagged as spam. Nobody was notified. Take care with links and files."

**`note`** (files dropped on the way in): `--text-sm` muted, under the attachments.

**Body:**
- **Ours:** `body_html` in `.o-em-body` (server cleaned, the one allowed `innerHTML`). `--text-base`, `--leading-body`, `overflow-wrap: anywhere`. Quote: `--office-wa-inset`, `--radius-sm`, padding `--space-2`, **no side bar**. Lists as in a bubble. Links espresso, underlined.
- **His, plain text** (`frame_url` empty): `body_text` as text nodes, `white-space: pre-wrap`, `dir="auto"`. When `body_full` differs: `o-quiet` "Show earlier text" swaps the node.
- **His, formatted:** the frame.

### His email in the frame
```html
<iframe class="o-em-frame" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" title="Email from Daniel" loading="lazy"></iframe>
```
Exactly those three flags. **Never `allow-scripts`.** With `allow-same-origin`, adding it would let his mail escape the sandbox altogether. Never put his HTML in the Office page. The white of his document against our surface is 1.02: it reads as one sheet, and his mail keeps its own look.

- **Load late.** Set `src` when the message first opens. Thirty frames would be heavy. **Never reload a frame on a poll:** apply `updates` to the status row only, or his scroll and Show images are lost.
- **Fit.** `width: calc(100% + 16px); margin-inline: -8px; border: 0; display: block`, so the frame's own 8px body padding lines his text up with the header. Phone frame is about 359px, at 1440 about 685px, and a typical 600 to 640px marketing email fits.
- **Too wide.** After load, if `scrollWidth` exceeds `clientWidth`, scale the document down to fit: `transform: scale(w)` with origin top left on `documentElement`, floor 0.6, and use the scaled height. Below the floor, leave it at 0.6 and allow sideways scroll inside the frame: small type that can be scrolled beats type too small to read.
- **Auto height.** On `load`, set the frame's height from `documentElement.scrollHeight`. Keep a `ResizeObserver` on the frame's `documentElement` for late pictures and folding. Minimum 5rem. `scrolling="no"` unless the too-wide case applies. The height never animates.
- **Show images.** With `has_remote_images`, a row above the frame: `i-image`, "Outside pictures are hidden." `--text-sm` muted, then `o-quiet` "Show images". The click sets `src` to `frame_images_url`, keeps the fold state, and removes the row. Per message, not remembered. Cannot be turned on globally: pictures can track who opened a message.
- **Quoted history.** From the page script, after load, in the frame's document: hide every `.quoted`, and any outermost `blockquote` with no text after it (a real quote in the middle of his message stays). Hide by a class on `<html>`, set through one injected `<style>`. A row **outside** the frame: `o-quiet` "Show earlier text" / "Hide earlier text". The toggle lives in our page because the frame runs no scripts. If folding would leave nothing to read, do not fold. Outlook's quotes carry no marker, so they stay shown: do not guess at them.
- **`FRAME_CSS` changes** (`emailchat/services.py`, small): replace both `border-left: 3px solid #ccc` with `background: #f6f5f2; border-radius: 6px; padding: 8px 10px`, because BRAND forbids a one-sided accent and this rule is ours. Add `@media (max-width: 30em) { body { font-size: 16px } }`, because BRAND's body minimum on a phone is 16.

### Attachments
`.o-em-files`: grid, one column on phone, `repeat(auto-fill, minmax(14rem, 1fr))` on desktop, `gap: var(--space-2)`, under the body. Each is the `.o-wa-file` card, on `--office-sunken` here: name, type and size, right-hand icon.

| File | Card | Does |
|---|---|---|
| `is_image` and `inline` | 3.5rem thumbnail, `loading="lazy"` | Opens in `.o-wa-lightbox` |
| `inline`, not image (PDF) | `i-file-pdf` | Opens in a new tab |
| The rest | `i-download`. `title="Downloads, does not open here"` | Downloads |

Show filenames through `textContent` only, with `dir="auto"`.

### Reply composer
`.o-em-foot` is the third grid row, so the reply is always in reach and the thread stays visible above it.

- **Closed:** `button.o-em-reply-open`, looks like the WhatsApp field: `--office-surface`, 1px `--color-control-line`, radius 1.375rem, `min-height: 2.75rem`, text "Write a reply" muted. With a draft: "Draft: Thanks Daniel, the..." Safe-area padding as the WhatsApp composer.
- **Open, desktop:** the foot grows, `max-height: 55%` of the pane, the sheets stay scrollable above. In order: To line, editor (min 8rem, then scrolls inside), tray, toolbar with Send.
- **Open, phone:** `[data-composing]` on the thread collapses the head and the scroller, so the composer fills `--wa-vh` and stays inside the thread at the same URL. Fade and 8px rise over `--office-dur-swap`, no slide. Top row, 3.5rem: `i-x` "Close" at left, "Reply to Daniel" 600, **Send** at right. Toolbar pinned on the keyboard. At 375 by 667 with a 291px keyboard: 376 visible, less head 56, To 24, toolbar 44, leaves about 252 for the editor. Close keeps the draft.
- **To line:** `--text-sm` muted, "To daniel@example.com". It is the thread address even when he wrote from another. `o-quiet` "Change subject" reveals a field prefilled from `reply_subject`, `--text-base`.
- **Editor** `.o-em-editor`: `contenteditable`, `role="textbox"`, `aria-multiline="true"`, `aria-label="Reply to Daniel"`, `dir="auto"`, **always `--text-base`** so iOS never zooms. Placeholder through `:empty::before`. Focus: 2px espresso outline on the composer, not the text.
- **Paste is plain text**, line breaks kept. Word and Outlook paste bring fonts and sizes that the server would strip anyway, and staff would see something other than what he gets.
- **Send:** `btn btn-primary` "Send", `i-paper-plane`, working "Sending", compact on desktop. **A word, not WhatsApp's disc.** Disabled until there is text or a file. Prevent default on `pointerdown` so the keyboard stays.
- **Enter is a new line, everywhere.** Cmd or Ctrl+Enter sends. Email is not chat, and a half-written email must not go on a stray key. Never during IME composition.
- **Draft:** `localStorage`, keyed by staff member and thread, as the spec says "in that browser". Cleared on send and on sign out, gone after 7 days. `o-quiet` "Discard" with `i-trash`, then the toast "Draft discarded."
- **After sending:** the sheet appears as `queued`, opened, composer closes, scroll to its top. Errors, under the composer, `--text-sm` danger, `role="alert"`, using the server's `message`. The text stays.
- **No send possible**, a muted line in place of the reply bar: view only, "View only. Sending is for Approvers and Admins." Suppressed, `thread.reason`. With `replies_to_mailbox`, one extra muted line in the open composer: "He will reply to the hello@ mailbox."
- **Poll:** same shape as WhatsApp, every 15 seconds visible and 60 hidden (email is not a live conversation). **`encodeURIComponent` the cursor.**

### New email
`/email/new/`. Desktop: swaps into the reading pane, list still visible, `pushState`. Phone: a whole-screen page with `data-office-detail`, using the composer's top row ("New email") and Send at right. Fields and editor share one scroller, so they move out of the way of the keyboard. Editor focused at 375 by 667: head 56 and toolbar 44 leave about 276 of scrolling room.

- **To** `.o-em-to`: `role="combobox"`, `aria-expanded`, `aria-controls`, label "To", `inputmode="email"`, `autocapitalize="none"`, `--text-base`. From two letters (250ms debounce, `/email/people/?q=`): a listbox of up to ten: name 600, address muted, quiet badges from `kinds`. `suppressed`: shown, `aria-disabled`, "Cannot be emailed". Last row when the text looks like an address: "Use daniel@example.com". Arrow keys, Enter and tap choose.
- **Chosen:** a chip in the field, `--office-sunken`, pill, name or address, `i-x` 2.75rem target. One recipient: no Cc or Bcc in this round. `recipient` prefills it. `recipient.error` shows under the field.
- **Subject:** label above, required, `enterkeyhint="next"`, `--text-base`.
- **Body:** the same editor and toolbar.
- **Send** disabled until To, Subject and a body or file. The server would otherwise make an empty thread that the inbox hides. With `?gold=`, post it along.
- **Errors**, under the field: `bad_address` "That email does not look right." `no_subject` "Add a subject." `empty` "Write something first." `too_big`, `bad_file`, `bad_target`: the server's `message`.
- **Leaving with text:** kept as a draft keyed `new`, restored here.

## 3. Rich text toolbar
`.o-em-tools`, `role="toolbar"`, `aria-label="Formatting"`, roving tabindex, buttons 2.75rem on touch and 2.25rem under a fine pointer, `aria-pressed` updated from `selectionchange`. Pressed: `--office-sunken` fill. Every button prevents default on `pointerdown`, so the selection and the keyboard stay. Thin gaps group them, not lines.

| Order | Button | Phone | Output | Keys |
|---|---|---|---|---|
| 1 | Bold, `i-text-b` | Shown | `strong` | Cmd+B |
| 2 | Italic, `i-text-italic` | Shown | `em` | Cmd+I |
| 3 | Underline, `i-text-underline` | More | `u` | Cmd+U |
| 4 | Strikethrough, `i-text-strikethrough` | More | `s` | Cmd+Shift+X |
| 5 | Text colour, `i-text-a-underline` | More | `span style="color: ..."` | |
| 6 | Highlight, `i-highlighter` | More | `span`, both properties, below | |
| 7 | Bulleted list, `i-list-bullets` | Shown | `ul` | Cmd+Shift+8 |
| 8 | Numbered list, `i-list-numbers` | More | `ol` | Cmd+Shift+7 |
| 9 | Link, `i-link` | Shown | `a` | Cmd+K |
| 10 | Quote, `i-quotes` | More | `blockquote` | |
| 11 | Attachment, `i-paperclip` | Shown | files | |

**Phone: five shown plus More** (`i-more`): 6 by 44 = 264px, fitting 320 as well as 375, and Send lives in the top row. Those five are what a short reply needs. **More opens a second row in place**, above the first, not a popover: a popover over a keyboard is fragile. Desktop shows all eleven in one row with Send at the far right. In the narrowest reading pane (416px at 64em), Send drops to its own row.

**Attachment:** `multiple`. Tray `.o-em-tray`: wrapping chips from `.o-wa-tray`'s parts: thumbnail or icon, name (ellipsis), size, `i-x`. Limits from `limits`, in danger under the tray: "Files up to 10 MB each." "Up to 9 MB of files an email." "Up to 20 files." Desktop also takes drop on the composer and paste.

**Link:** the existing `fb-modal` dialog, title "Add a link", fields Text and Address, Cancel and Add. The selection is saved before it opens and restored after. A bare `spa99.uk` gains `https://`. Only http, https and mailto: "Links start with https:// or mailto:". The server strips anything else, so refuse it here rather than lose it silently. Cursor in a link: the dialog also offers Remove.

**Colour choices, and why these.** The body travels in `.e-card` (`#FBF9EC`), and every value is in the allow-list (hex in `span`). Named, not just shown: `aria-label` and `title`. Desktop: a small popover from the button, opacity only, 120ms. Phone: replaces the More row, back on choosing.

| Choice | Value | On the card | On white (other clients) |
|---|---|---|---|
| Default | No `span` at all | 11.71 | 12.38 |
| Gold | `#8a5a2e` (`--office-gold-text`) | 5.54 | 5.86 |
| Red | `#8b1e1e` (`--color-danger`) | 8.63 | 9.12 |
| Soft | `#745f4f` (`--color-text-muted`) | 5.69 | 6.01 |

**Highlight:** one choice, on or off: `background-color: #f6e1c8; color: #492e21` (`--office-wa-out`, espresso, 9.74). **Always write both properties, and never output `mark`:** Outlook's Word engine and many clients ignore it, and browsers paint it yellow.

**Dark mode, the catch.** `_base.html` forces `.e-card span { color: #F5F2D8 !important }` in dark mode and under `[data-ogsc]`. So text colours become cream there, which is safe: the emphasis is lost, the word stays readable. Highlight is not safe: cream text on the pale wash is **1.12, unreadable**. Add one rule to both blocks:
```css
.e-card span[style*="background-color"] { color: #492E21 !important; }
[data-ogsc] .e-card span[style*="background-color"] { color: #492E21 !important; }
```
Send a real one to Apple Mail in dark mode before calling this done. The plain text copy drops colour and highlight, which is expected.

## 4. WhatsApp additions
All in the existing chat. Tokens as before. No new colours.

### Actions on a bubble
`.o-wa-acts`, on messages with a server id, only in the `open` state (no Reply or emoji into a closed window, STOP, view only or unconfigured).

- **Desktop:** on hover or focus of the line, Reply (`i-reply`) and, on his messages, Emoji (`i-smiley`) appear beside the bubble on its inner side, 2rem discs, `--office-surface`, `--office-shadow-1`, absolutely placed so nothing shifts. Opacity only, 120ms, under `(hover: hover) and (pointer: fine)`.
- **Phone:** tap the bubble. The row opens under it, in the flow. Tap elsewhere closes it. Ignore the tap when text is selected, or when it landed on a link, photo, video or audio control. Long press stays with the phone for selecting text. **No swipe:** his bubbles sit at the left edge, where the swipe belongs to the browser's Back.
- **Keyboard:** the log is one tab stop, with a roving tabindex on the lines. Up and Down move, Enter opens the actions, R replies, Escape closes. Focus outline 2px espresso.

### Reply
- **In the composer:** `.o-wa-quote` in the foot, directly above the composer: `--office-wa-inset` on the page tone, `--office-radius`, padding `--space-2`, `i-reply`. "Replying to Daniel" (or "Replying to Spa 99" for ours), `--office-text-xs` 600 espresso (9.78). Quoted text one line, ellipsis, `--text-sm` muted (5.19). `i-x` "Remove the quote", 2.75rem. Focus goes to the field. **No side bar** (BRAND).
- **The note, always shown with a quote, also with the keyboard up:** `--office-text-xs` muted, under the quoted text: **"On his phone this shows as a quoted line."** It is the honest difference from the tap-to-jump box he would see from a real WhatsApp reply. For a voice note it changes to: **"A voice note carries no quote on his phone."**
- **Post** `reply_to=<id>` with `send`, `send-media` or `send-voice`. `bad_reply` clears the quote, and says "That message can no longer be quoted." Count the 1600 limit on the final text: when `too_long` comes back, show the server's message and keep his text.
- **In a bubble, both directions:** `button.o-wa-reply`, first thing inside the bubble: `--office-wa-inset`, `--radius-sm`, padding `0.25rem var(--space-2)`, `margin-bottom: 0.25rem`, full width of the bubble. Who, `--office-text-xs` 600 **espresso** ("Spa 99" when `reply_to.direction` is out, else his first name; gold text would be 4.09 here). Text `--text-sm` muted (4.58 on out, 5.73 on in), two-line clamp, `reply_to.text` through `textContent`, `dir="auto"`. **Tap:** scroll to the original if it is loaded, with one soft fade of a `--office-sunken` overlay on it (`opacity` over 900ms, once; off under reduced motion). If it is not loaded, say "That message is further back." in the live region and a toast. `reply_to` null: nothing shows.
- The text in the bubble stays as typed. Do not show the `> ` line that goes to Twilio.

### Emoji
**Honest row.** On his messages only. Phone: in the actions row after Reply. Desktop: `i-smiley` opens a small popover from the button, opacity only, 120ms.

- **Five, calm:** thumbs up U+1F44D, folded hands U+1F64F, slightly smiling face U+1F642, OK hand U+1F44C, check mark button U+2705. 2.75rem targets, `aria-label="Send thumbs up"`, native glyphs. No laughing and no hearts: staff are writing to a guest.
- **Under them, every time,** `--office-text-xs` muted: **"Goes as a normal message, not a reaction."**
- **Tap sends at once**, as a plain message with no quote, because a quote plus one emoji reads worse on his phone than the emoji. It appears as its own bubble straight away, which also proves the note true. Six buttons at 375: about 320 of 343px. Below 370px wide the row wraps, Reply on its own line.

### Video
- **Attach:** `accept="image/jpeg,image/png,application/pdf,video/mp4"`, `aria-label="Attach a photo, PDF or video"`. Tray: `i-video`, name, size. **Refused**, in danger: "Photos, PDFs or MP4 videos only." (the server's words), "Videos up to 16 MB." An iPhone's own `.mov` will be refused: test what its picker hands over.
- **Display:** the existing `.o-wa-video`, bubble padding as `.has-photo`. `controls`, `playsinline`, `preload="metadata"`, no autoplay, `aspect-ratio` from `media.width` and `media.height` when known. **The time and tick go on their own line beneath, not the veil pill over the corner,** because the video's controls live there. Caption below as normal. Upload progress as a photo: 72% opacity, 3px bar.
- **Unplayable:** on the element's `error`, swap to the `.o-wa-file` card with `i-video`, "Video", size and download.

### Voice notes
**The microphone.** `button.o-wa-mic`, in the Send slot, 2.75rem disc, `--office-sunken`, espresso `i-microphone`, `aria-label="Record a voice note"`. Shown when the field is empty, no file is in the tray, **`contact.voice.available` is true** and `window.MediaRecorder` exists. Otherwise the muted Send disc shows, as today. Typing swaps it to Send instantly. Re-check `voice` on each poll.

**Tap to start, tap to send.** Not hold: hold fights text selection and is hard for a five-minute note. The permission prompt only ever follows that tap. Recording blurs the field, so the keyboard goes.

| State | Composer row | Notes |
|---|---|---|
| Asking | Mic disc at 50%, "Allow the microphone" `--text-sm` muted | No timer until the stream is live |
| Recording | `i-trash` (`aria-label="Cancel"`), then a danger dot 0.625rem + timer `0:12` tabular `--text-base` + "Recording" muted, then Send disc, ready | The dot is the one looping thing in the Office: `opacity` 1 to 0.4 over 1600ms, steady under reduced motion. Live region: "Recording" once, never each second |
| Last 30 seconds | Timer line on `--office-caramel-tint` pill: "Stops at 5:00" | From `max_seconds`. Told once to the live region |
| Stopped | Same row, no dot: "Stopped at 5:00" | At the limit, or when the page is hidden mid-recording (the phone locks). He still chooses Cancel or Send |
| Sending | Back to the normal composer; voice bubble appears at once with the 3px bar and queued tick | Conversion takes a moment: stays at "Sending" until the server answers |

Always stop every track on cancel, send, leaving the chat or a pane swap, or the phone's microphone indicator stays on. Post `file`, `duration`, `reply_to`, `gold` to `urls.send_voice`.

**Errors**, `.o-wa-tray-error`, `role="alert"`:

| Case | Words | Then |
|---|---|---|
| Permission denied | "Microphone blocked. Allow it in your browser settings, then try again." iPhone app: "Microphone blocked. Allow it in Settings, then try again." | Mic stays |
| No device | "No microphone found." | Mic stays |
| `voice_too_long` | "That voice note is over 5 minutes." | Bubble's failed row |
| `too_big` | "That voice note is too large to send." | Failed row |
| `bad_file` | "That recording could not be used. Try again." | Failed row, "Try again" resends the held recording |
| `voice_unavailable` | "Voice notes are not available right now." | Mic hides |

**The bubble:** existing `.o-wa-audio`, `controls`, `preload="metadata"`. Older iPhones may not play OGG: when `canPlayType('audio/ogg; codecs=opus')` is empty, show the `.o-wa-file` card instead ("Voice note", size, download). This also covers his own voice notes. Judge on the phone test.

### The message the Office cannot show
`kind: "other"`. An ordinary incoming bubble: time as normal, tail as normal. Text `--text-sm` muted (6.47): **"This message cannot be shown here."** No icon, no warning colour: it is not a fault, and may be a reaction. No Reply or emoji on it. The list preview reads "Message" (the server's). A quote of one reads "Message". Screen reader: "Daniel, 14:20: this message cannot be shown here."

## 5. Assistant rename and navigation
### Rename
Keep `office_chats`, `/chats/`, `section == "chats"`, `data-office-nav-item="chats"`, `data-chats-all`, `i-chat` and the code names: changing them moves links and hooks for nothing. Visible words only.

| File | Now | Becomes |
|---|---|---|
| `office/base.html` rail | Chats | Assistant |
| `office/base.html` More sheet | Chats | Assistant |
| `office/base.html` header title | Chats | Assistant |
| `office/chats.html` title | Chats \| Spa 99 Office | Assistant \| Spa 99 Office |
| `office/chats.html` h1 (sr-only) | Chats | Assistant |
| `office/chats.html` line | Chats with {{ person.label }}. Kept for 90 days. | What {{ person.label }} asked the assistant. Kept for 90 days. |
| `office/chats.html` line | Chats with the assistant. Kept for 90 days. | What people asked the assistant. Kept for 90 days. |
| `office/chat_detail.html` title | Chat \| Spa 99 Office | Assistant chat \| Spa 99 Office |
| `office/chat_detail.html` back link | Chats | Assistant |
| `office/chat_detail.html` h1 | Chat, {{ date }} | Assistant chat, {{ date }} |
| `office/_chats_card.html` h2 | Chats with the assistant | Assistant chats |
| `office/_chats_card.html` link | See all in Chats | See all in Assistant |
| `office/_chats_card.html` empty | No chats kept. Chats are deleted after 90 days. | Nothing kept. Assistant chats are deleted after 90 days. |
| `office/leads.html` filter chip | Gave email in chat | Gave email to the assistant |
| `office/_leads_rows.html` tag | via chat | via assistant |
| `whatsapp/_list.html` `aria-label` | Chats | WhatsApp chats |
| `whatsapp/_thread.html` back `aria-label` | Chats | Back to WhatsApp chats |
| `whatsapp/inbox.html`, `thread.html` pane `aria-label` | Chat | WhatsApp chat |
| `whatsapp/_notify_sheet.html` | This browser cannot show notifications. Chats still update here. | This browser cannot show notifications. Messages still update here. |
| `office/base.html`, `office.css` comments, `office/lists.py`, `office/profile.py`, `office/views.py` docstrings | Office > Chats | Office > Assistant |
| `docs/features/office-mobile.md` tab line | Chats | Assistant, and the new tabs |

**Leave alone:** "No chats yet", "Choose a chat." and "Start of this chat" inside WhatsApp (accurate there); the public site's "AI assistant. Chats are kept for 90 days."; the CSV column `gave_email_in_chat` (an export heading other tools may read).

**Tests to update:** `office/tests/test_insights_additions.py` lines 87, 110, 111 ("Chats with the assistant", "No chats kept", "Chats with sam@example.com"). Search `e2e/` for the same words.

### Side navigation
Order: Dashboard, Analytics, Registered, Leads, WhatsApp, **Email**, Approach list, Invited, Assistant, Gold. Email: `data-office-nav-item="email"`, count from `email_unread`, `data-office-badge="email"`, capped at 99+, `aria` " unread". The page title leads with the count: "(3) Email". In the installed app, `setAppBadge` is WhatsApp plus Email. Extend the service worker's "nothing for a chat he has open" to an open thread.

**Icons: Email takes the envelope. Leads changes to `i-address-book`.** Everyone reads an envelope as email, and a section called Email with any other icon would be the odd one. A lead is someone whose contact details we hold, which is what an address book says. It is also unlike Registered's two heads and Invited's person with a plus. Change the Leads `<li>` in `base.html` and any Leads empty state using the envelope. The Email buttons on the pages use the envelope too.

### Phone tabs: **Home, WhatsApp, Email, Gold, More. Leads moves to More, as its first row.**
- **Why not six tabs:** the icon pill is fixed at 56px (24 plus 16 each side) and six tabs give 53.3px at 320, so it overflows, and "WhatsApp" (about 57px) would be cut. `office-mobile.md` also caps tabs at five.
- **Why not one "Messages" tab:** the owner wants two channels plainly different.
- **Why Leads moves, not Home:** the phone user in `OFFICE.md` is Barry, who checks the day and approves Gold, so Home and Gold stay. Conversations come to staff through notifications many times a day, and each opens a man's page in one tap, so the Leads list is mostly a desk job. It is the same reasoning that moved Registered.
- **Cost:** starting from a new lead on a phone is one more tap. Moishe can reverse this by swapping Home and Leads. The rest holds either way.

**Changes:** `data-nav-overflow` on the Leads `<li>`. In `office.css`: dashboard stays first, `whatsapp` order 1, `email` order 2, `gold` order 3, More order 4, and update the comment. Sheet rows: Leads, Registered, Approach list, Analytics, Assistant, Invited. Add `leads` to the More `is-current` check. A list page that came from Leads still backs to it.

## 6. Journey email step
Public site, journey `--s-*` tokens, espresso surface, 7B motion. **No new tokens.** Words in `journey/copy.py` `GATE`.

### Final copy
| Key | Text |
|---|---|
| `mobile_label` | **Mobile (optional)** |
| `mobile_hint` | **Add it and the team can reach out with good offers.** |
| `errors.mobile` | That mobile does not look right. Check it, or leave it blank. |

Why: "optional" is in the label so nobody has to read further to know. The line gives one reason, in the owner's own words, and asks nothing. No "don't miss", no "exclusive", no "limited".

### Placement
Hint: `<p class="feedback mobile-hint" id="lead-mobile-hint" data-state="hint">` in `.mobile-group`, under `.mobile-row`, above `mobile.msg`. Add it to the input's `aria-describedby`. `--s-muted` on espresso: 6.50. An error replaces it, so the block does not grow: `.mobile-group:has(.feedback[data-state="error"]) .mobile-hint { display: none }`. Live validation with `optional=1`. A blank number is never an error. Update the "all required" comment on `renderGate`. No stars or marks on the two required fields.

### The tick
Now: "Yes, Spa 99 may email and WhatsApp me about opening. I can stop at any time."

It does not read properly, for two reasons. With no number, "WhatsApp me" permits something he has just chosen not to give. And it says "about opening", while the line above it now promises "good offers": the hint offers more than the tick allows. **Proposed:**

> Yes, Spa 99 may email me, and WhatsApp me if I add a number, about opening and offers. I can stop at any time.

This changes consent, so it is the owner's call, not a wording tweak: bump `CONSENT_VERSION`, and check the privacy notice covers offers. **If he keeps the tick as it is,** the hint must change to fit it: "Add it and the team can reach out about opening."

### Fit at 375 by 667 (calculated)
**The tick is the tight part.** `.check` keeps 24px side padding and a 16px gap, so its text is only 247px wide at 375. The new wording would run to 5 lines and put the step at 672, over the screen. So below 64em: `.lead-gate .check { padding-inline: var(--space-3); gap: var(--space-2) }` (text 271px wide, 4 lines) and the gap above the tick drops to `--space-3`.

| Part | Height |
|---|---|
| Header 64, padding 24, heading 40, gap 8, lead 52 | 188 |
| Gap to the fields | 24 |
| Three fields and their gaps | 196 |
| Hint, with its 4px gap | 24 (44 if it wraps) |
| Gap to the tick | 16 |
| Tick: 4 lines at 25.6, 16 padding | 118 |
| Action bar | 72 |
| **Total** | **638 (658 if the hint wraps)** |

It fits, with 9 to 29px spare, and the page note stays hidden on a phone. The hint is about 330 of 335px by estimate, so it may wrap: both cases fit. If the screenshot runs over, tighten `.lead-gate .screen-head .lead` first, and never shrink the fields or the 16px type. At 320 by 568 the page scrolls and the bar stays. If the owner keeps today's tick, it takes 3 lines and there is 25px more room.

## 7. Motion
Restrained, BRAND 7B, tools are not stages. All through the tokens, so reduced motion is free.

| What | Motion | Why |
|---|---|---|
| Message opening or collapsing | Height instant; content fades in over `--office-dur-swap` | BRAND: never animate height |
| Composer opening, phone | Opacity plus 8px rise, `--office-dur-swap`, `--ease-soft` | Says where it came from |
| Composer opening, desktop | Instant | Used all day |
| Colour popover, emoji popover, bubble actions | Opacity, 120ms | Hover-rate things stay near-invisible |
| More row, toolbar pressed, status words, chips, row moves, frame height | None | State, read at a glance |
| Bubble quote jump | One fade of an overlay's opacity, 900ms | Shows where he landed |
| Recording dot | Opacity loop, 1600ms | Real state: the microphone is on |
| Buttons | Existing press feedback | |

No sound, no bounce, no sideways travel.

## 8. Accessibility and safety
- **Nothing from an email or a message builds HTML in the page**, except the server's cleaned `body_html` for ours. Subject, names, addresses, filenames, previews and quotes: `textContent`.
- Thread: `article` per message with `aria-label="From Daniel, 3 November, 14:20"`. Collapsed header: `button`, `aria-expanded`. The scroller is not `role="log"` (it is a document, not a stream). New mail: one polite sr-only line, "New email from Daniel".
- Frame: `title` per message. Keyboard reaches its links.
- 2.75rem targets on touch. Hover only under `(hover: hover) and (pointer: fine)`. `dir="auto"` on anything he or staff wrote.
- `forced-colors`: sheets get a 1px border; pressed toolbar buttons keep `aria-pressed` with a 2px outline.
- No one-sided accents: not on quotes, unread rows, notes or the selected row.

## 9. To judge at first screenshots (375, 1440)
In order of importance:
1. **Does Email read as email at a glance beside WhatsApp?** Subject, sender and the plain page tone against the wall. If it looks like a card-heavy dashboard on desktop, drop the sheets' shadow first.
2. Frame fit with a real newsletter, a real Outlook reply and a plain Gmail reply at 375. Scale floor 0.6, height after pictures load, folding.
3. Reply composer on a real iPhone: Send and toolbar with the keyboard up, nothing jumps, closing keeps the draft.
4. The clickable greyed line against the static one: is the underline enough to invite a click?
5. Highlight in Apple Mail, Gmail and Outlook, light and dark. The `_base.html` rule must hold.
6. Row at 320: person, time and Gold badge sharing line 1.
7. Microphone on a real iPhone: permission, recording while the phone locks, playback of the OGG.
8. Eleven toolbar icons at 1024: are text colour and highlight told apart?
9. The gate at 375 by 667 and 320 by 568.
