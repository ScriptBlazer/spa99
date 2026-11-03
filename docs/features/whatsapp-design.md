# WhatsApp in the Office, and the journey gate: design brief
Spec: `docs/features/whatsapp.md`. Builds on `docs/design/OFFICE.md`, `docs/features/office-mobile.md`, `docs/features/office-outreach-design.md`. `docs/BRAND.md` wins. Desktop = `min-width: 64em`, phone = below (tablets follow the phone, as in the rest of the Office). Test at 320, 375, 414 and 1440, and on a real iPhone, installed and not installed: keyboard, safe areas and push cannot be judged in emulation.

- **Design read.** A working chat tool for staff who already know WhatsApp. The shape, habits and ticks are WhatsApp's, so nobody has to learn anything. The room is ours: warm paper, gold tint, espresso, the swan faintly in the wall, Signika and Figtree. Dials: variance 2, motion 2, density 5. Clarity beats theming wherever they disagree.
- **Not rendered yet.** The sandbox refused to start Chromium, so the values below are calculated, not seen. Section 11 lists what to judge at the first screenshots.

## 0. Tokens
**Proposed additions** (Office only, `office-tokens.css` under `.office`; copy them into `OFFICE.md` section 2 and the "Office tokens" line of `BRAND.md`, marked proposed). One new colour, the rest aliases.

| Token | Value | Use | Contrast |
|---|---|---|---|
| `--office-wa-wall` | `var(--office-sunken)` | Thread wall | Espresso 10.13, muted 5.38 |
| `--office-wa-in` | `var(--office-surface)` | Incoming bubble | Espresso 12.19, muted 6.47, against wall 1.20 |
| `--office-wa-out` | `#F6E1C8` **new**, gold 35% over surface | Outgoing bubble | Espresso 9.74, muted 5.17, gold-text 4.61, danger 7.18, against wall 1.04 (hue and side carry it, as in WhatsApp) |
| `--office-wa-inset` | `rgb(73 46 33 / 0.07)` | Code, quote, PDF card, inside a bubble | On out: espresso 8.63, muted 4.58. On in: espresso 10.8, muted 5.73 |
| `--office-wa-pattern` | `0.6` | Opacity of the swan layer (about 4.8% espresso) | Decoration, swan against wall 1.09. Nothing reads on it, but muted would still be 4.96 and danger 6.88 |
| `--office-wa-tick` | `var(--color-control-line)` | Queued, sent, delivered | 3.15 on out, 3.94 on surface, 3.28 on sunken (UI, 3:1 needed) |
| `--office-wa-tick-read` | `var(--office-text)` | Read | 9.74 on out, 12.19 on surface |
| `--office-wa-list-w` | `clamp(19rem, 26vw, 24rem)` | Chat list pane | |
| `--office-wa-bubble-max` | `36rem` | Longest bubble, desktop | |
| `--office-wa-avatar` | `3rem` | List avatar (2.5rem in the thread header) | |
| `--office-wa-mono` | `ui-monospace, "SF Mono", Menlo, Consolas, monospace` | Code only; the brand has no mono | |

Existing and reused: `--office-page`, `--office-surface`, `--office-sunken`, `--office-row-alt`, `--office-muted`, `--office-gold-text`, `--office-danger`, `--office-caramel-tint`, `--office-overlay`, `--office-shadow-1/2/3`, `--office-radius(-lg)`, `--office-pill`, `--office-text-xs`, `--office-dur-swap`, `--office-dur-lift`, `--ease-soft`, `--radius-sm`, `--radius-md`, `--color-tier-edge`, `--color-gold`, `--color-cream`, `--color-veil`, `--chat-text`, `--control-h`, `--space-*`, `--text-*`.

- **New font file (proposed):** Figtree Italic, self-hosted (OFL), latin subset, `figtree-latin-italic.woff2`, weights 400 to 600, declared in the Office CSS only. The site has upright Figtree only, so `_italic_` would otherwise be a browser slant. Figtree stops at 600, so `*bold*` is 600, and names in the list are 600 too.
- **New icons** in `_icons.html` (24 grid, 1.5 stroke, `currentColor`, redrawn from Phosphor regular): `i-whatsapp`, `i-tick`, `i-ticks`, `i-clock`, `i-arrow-down`, `i-arrow-clockwise`, `i-file-pdf`, `i-bell`, `i-bell-slash`, `i-share` (the iOS square and arrow), `i-mobile`. `i-chat` stays with the assistant's Chats.
- **Naming.** The section is always "WhatsApp". "Chats" stays the assistant. Classes `o-wa-*`, new CSS file `office-whatsapp.css`.

## 1. The inbox `/whatsapp/`
`section = "whatsapp"`. In that section `.o-main { padding: 0; max-width: none }` and the document does not scroll; only the panes do. No reveal animation here: this is a tool, and it should simply be there.

