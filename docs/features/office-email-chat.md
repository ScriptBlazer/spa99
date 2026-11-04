# Email chat in the Office (plan, 2026-11-04)

Status: **server side built** (2026-11-04, branch `feature/whatsapp`; see "Built" at the end for every endpoint, payload and context key); UI follows. Decisions in PROJECT.md (2026-11-04 rows).

## Goal
Staff have two clearly separate ways to talk to a person: **WhatsApp** and **Email**. Email is a real chat: staff write in the Office, he replies from his normal mailbox, and the reply lands in the Office thread.

This reverses 2026-11-03 "email Message goes away, staff messages go by WhatsApp only". Automatic emails and Send guide are unchanged.

## How a reply gets back (Postmark inbound)
- Each thread has a random token. Office emails go from hello@ with `Reply-To: reply+<token>@<EMAIL_INBOUND_DOMAIN>`.
- Postmark receives mail for that domain and POSTs JSON to our inbound webhook. `MailboxHash` holds the token; `StrippedTextReply` holds only his new text (fall back to `TextBody`; if there is only `HtmlBody`, strip it to text). `MessageID` makes the webhook idempotent. Attachments arrive base64.
- Postmark retries on anything but 200, and stops on 403 (10 retries, up to 6 hours apart).
- `EMAIL_INBOUND_DOMAIN` blank: Reply-To stays hello@, the Office still sends and shows sent emails, and the screen says replies go to the hello@ mailbox.

## Setup Moishe does (no code)
1. Postmark plan must include inbound: 10K Pro ($16.50 a month) or Platform ($18), against Basic ($15), per Postmark's August 2025 update. Check Account > Plans & Add-ons.
2. Cloudflare DNS: `MX`, name `reply`, value `inbound.postmarkapp.com`, priority 10. This subdomain only, so hello@ and BML mail are untouched.
3. Postmark > server > Inbound stream > Settings: inbound domain `reply.spa99.uk`, webhook URL with its own password.
4. Server `.env`: `EMAIL_INBOUND_DOMAIN=reply.spa99.uk`, webhook user and password.

## Screens
- **Reach out card** (lead, person, Gold): two labelled parts, WhatsApp and Email, each with its own button and status. A channel that cannot be used stays visible and says why.
- **Email** in the Office navigation: inbox and thread, in the same family as WhatsApp but visibly a different channel.
- Thread: his and our emails, subject on the first and when it changes, attachments, delivery state, bounce shown plainly. Staff can write at any time (no 24-hour window).
- The assistant chat tab is renamed **Assistant** so "chats" no longer means three things.

## Rules
- Viewing: `reader`. Sending: `editor` (Approver or Admin and up), same as WhatsApp.
- Text only is rendered: no HTML from an email ever reaches the page. Attachments download, they never open inline, except images and PDFs.
- A Gold email sent from the application marks New as Contacted, once, like WhatsApp.
- Replies notify staff by the same push and mute setting as WhatsApp.
- Reply from another address (forwarded mail): stored, and the bubble shows that address.
- Spam flagged by Postmark (`X-Spam-Status: Yes`): stored and marked, no push.
- UK GDPR: threads, messages and files are in staff delete and export. Member self-service includes a thread only when his account's email is verified and equals the thread address.

## Mini Outlook (Moishe, 2026-11-04, replaces the plain text parts above)
- **Buttons on every lead, person and Gold page, where Message used to be:** one for WhatsApp and one for email, always both. The wording shows the state: "Start WhatsApp chat" or "Open WhatsApp chat", "Start email" or "Open email thread".
- **Email tab in the side navigation, like WhatsApp:** thread list on the left, the open email large on the right. Phone: list, then the email.
- **Several threads per person,** each with its own subject and reply token, like Outlook. The page button opens his latest thread, or a new email if he has none.
- **New email** from the Email tab: search for a known person or type an address, then subject and body. Reply from inside a thread.
- **Rich text:** bold, italic, underline, strikethrough, highlight, text colour, bulleted and numbered lists, links, quotes, attachments. The server cleans the HTML to an allow-list and always sends a plain text copy too.
- **His emails display as formatted,** with HTML cleaned on the server, shown in a sandboxed frame with no scripts, and outside images blocked until staff click Show images. Earlier quoted text collapses.
- List filters: All, Unread, Sent with no reply. Search by name, address and subject.
- Not in this round: Bcc, Forward, shared folders, server-side drafts (an unsent draft stays in that browser).

