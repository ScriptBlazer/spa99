# WhatsApp in the Office (plan, 2026-11-03)

Status: **planning**, not started. Branch `feature/whatsapp` (plan only for now). Build only when Moishe says go; ship in one go after testing. Decisions in PROJECT.md (2026-11-03 WhatsApp rows).

## Provider: Twilio (Moishe, 2026-11-03)
The number is a **Twilio** number and the WhatsApp side is already verified at Meta. We talk to **Twilio**, not to Meta directly:
- **Send:** Twilio Messages API (`From=whatsapp:+44...`, `To=whatsapp:+44...`), free text inside the window, templates via Twilio **Content Templates** (`ContentSid` + `ContentVariables`), media by URL.
- **Receive:** Twilio posts each incoming message to our **webhook** (form-encoded), signed with `X-Twilio-Signature` (HMAC with the Auth Token over the full URL and parameters). Media come as Twilio URLs that need our credentials to fetch; we copy them to S3.
- **Ticks:** Twilio **status callbacks** (queued, sent, delivered, read, failed, undelivered) to a second webhook URL.
- **Secrets** in the server `.env`: Account SID, Auth Token (or an API key + secret), the WhatsApp sender number, optionally a Messaging Service SID. Never in chat or git.
- Twilio's Python SDK or plain HTTPS; tests mock Twilio entirely.

## Twilio account facts (checked by the dev team, 2026-11-03)
- Sender **+44 20 4538 4999**, display name **Spa 99**, status **Online**, 80 messages a second. Quality rating "Unavailable" is normal until it has sent messages.
- **Shared account:** the same Twilio account and WhatsApp Business Account also hold **BML Group** (+44 20 7101 4800, quality High) and 5 approved BML property templates. So:
  - Webhooks go on the **Spa 99 sender only** (never account-wide), so BML is untouched. No Messaging Service: send with `From=whatsapp:+442045384999`.
  - **Templates are shared across both numbers.** Spa 99 templates are named `spa99_...`; the system only lists and sends that prefix, so a BML template can never go out from Spa 99.
  - A separate **API key** for sending (revocable without touching BML). Checking `X-Twilio-Signature` needs the account **Auth Token**, stored in the server `.env`; if BML rotates it, ours must change too.
  - A poor Spa 99 quality rating could affect the shared business account, so stick to people who ticked consent.
- **Balance is shared and low (£16.19):** sending stops if it runs out, for BML too. Top up and turn on auto-recharge before launch.
- **Webhook URLs** (public site host, same pattern as Postmark): `https://spa99.uk/twilio/whatsapp/incoming/` and `https://spa99.uk/twilio/whatsapp/status/`. Cloudflare must let them through (Bot Fight Mode stays off).

## Goal
A new number on **WhatsApp (through Twilio)** becomes a full staff to lead chat in the Office, as close to WhatsApp as we like, with push notifications (PWA). The AI assistant chat stays separate. Email Message stays.

## How the API works (constraints we design around)
- A chat we start must open with an **approved template**. Templates are submitted to Meta (minutes to a day to approve).
- When he replies, a **24-hour window** opens: free text and media allowed; each message from him restarts it. Outside the window only templates.
- Cost: Meta charges per template message (marketing dearer than utility); free-form replies inside the window are free.
- He must have **agreed** to WhatsApp messages (opt-in), or message us first.
- Incoming messages and delivery ticks arrive by **webhook** (HTTPS POST, signed with the app secret: `X-Hub-Signature-256`).

## Decisions (Moishe, 2026-11-03)
- Leads must give a **mobile** at the email step (required, not optional), alongside the email. Staff can also **add or fix a mobile by hand** on a lead.
- Site "WhatsApp us" buttons (`/whatsapp/`) switch to the **new number**, so every chat lands in the Office.
- **Everyone** who can see the chats gets notifications (each can mute).
- **Sending** follows the Message rule: Approver or Admin and up (`can_edit`).
- The Office chat looks and works like WhatsApp.

## Messaging is WhatsApp, not email (Moishe, 2026-11-03)
- Staff messages to a lead, person or Gold applicant go by **WhatsApp**, in the chat. The Message button opens his chat; email Message goes away.
- **Email stays only for** Send guide, automatic emails and anything the system sends.
- **The chat:** looks very like WhatsApp but themed to Spa 99 (brand colours and fonts, clear and calm). Designer brief first.
- **WhatsApp text formatting works** in the composer and in the bubbles, the same as in the app: `*bold*`, `_italic_`, `~strikethrough~`, ` ```monospace``` `, `` `inline code` ``, `- ` and `* ` lists, `1. ` numbered lists, `> ` quotes. The text is sent as typed; WhatsApp formats it on his phone and the Office shows the same. Note: WhatsApp's bold is one star each side, not two. Escaped safely (no HTML from message text).

