# Ask us: the chat panel

For the frontend agent. Spec: `docs/features/ai-chat.md`. `docs/BRAND.md` wins on any conflict. Branch `feature/ai-chat`.

Design read: a quiet concierge desk, not a support widget. Espresso, one small control, one conversation at a time. Motion 3 (BRAND 7B, restrained). Moishe removed Back to top because it felt unnecessary, so the entry must earn its place by being almost invisible until wanted.

---

## 1. Entry: the "Ask us" control

**Where it shows:** public pages only (Home, The spa, Memberships, Gold Card, Book, Visit us, legal, 404). Never on the journey, sign up, sign in, account / My Spa 99, the Gold application, Office, System, Control. Also **not on the Virtual tour** (full-screen 3D with its own markers and captions in the corners). Not rendered at all when the chat is off (no API key). Rendered in `base.html` in its own `{% block chat %}` after `feedback`, so reduced templates can empty it.

**Look:** one pill, bottom right.
- `min-height: var(--chip-h)` (44px), `padding: 0 var(--space-4)`, `border-radius: var(--radius-md)` (same as the site's chips).
- Background `--color-espresso-raised`, 1px `--color-hairline-inverse`, shadow `--shadow-toast` (warm, already approved). Text "Ask us", Figtree 500 `--text-base`, `--color-text-inverse` (9.45:1). A gold swan (`_mark.html`, `--color-gold`, 16px tall) before the word, `gap: var(--space-2)`.
- Same pill on dark scenes and cream pages: on espresso it reads as a quiet raised tab, on cream as a small dark object. No colour change on scroll.
- Hover (fine pointer only): scale 1.01, press 0.99, `--duration-press` (BRAND 7B).
- No badge, no dot, no greeting bubble, no sound, no auto-open, ever.

**Position:**
- Desktop (64em+): `right: var(--space-4)`, `bottom: var(--space-4)`.
- Phone: `right: calc(var(--page-margin) + env(safe-area-inset-right))`, `bottom: calc(var(--space-3) + env(safe-area-inset-bottom))`. Label stays "Ask us" (words beat an icon here).
- **Pages with a bottom bar on phone** (Memberships sticky tag `.mem-choice`): the pill sits above the bar, `bottom: calc(var(--bar-h) + env(safe-area-inset-bottom) + var(--space-3))`, and shrinks to the swan alone in a 44px square (`aria-label="Ask us"`). Use the existing `body[data-has-bar]` hook (set it on Memberships below 64em if not already). Never covers Continue.
- Footer: when the chat is on, the footer's last row gets `padding-bottom: calc(var(--chip-h) + var(--space-5))` on phone so no legal link sits under the pill.
- Sale bar and header are at the top; the pill is at the bottom. No clash by construction.

**When it appears (decided):** after the first screen. It fades in once the visitor has scrolled 50% of the first viewport, or straight away on pages shorter than 1.5 screens (legal, 404). Once shown it stays for the rest of the page (no flicker on scroll up). The first screen of every scene stays pure: one idea, one primary action.
- Arrival: `opacity 0 → 1`, `translateY(8px → 0)`, 600ms `--ease-soft`, once. Reduced motion: appears without movement.
- Hidden while the panel is open, while the menu dialog is open, and on coarse pointers while any page field has focus (so it never floats over a field above the keyboard).

**Layers (add as derived tokens, section 6):** header 10, sale bar 11, sticky bars 20, **pill 30**, toasts 100, site modal 110. The panel is a `<dialog>` opened with `showModal()`, so it lives in the top layer above everything. The menu is also a top-layer dialog; opening one closes the other. The chat never raises a toast or the site modal: every chat state is inline in the panel.

---

## 2. The panel

**Decided: espresso.** The site lives in espresso, Moishe loves it, and cream on espresso is 10.95:1, as legible as the reverse. Long replies are kept readable by type, not by a light surface: Figtree `--text-base`, `--leading-body` (1.6), max 34rem line. The panel root gets `class="chat on-dark"` so buttons, fields and checks pick up their dark theme from the existing `--s-*` tokens.

**Desktop (64em+):** a floating sheet docked right. `width: var(--chat-w)` (27rem), `top/right/bottom: var(--space-4)`, `border-radius: var(--radius-md)`, background `--color-espresso`, 1px `--color-hairline-inverse`, `--shadow-raised`. Backdrop `--color-overlay-soft`, no blur (the page stays visible, dimmed). Click on the backdrop closes.

**Phone:** full-height sheet, `inset: 0`, `height: 100dvh`, top corners `--radius-md`, safe-area padding all round. Inputs 16px minimum (no iOS zoom). Keep the input above the keyboard with `visualViewport` resize (set the sheet height to `visualViewport.height`).

**Structure (grid rows auto / 1fr / auto):**
1. **Head**, `min-height: var(--header-h)`, hairline below. Left: gold swan 20px + "Ask us" in Signika 400 `--text-lg`, `--tracking-display` (this is the dialog title, `id` used by `aria-labelledby`). Right: "New chat" (quiet text button, only once there are messages) and "Close" (text button, same as the menu's Close). 44px targets.
2. **Conversation**, scrolls, `padding: var(--space-4)`, `gap: var(--space-4)` between messages, `overscroll-behavior: contain`.
3. **Compose**, hairline above, `padding: var(--space-3) var(--space-4)` plus safe area: input, send, limit hint, privacy line.

**Welcome (empty state):** at the top of the conversation, not centred.
- Signika `--text-xl` cream: "Ask us anything."
- Figtree `--text-base`, `--color-text-muted-inverse` (6.50:1): "The spa, memberships, hours or the Gold Card."
- Chips below, `gap: var(--space-2)`, wrap. 3 to 4 questions from the FAQ: the FAQ entries Moishe marks as suggested in System, first four in his order. Fallback set until he does: "When do you open?", "What is included in a membership?", "What is the Gold Card?", "Where are you?". Chip: `min-height: var(--chip-h)`, `padding: 0 var(--space-3)`, `--radius-md`, 1px `--color-control-line` (3.09 on espresso), cream text. Tapping sends it as the visitor's message. Chips leave once the first message is sent.
- A quiet line under the chips: "Prefer a person? Message our team." where "Message our team" is a gold underlined button that shows the hand-off block (section 2.5).

### 2.1 Messages
- **Visitor:** right aligned, `max-width: 85%`, background `--color-espresso-raised` (cream 9.45:1), `--radius-md`, `padding: var(--space-2) var(--space-3)`. Plain text only, newlines kept.
- **Spa 99:** left aligned, **no bubble**, cream on espresso, full measure. Reads like a note from the desk, not a chat app. Light markdown only: paragraphs, short lists, bold. Links in gold (6.17:1), underlined, 1px, offset 4px. Site links open in the same tab after closing the panel; WhatsApp and mail open new.
- **Suggested next steps** the model may attach (Tailor your membership, Register): small secondary buttons under the reply (`btn btn-secondary btn-sm`, cream outline). Never more than two.
- Each message has a visually hidden prefix: "You said:" / "Spa 99:". No avatars, no timestamps.

### 2.2 Waiting and streaming (calm, reduced-motion safe)
- After send, if no text has arrived within 300ms, show "One moment" in `--color-text-muted-inverse` where the reply will start (same words as the journey gate). No dots, no pulse, no loop (IMMERSIVE: nothing loops faster than 15s).
- Streamed text replaces it and simply grows. No per-word fades, no caret. The text arriving is the motion, so reduced motion needs nothing extra.
- Auto-scroll follows the reply only if the visitor is within 80px of the bottom. If he has scrolled up, leave him there.
- While streaming: the send button is `aria-disabled`, the input stays typeable.

### 2.3 Compose
- `<textarea>` auto-grows 1 to 4 lines, then scrolls. Visually hidden label "Your question"; placeholder "Ask a question" (`--color-text-muted-inverse`). Fill `--color-espresso-raised`, no border, `--radius-sm`, focus ring `--color-focus-inverse` (gold) 2px offset 2px.
- Send: 44px square, `btn-primary` (gold, espresso arrow `arrow-right` icon), `aria-label="Send"`. Enter sends, Shift+Enter is a new line.
- **Limit: 500 characters.** Hidden until 400, then `--text-sm` muted: "100 characters left". At 0: "That is the limit for one message." and the field stops taking input.
- **Privacy line** under the compose row, `--text-sm`, muted: "AI assistant. Chats are kept for 90 days. [Privacy notice]" linking to the privacy notice's chat section, gold underline.

### 2.4 Email for prices
Shown inline when the backend says the visitor asked about prices and has no lead email. Sits in the conversation after the Spa 99 reply, as a block: 1px `--color-hairline-inverse`, `--radius-md`, `padding: var(--space-4)`, on espresso (not espresso-raised, so field borders keep their contrast).
- Line: "We share prices once we have your email. Leave it here and we will show them in this chat."
- Field: the site's email field (`_field.html`, on dark), label "Email", `autocomplete="email"`, `inputmode="email"`.
- Consent: `_check.html`, words exactly as the journey gate: "Yes, Spa 99 may email me about opening. I can unsubscribe at any time." followed by the link "How we use your email". Not pre-ticked.
- Button: "Show prices" (`btn-primary`, full width on phone). Saving: "One moment".
- Errors under the field, `--color-danger-inverse`: the journey's own messages (`CONSENT_MESSAGE`, the email error). Server failure: "We couldn't save that just now. Please try again."
- Quiet "Not now" text button beside or under it; the chat carries on without prices.
- Success: the block collapses to one line, "Thank you. Prices are now shown.", and the answer to the pending question streams in below without the visitor asking again.

### 2.5 Hand-off
Shown when the model cannot help, when the visitor asks for a person, from "Message our team", and in every unavailable state. Same block style as 2.4.
- Line: "Our team will gladly help."
- Two buttons side by side (stacked on phone, full width): **"WhatsApp us"** (`btn-primary`) to the WhatsApp link from System settings, and **"Email us"** (`btn-secondary`) as `mailto:` to hello@ (from `site_settings.contact_address`) with subject "A question for Spa 99". If no WhatsApp link is set, Email alone, as primary.
- Small line under, muted: the address itself, so it can be copied.

### 2.6 States (every string)
| State | What shows | Copy |
|---|---|---|
| Cap reached or Anthropic down or key fails at runtime | Welcome heading, line, hand-off. No chips, no input, no privacy line. Same for both causes; the visitor never sees why. | "Ask us." / "Our assistant is not available just now. Our team will answer you directly." |
| Reply failed (network or stream cut) | Under the partial reply, muted, with a gold text button | "That answer did not come through." [Try again] |
| Failed twice in a row | The line above, then the hand-off block | as above |
| Rate limit (too many messages) | Muted line, then hand-off | "You have asked a lot in a short time. Please wait a few minutes, or message our team." |
| Conversation too long | Muted line, "Start again" secondary button, hand-off | "This conversation is full. Start again, or message our team." |
| Offline (`navigator.onLine` false) | Muted line above the input, send disabled | "You seem to be offline." |
| New chat | Clears the view to the welcome. No confirm. | "New chat" |

Model tone (for the system prompt, shared with backend): calm, short, British English, "we" for Spa 99, no exclamation marks, no emojis, no "Great question". Two short paragraphs at most unless listing a plan.

---

## 3. Focus, keyboard, screen readers
- Pill is a `<button aria-haspopup="dialog" aria-controls="ask-us">`. Panel: `<dialog id="ask-us" aria-labelledby="ask-us-title">`, opened with `showModal()` (native focus trap, inert page, Esc closes via `cancel`). Lock page scroll; call `lenis.stop()` if Lenis is on.
- On open: fine pointer focuses the textarea; coarse pointer focuses the title (`tabindex="-1"`) so the keyboard does not cover the welcome. On close: focus returns to the pill.
- Tab order: New chat, Close, conversation links and buttons, chips, input, send, privacy link.
- Conversation list `role="log"` with `aria-live="off"` and `aria-busy="true"` while streaming. A separate visually hidden `aria-live="polite"` region receives each **finished** reply in full (never chunk by chunk), plus state lines ("That answer did not come through.").
- Email block errors use the existing `aria-live="polite"` feedback in `_check.html` / `_field.html`. Focus moves to the email field when the block appears only if the visitor tapped into it; it never steals focus mid-reading.
- Everything works at 200% zoom and 320px wide.

## 4. Motion
| What | Motion | Reduced motion |
|---|---|---|
| Pill arrival | opacity + 8px rise, 600ms `--ease-soft`, once | appears |
| Panel open, phone | `translateY(100% → 0)`, 400ms (`--duration-base`) `--ease-soft`; backdrop opacity | appears |
| Panel open, desktop | opacity 0 → 1, `translateY(12px) scale(0.98) → none`, `transform-origin: bottom right` (towards the pill), 400ms | appears |
| Panel close | reverse, 240ms (faster than in) | disappears |
| New message (visitor's bubble, a block) | opacity 0 → 1, 8px rise, 240ms (`--duration-ack`) | appears |
| Streaming | none beyond text growing | same |

Only `transform` and `opacity`. No sideways travel, no bounce, no blur. Use `@starting-style` plus `transition-behavior: allow-discrete` on `dialog[open]` and `::backdrop`, with a class fallback.

## 5. Spacing and type summary
Head title Signika `--text-lg`; welcome Signika `--text-xl`; everything else Figtree `--text-base`, hints and privacy `--text-sm`. Spacing only from `--space-2` to `--space-5`. Radius: `--radius-md` for the panel, bubbles, chips and blocks; `--radius-sm` for the input and buttons (as everywhere).

## 6. Tokens
From BRAND, no new colours: `--color-espresso`, `--color-espresso-raised`, `--color-text-inverse`, `--color-text-muted-inverse`, `--color-gold`, `--color-control-line`, `--color-hairline-inverse`, `--color-danger-inverse`, `--color-focus-inverse`, `--color-overlay-soft`, `--shadow-toast`, `--shadow-raised`, `--chip-h`, `--bar-h`, `--header-h`, `--page-margin`, `--ease-soft`, `--duration-base`, `--duration-press`, `--duration-ack`.

**Proposed additions to `tokens.css` and BRAND section 8 (marked "proposed, Ask us"):**
```css
--chat-w: 27rem;          /* proposed, Ask us: desktop panel width */
--z-chat-entry: 30;       /* proposed, Ask us: the pill; above sticky bars (20), below toasts (100) */
```

## 7. Check before done
375x667 and 1440x800: pill never over a CTA, Continue bar, footer link or field; hidden on the first half screen of every scene; panel open, streaming, email block, hand-off, cap state and error each screenshotted; Esc, Tab loop and focus return work; VoiceOver reads one finished reply once; reduced motion shows no movement; espresso contrast holds for every string (muted 6.50, gold 6.17, danger-inverse 6.81).

---

## Revision 2026-10-28 (Moishe: "too big", cream panel)

This revision wins over sections 2 to 5 where they differ. Everything not mentioned stays.

- **Compact card on desktop (64em+):** `--chat-w` 23.75rem (380px), height 70vh (max 40rem), docked bottom right above the pill area (`bottom: space-4 + chip-h + space-2`), radius `--radius-md`, `--shadow-raised`. Phone keeps the full-height sheet.
- **Cream panel** (`class="chat on-light"`): cream background, espresso text, `--s-*` light tokens. Buttons are espresso with cream text (`.btn-primary` on-light), secondary is an espresso outline. Links are espresso, underlined (gold fails AA on cream). The header swan is espresso; gold stays only on the pill's swan (espresso pill, unchanged, reads as a small dark object on cream and a raised tab on espresso). Visitor bubbles: `--color-cream-raised` with a hairline. Hand-off and email blocks: 1px `--s-line` border, transparent fill (so field underlines keep their contrast).
- **Smaller type and spacing:** body 15px (`--chat-text`), welcome heading 24px (`--chat-heading`), chips 14px (`--text-sm`), header 16px (`--text-base`), hints and privacy 13px (`--chat-small`). Spacing `--space-3` (16px) for padding and gaps, header height `--chip-h`. The compose input stays 16px (a smaller input makes iOS zoom the page); the Send button and chips stay 44px targets. New derived tokens: `--chat-text`, `--chat-small`, `--chat-heading` (BRAND section 8).
- **Header** shows the assistant name (System > Assistant, fallback "Spa 99 Assistant") beside the swan. "New chat" and "Close" are smaller, muted, 44px targets.
- **Welcome words** (heading, line) come from System > Assistant (`chat_assistant`, also in `/chat/state/`), with the fallbacks "Ask us anything." and "The spa, memberships, hours or the Gold Card.". The pill still says "Ask us".