---

# Built (server side, 2026-11-04)

App `emailchat` (models, `services.py` for all logic, `webhooks.py`, `views.py`, `tasks.py`, `context.py`, `admin.py`). Shared helper `common/richtext.py` (cleaning and plain text). `nh3==0.3.7` added. Deviation: no `django-simple-history` on these models (messages are the log; copies would double what must be erased). Minimal placeholder templates in `emailchat/templates/emailchat/` (`inbox.html`, `_rows.html`, `thread.html`, `new.html`) for the frontend to replace.

## Settings (server `.env`, all optional)
`EMAIL_INBOUND_DOMAIN` (blank = replies go to hello@, nothing lands in the Office), `EMAIL_INBOUND_USER`, `EMAIL_INBOUND_PASSWORD` (the inbound webhook is 404 until both are set and the domain is set). Limits in settings: file 10 MB, 9 MB of files per email we send, 20 files, whole inbound POST 50 MB. Startup line: `emailchat=replies-in-office | replies-to-mailbox | inbound-webhook-not-set`.

## Models
`Thread` (UUID; `email` lower case, NOT unique: many threads per address; `token` unique random 24 hex; `subject` the first one; owner links `user` / `lead_email` / `application` kept for erasure; `name`; `last_message_at`, `last_inbound_at`, `last_preview`, `last_direction`, `has_attachment`), `ThreadRead` (per staff member), `Message` (integer id; direction in/out; `subject`, `shows_subject`, `body_text`, `body_full`, `body_html` cleaned, `has_remote_images`; author; status queued, sent, delivered, bounced, failed, received; `provider_id` unique (Postmark MessageID); `rfc_message_id`, `in_reply_to`, `references`; `from_address`, `from_name`; `spam`; `note`; error code and message; `claimed_at`; `legacy_person_message`), `Attachment` (storage key, filename, served type, declared type, size, `content_id`, `inline_ok`, `checked`). Files are in the default storage (S3 on live) under `emailchat/<thread id>/<random>`.

## Sending
`services.send` cleans the HTML (`common.richtext.clean_outgoing`: p, br, strong, b, em, i, u, s, mark, span with only `color` and `background-color` values that are plain colours, ul, ol, li, a with http, https and mailto only and `rel`/`target` set, blockquote, h2, h3), makes the plain text copy, stores files, queues `emailchat.tasks.send_message` (id only). The worker (`services.deliver`, claimed once, never twice) calls `notifications.services.send_templated("office_message", ..., html_body=..., plain_body=...)` from the From address of that email's sender setting (hello@ by default). `send_templated` gained `html_body`: cleaned AGAIN there with the same allow-list before it is marked safe, and a `html_body` key in the `context` argument is ignored, so no existing path changed. The suppression guard still runs: a suppressed address comes back as **failed**, `error.reason` "Not sent. This address bounced before or marked an email as spam, so nothing more can be sent to it.", no retry. A duplicate (same body, same person, within 10 seconds) is refused. A subject left blank becomes "Re: <last subject>" (the thread's own subject while it is empty). Threading headers: our own `Message-ID`, `In-Reply-To` and `References` from his last mail that carried a Message-ID, `X-PM-Tag: office-chat` and `X-PM-Metadata-chat: <message id>` (SMTP gives no Postmark MessageID at send time, so the metadata is how a bounce finds the message). Never sent: files named .exe, .bat, .js and the like (`bad_file`).
- Reply-To `reply+<token>@<EMAIL_INBOUND_DOMAIN>`; with the domain blank Reply-To is the contact (hello@) address and context carries `replies_to_mailbox: true` (the screen says replies go to the mailbox).
- Gold: sending from a Gold thread (`gold=<application id>` posted) turns New into Contacted once, with a `responded` event, `meta {"email": true}` (`gold.actions.whatsapp_sent(..., via="email")`); the Gold history says "Marked Contacted: an email went to the applicant."

