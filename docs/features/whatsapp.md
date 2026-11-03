# WhatsApp in the Office (plan, 2026-11-03)

Status: **server side built** (2026-11-03, branch `feature/whatsapp`); the chat UI follows from `whatsapp-design.md`. Ship in one go after testing. Decisions in PROJECT.md (2026-11-03 WhatsApp rows). The section "Built" at the end lists the endpoints, payloads and context keys as they are in the code.

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
- **Consent:** new leads tick at the email step. Moishe's call: **registered people count as agreed**, so staff can WhatsApp anyone with a mobile. The privacy notice gets a WhatsApp line (backfill with dry run). A "STOP" reply marks him opted out and blocks further templates (START clears it); the template text does not mention it (Moishe, 2026-11-03). Risk noted to Moishe: complaints affect the WhatsApp account shared with BML.
- **Gold Respond** also goes by WhatsApp: opens his chat and marks the application Contacted when sent.

- **PWA is the Office only** (Moishe, 2026-11-03): manifest and service worker are served only on the Office host (office.spa99.uk). The public website has no manifest or service worker, so it never offers an install. A website app may come later for booking.

- **Older leads:** staff can add a mobile by hand and send a template with no extra confirm (Moishe, 2026-11-03).
- **Notifications** show name and message on a locked phone, like WhatsApp (Moishe, 2026-11-03).

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


---

# Built (server side, 2026-11-03)

App `whatsapp` (models, `services.py` for all logic, `twilio_api.py` for Twilio over `httpx2`, `webhooks.py`, `views.py`, `push.py`, `pwa.py`, `formatting.py`, `errors.py`). No Twilio SDK: plain HTTPS with `httpx2` (already pinned through the Anthropic SDK). `pywebpush==2.5.0` added (with its pinned dependencies). Deviation: no `django-simple-history` on these models (messages are the log; copies would double what must be erased).