### Desktop
- The shell stays: rail, then `.o-header` with the title "WhatsApp" and the person disc.
- `.o-wa` is one card under the header: `display: grid; grid-template-columns: var(--office-wa-list-w) minmax(0, 1fr); height: calc(100dvh - var(--office-header-h) - var(--space-4)); margin: 0 var(--space-4) var(--space-4) 0; border-radius: var(--office-radius-lg); box-shadow: var(--office-shadow-1); overflow: hidden`.
- List pane `--office-surface`. Thread header and composer `--office-page`. Wall `--office-wa-wall`. No rules between them; tone does the separating (OFFICE rule 5).
- Choosing a chat swaps the thread pane and pushes `/whatsapp/<id>/`, so Back and deep links work. The selected row fills `--office-sunken`.
- Nothing chosen: wall, swan mark 3rem at 24% espresso, then "Choose a chat." in muted on a surface pill. No mark if there are no chats at all (section 2).

### Phone
- **List** at `/whatsapp/`: normal shell, header and tabs; rows straight on `--office-surface`, full bleed, with the list as the scroller.
- **Thread** at `/whatsapp/<id>/`: `data-office-detail` plus `data-wa-thread`. Header and tabs hide. `.o-wa-thread` is a grid (`auto 1fr auto`) filling the screen.
- **Keyboard-safe. `100dvh` is not enough:** iOS does not shrink `dvh` for the keyboard, and it also ignores `interactive-widget`. So:
  - `height: var(--wa-vh, 100dvh)` on the thread.
  - A small `visualViewport` listener (`resize` and `scroll`) sets `--wa-vh` to `visualViewport.height`, pins the thread to `offsetTop`, and sets `data-keyboard` when the viewport has shrunk by more than 120px. Works the same on Android.
  - Add `interactive-widget=resizes-content` to the viewport meta in `base.html`.
  - `html, body { overscroll-behavior: none }` in this section; panes `overscroll-behavior: contain`.
- **Safe areas:** thread header `padding-top: env(safe-area-inset-top)`; composer `padding-bottom: max(var(--space-2), env(safe-area-inset-bottom))`, dropping to `--space-2` under `[data-keyboard]`; left and right insets on both, and on the scroller, for landscape.
- Back is the existing `.o-back` (`i-chevron-left`, 2.75rem target, no label), to `/whatsapp/`, keeping the list's scroll. Keep the swipe from the edge to the browser.
- Toasts sit above the composer in this section.

### Rail and tabs
- **Rail:** new item directly after Leads. `i-whatsapp`, "WhatsApp", `.o-badge-count` with `data-office-badge="whatsapp"`. Shown to anyone who may see chats.
- **Phone tabs, my recommendation: WhatsApp takes a tab, and Registered moves into More.** Tabs become Home, Leads, WhatsApp, Gold, More. A chat is reached many times a day and from notifications, so it cannot sit behind a sheet. Registered is the least urgent of the four: staff usually reach a registered man from a chat, a search or a Gold page. Add `data-nav-overflow` to the Registered `<li>`, add it as the first row of the More sheet, and add `people` to the More `is-current` check.
- **Badge:** the number of chats with unread messages, not messages, capped at "99+". `aria` text " unread". "WhatsApp" fits 64px at 320. The page title leads with the count: "(3) WhatsApp". In the installed app `navigator.setAppBadge(count)` mirrors it.

## 2. Chat list
- **Head** (`.o-wa-listhead`, sticky in the pane): search field, 2.5rem, `--office-sunken`, pill, `i-search`, placeholder "Search name or number" with `aria-label`, `type="search"`, `--text-base` so iOS does not zoom. Under it chips (`.o-chip`, 2rem, 2.75rem under `pointer: coarse`): **All**, **Unread**, **No reply**. Search filters as he types (250ms debounce, server side), by name and number. Message text search is later.
- **Row** (`a.o-wa-row`): `display: grid; grid-template-columns: var(--office-wa-avatar) minmax(0, 1fr) auto; column-gap: var(--space-3); min-height: 4.5rem; padding: var(--space-2) var(--space-3); border-radius: var(--office-radius)`. Margin 0 `--space-2` within the pane. No rules. Hover (fine pointer) `--office-row-alt`, selected `--office-sunken`, press `scale(0.99)` on touch.

