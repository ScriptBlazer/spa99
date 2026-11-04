# WhatsApp in the Office (plan, 2026-11-03)

Status: **built and reviewed** (2026-11-03 server side and UI, round 2 and review fixes 2026-11-04, branch `feature/whatsapp`, not released); the design is in `whatsapp-design.md`. Ship in one go after testing. Decisions in PROJECT.md (2026-11-03 WhatsApp rows). The section "Built" at the end lists the endpoints, payloads and context keys as they are in the code.

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
A new number on **WhatsApp (through Twilio)** becomes a full staff to lead chat in the Office, as close to WhatsApp as we like, with push notifications (PWA). The AI assistant chat stays separate. Staff messages go by WhatsApp; email stays only for Send guide and automatic emails (the email Message was removed).

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
| `/people/<id>/whatsapp/`, `/leads/<id>/whatsapp/`, `/gold/<id>/whatsapp/` | GET | opens his chat read-only (`?from=<kind>:<id>` and `gold=` ride along): **no write, ever**. This is also the Gold approver email's `?do=respond` target. No chat yet: back to the page with a note; no mobile: back to the page with a note |
| same three URLs | POST (editor, CSRF) | the Start WhatsApp chat button: makes the chat when there is none and links the NEW chat to this page's person (`ownership.link`); an existing chat is opened untouched (no write), the thread then offers the link |
| `/whatsapp/<contact>/link/` | POST `from=<kind>:<id>` (editor) | the thread's "This number isn't linked to <name>. Link it?" button (shown to an editor, for an unlinked chat reached from a page whose person has this number, after the chat's name, number and messages are on screen). Only an unlinked chat is linked; refused when the number is not his |
| `/whatsapp/<contact>/delete/` | POST `confirm` (Admin and up, like person delete) | erase one chat: messages, files, queue records. Audited in the System log (`chat_deleted`: who, when, counts, never text) |
| `/leads/<id>/contact/` | POST `first_name`, `mobile_country`, `mobile` | add or fix a lead's name and mobile (all his journeys), audited |
| `/people/<id>/mobile/` | POST `mobile_country`, `mobile` | the same for a registered person |

Message dict (`services.message_dict`): `{id, direction, kind, body, body_html, status, error{reason, can_retry} or null, author, author_id, author_first_name, template{id, name, label} or null, media{url, type, filename, size, width, height} or null, created_at, sent_at, retry_url}`. `body_html` is formatted safely by `whatsapp.formatting.render` (escaped first; also the template filter `{{ text|wa_format }}` from `whatsapp_tags`).

Contact dict: `{id, name, has_name, phone, profile_name, labels[Lead|Registered|Gold], page_url, opted_out, window{state: open|closed|opted_out|empty|template_waiting, open, ends_at}, can_send, url, last_message_at, limits{body, image_bytes, file_bytes}}`.

Lead, person and Gold pages get `whatsapp` = `{configured, has_mobile, mobile, first_name, contact_url, start_url, edit_url (on Gold: `/gold/<id>/mobile/`), can_send, can_edit, has_chat, window_open, window_closes_at, opted_out, unread, thread_url, open_url}` and `mobile_countries`. `start_url` is where the Start form POSTs; `open_url` is the read-only link for Open (the thread with `?from=`).

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
Configured yes or no (names of empty settings only, never values), the two webhook URLs, **Check Twilio** (is the Spa 99 sender online; read through the WhatsApp Senders API only, because a Standard API key cannot read the Twilio account), the `spa99_` templates with approval status, **Sync templates** (a background job), push keys set and devices. Developer level and the unlock, like the other System pages.