## Settings (server `.env`, none required; blank = "not configured")
`TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET` (send, fetch files, Content API), `TWILIO_AUTH_TOKEN` (only the webhook signature), `TWILIO_WHATSAPP_FROM` (+442045384999), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`. `python manage.py whatsapp_vapid_keys` prints a pair. Limits in `settings`: body 1600 characters (Twilio's Messages API limit; the WhatsApp-specific figure could not be confirmed in Twilio's pages), images 5 MB, PDFs, audio and video 16 MB (checked against Twilio's WhatsApp media page). Startup log line shows `whatsapp=on|off`.

## Models
`Contact` (phone E.164 unique, `profile_name`, resolved `name`, links `user` / `lead_email` / `application`, `opted_out_at`, `last_inbound_at` = the window, `last_message_at`, `last_preview`), `ContactRead` (per staff member: read time, unread = his messages after it), `Message` (integer id; direction in/out; kind text, image, document, audio, video, file, template, other; body; media key, type, filename, size, width, height; `twilio_sid` unique; status queued, sent, delivered, read, failed, undelivered, received; error code and message; author; template; `claimed_at`; created, updated, sent), `Template` (Twilio Content SID unique, name, language, category, approval status, body, variables, `variable_labels`), `PushSubscription`, `WhatsAppPrefs` (mute). `outreach.PersonEdit` records staff edits of a first name or mobile (timeline lines). `journey.JourneySession` gains `lead_first_name`, `lead_mobile`, `lead_consent_version` (with database defaults).

## Webhooks (public site host, no sign-in, no CSRF, signature checked)
- `POST /twilio/whatsapp/incoming/` and `POST /twilio/whatsapp/status/`. `X-Twilio-Signature` = HMAC-SHA1 with `TWILIO_AUTH_TOKEN` over `SITE_URL` + path (+ query) and the sorted POST parameters, constant-time compare. 404 until configured, 403 on a bad signature, 413 over 64 KB. Answer `<Response/>` at once. Only messages To our sender are stored (BML shares the account). Idempotent on `MessageSid`.
- STOP, STOPALL, UNSUBSCRIBE, END, QUIT, CANCEL (whole message, any case) set `opted_out_at`. Only START or UNSTOP clears it: any other message from him is stored and shown but he stays opted out, and nothing at all is sent to him until then (texts and templates).
- His file is copied from Twilio by the worker (`whatsapp.tasks.process_inbound`) into the default storage (over 16 MB: not kept, the bubble says so). Voice notes, video and other files are kept with kind `audio`, `video`, `file`. Then the push goes out.
- `GET /twilio/whatsapp/media/<signed token>/`: the public, signed link (valid 1 hour) Twilio fetches an outgoing photo or PDF from. Django signing, not S3 presigning, so it works with local storage too.

## Sending (Approver or Admin and up, `editor`)
Free text and files only inside the 24-hour window; templates any time; nothing after STOP. Sent by the worker (`whatsapp.tasks.send_message`, never twice), `StatusCallback` on each send, the outcome is written on the message and shown in the chat. A duplicate within 10 seconds is refused. A failure shows a plain reason (`whatsapp/errors.py`; the Twilio code never shows) and, when it makes sense, `retry_url`. Only approved templates whose name starts `spa99_` can be sent, enforced in the service. Template variables: one line, at most 200 characters, all required.

## Office endpoints (Office host; `reader` views, `editor` sends)
| URL | Method | Does |
|---|---|---|
| `/whatsapp/` | GET | Inbox. `?q=` (name, profile name, number, lead address), `?unread=1`, `?page=`. HTMX gets the rows only. Context: `rows[{id, name, phone, preview, preview_kind, direction, last_message_at, unread, opted_out, window_open, url}]`, `has_next` (one extra row, no counts), `page`, `q`, `unread_only`, `unread_total`, `more_url`, `can_send`, `configured` |
| `/whatsapp/unread/` | GET | `{unread_total}` (chats with unread messages) for the badge |
| `/whatsapp/<contact>/` | GET | Thread page. Context: `contact`, `messages` (newest 30, oldest first), `has_older`, `older_url`, `unread{count, first_id}`, `last_id`, `cursor`, `templates`, `gold` (with `?gold=<application id>`), `open_picker` (`?picker=1`), `urls{poll, send, send_media, send_template, read, inbox, templates}`, `configured` |
| `/whatsapp/<contact>/messages/?before=<id>` | GET | JSON `{messages, has_older, older_url}` |
| `/whatsapp/<contact>/poll/?after=<id>&since=<cursor>` | GET | JSON `{messages (new), updates (changed ticks or errors since the cursor), contact, unread_total, last_id, cursor}` |
| `/whatsapp/<contact>/send/` | POST `body` | JSON `{ok, message}` or `{ok: false, error, message[, missing]}` (409 window closed or opted out, 400 other) |
| `/whatsapp/<contact>/send-media/` | POST file `file`, `body` (caption) | same; 413 too big |
| `/whatsapp/<contact>/send-template/` | POST `template`, `var_<key>` | same; `missing` lists empty variable keys |
| `/whatsapp/<contact>/read/` | POST | mark read for me |
| `/whatsapp/<contact>/retry/<message id>/` | POST | send a failed message again |
| `/whatsapp/templates/?contact=<id>` | GET | JSON `{templates: [{id, name, label, category, body, body_html, variables[{key, label, prefill}]}]}` |
| `/whatsapp/media/<message id>/` | GET | his or our file, for staff (photos, PDFs, audio and video inline, the rest downloads) |
| `/people/<id>/whatsapp/`, `/leads/<id>/whatsapp/`, `/gold/<id>/whatsapp/` | GET | the Message button: opens his chat (made on the first click); no mobile: back to the page with a note |
| `/leads/<id>/contact/` | POST `first_name`, `mobile_country`, `mobile` | add or fix a lead's name and mobile (all his journeys), audited |
| `/people/<id>/mobile/` | POST `mobile_country`, `mobile` | the same for a registered person |

Message dict (`services.message_dict`): `{id, direction, kind, body, body_html, status, error{reason, can_retry} or null, author, author_id, author_first_name, template{id, name, label} or null, media{url, type, filename, size, width, height} or null, created_at, sent_at, retry_url}`. `body_html` is formatted safely by `whatsapp.formatting.render` (escaped first; also the template filter `{{ text|wa_format }}` from `whatsapp_tags`).

Contact dict: `{id, name, has_name, phone, profile_name, labels[Lead|Registered|Gold], page_url, opted_out, window{state: open|closed|opted_out|empty|template_waiting, open, ends_at}, can_send, url, last_message_at, limits{body, image_bytes, file_bytes}}`.

Lead, person and Gold pages get `whatsapp` = `{configured, has_mobile, mobile, first_name, contact_url, start_url, edit_url (empty on Gold), can_send, can_edit, has_chat, window_open, window_closes_at, opted_out, unread, thread_url}` and `mobile_countries`.

Gold: sending from a Gold chat (`gold=<application id>` posted with the message) turns New into Contacted with a `responded` event (`meta {"whatsapp": true}`), once. `/gold/<id>/respond/` and `?do=respond` (the approver email's link) redirect to the chat. The email Message and Respond views, forms and dialogs are gone; old `PersonMessage` rows still show in timelines; the email template rows `office_message` and `gold_respond` stay in System > Emails, unused.

Timeline (lead, person): not one line per message: "First WhatsApp sent by X" (template name as detail), "WhatsApp: 3 from him, 2 from us" a day (his last message as detail; link to the chat), "He replied STOP", "WhatsApp not sent" with the reason (`kind` `whatsapp_failed`), "Mobile added/changed by X", "First name added/changed by X", "Gold application marked Contacted".

## Push and the Office web app (Office URLconf only)
`/manifest.webmanifest` and `/sw.js` (header `Service-Worker-Allowed: /`, no cache, public files) exist only in `config.urls_office`; the public site, Control and System return 404 for both and link no manifest. Source: `whatsapp/pwa.py` (manifest fields and the `ICONS` list for the frontend to fill) and `whatsapp/templates/whatsapp/sw.js`. `office/base.html` links the manifest.
- `GET /whatsapp/push/config/`: `{configured, vapid_public_key, muted, devices, urls{subscribe, unsubscribe, mute, test}}` (also context `whatsapp_push`, `whatsapp_unread`, `whatsapp_configured` on every Office page).
- `POST /whatsapp/push/subscribe/` JSON `{endpoint, keys{p256dh, auth}}`; `/unsubscribe/` JSON `{endpoint}`; `/mute/` JSON `{muted: bool}`; `/test/` sends a test to my devices.
- On each message from him the worker pushes `{title: name, body: first line or "Sent a photo", url: "/whatsapp/<contact>/", tag: <contact id>}` to every unmuted staff member with an Office level. 404 or 410 from the push service removes the device.

## Mobile numbers (two parts everywhere)
Forms post `mobile_country` (ISO code, default `GB`) and `mobile`; `common/phone.py` normalises to E.164 with the `phonenumbers` library (possible, valid, a mobile line), drops a leading 0, lets a typed `+` or `00` win, and answers "That doesn't look like a valid mobile number." `phone.countries()` is the list (`{iso, dial, name}`: UK, Ireland, Israel, US, Canada, Belgium, France, Germany, Netherlands, then A to Z). Context keys: `mobile_countries` (Register and the Office pages), `gate.countries` (the journey page config). Register also still takes a single `mobile` (UK unless it starts with +). The Gold application form still asks for a UK mobile (unchanged).

## System > WhatsApp
Configured yes or no (names of empty settings only, never values), the two webhook URLs, **Check Twilio** (account active, sender online), the `spa99_` templates with approval status, **Sync templates** (a background job), push keys set and devices. Developer level and the unlock, like the other System pages.

## Erasure and export
Person delete, lead delete and the GDPR exports include the chats (found by his numbers: account, email step, Gold application): contact, messages, files in storage and the queue records that name those messages. Push subscriptions belong to staff and are not part of a person's data.

## Not done, on purpose
Unknown numbers that write first make a contact only (no lead row: a lead needs an email). One file per message (WhatsApp sends one per message). Template approval labels come from code defaults (`spa99_lead_follow_up`: First name) or the admin; Twilio does not hold them.
