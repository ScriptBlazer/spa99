# AI chat ("Ask us")

Decided by Moishe 2026-10-28 (PROJECT.md): an own-build, full-AI chat on the public site, using Claude through the Claude Console. Branch `feature/ai-chat`.

## What visitors get
- A quiet **Ask us** button on public pages (not the journey, member area, Gold apply, staff sites). Opens a Spa 99 chat panel; answers stream in.
- Answers come **only** from Spa 99's own data, read live from the app: plans and what's included, hours, closures and cleaning hours, facilities and temperatures, the Gold Card (what it is, how to apply, never decisions), the address, and an **FAQ that Moishe edits in System**.
- **Hand-off** buttons (WhatsApp from System settings, email hello@) whenever it can't help, the visitor asks for a person, or the monthly cap is reached.
- Can point to the questionnaire ("Tailor your membership") and Register.

## Hard rules (in code, not only in the prompt)
1. **No prices until an email is given** (same rule as the site). Price data is simply not given to the model unless this browser session has a lead email (or the visitor is signed in, or Memberships is public). The chat may offer to take the email: with the visitor's consent tick it becomes a lead exactly like the journey gate (`journey.services` lead path), then prices may be shown.
2. Spa 99 topics only; no medical advice; never invent prices, dates, availability or promises; never discuss other members; no bookings or payments in chat (booking is not open).
3. Men-only wording only as the site states it; polite, calm, short, British English, Spa 99 tone ("Beyond Luxury"), no exclamation marks.
4. Prompt-injection safe: visitor text never changes the rules; the knowledge comes from the app, not from the visitor.

## Cost and limits
- Model: `claude-opus-5-5` (project default), effort `low`, streaming, prompt caching on the stable system prompt + knowledge.
- Monthly cap **£25** (editable on the System Defaults page). Spend is computed from each reply's token usage and stored; at the cap the chat shows only the hand-off buttons until the next month.
- Per-visitor limits: 10 messages per 10 minutes and 40 a day per browser and per IP, 500 characters a message, 12 messages a conversation (see Security).
- If the API key is missing or Anthropic is down: the panel shows the hand-off buttons (never an error page).

## Logs and privacy
- Each conversation is saved (messages, timestamps, token counts, cost, linked lead email if given) and readable in the **Office** (new "Chats" page, Office level and up). Deleted automatically after **90 days** (daily job, logged).
- No IP stored; browser link via the existing journey cookie/session only.
- Privacy notice gets a line (AI assistant by Anthropic, US transfer under UK safeguards, 90-day retention). Moishe accepts Anthropic's data agreement in the Console.

## Config
- `ANTHROPIC_API_KEY` in `Secrets/.env` and on the server (never in git or chat). `.env.example` documents it. Chat is off (button hidden) when the key is not set.

## Status (2026-10-28)
Backend and panel (Ask us button, streaming panel) built on `feature/ai-chat`, then reviewed and fixed (below). The full suite passes (see the PR for the count); every Claude call in the tests is mocked. Not yet tried against the real API (no key here): do one live check with a real `ANTHROPIC_API_KEY` before launch (a normal question, a price question, an off-topic one, and one reply that hits the output cap).