## Erasure and export
Staff-run person delete, lead delete, Django admin delete and the staff exports include the chats (found by the ownership rule in `common/ownership.py`, see "Ownership" in office-email-chat.md: the owner link, the lead address when his account is verified, a proven Gold application; never by a number): contact, messages, files in storage and the queue records that name those messages. **A member's own self-service download and account delete leave chats out**: a mobile number is not proven (anyone can register with a lead's number), so a number must never select someone else's chat (`person_phones` is gone); a member who wants his chat exported or erased asks the team. The chat keeps a stored owner link (`user`, `lead_email`, `application`), kept even when the number is later changed or removed, so an erasure finds an old chat. Push subscriptions belong to staff and are not part of a person's data.

## Not done, on purpose
Unknown numbers that write first make a contact only (no lead row: a lead needs an email). One file per message (WhatsApp sends one per message). Template approval labels come from code defaults (`spa99_lead_follow_up`: First name) or the admin; Twilio does not hold them.

---

# Built, UI (2026-11-03)

Design brief: `whatsapp-design.md`. Files: `whatsapp/templates/whatsapp/` (`inbox.html`, `thread.html`, `_list.html`, `_rows.html`, `_cards.html`, `_thread.html`, `_who.html`, `_notify_sheet.html`, `sw.js`), `office/templates/office/_wa_button.html`, `common/static/common/css/office-whatsapp.css`, JS `wa-thread.js` (one chat), `office-whatsapp.js` (list, swap, title), `office-push.js` (service worker, notifications sheet, install hints), `wa-badge.js` (unread count), `office-mobile.js` (Add a mobile dialog).