| Part | Style |
|---|---|
| Avatar `.o-wa-avatar` | Disc, Signika 500 `--text-base`, initials. `--office-sunken` with espresso; on a selected row `--office-surface`. A Gold person: gold fill, espresso (6.17). Unknown name: `i-mobile` instead of initials |
| Name | Figtree 600 `--text-base`, one line with ellipsis. Order: name staff typed, name from the gate, WhatsApp profile name, number |
| Time | `--office-text-xs` muted, top right. Today "14:32", "Yesterday", weekday within 7 days ("Mon"), else "3 Nov" |
| Preview | `--text-sm` muted, one line with ellipsis, plain text with the markers stripped. Ours starts with the tick; a failed one starts with `i-warning` in danger and reads "Not sent". A photo reads "Photo", a PDF its name |
| Unread | Time espresso 600, preview espresso 500, gold `.o-badge-count` bottom right. No dot, no side stripe (BRAND) |
| Opted out | Quiet badge bottom right, `--office-sunken`, muted, "Opted out" |
| No reply | We wrote last, he has never replied, more than 3 days ago: quiet badge "No reply". Nothing shouts; the chip finds them |

Newest first. A row that moves to the top moves instantly, with no animation: the list is read in a glance, and travel would make it harder.

- **Empty states** (centred, muted, no illustration): no chats, "No chats yet. Start one from a lead, or wait for him to write." Search, "Nobody by that name or number." Unread, "Nothing unread." No reply, "Everyone has replied."
- **Loading:** rows are server rendered. When swapping, dim to 0.5 only after 300ms (Office rule). No spinner.

## 3. Thread
**Header** `.o-wa-head`: `min-height: 3.5rem`, 4.5rem from 64em so it lines up with the shell header; `--office-page`; `box-shadow: var(--office-shadow-scrolled)`.
- Avatar 2.5rem, name 600 `--text-base`, number `--text-sm` muted beneath (selectable, in international format).
- **His page.** Desktop: quiet pills to the right of the name block, `o-badge o-badge--type` with `i-chevron-right`: "Lead", "Registered" or "Gold"; both when he is both. Phone: the name block itself is the link, with a chevron, going to Gold if he has an application, otherwise his person or lead page.
- **Window state.** Desktop: a quiet pill at the far right, "Open, 5h left" (`--office-sunken`, muted), "Closed" or "Opted out". Phone: no pill; the line above the composer does the job and the header has no room.
- **Wall** `.o-wa-wall`: `position: relative; isolation: isolate; background: var(--office-wa-wall)`. The swan is a `::before` on this fixed pane, never on the scroller, so scrolling does not repaint it:
`content: ""; position: absolute; inset: 0; z-index: -1; background: var(--office-text); opacity: var(--office-wa-pattern); mask: url("../img/swan-pattern.svg") 0 0 / 200px 240px; -webkit-mask: same`.
The file's fill is gold at 8%, invisible on a light wall, so it is used as a mask for its shape and alpha. Off under `forced-colors` and `prefers-contrast: more`. **All text on the wall sits on something opaque**, so the pattern can never hurt reading.

- **Scroller** `.o-wa-scroll`: `overflow-y: auto; overscroll-behavior: contain; padding: var(--space-3)` (`--space-4` from 64em), `role="log"`, `aria-label="Messages with Daniel"`.
- **Bubble** `.o-wa-msg` (`--in`, `--out`): opaque; `max-width: min(var(--office-wa-bubble-max), 72%)`, 85% on phone; `padding: 0.375rem 0.625rem 0.3125rem`; `border-radius: var(--radius-md)`; `box-shadow: inset 0 0 0 1px var(--color-tier-edge), 0 1px 1px rgb(73 46 33 / 0.08)` (same warm family as `--office-shadow-1`). Text `--text-base` phone, `--chat-text` from 64em, `line-height: var(--leading-snug)`, `overflow-wrap: anywhere`, `dir="auto"` (a Hebrew or Arabic message must set itself right to left), line breaks kept, selectable. Incoming left, outgoing right.
- **Tails: yes, small**, because that is what makes it read as WhatsApp at once. Only the first bubble of a group: `::before`, 0.5rem by 0.75rem, `background: inherit`, `clip-path: polygon(...)`, at the top outer corner, with that corner's radius 0. Hidden under `forced-colors`.
- **Grouping:** same sender (same staff member for ours) within 5 minutes is one group, 0.125rem apart. A new group is `--space-2` from the last.
- **Time and ticks** `.o-wa-meta`: inside the bubble, bottom right, `--office-text-xs`, muted, tabular, on every bubble. It sits on the last line of text when there is room: absolutely positioned, with an `inline-block` spacer after the text (`--meta-w`: 3.25rem in, 4.75rem out). When the bubble ends in a block (list, quote, code) it takes its own line.

| Status | Icon | Colour | Screen reader |
|---|---|---|---|
| Queued | `i-clock` | `--office-wa-tick` | Sending |
| Sent | `i-tick` | `--office-wa-tick` | Sent |
| Delivered | `i-ticks` | `--office-wa-tick` | Delivered |
| Read | `i-ticks`, stroke 2 | `--office-wa-tick-read` (espresso) | Read |
| Failed | `i-warning` | `--office-danger` | Not sent |