- **No mobile:** the Message button says "Add a mobile to WhatsApp him"; staff cannot email from it. Send guide and automatic emails still reach him.
- **Consent:** new leads tick at the email step. Moishe's call: **registered people count as agreed**, so staff can WhatsApp anyone with a mobile. The privacy notice gets a WhatsApp line (backfill with dry run). Every first template carries a way to stop: "STOP" in the reply marks him opted out and blocks further templates. Risk noted to Moishe: complaints affect the WhatsApp account shared with BML.
- **Gold Respond** also goes by WhatsApp: opens his chat and marks the application Contacted when sent.

## Open points
- Launch turns the email step off once; Moishe can switch "Journey asks for an email" back on in System > Settings after launch (decided 2026-11-03).
- Consent: one required tick, "Yes, Spa 99 may email and WhatsApp me about opening. I can stop at any time." (decided 2026-11-03).
- Lead fields at the email step: **first name, email and mobile, all required** (Moishe, 2026-11-03, replaces email and mobile only). Staff can add or fix them by hand. When he replies we also store his WhatsApp profile name (Twilio `ProfileName`) for reference; a name staff typed wins.
- The first WhatsApp is **sent by staff with a click** on the lead page; nothing automatic (decided 2026-11-03).
- First template (Moishe to confirm the text, then submit in Twilio, likely category Marketing): `spa99_lead_follow_up`: "Hi {{1}}, thanks for checking out Spa 99. For custom prices, or more information about memberships, just reply here and we'll look after you."
- Templates text (3 to 5, written together, submitted by Moishe).

## What Moishe does (walkthrough, no code)
Meta side: **done** (verified, number connected).
In **Twilio Console**:
1. Confirm the WhatsApp sender shows as **Online** (Messaging > Senders > WhatsApp senders).
2. Put the Account SID, Auth Token (or API key/secret) and sender number in the server `.env`.
3. On the sender (or its Messaging Service): set **"A message comes in"** webhook to our URL (POST) and the **status callback** URL (we give both).
4. Create the templates in **Content Template Builder** and submit them for WhatsApp approval (we write the text together).

## What we build
1. **Data:** `whatsapp` app. Contact (E.164 phone, link to user / lead email / Gold application, opt-in source and time), Conversation (last inbound time = window, unread per user), Message (direction, type text / image / document / template, body, media in S3, Twilio MessageSid, status queued / sent / delivered / read / failed with error, author), Template (Twilio Content SID, name, language, category, approval status, body with variables; synced from Twilio).
2. **Mobile at the gate:** required mobile field + consent; normalised to E.164 (UK default); stored on the journey session; shown on lead pages; staff edit on lead and person pages (audited). Privacy notice gets a WhatsApp line (backfill script with dry run).
3. **Webhook (Twilio):** `POST` receive; `X-Twilio-Signature` check (behind Caddy: the exact public URL); idempotent on the Twilio `MessageSid`; store fast, process in the worker; statuses update ticks; unknown numbers create a new contact (and a lead row if needed).
4. **Sending:** worker task to the Twilio Messages API with retries (status callback URL on each send); text and media inside the window, templates outside; errors shown in the chat; no real API calls in tests (mocked).
5. **Office inbox:** chat list (search, unread badges, newest first), thread (bubbles, date dividers, ticks, media previews, the window bar "Window closes in 5h" / "Window closed: send a template"), composer (text, attach photo or PDF, template picker with variable fill-in). Live updates by short polling first (SSE later if needed). Phone: list, then thread. Linked from lead, person and Gold pages ("WhatsApp" button), and in the timeline.
6. **System > WhatsApp:** connection status (credentials work, sender online), templates list with approval status from Twilio Content API (sync button), the site WhatsApp number setting moved to the new number.
7. **PWA and push:** web app manifest + service worker for the Office host, install prompt hint, Web Push (VAPID keys in `.env`), push subscription per staff device, notification on each inbound message (who and first line), tap opens the chat, per-user mute in their settings. iPhone needs iOS 16.4+ and the Office added to the Home Screen.
8. **Erasure and export:** WhatsApp contact and messages included in person / lead delete and GDPR export.

## Phases
1. Twilio settings + mobile at the gate (data starts flowing).
2. Webhook + inbox (receive and reply inside the window).
3. Templates + starting chats from lead pages.
4. PWA and push notifications.
All on one branch, tested with the Twilio WhatsApp sandbox (or the real number on a staff phone), shipped together.