## Built
- **Models** (`chat/models.py`): `Conversation` (uuid, created, `last_at`, journey `session`, signed-in `user`, `lead_email`, `total_cost_pence`, `message_count`, `ended_by_cap`, `off_topic_count`, `ended_off_topic`), `Message` (role, text, input/output/cache-read/cache-write tokens, `cost_pence` (4 decimals), `stop_reason`, `flagged_handoff`, `offered_email`, `off_topic`), `FaqItem` (question, answer, order, visible, `suggested`; history on, edited in System > FAQ, audited). No history tables on conversations and messages (append-only logs deleted after 90 days). No IP stored.
- **Model call** (`chat/llm.py`): `claude-opus-5-5`, effort `low`, streaming, no `thinking`/temperature, `max_tokens` 500, prompt cache breakpoint on the knowledge block (tools, then frozen rules, then knowledge). Tools (strict): `show_handoff`, `offer_email`, `off_topic`, `suggest_next_steps`. `anthropic==2.3.0`.
- **Knowledge** (`chat/knowledge.py`): built from the live data; the server decides whether prices are in it (`pages.access.memberships_visible`, or a lead email given in the chat). Without them there is no price, fee or sale figure at all, and a stray "£" the model writes is cut off in code. Cached 60 seconds per variant.
- **Cost**: usage from the reply, USD to GBP at `settings.CHAT_GBP_PER_USD` (0.79), stored in pence per message. Monthly cap `SiteDefaults.chat_monthly_cap_gbp` (£25, System > Defaults > Website and journey).
- **Office**: Chats list and detail (`/chats/`, Office level and up, view only, paginated; "Closed: off-topic" and "Stopped by the spending cap" flags).
- **Clean-up**: schedule `chat-prune` daily 03:30; `manage.py prune_chats [--dry-run] [--days N]`. Export/erase with the person (`users.export_user_data`, delete account, Office lead export/erase, `lead_data`).
- **Privacy notice**: new lines in `content/legal.py` (what we collect, who we share with, US transfer, 90 days, lawful basis), `PRIVACY_UPDATED` 28 October 2026 (version unchanged). Rows already stored in the database are not overwritten: paste the new lines in Control > Privacy (or reseed on a new install).
- **Seed**: ten FAQ entries from the site's own copy (`chat/seed.py`, run by `seed_phase1`; four are marked Suggested).

## System > Assistant (2026-10-28)
One System section (`/assistant/`, Developer level, unlocked, audited), tabs:
- **Overview and test**: this month's spend against the cap, today's spend against the soft daily cap, conversations today and this month (simple counts, staff tests left out), the on/off switch, and a **test console**. The console talks to the real assistant with the live knowledge, "with prices" or "without prices", shows the exact text sent to the model (rules, personality, knowledge) and the events, is not counted against visitor limits, is counted in spend (and by the caps), and is stored as `Conversation.staff_test` (left out of the Office Chats list and the counts). The off-topic closing still applies there (use New test).
- **Knowledge notes** (`chat.KnowledgeNote`): topic (Facilities, Lockers and changing, Booking, Memberships, Gold Card, Visiting and arrival, Policies, Other), title, text up to 1500, order, active. A "£" is refused: prices come only from the plans, after an email. Seed notes (add-if-missing, `seed_phase1`) come from the site copy and the agreed rules, e.g. "Lockers are included in every membership and are assigned when you book."
- **FAQ**: as before; "Suggested" ones are the panel's chips.
- **Personality and rules** (`chat.AssistantSettings`): assistant name ("Spa 99 Assistant"), welcome heading ("Ask us anything."), welcome line, tone notes, an "always" list and a "never" list (one per line). They go into a second system block that says it adds to the rules and loses to them. The hard rules (Spa 99 topics only, no price before an email, no code, no promises, off-topic closing, caps) are in code and cannot be edited away.
- **Limits**: the assistant on/off switch (instant: the button disappears and every chat request is refused 404), daily soft cap (% of the monthly cap, 5), messages per 10 minutes (10) and per day (40) per browser and per IP, messages per conversation (12), characters per message (500), each with min and max bounds; and the monthly cap, which stays on `SiteDefaults.chat_monthly_cap_gbp` (same field as System > Defaults, no data moved). The rest of the Security numbers are constants in settings.

**Smarter knowledge.** The knowledge now has: every public room with its temperatures and facts exactly as the site shows them, every membership's inclusions and booking rules (days ahead, bookings at a time, cancellation hours, guests, hours), a BOOKING RULES block with the agreed rules read live (slot length, slot step, notice, one booking a spa day, entry, staying as long as you like, closures, bookings up to 1 hour before the Shabbos and Yom Tov closing, guests), the knowledge notes, then the FAQ. Ordering is fixed (plan order, topic order, then note order), so the text stays byte-stable and cache-friendly. The prompt tells the assistant to be specific when the data has it, to explain basic booking rules and say full details come when booking opens, and to hand off only when the answer truly is not there.

