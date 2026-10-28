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
- Per-visitor limits: e.g. 20 messages per 10 minutes per browser/IP, max message length, max conversation length.
- If the API key is missing or Anthropic is down: the panel shows the hand-off buttons (never an error page).

## Logs and privacy
- Each conversation is saved (messages, timestamps, token counts, cost, linked lead email if given) and readable in the **Office** (new "Chats" page, Office level and up). Deleted automatically after **90 days** (daily job, logged).
- No IP stored; browser link via the existing journey cookie/session only.
- Privacy notice gets a line (AI assistant by Anthropic, US transfer under UK safeguards, 90-day retention). Moishe accepts Anthropic's data agreement in the Console.

## Config
- `ANTHROPIC_API_KEY` in `Secrets/.env` and on the server (never in git or chat). `.env.example` documents it. Chat is off (button hidden) when the key is not set.