Icon 1rem by 0.75rem. Pale to dark espresso is the read signal: a brand colour, and it survives colour blindness. Exact time and status on `title`. Ticks change instantly.

- **Failed:** the bubble stays. Below it, right aligned on a surface pill: `i-warning` and a reason in `--office-danger` `--text-sm` (8.98), then `o-quiet` "Try again" with `i-arrow-clockwise` when it can be retried. Reasons: "Not sent. Try again." / "Not delivered. He may not be on WhatsApp." / "Not sent. The window has closed." / "Not sent. Sending has stopped, check the Twilio balance." Twilio's codes never show.
- **Author:** on the first outgoing bubble of a group, only when more than one staff member has written in this chat: first name, `--office-text-xs` 600 `--office-gold-text` (4.61). The title on the time gives full name and time either way.
- **Template label:** first line inside the bubble, `--office-text-xs` muted, "Template: Lead follow up" (the `spa99_` name, humanised). No fill, no icon.
- **Date divider** `.o-wa-day`: centred pill, `--office-surface`, `--office-text-xs` 600 muted, `position: sticky; top: var(--space-2)`. "Today", "Yesterday", "Monday" within 7 days, else "3 Nov 2026".
- **Unread divider** `.o-wa-unread`: full width band, surface at 72%, `--office-text-xs` 600 espresso, centred, "2 unread messages". The chat opens with it a third of the way down the pane; with nothing unread, at the newest message. It stays until he leaves the chat.
- **Images** `.o-wa-photo`: bubble padding 0.1875rem; `button` with `aria-label="Open photo"`; inner radius 9px; `max-width: min(18rem, 100%)`, `max-height: 20rem`, `object-fit: cover`. **`aspect-ratio` from stored width and height** (backend to store them), so nothing jumps while scrolling. `--office-sunken` until loaded, `loading="lazy"`. Caption below as normal text. No caption: the meta sits on a small `--color-veil` pill over the corner in cream (6.5 or more).
- **Lightbox** `dialog.o-wa-lightbox`, `showModal()`: `--color-veil` over all, photo `object-fit: contain` within safe areas, no card. Top right: Download and close, 2.75rem discs, cream icons. Under it, in cream: who and when. Native pinch zoom stays (`touch-action: pinch-zoom`). Escape and backdrop close, and focus returns. Fade only, `--office-dur-swap`.
- **PDF card** `.o-wa-file`: a link inside the bubble, `--office-wa-inset`, `--office-radius`, `min-height: 3.5rem`, padding `--space-2`. `i-file-pdf` 1.75rem, name 500 `--text-sm` (two-line clamp), "PDF, 1.2 MB" `--office-text-xs` muted, `i-download` at the right. Caption below.
- **Upload progress:** sending shows the bubble at once, the photo at 72% opacity, with a 3px bar at its foot: espresso, `transform: scaleX()`, origin left, linear. Queued tick until it lands. PDF the same, along the foot of the card. A failed upload shows the failed row. Before sending, section 4 has the tray.
- **Jump to latest** `.o-wa-jump`: appears when the bottom sentinel leaves view by more than a screen (IntersectionObserver, no scroll listener). 2.75rem disc, `--office-surface`, `--office-shadow-2`, `i-arrow-down`, bottom right, `--space-3` above the composer. Fade and 8px rise, `--office-dur-swap`. `aria-label="Go to the latest message"`.
- **New message while scrolled up:** his position never moves. The jump disc gains a gold count badge, and an sr-only polite live region says "New message from Daniel". At the bottom (within 6rem), it follows to the new message. His own send always goes to the bottom.
- **Older messages:** a top sentinel loads 30 more about a screen early. Quiet line "Loading earlier messages" `--office-text-xs` on a surface pill, no spinner; at the end, "Start of this chat". Keep his place by adding the height difference to `scrollTop`: iOS Safari has no `overflow-anchor`.
- **Arrival motion:** incoming, opacity 0 to 1 and `translateY(4px)` to 0 over `--office-dur-swap`, `--ease-soft`. His own, opacity only over 120ms; it answers a keystroke, so it must feel immediate. No stagger, and nothing animates on first load. Ticks, list changes and composer growth do not animate. All off under reduced motion through the tokens.
- **Types we cannot show** (voice note, video, sticker, location, contact): a muted card in the same PDF card form, "Voice note" and "Download" if we hold the file, otherwise "Voice note. This type cannot be shown here." See decisions.
- **Not in this round:** reply to a specific message, reactions, typing indicator, emoji picker (phones have the keyboard; desktops the system panel). His emoji render as they come.

## 4. Formatting and composer
**Rules are WhatsApp's.** Escape first, then format; no HTML from message text, ever. Formatted on the server by one filter, so bubbles, previews and templates cannot disagree. Markers only count at word boundaries with no space inside them (`*bold*`, not `* bold *`). Nothing formats inside code. The marks are removed from the bubble, as in the app.