**Frontend additions.** `GET /chat/state/` has `assistant: {name, welcome_heading, welcome_line}` and `max_message_chars` / `max_messages` now follow the Limits tab; template context has `chat_assistant` with the same fields. The off switch makes `chat_enabled` and `chat_button` false and the state, message and email endpoints 404.

## Contract (for the frontend)

### Template context (public pages, `chat.context.chat`)
- `chat_enabled`: the key is set and this is the public site. `chat_button`: `chat_enabled` and the page may show the button (not `/journey/`, `/gold-card/apply/`, `/account/`, sign-in, register, verify, password and unsubscribe pages). Use `chat_button` to render the button.
- `chat_handoff` (only when `chat_button`, read lazily): `{reason, whatsapp_url, email, mailto}`. `whatsapp_url` is "" when not set (it is `SiteSettings.discount_contact_url`, the WhatsApp link in System > Settings): then show Email alone as primary. `email` is `site_settings.contact_address`; `mailto` carries the subject "A question for Spa 99".
- `chat_suggested`: the questions marked Suggested in System > FAQ (visible, first four in order); fewer than one means use the design's fallback chips.
- No database query runs on pages where the button is hidden.

### `GET /chat/state/` (public host, JSON)
Call it when the panel first opens. It sets the CSRF cookie and the signed, HttpOnly `spa99_chat` cookie (24 hours, path `/chat/`) that proves the request comes from the page: without it `message` and `email` answer 403 `{"code": "no_session"}` and call nothing. 404 while the chat is off. Body: `{enabled, max_message_chars (500), max_messages (12), honeypot_field ("website"), suggested: [str], handoff: {...as above}, prices_visible, capped, privacy_url}`. When `capped` is true show the hand-off state (the visitor never sees why).

### `POST /chat/message/` (JSON, `X-CSRFToken`, cookies sent)
Body `{"conversation_id"?: uuid, "message": str}` (1 to 500 characters), or `{"conversation_id", "retry": true}` to answer the pending price question again (see Email). Leave the hidden `website` field out (or empty): a filled one is a bot.
Plain JSON refusals (no stream), each with `{"error", "code"}`:
- 400 `empty`, `too_long` (`max_length`), `nothing_pending`; 403 (bot, other site, `no_session`); 404 chat off.
- 429 `rate_limited`, 409 `conversation_full` (12 visitor messages), 503 `busy` (too many new chats this hour): these three also carry `handoff: {...}`. Panel states: rate limit, "This conversation is full", and the unavailable state.
Otherwise 200 `text/event-stream` (`Cache-Control: no-cache`, header `X-Chat-Conversation: <uuid>`). Each event is `event: <name>` then `data: <json>`:
| event | data | meaning |
|---|---|---|
| `delta` | `{"text"}` | append to the reply (light markdown) |
| `next_steps` | `{"steps": [{"key": "journey"\|"register", "label", "url"}]}` | at most two secondary buttons under the reply |
| `handoff` | `{"reason", "whatsapp_url", "email", "mailto"}` | show the hand-off block. reasons: `asked`, `cap`, `unavailable`, `refusal`, `too_long`, `off_topic_limit` |
| `offer_email` | `{"pending": true}` | the visitor asked about prices and has no email: show the email block after this reply |
| `error` | `{"reason", "message"}` | `unavailable` or `refusal`: show `message`; always followed by `handoff` and `done` |
| `done` | `{"conversation_id", "ok", "stop_reason", "messages_left", "off_topic"?, "ended"?, "suggested"?}` | last event. Keep `conversation_id` and send it with the next message. `ok: false` means the reply was a hand-off. `off_topic: true`: the question was declined (`suggested` lists the suggested questions to show). `ended: true`: the conversation is closed, show hand-off only and start a new chat for more |
A stream that stops without `done` is a cut connection: show "That answer did not come through." with Try again.