- **Safety:** no HTML is built from message text in JS. Bubbles use `createElement` and `textContent`; the only `innerHTML` is the server's `body_html` (and a template's `body_html` for the preview). An unsent bubble shows plain text until the server answers.
- **The thread page** embeds its data (`#wa-data`, from context `wa`); the thread view's message list is `chat_messages` (not `messages`, which is Django's own name and made the toasts print every message). The list pane beside it comes from the same list context as the inbox.
- **Inbox rows** gained `status` (the tick of our latest message), `gold`, `has_name`, `no_reply`; the list takes `?noreply=1` (we wrote last, he never replied, more than 3 days ago).
- **Polling:** `poll` every 4 s while visible, 30 s hidden, back off when offline, ticks through `updates`. Sends are optimistic (temporary bubble, replaced by the server's message); polling pauses while a send is in flight.
- **Window slots:** one `data-state` on the chat (`open`, `closed`, `template_waiting`, `empty`, `opted_out`, `viewonly`, `unconfigured`) decides which bar or composer shows; the "closes in" line is recalculated every 30 s.
- **Phone keyboard:** `visualViewport` sets `--wa-vh` and `--wa-top` on the chat and `data-keyboard` when the viewport shrank by more than 120 px; `interactive-widget=resizes-content` is in the Office viewport meta.
- **Pages:** `_wa_button.html` is the one WhatsApp button (states in the brief); the Add a mobile dialog posts with `X-Requested-With: fetch` and gets 200 with `ok: false` for a wrong or taken number (a plain `Accept: application/json` caller still gets 400); on success the Reach out card is swapped from the server.
- **Web app (Office host only):** `base.html` has the apple meta tags, `apple-touch-icon` and the manifest link; `pwa.ICONS` lists the three manifest icons; the worker shows push (icon and badge, "3 new messages" from the third, nothing for a chat he has open and can see), focuses or opens the chat on tap, has no fetch handler and caches nothing.
- **Mobile numbers:** the email step and Register show a country select (only its dial code in the box) beside the number. `validate.js` checks lightly when a form has a country select (UK rules for +44, otherwise 6 to 15 digits); `POST /validate/mobile/` takes `mobile_country` and uses `common.phone`; the Gold form stays UK only.

Departures from the brief: see the build report in PROJECT.md; the main ones are the Moishe calls above, the country select in place of the "Outside the UK?" hint, no side link to System on the empty template message, and the page note under the email step hidden on a phone so the step fits 375 by 667.


---

# Round 2 (plan, 2026-11-04)

Checked in Twilio's docs on 2026-11-04. The Create Message request has no parameter to quote a message or send a reaction, and the incoming webhook page does not mention reactions. Meta's own API has both, but moving off Twilio is not worth it for these.

- **His replies:** the webhook's `OriginalRepliedMessageSid` links his message to ours and shows the quote. Twilio only sends it for replies to messages under 7 days old.
- **Staff replies:** Reply on a bubble. The Office links them; his phone gets the quoted line as WhatsApp's `> text` formatting, not the tap-to-jump quote box.
- **His reactions:** unknown until a real phone test. A message with no text and no file gets a neutral bubble and logs the parameter names only (never values), so we can see what Twilio sends.
- **Staff reactions:** cannot be sent. A quick emoji row sends the emoji as a normal message, and says so.
- **Video:** MP4 (H.264 and AAC), up to 16 MB, inside the window.
- **Voice notes:** recorded in the chat with the browser's recorder, converted on the server to OGG Opus with ffmpeg, because Twilio only takes Opus in OGG and browsers record WebM or MP4. Needs ffmpeg in the Docker image. May show as an audio file rather than a voice note on his phone: check in the phone test.
- **Button:** the WhatsApp button stays visible when Twilio is not set up, and says so. It was hidden because `wa.configured` was false.

## Mobile optional at the end of the journey (Moishe, 2026-11-04, replaces "all required")
- The email step asks for first name and email (required) and mobile (optional), so the number does not put people off signing up. A line under the field encourages it: optional, add it if you want the team to reach out with good offers. Designer writes the final wording.
- A number given is checked as before. A blank number is fine. The one consent tick stays as it is.
- **No mobile on a page:** only the email button shows, with a greyed line under it, "Add a number to enable WhatsApp". Clicking it opens the staff Add a mobile dialog. Once saved, the WhatsApp button appears.
- Register and the Gold form are unchanged (still ask for a mobile).


---

# Built, round 2 (server side, 2026-11-04)

Settings added: `FFMPEG_BIN` (optional, default `ffmpeg`), limits in settings `WHATSAPP_VOICE_MAX_SECONDS` (300), `WHATSAPP_VOICE_MAX_UPLOAD_BYTES` (10 MB), `WHATSAPP_VOICE_TIMEOUT_SECONDS` (30). Startup line: `voice=on|off`. Migration `whatsapp 0002` (nullable `Message.reply_to`).

- **Replies in.** `Message.reply_to` (self FK, SET_NULL). `record_inbound` links it from `OriginalRepliedMessageSid` only when that sid is a message of the same chat. Twilio sends it for replies to messages under 7 days old.
- **Replies out.** `send`, `send-media` and `send-voice` accept `reply_to=<message id>` of the same chat (anything else: 400 `bad_reply`). `body` stays as typed. What goes to Twilio is built in `services.deliver` by `outgoing_text`: `> first line of the quoted text`, a blank line, the body (a photo quotes as "Photo", also "Voice note", "Video", "PDF", "File", "Message"; first line cut at 100 characters). The 1600 limit counts the final text (`too_long`). A retry sends the same text. A voice note carries no quote (no text to put it in) but the Office still links it. Message dict gains **`reply_to`**: `{id, direction, kind, text}` or `null`.
- **Unknown inbound.** No text, no file, no location: `kind: "other"` with an empty `body` (the page shows a neutral bubble such as "Message type not supported here"; the list preview reads "Message"). The log line `WhatsApp message with no text, file or location; parameter names: ...` lists parameter NAMES only, never values or numbers. No reaction format is invented.
- **Video.** `video/mp4` is accepted from staff (`send-media`), found by its `ftyp` brand (isom, iso2..iso6, mp41, mp42, avc1, M4V, MSNV, dash; QuickTime `.mov` is refused), up to 16 MB. The signed media link serves the stored type (`video/mp4`, `audio/ogg`, `application/pdf`, images), which is what Twilio checks. `BAD_FILE` now reads "Photos, PDFs or MP4 videos only."
- **Voice notes.** `POST /whatsapp/<contact>/send-voice/` (`editor`): file `file`, `duration` (seconds, the browser's own figure, only used to refuse early), optional `reply_to`, `gold`. The first bytes decide the format (WebM, MP4 or Ogg audio; the declared type is ignored). ffmpeg converts to OGG Opus mono 32 kbit/s: subprocess with an argument list (no shell), 30 s timeout, `-protocol_whitelist file`, the demuxer forced from the first bytes (`-f`), `-t 301`, `-map_metadata -1`, in a temporary folder that is always removed. The real length is measured from ffmpeg's own progress output and over 5 minutes is refused (`voice_too_long`, 400); over 10 MB uploaded is `too_big` (413); not audio or unconvertible is `bad_file` (400); ffmpeg missing is `voice_unavailable` (503). Sent as `audio/ogg`, filename `voice-note.ogg`, kind `audio`; the answers are those of `send-media`. Whether his phone shows it as a voice note or as an audio file is for the phone test.
- **Context for the screen.** `contact.voice` = `{available, max_seconds, max_bytes}` (in the thread page's `contact` and in every poll): hide the microphone when `available` is false. `urls.send_voice` is in the thread context.
- **Docker and CI.** The `Dockerfile` installs `ffmpeg` with `--no-install-recommends` before `USER app` (size effect: see GO-LIVE; not measured here). Tests mock `subprocess.run`; one optional test converts a real file and skips when ffmpeg is not installed, and nothing else needs ffmpeg, so CI without it passes.
- **Microphone permission.** No `Permissions-Policy` header existed. `HostRoutingMiddleware` now sets `microphone=(self)` on the Office host and `microphone=()` on every other host.
- **Button state when Twilio is not set up.** `whatsapp` (lead, person, Gold pages) keeps all its keys and gains **`state`** (`no_mobile`, `unconfigured`, `view_only`, `ready`, `chat`), **`reason`** (plain words for the greyed line: "Add a number to enable WhatsApp" when there is no mobile, "WhatsApp is not set up yet." when `configured` is false), **`can_add_number`** (a staff member who may edit, a page with an `edit_url`, and no mobile) and `thread_url` always present. `can_send` is still false when not configured, so the template should key on `state`, not on `configured`.

## Mobile optional at the end of the journey (server side, 2026-11-04)
- `journey.services.save_lead`: first name and email are required, consent as before; a blank `mobile` is stored blank; a typed one is still validated by `common.phone` (error key `mobile`). `POST /journey/lead/` errors no longer include `mobile` when it is blank. The gate config (`gate`, from `journey.copy.GATE`) gains `mobile_optional: true` and `mobile_hint` (placeholder wording, the designer writes the final line). The browser should not send a blank mobile through live validation as an error: `POST /validate/mobile/` takes `optional=1` and then answers valid for a blank number (a typed one is still checked). Register and the Gold form are unchanged.
- Office: `whatsapp.state == "no_mobile"` on a lead or person with no number: show the email button alone and the greyed line `whatsapp.reason`; when `whatsapp.can_add_number`, it opens the existing Add a mobile dialog (`whatsapp.edit_url`). **A Gold applicant with no mobile can occur** (the application form requires one, but `GoldApplication.mobile` is `blank=True`, so an old or admin-made row can have none; the number may also come from his account or a journey lead on his address) and the Gold page has an `edit_url` too (`POST /gold/<id>/mobile/`, `mobile_country` and `mobile`; `outreach.services.set_gold_mobile`: an applicant with an account gets his account's mobile set, otherwise the application's, and any journey of his that already holds a number is kept in step; audited as a Mobile line in his timeline, like the lead and person ones), so `can_add_number` works there and the same dialog (`_mobile_dialog.html`) opens.


---

# Built, UI, round 2 (2026-11-04)

Design brief: `email-chat-design.md` (sections 1, 4, 5 and 6). Files: `office/templates/office/_channels.html`, `_wa_button.html` and `_email_button.html` (the two reach out buttons), `whatsapp/templates/whatsapp/_thread.html` (quote bar, microphone, recording panel), `common/static/common/js/wa-thread.js` (extended), `office-keyboard.js` (the phone keyboard handling, now shared with email), `office-dom.js` (small shared helpers), `office-whatsapp.css` (round 2 section at the end).

- **Buttons.** `_channels.html` draws WhatsApp then Email, one channel a row, keyed on `whatsapp.state` (never on `configured`). Twilio not set up: "Start WhatsApp chat" stays, greyed, with "WhatsApp is not set up yet."; with a chat already, "Open WhatsApp chat" stays a link to the history. No mobile: the email button alone and, under it, a grey line that opens the Add a mobile dialog (staff who may add one), or a static line (view-only staff: "No mobile on file."; staff can add a number on every page, Gold included). After the dialog saves, the card is swapped from the server and focus moves to the new button. `reach_primary` (in `office_tags`) decides the one primary: WhatsApp when he can be sent to on it, else Email, none on Gold.
- **Reply.** Open window only. A fine pointer: Reply (and, on his messages, an emoji disc) appear beside the bubble on hover or focus; a touch screen: tap the bubble and the row opens under it (not on a link, photo, video or audio control, not while text is selected). The log is one tab stop with Up and Down between messages, Enter opens the actions, R replies, Escape goes back. The quote bar sits above the composer with the note "On his phone this shows as a quoted line." (a voice note: "A voice note carries no quote on his phone."). In a bubble the quote is a button that scrolls to the original with one soft fade (or says "That message is further back."). The 1600 limit counts the final text with the `> ` line.
- **Emoji.** Five calm emoji, a tap sends one normal message with no quote, and the row says "Goes as a normal message, not a reaction."
- **Video.** `accept` gains `video/mp4`; an iPhone `.mov` is refused in the server's words. The bubble shows the video with controls, its time and tick on their own line beneath; if the browser cannot play it the bubble becomes a file card with a download.
- **Voice notes.** The microphone takes the Send slot while the field is empty, nothing is attached, `contact.voice.available` is true and the browser can record (re-checked on every poll). Tap to start, tap to send. States: asking, recording (red dot, timer, "Stops at 5:00" in the last 30 seconds), stopped (limit, or the phone locked), then the bubble at once with a progress bar. Every exit (cancel, send, the limit, a hidden page, leaving the chat or the page) stops the recorder and every track of the stream. Errors as in the brief (blocked, no microphone, too long, too large, unusable with "Try again" resending the held recording, unavailable).
- **A message the Office cannot show** (`kind: other`) is an ordinary incoming bubble that says "This message cannot be shown here." in muted text, with no actions.

## Mobile optional at the email step, the screen (2026-11-04)
See `journey.md` (Updated 2026-11-04). The staff side is in the buttons above.

---

# Review fixes (2026-11-04)

- **Reply works on template bubbles.** `reply_target` no longer refuses a template; the quote is its text (the filled body), or its name when it has none.
- **A send claimed by a worker that died** (queued, claimed more than 10 minutes ago, no Twilio id) shows "This may not have been sent" with Try again (`whatsapp.services.is_unsure`). The retry is still one conditional update, so a double click sends once. It cannot be made safe in one rare case: the worker died after Twilio took the message and before its id was saved; Try again then makes a second WhatsApp for him. The wording tells staff to check his phone first.
- **Gold with no number:** staff can add or fix a mobile on the Gold page (see above).
- **Consent text in the Office follows the version he ticked** (`journey.copy.consent_text`): "" (email only), `2026-11-03` (email and WhatsApp) and `2026-11-04` (email, WhatsApp if a number was added, about opening and offers).