| Typed | Class | Style |
|---|---|---|
| `*bold*` | `strong` | Weight 600 |
| `_italic_` | `em` | Figtree Italic |
| `~strike~` | `s` | Line through, `text-decoration-thickness: 1px` |
| `` `code` `` | `code` | `--office-wa-mono`, 0.875em, `--office-wa-inset`, radius 4px, padding 0.0625rem 0.25rem |
| ` ```block``` ` | `pre` | Same font, `--office-wa-inset`, `--radius-sm`, padding `--space-2`, `margin-block: var(--space-1)`, keeps spaces, wraps (no sideways scroll in a bubble) |
| `- ` or `* ` | `ul` | Real list, `padding-inline-start: 1.125rem`, 0.125rem between items |
| `1. ` | `ol` | Same, tabular numbers |
| `> ` | `blockquote` | `--office-wa-inset` fill, `--radius-sm`, padding `0.25rem var(--space-2)`, muted text (4.58 or more). **No side bar**: WhatsApp's stripe is a one-sided accent, which BRAND forbids |
| `https://...` | `a` | Espresso, underlined, offset 0.15em, `overflow-wrap: anywhere`, `target="_blank" rel="noopener noreferrer nofollow"`. Bare `www.` links too. Numbers and emails are not linked |

**Composer** `.o-wa-composer`: `--office-page`, padding `--space-2` `--space-3`; grid `auto minmax(0, 1fr) auto`, `align-items: end`, `gap: var(--space-2)`.