## Inbound (Postmark)
`POST /postmark/inbound/` on the PUBLIC host (`config/urls.py`, next to `postmark/webhook/`). HTTP Basic with `EMAIL_INBOUND_USER` and `_PASSWORD`; 404 until configured; 401 wrong or missing credentials. Reads the body with `request.read()` (not `.body`: Django's 2.5 MB check would refuse a mail with files). Over 50 MB: 200 and a log line. Not JSON: 400. **Always 200 for anything we choose not to store** (unknown, missing or malformed `MailboxHash`, no `MessageID`), logged without personal data. Idempotent on `MessageID`. Text = `StrippedTextReply`, else `TextBody`, else the HTML stripped (`body_full` keeps the whole `TextBody` when it differs). `HtmlBody` is cleaned by `richtext.clean_incoming` and stored. Sender: `FromFull.Email` (else `From`) stored as `from_address`; the message dict has `from_other` when it is not the thread address. Spam (`X-Spam-Status` starting Yes): stored and flagged, never pushed, never counted unread, never moves the thread.
- **How attachment bytes reach the worker:** the web process decodes each file and writes it straight to the default storage (S3 on live; web and worker share no disk, so storage is the one safe place) and the task queue only ever gets the message id. If storage fails the webhook removes the half-stored email and answers 500, so Postmark's retry stores it whole. The worker (`emailchat.tasks.process_inbound`) then checks each file's first bytes and sends the push. Over 10 MB, undecodable or past 20 files: dropped, with a note on the message (`note`). Only an image (PNG, JPEG, GIF, WebP) or PDF whose first bytes match its declared type is `inline_ok`; everything else downloads as `application/octet-stream`.
- Push: `whatsapp.push.notify_payload` (the same devices and the same mute setting) with `{title: "Email from <name>", body: "<subject>: <first line>", url: "/email/<thread>/", tag: "email-<thread>"}`.
- **Bounces:** `notifications.postmark.apply` calls `emailchat.services.apply_feedback` for Bounce, SpamComplaint and Delivery records before its own logic (which is unchanged, including the suppression list and the bounce log that drives "Possible fake"). The chat message named by `Metadata.chat`, and only when the recipient is the thread's address, becomes `bounced` (reason "Bounced. The address did not accept this email.") or, on a spam complaint, "Marked as spam by the recipient". Transient, AutoResponder and DnsError bounces change nothing. A Delivery record moves `sent` to `delivered` (tick Delivery in Postmark). Never raises.

## His HTML (the frame)
`GET /email/message/<message id>/frame/` (`reader`, his messages with HTML only): a complete document for `<iframe sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" src=...>` (no `allow-scripts`; `allow-same-origin` only so the page can read the height to size the frame, which is safe with no scripts). Never put his HTML in the Office page. `?images=1` loads outside pictures (staff chose Show images); without it they are removed and the header `X-Blocked-Images: <n>` says how many. `cid:` pictures come from the stored files as `data:` addresses (up to 1 MB each, 5 MB in all). Headers: CSP `default-src 'none'; img-src data: [https: http: with images=1]; style-src 'unsafe-inline'; font-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'; sandbox allow-same-origin allow-popups allow-popups-to-escape-sandbox` (no script source at all), `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: no-referrer`, `nosniff`, no cache. Links carry `rel="noopener noreferrer nofollow" target="_blank"`. **Quoted history:** the cleaner keeps `<blockquote>` and turns Gmail and Yahoo quote containers into `class="quoted"`; collapsing is left to the frontend (the frame is same origin, so the page script can find `blockquote, .quoted` and fold them). Outlook's quoted blocks have no marker we can rely on, so those are not marked.

## Office endpoints (Office host; `reader` views, `editor` sends)
| URL | Method | Does |
|---|---|---|
| `/email/` | GET | Inbox. `?q=` (name, address, subject), `?filter=unread` or `noreply` (Sent with no reply: the newest message is ours), `?page=`. HTMX gets the rows only. Context: `rows[{id, subject, name, has_name, email, preview, direction, status, last_message_at, unread, has_attachment, no_reply, gold, url}]`, `has_next`, `page`, `q`, `filter`, `unread_total`, `more_url`, `can_send`, `replies_to_mailbox`, `new_url`, `people_url` |
| `/email/unread/` | GET | `{unread_total}` (threads with unread email) |
| `/email/new/` | GET | New email screen. `?person=lead:<id>`, `person:<id>`, `gold:<id>` or `?to=<address>` pre-fills. Context: `recipient{email, name, person, error}`, `urls{create, people, inbox}`, `can_send`, `replies_to_mailbox`, `limits` |
| `/email/new/` | POST | `person` or `to`, `subject` (required), optional `body_html`, `files`, `gold`. Always a NEW thread; with a body or file it also sends the first email. JSON (`Accept: application/json` or `X-Requested-With: fetch`) `{ok, thread_url, message}` or `{ok: false, error: bad_address|no_subject|bad_target|empty|too_big|bad_file, message}`; else redirects to the thread |
| `/email/people/?q=` | GET | `{results: [{name, email, kind, kinds[lead|registered|gold], person, suppressed}]}`: two letters at least, ten at most, name and address only |
| `/email/<thread>/` | GET | Thread page. Context: `thread{id, email, name, has_name, subject, labels, page_url, url, last_message_at, replies_to_mailbox, suppressed, reason, can_send, limits{file_bytes, send_bytes, files}}`, `chat_messages` (newest 30, oldest first), `has_older`, `older_url`, `unread{count, first_id}`, `last_id`, `cursor`, `reply_subject`, `gold` (with `?gold=<application id>`), `urls{poll, send, read, inbox, new, people}`, the list context, and `em` (the embedded data) |
| `/email/<thread>/messages/?before=<id>` | GET | JSON `{messages, has_older, older_url}` |
| `/email/<thread>/poll/?after=<id>&since=<cursor>` | GET | JSON `{messages, updates, thread, unread_total, last_id, cursor}`. **URL-encode the cursor** (its `+00:00` becomes a space otherwise, and `updates` come back empty) |
| `/email/<thread>/send/` | POST | `body_html`, `subject` (optional), files in `files` (several), `gold`. JSON `{ok, message}` or `{ok: false, error: empty|too_long|duplicate|bad_file|too_big, message}`; the returned message shows `queued`, the status changes through the poll |
| `/email/<thread>/read/` | POST | mark read for me |
| `/email/<thread>/retry/<message id>/` | POST | send a failed message again (a bounce is never retried) |
| `/email/file/<attachment id>/` | GET | a file for staff: only a checked image or PDF opens inline, the rest downloads |
| `/email/message/<id>/frame/` | GET | his HTML, see above |
| `/people/<id>/email-chat/`, `/leads/<id>/email-chat/`, `/gold/<id>/email-chat/` | GET | the page button: his latest thread, or the New email screen when he has none (Gold adds `?gold=<id>`) |

Message dict (`services.message_dict`): `{id, direction, subject, shows_subject, body_text, body_full, body_html, frame_url, frame_images_url, has_remote_images, status, error{reason, can_retry} or null, author, author_id, author_first_name, from_address, from_name, from_other, spam, note, attachments[{id, filename, type, size, url, inline, is_image}], created_at, sent_at, retry_url}`. **`body_html` is ours only** (cleaned, safe to show; an old copied message gets safe paragraphs made from its text); for his messages it is always `""` and `frame_url` is the sandboxed frame (empty when he sent plain text only: show `body_text` as text nodes). Show `subject` when `shows_subject`. Statuses: queued, sent, delivered, bounced, failed (out); received (in).

Lead, person and Gold pages get **`email_chat`**: `{has_thread, thread_count, latest_thread_url, new_email_url, open_url (the GET above: opens his latest thread or New email), state ("start" or "open"), label ("Start email" / "Open email thread"), email, can_send, can_edit, unread, replies_to_mailbox, suppressed, reason}` (key `email_chat`, in `office.tools.tools_context`). Every Office page also gets `email_unread` and `email_replies_to_mailbox` (context processor `emailchat.context.unread`).

## Timeline, GDPR, old messages
- Timeline (lead, person): "First email sent by X" (subject as detail), "Email: 2 from him, 1 from us" a thread a day (subject as detail, link to the thread), "Email bounced" / "Email not sent" with the reason; across all his threads. Old `PersonMessage` rows still show as "Message sent by X" until copied.
- `python manage.py backfill_email_threads [--dry-run]` copies old `PersonMessage` rows into threads (one thread per address, subject "A message from Spa 99"), idempotent, and a copied one stops showing twice. Never a migration.
- Staff export (person, lead) and erase (person delete, lead delete, Django admin delete of a thread) include every thread held for him (his addresses and the owner link): rows, files in storage and queue records (`emailchat.services.erase_threads`). A member's own download and account delete include only the thread(s) on his account email, and only when that address is verified.
- **Privacy notice not changed** (flag to Moishe: see GO-LIVE).

## Not done, on purpose
Bcc, Cc, Forward, shared folders, server-side drafts. A thread an address has never replied to stays hidden from the inbox until its first message exists. Postmark inbound mail to `reply@` with no token, or a token we do not know, is not stored.