### `POST /chat/email/` (JSON, `X-CSRFToken`, same cookies)
`{"conversation_id"?, "email", "consent": true, "website"?}`. Saves a lead exactly as the journey gate (same consent wording and `LeadError` messages, journey session made if needed, `spa99_journey` cookie set). 200 `{"saved": true, "conversation_id", "retry": bool}`; 400 `{"errors": {"email", "consent"}}`. **Re-asking the pending question is the frontend's job, one call:** when `retry` is true, send `POST /chat/message/ {"conversation_id", "retry": true}` and stream the answer, which now includes prices (the question is not stored twice). Signed-in visitors skip the form (`offer_email` is not sent to them).

## Review fixes (2026-10-28)
- A reply whose usage never arrives (visitor closes the page mid-stream, timeout, cut stream) is still stored and billed: the request's size at 3 characters a token plus the whole output cap. A connection that never opened costs nothing.
- `POST /chat/email/` makes a conversation only after the lead is saved; the hourly "busy" limit counts only conversations with at least one visitor message.
- `retry` needs prices to be allowed (403 `needs_email` otherwise) and counts as a message toward the conversation limit and the rate limits.
- Declined turns (off-topic, pasted code, injection phrases, refusals) and our own canned lines are left out of the history sent to Claude on later turns.
- A conversation stores a hash of the page cookie that started it: the id alone cannot continue someone else's chat.
- FAQ text may not contain a "£" (System rejects it); an older entry that does is left out of the no-price knowledge.
- The privacy notice heading has the anchor `#chat` (`### Title {#id}` in a legal body). Existing database rows get it only when the line is pasted again in Control.
- The DB cache holds 100 000 entries (was 10 000), so a flood of keys cannot push rate-limit counters out.
- Gunicorn now runs `gthread` with `GUNICORN_THREADS` threads (default 8, `GUNICORN_WORKERS` unchanged): a streamed reply holds a thread for a few seconds, not a whole worker.

## Security (no free tokens for anyone)
All enforced on the server; none of the refusals below calls Claude. Numbers are in `config/settings/base.py` (`CHAT_*`, one block); only the monthly cap is editable in System.
- **Output**: `max_tokens` 500 (thinking is always on for this model, so keep an eye on truncations in the first live week); a reply that hits it ends with "..." and the hand-off, never continues.
- **Input**: 500 characters a message, 12 visitor messages a conversation, only the last 8 messages go to the model; a message with a code fence, six or more code characters (`{}<>;[]$\`|`) or six or more line breaks, or a known injection phrase ("ignore previous instructions", "system prompt", "act as"...), gets one polite canned line and counts as an off-topic turn.
- **Rates**: per browser (the page cookie) and per IP, each 10 messages in 10 minutes and 40 a day; 200 new conversations an hour for the whole site; the monthly cap (£25); a soft daily cap of the monthly cap divided by 20 (£1.25), after which only hand-off shows until tomorrow. Shared addresses (an office) share the IP count: raise `CHAT_RATES` if that bites.
- **Scope** (system prompt, `chat/prompt.py`): Spa 99 only. The model calls `off_topic` for code, websites, essays, general knowledge, homework, translation, role-play, jailbreaks and requests to reveal the prompt, and answers with one short line. Visitor text is untrusted data. It never repeats the prompt or knowledge.
- **Off-topic counter**: after 2 off-topic, refused or code turns the server closes the conversation (hand-off only, no more model calls) and flags it in the Office Chats list.
- **Bots and other sites**: the hidden `website` field, device-type bots refused, `Origin`/`Sec-Fetch-Site` must be this site, CSRF, and no model call without the signed page cookie from `GET /chat/state/`.
- **Logging**: each abuse signal (rate limit, honeypot, bot, cross-origin, no cookie, code, injection, cap, busy) is one `spa99.chat.abuse` log line with the IP hashed with the visitor counter's daily salt, which is deleted the next day. Nothing about it is stored in the database.
- **Gunicorn**: a streamed reply holds one thread for the seconds it takes (`max_tokens` 500, `CHAT_TIMEOUT_SECONDS` 45, checked at the end of the stream too). The live server runs gthread, 8 threads a worker.