- **Attach** `button.o-wa-attach`, 2.75rem, `i-paperclip`, `aria-label="Attach a photo or PDF"`. One hidden file input, `accept="image/jpeg,image/png,application/pdf"`: the phone's own sheet already offers camera, library and files, so no menu of ours. Desktop also takes drag on to the thread (wall shows a surface pill, "Drop to attach") and paste.
- **Field** `textarea.o-wa-input`: `--office-surface`, 1px `--color-control-line` edge (3.58), radius 1.375rem, `min-height: 2.75rem`, padding 0.625rem `--space-3`, **always `--text-base`** so iOS never zooms. Placeholder "Message". `aria-label="Message to Daniel"`, `autocapitalize="sentences"`, `spellcheck`, `dir="auto"`, focus 2px espresso outline with 1px offset.
- **Growth:** `field-sizing: content` with a `scrollHeight` fallback; no animation. Up to 6 lines on phone, 10 on desktop, then scrolls inside (3 lines under `[data-keyboard]` on a screen under 40rem tall).
- **Send** `button.o-wa-send`, 2.75rem disc, espresso, cream `i-paper-plane` (10.95), `aria-label="Send"`. Empty: `--office-sunken`, muted icon, `aria-disabled`. Press `scale(0.97)`. Prevent default on `pointerdown` so tapping it does not close the keyboard.
- **Enter:** under `(hover: hover) and (pointer: fine)`, Enter sends, Shift+Enter is a new line. On touch, Enter is a new line and the button sends (`enterkeyhint="enter"`). Cmd or Ctrl+Enter sends on both. Never send during IME composition (`isComposing`).
- **Formatting help: a hint, no toolbar.** A toolbar costs a row on a phone with the keyboard open, and staff already type this on WhatsApp. Desktop only: on focus, one line under the field, `--office-text-xs` muted, each shown in its own style: **\*bold\*** _\_italic\__ ~\~strike\~~ and "Shift + Enter for a new line". Cmd+B and Cmd+I wrap the selection in `*` and `_`. The field itself stays plain text, sent as typed.
- **Draft:** kept per chat in `sessionStorage`; restored on return, cleared on send.
- **Tray** `.o-wa-tray` above the field when a file is chosen: 3.5rem thumbnail or `i-file-pdf`, name (ellipsis), size muted, `i-x`. One file a message. The text becomes the caption, placeholder "Add a caption". Refused file, in danger: "Photos up to 5 MB, PDFs up to 16 MB." or "Photos or PDFs only." (backend to confirm the limits with Twilio).
- **Limit:** from the server, `max`; I expect 1,600 (Twilio's body limit; backend to confirm). Silent until 100 from the end, then a right-aligned `--office-text-xs` muted line, "1510 of 1600". Over: danger, "Too long by 40 characters.", send `aria-disabled`. Never cut pasted text, and never use `maxlength`, which cuts silently.
- **Offline:** quiet surface pill above the composer, "No connection. Trying again." Anything sent meanwhile shows the failed row.
- **View only** (no `can_edit`): the composer becomes a muted line, "View only. Sending is for Approvers and Admins." Same for templates.

## 5. The 24-hour window
Every state lives in one slot, `.o-wa-window` plus the composer, so the thread height barely changes. Counts from `data-window-ends`, recalculated each minute on the client.

| State | Above the composer | Composer |
|---|---|---|
| Open, 1h or more | `--office-text-xs` muted, centred: "Window closes in 5h". Hidden under `[data-keyboard]` | Normal |
| Open, under 1h | Pill `--office-caramel-tint`, espresso 600 (10.25), `i-clock`: "Window closes in 40 minutes", then "in under a minute". Always shown; told once to the live region | Normal |
| Closed | None | Replaced, below |
| Template sent, no reply | None | "Template sent. The window opens when he replies." plus secondary "Send another" |
| No messages yet | Wall shows a surface pill "No messages yet." | "Start with a template." plus primary "Choose a template" |
| Opted out | None | Muted: "He replied STOP. He gets no more messages." No buttons. History stays readable |
| No mobile | Wall shows a surface pill "No mobile on file." | Primary "Add a mobile" (section 6 dialog) |

- **Closed** `.o-wa-closed`: `--office-page`, safe-area padding, one line and one button. Desktop in a row, phone stacked. "Window closed. Send a template to reopen." `--text-sm` espresso, primary `btn` "Choose a template". If it closes while he types, the draft stays in storage and the send fails politely with the failed row.
- **Template picker** `dialog.o-sheet.o-wa-tpl`: phone is the existing bottom sheet (`85dvh`, scroll, `modal-in`); desktop a centred dialog, `max-width: 44rem`, `--office-radius-lg`, `--office-shadow-3`, two columns (choices and fields left, preview right). Title "Choose a template". Only approved `spa99_` templates, as Twilio lists them.

1. **Choose.** Tiles `.o-wa-tpl-item` as radios: humanised name 600 ("Lead follow up"), first line of the text in muted, `min-height: 4rem`, `--office-sunken`; chosen is espresso fill with cream text and a check, instantly. With one template it starts chosen.
2. **Fill.** One `fb-modal-field` per variable, using a label from the backend ("First name"), never `{{1}}`. First name comes pre-filled. Empty fields are required.
3. **See.** Preview: a real outgoing bubble on a small wall panel (with the swan), template label included. The server renders the body with each variable as `<span data-var="1">`, and JS only sets `textContent`, so no second formatter is needed. An empty variable shows its label, muted, in square brackets.
4. **Send.** Primary "Send template", working "Sending", sticky at the foot on phone. Muted line above it: "Charged per message. His replies are free." Disabled until complete. On success the sheet closes, the bubble appears, and on a Gold application the toast says "Marked Contacted."

Empty: "No templates approved yet. Add them in System > WhatsApp." Link only if he can open System.

## 6. Lead, person and Gold pages
**The button.** Email Message and the Respond dialog go; their dialogs and the "Unsubscribed from news" warning go with them. Send guide and Add to list are untouched.

- **Lead and person**, Reach out card: **WhatsApp**, `btn btn-primary btn-block`, `i-whatsapp`, first in the card. It is now the main thing to do on these pages. Phone: side by side with "Add to list", as today.
- **Gold**, `.o-actions-more`: **WhatsApp** | **Send guide**, `btn btn-secondary` so Approve stays the one primary. It replaces Respond and opens the chat. When a message is sent the application becomes Contacted. The phone decision bar does not change. `?do=respond` and the Respond link on `gold_confirm.html` now go to the chat; the link reads "WhatsApp".

| State | Looks like | Does |
|---|---|---|
| Has a chat, nothing unread | WhatsApp | Opens `/whatsapp/<id>/` |
| Unread | WhatsApp + gold `.o-badge-count` pushed right, " unread" for screen readers | Same |
| Mobile, no chat | WhatsApp, one muted line under: "No messages yet." | Opens the thread with the picker open |
| Opted out | WhatsApp in `btn-secondary`, muted line: "He replied STOP." | Opens the history |
| No mobile | `btn btn-secondary btn-block`, `i-plus`, **"Add a mobile to WhatsApp him"**. Spans the full width on phone and in the Gold grid (`grid-column: 1 / -1`), with Send guide below; the words do not fit half of 335px | Opens the dialog |
| View only, chat exists | WhatsApp in `btn-secondary` | Reads the chat |
| View only, no mobile | Nothing | |

- **Dialog** `fb-modal.o-dialog[data-dialog=mobile]`: title "Add a mobile". Body "So the team can WhatsApp him." Fields, prefilled if known: **First name** (`autocomplete="off"`, `autocapitalize="words"`) and **Mobile** (`type="tel"`, `inputmode="tel"`, `autocomplete="off"`). Hint "UK numbers can start with 07. Otherwise add the country code." Errors under the field, in danger: "That does not look like a mobile number." and "This number is already on Daniel Cohen." with a link to him. Actions **Cancel** / **Save** (working "Saving"). Toast "Mobile saved." The button becomes WhatsApp without a reload. The same dialog is the "Change" `o-quiet` link beside Mobile in his details.
- **Timeline** (`_timeline.html`, `kind="whatsapp"`, label links to the chat through `e.href`; not one line per message, or it drowns everything else):
- "First WhatsApp sent by Moishe", detail is the template's name.
- Per day: "WhatsApp: 3 from him, 2 from us", linking to the chat. Detail is his last message, clamp 3.
- "He replied STOP", "Mobile added by Moishe", "Mobile changed by Moishe", "Gold application marked Contacted by Moishe".
- A send that finally failed: label "WhatsApp not sent", red like an email bounce (`o-danger`, `i-warning`), detail is the reason.

## 7. Notifications and PWA
- **Manifest:** name "Spa 99 Office", short name "Office", `display: standalone`, `start_url: "/"` (the Office home; notifications deep-link to the chat, so no need to start in it), `scope: "/"`, `theme_color` and `background_color` `#F4F2ED` (`--office-page`, already the Office's `theme-color`).
- **App icon:** gold swan on an espresso tile, square, swan within the central 60% (the maskable safe zone), 192, 512 and maskable 512, plus 180 `apple-touch-icon`, opaque as iOS needs. Monochrome swan for the notification badge on Android. Not the WhatsApp logo: this is the Office.
- **Status bar:** `apple-mobile-web-app-status-bar-style: default`, as the page is light. **Splash:** Android builds its own from the manifest. iOS: page tone with the espresso swan centred, 4 common sizes through `apple-touch-startup-image`; anything else falls back to plain page tone. Not an espresso splash, which would flash on its way to a light page.
- **No offline shell.** The service worker handles push and a single "No connection" page; never caches staff data.
- **Install card** `.o-wa-install`, top of the chat list (phone), hidden in `display-mode: standalone`. Dismiss `i-x`, remembered 30 days per device. `--office-caramel-tint`, `--office-radius`, padding `--space-3`.
- **iPhone in Safari:** "Add the Office to your Home Screen, to get notifications." Then a numbered list, with the real icon inline: "1. Tap Share `i-share`" "2. Choose Add to Home Screen" "3. Open Spa 99 Office from your Home Screen". Below iOS 16.4: no card, since push cannot work.
- **Chrome and Edge, phone or desktop** (when `beforeinstallprompt` fires): "Install the Office for notifications." and secondary "Install", which opens the browser's prompt. Desktop puts this in the notifications sheet, not the list.
- **Others** (Firefox, desktop Safari): no card.
- **The control.** There is no settings page today, so a new row in the person menu `.o-menu`: `i-bell`, "Notifications", state in muted at the right. It opens `dialog.o-sheet.o-wa-notify`. A one-time card sits at the top of the list once he has installed and not chosen yet. **The browser's permission prompt only ever follows a tap**, never a page load.

| State | Row | Sheet shows |
|---|---|---|
| Off | Off | "Turn on notifications for new messages on this device." Primary "Turn on notifications", working "Asking your phone" |
| On | On | Switch on, "On for this device." Secondary "Send a test". `o-quiet` "Turn off" |
| Muted | Muted, `i-bell-slash` | "Muted. Messages still arrive here. You get no notifications on any device." Switch **Mute all notifications** |
| Blocked | Blocked | "Blocked by your browser. Allow notifications for office.spa99.uk in its settings, then come back." On iPhone: "Settings, Notifications, Spa 99 Office." |
| iPhone, not installed | Add to Home Screen | The three steps from the install card. Nothing to turn on yet |
| Not supported | Not available | "This browser cannot show notifications. Chats still update here." |

Mute is per person, the switch appears in On and Muted. On/off is per device. No per-chat mute in this round.

**Notification text.** Title: his name, else the number. Body: first line, markers stripped, up to 80 characters. Photo: "Sent a photo". PDF: "Sent a PDF: guide.pdf". Other: "Sent a voice note". `tag` is the chat id, so a second message replaces the first; after two: "3 new messages". Tapping opens `/whatsapp/<id>/`, focusing an open Office window if there is one. No notification for a chat he has open and visible. No actions on the notification. Test: "Spa 99 Office" / "Notifications are on."

## 8. Journey email step
Public site, journey `--s-*` tokens, espresso surface, 7B motion. **No new tokens.** Same screen, same split at 64em (heading left, form right), same sticky action bar. Words live in `journey/copy.py` `GATE`.

- **Copy.** Heading stays "One last thing." Body changes to: "We will show you your tailored membership, with its price." The privacy link becomes "How we use your details" (it no longer concerns only email). CTA stays "See my tailored membership" with the arrow. Tick, as decided: "Yes, Spa 99 may email and WhatsApp me about opening. I can stop at any time."
- **Order and fields**, all in one `.question` so the `--space-6` gap between questions does not push them apart; `.field` `gap: var(--space-2)` between them, so they read as one small group:

| Label | `name` | `type` | `autocomplete` | `inputmode` | Other |
|---|---|---|---|---|---|
| First name | `first_name` | `text` | `given-name` | `text` | `autocapitalize="words"`, `spellcheck="false"`, `enterkeyhint="next"` |
| Email | `email` | `email` | `email` | `email` | `autocapitalize="none"`, `spellcheck="false"`, `enterkeyhint="next"` |
| Mobile | `mobile` | `tel` | `tel` | `tel` | `enterkeyhint="done"`. Hint under it: "Outside the UK? Start with your country code." |

Then the tick (`.check`), then the privacy link in its sentence as today. The labels stay as words, not placeholders, using the existing label-inside field (`--control-h-label`).

**Feeling short, not long.**
- Correct autocomplete is the main trick: on most phones one tap fills all three.
- Enter on the first two moves to the next field and never submits half a form.
- No "required" stars, no "Step", no field numbers. All three are required, so nothing needs marking.
- Nothing reveals progressively: autofill needs all fields present, and a growing form feels longer.
- `.lead-gate .feedback:empty { min-height: 0 }`, so empty error slots do not add 3 lines of air. The small shift when an error appears is acceptable and only on a failed send.

- **Fit at 375.** `.lead-gate .screen-title { max-width: none }` keeps the heading on one line. Below 64em `.lead-gate.screen { padding-top: var(--space-4) }`, `.screen-head .lead` margin-top `--space-2`, `.question` gap to the tick `--space-4`. By my sums: 64 header + 24 + 40 heading + 8 + 52 lead + 24 + 196 fields + 24 hint + 24 + 72 tick + 72 bar is about 600px, so it fits 375 by 667 with the bar pinned. To be checked at 320 by 568, where the page may scroll; the bar stays, and `scroll-margin-bottom: calc(var(--bar-h) + var(--space-3))` on each field keeps the focused one clear of it and the keyboard. Desktop: one column, `max-width: 26rem`; no side-by-side fields.
- **Errors** (`.feedback` under each field, `data-state="error"`, `aria-invalid`, `--s-danger`, the existing icon; all shown together, focus moves to the first; each clears as he types):
- First name: "Please add your first name."
- Email: "That email does not look right."
- Mobile: "That mobile does not look right. Try 07700 900123." Landlines are refused the same way.
- Tick: "Please tick the box to carry on."
- Server down: the existing `error`, under the last field.

**Other cases.** Invite link: email prefilled and editable as today, and now he is asked for name and mobile; the tick is never ticked for him. Restart in the same browser carries all three, so he is not asked again. "Not you? Use another email" becomes "Not you? Start again" (it now clears all three). Motion: the existing hero reveal, once; no per-field motion.

## 9. Sounds
**None.** BRAND section 7 says "no sound", and an in-app ping is one more setting that staff would need to find. The installed app's push uses the phone's own notification sound, which staff control in their phone settings. If an open tab ever needs attention, the title count does it: "(3) WhatsApp".

## 10. Accessibility and touch
- Keyboard: list rows are links; Tab to composer; Escape closes every dialog, sheet and lightbox, returning focus. On desktop, choosing a chat moves focus to the composer (or the Closed button), and Escape in the empty composer goes back to the row.
- `role="log"` on the scroller stays quiet on first load; new messages use one polite sr-only region (name plus first line), never the whole log.
- Each bubble reads: "Daniel, 14:20: text" or "You, 14:28, read: text" with sr-only prefixes.
- 2.75rem targets throughout on touch. `touch-action: manipulation` on controls. Hover styles only under `(hover: hover) and (pointer: fine)`.
- `forced-colors`: bubbles get a 1px border, no tails, no pattern; the read state keeps its stroke weight and has `title` text.
- No one-sided accents anywhere: not on unread rows, quotes, warnings or the selected row.

## 11. To judge at first screenshots (375, 1440)
In order of importance:
1. Outgoing bubble against the wall (1.04 by luminance). If it is weak, go from 35% to 40% gold (`#F5DDC1`). All pairs hold except muted on inset (just under 4.5), so quote text then goes espresso.
2. Swan on the wall: seen as texture only when looked for. Tune `--office-wa-pattern` between 0.4 and 0.8. If in doubt, less.
3. Read against delivered ticks at arm's length on a phone. If they are too alike, the fallback is read ticks on a small gold fill.
4. Tail seam with the bubble's shadow, and the three close tones where list, thread header and wall meet.
5. Keyboard on a real iPhone: composer directly on the keyboard, nothing jumps, send keeps the keyboard up.
6. The gate at 375 by 667 and 320 by 568.
