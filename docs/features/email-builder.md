# Email builder and "Booking is open" email

Decided by Moishe on 2026-10-27 (see the PROJECT.md decisions log). Built on `feature/defaults`. Technical choices were made by the lead and logged.

## What it is

Group mailings in **System > Emails > Mailings** are built from parts instead of one plain body. The subject stays its own field, and `{first_name}` works in the subject and in every text part.

Parts can be added, removed and moved up or down:

| Part | Fields | Rendered as (shared email layout, docs/design/EMAIL-LAYOUT.md) |
|---|---|---|
| Heading | text (max 120) | h2 in the layout's heading style |
| Paragraph | text (max 2000), blank line = new paragraph | `<p>` with the layout's paragraph style. Text is escaped. |
| Button | label (max 40), link (absolute http(s) URL, or a site path like `/memberships/` made absolute on the public site) | the layout's table button, plus "paste this link" fallback; plain text: `Label:` then URL |
| Image | uploaded file, alt text (required), optional link | full-width image (max 552 px wide), with alt text |
| Divider | none | the layout's hairline |
| Small print | text (max 500) | small muted paragraph |

- **Limits:** at most 30 parts per email, and at least one part that isn't a divider.
- **Headings:** the email's top heading is the subject without "[Test]", as now. Heading parts are section headings inside the email.
- **Footer:** the existing footer stays. News emails get the notice and unsubscribe link; Service emails get the "why you get this" line.
- **Preview:** the live preview, Desktop/Phone switch and "Send me a test" keep working.
- **Plain-text version:** built from the same parts.

## Images (lead's choices)

- **Allowed files:** JPEG, PNG or GIF, up to 2 MB. The type is checked from the file content, not just the name.
- **Storage:** the project's media storage (S3 live, local folder in dev) under `mailings/images/`, with a random file name.
- **Served by the app:** emails need public image links, but the bucket is private. Images are served through the app at `/email-image/<random id>/`, on the public site with an absolute URL. That view streams the file from storage, with long cache headers.
- **Not deleted while used:** an image used by a sent mailing is never deleted.

## Storage of parts

- **Field:** `Mailing.blocks` is a JSON list of `{type, ...fields}`, validated on save, unknown types refused.
- **Old mailings:** existing mailings keep `body`. A mailing with no blocks renders from `body` as before.
- **Opening an old draft:** the editor turns its body into paragraph parts.
- **Field kept:** `body` stays for now. Removing it is a later cleanup, with a script, never a migration backfill.

## "Booking is open" email

- **Template:** the New mailing page gets a **Start from** choice: Blank, or **Booking is open**. The template is a prefilled Service mailing to **Everyone registered**, with editable parts:
  - a heading "Booking is open"
  - a short paragraph
  - a button "Book your first visit" linking to `/account/book/`
  - small print
- **Sending:** sent like any mailing, with a test first and then Send or Schedule.
- **Starting value:** the template's words are a starting point stored in code, and the mailing is edited freely.

## Out of scope

- No "send a test to anyone" (Moishe, 2026-10-27). Tests go to the signed-in person.
- The automatic emails (confirm, reset, Gold) keep their current single-body editor.

## Status

Backend built on `feature/defaults` (2026-10-27): parts model and validation, rendering (HTML and text), picture upload and public image view, the Booking is open starter, and the endpoints below. The editor screen is built (commit 2356bd0: parts list, upload, Start from, live preview). Second round (same day): saved templates, a test without Who, and the review fixes below.

## Contract (for the editor screen)

Code: `mailings/blocks.py` (parts), `mailings/images.py` (pictures), `system/views_emails.py` and `system/emails.py` (endpoints and form).

### Parts (`blocks`: JSON list)

| type | fields | limits |
|---|---|---|
| `heading` | `text` | 120, one line |
| `paragraph` | `text` | 2000, blank line = new paragraph |
| `button` | `label`, `url` | label 40, one line; url max 500: `http(s)://...` or a site path starting with a single `/` (made absolute on SITE_URL when rendered). Anything else (`javascript:`, `data:`, `mailto:`, `//host`) is refused |
| `image` | `image` (the uploaded id), `alt` (required, 200), `url` (optional, same rules as a button link) | |
| `divider` | none | |
| `small_print` | `text` | 500 |

- `{first_name}` works in `heading`, `paragraph` and `small_print` (and the subject); no other placeholder. Not in labels, alt text or links.
- At most 30 parts, at least one that is not a divider. Unknown fields are dropped; an unknown `type` is an error.
- The limits above are also given to the page as `block_types` (`{type: {field: {max, required}}}`) and `block_max_parts`.

### Endpoints (System host, Developer, unlocked, CSRF)

- **Save: `POST /emails/mailings/new/` and `/emails/mailings/<id>/edit/`.** Form fields `name`, `subject`, `kind`, `group` (+ the group's options) and `blocks` (a JSON string, e.g. a hidden input). If `blocks` is present it is used and the old `body` is cleared; if absent the old plain-body form still works. Send `Accept: application/json` (or `X-Requested-With: fetch`) to get JSON:
  - saved: `200 {"ok": true, "id", "redirect"}`
  - refused: `400 {"ok": false, "errors": {...}}` where field errors are `{"subject": ["..."], "name": [...], "group": [...]}` and parts are `{"blocks": {"_": ["whole-email problem"], "2": {"url": ["..."]}}}`. The key under `blocks` is the part's position, counting from 0 (so `"2"` is the third part), then the field name. `"_"` is for problems with the email as a whole (too many parts, only dividers, unreadable JSON). Without the JSON header the page is rendered again with status 400 and `block_errors` in the context (same shape).
- **Preview: `POST /emails/mailings/preview/`** with `subject`, `kind`, `group` and `blocks` (JSON). Answers `200 {"ok", "subject", "html", "text", "errors"}`; when something is wrong `ok` is false, `html` is empty and `errors` has the same shape as above (`errors.blocks`). Without a `blocks` field it previews `body` as before. Previews use the sample name James.
- **Upload a picture: `POST /emails/mailings/images/`** (multipart, field `file`). JPEG, PNG or GIF by file content, max 2 MB (`image_max_bytes` in the page context). Answers `200 {"ok": true, "id", "url", "width", "height"}` (`width` and `height` are `null` if the header could not be read) or `400 {"ok": false, "message"}` (`429` when too many: 30 per 10 minutes). Put `id` in the part's `image`; `url` is the address to show in the editor.
- **Public image: `GET /email-image/<id>/`** on the public host, no login, long cache.
- **Send me a test / Send / Schedule** are unchanged and use the saved parts. Send and Schedule re-check the parts (a missing picture or bad link stops it with a plain message "Part 3: ...").

### Page context for the mailing form (New and Edit)

`blocks` (the parts to show: what was posted after a failed save, else the saved parts, else an old draft's body turned into paragraph parts, else the chosen starter, else `[]`), `block_errors`, `block_types`, `block_max_parts`, `image_upload_url`, `image_max_bytes`, `starters` (`[("", "Blank"), ("booking_open", "Booking is open")]`) and `start` (the chosen key). New mailing with `?start=booking_open` prefills `name`, `subject`, kind Service, group Everyone and the parts (form initial values, so `form.name.value` etc. work as before).

### Rendering notes

- Heading parts are `h2` (Signika 22/28); dividers use the layout hairline; small print is the muted 13/20 paragraph; buttons are the layout's table button plus the "paste this link" line.
- Images are capped at 504 px wide (the layout's content width, inside the 552 px cap in this spec), with `width`/`height` attributes when known and the alt text; with a link they are wrapped in it. Plain text shows `[Image: alt text]` (and the link).
- The inbox preview line is the first paragraph part (never one with a link, greeting lines skipped); if there is no paragraph it falls back to headings and small print.
- A test email sent from a development machine shows pictures as broken in Gmail (it cannot fetch `localhost`); live uses the public address.

## Round 2 (2026-10-27): saved templates, test without Who, review fixes

### Saved templates (`MailingTemplate`)

- **Model:** name (unique, ignoring capitals), subject, kind, group (may be blank), parts (`blocks`, same rules as a mailing), `key` (set only for the built-in ones the seed makes), created_by, history. Code: `mailings/saved.py`.
- **Booking is open** is now a saved template made by `seed_phase1` (by key `booking_open`; never overwrites an edited one, and renaming keeps the key so seeding does not add a second copy). There is **no code fallback**: Start from lists what is in the database. If someone deletes it, it stays deleted until `seed_phase1` is run again (it is not a migration and is not run on every deploy). This lets Moishe really remove or edit it. The words stay in `blocks.STARTERS` as the seed's source.
- **Pictures** used by templates are never deleted (there is no image delete at all).
- **Page context** for the mailing form (changed): `starters` is `[("", "Blank"), (<template id>, <name>), ...]` from the database; `starter_details` is a list of `{id, key, name, subject, kind, group, parts, description}`; `start_cards` is `[(id, name, description)]` with Blank first (the description is built from the data, e.g. "Service message to Everyone registered: a heading, a paragraph, a button and small print."); `start` is the chosen template id (or ""); `template_save_url`. `?start=<template id or key>` prefills name, subject, kind, Who and the parts.
- **Save as template: `POST /emails/mailings/templates/save/`** with `name` and either `mailing` (a saved mailing's id) or `subject`, `kind`, `group`, `blocks` (JSON). A name that already exists (any capitals) is refused with `409 {"ok": false, "exists": true, "errors": {"name": [...]}}`; resend with `overwrite=1` to replace it (the typed name is kept). Other problems are `400 {"ok": false, "errors": {...}}` in the same shape as saving a mailing (`errors.blocks` per part). Success: `200 {"ok": true, "id", "name", "created"}`. The subject may be empty; the parts must be valid.
- **Templates page: `GET /emails/templates/`** (tab "Templates"). **Rename: `POST /emails/templates/<id>/rename/`** (`name`; 409 if taken). **Delete: `POST /emails/templates/<id>/delete/`** (the button uses the `data-confirm` pattern). All three answer JSON with `Accept: application/json`, else a toast and redirect. Saving, renaming and deleting are System audit events (`tpl_saved`, `tpl_renamed`, `tpl_deleted`).

### Send me a test without Who

- **`POST /emails/mailings/test/`** (new): `subject`, `blocks` (JSON; or `body` for the old form), optional `kind` (default `news`, which decides the footer: News gets a real unsubscribe link, Service the "why you get this" line) and optional `name`. Nothing is saved and no Who is needed. It sends only to the signed-in person. `200 {"ok": true, "message"}`, or `400 {"ok": false, "message", "errors": {...}}` when the subject or a part is not valid (the UI can enable the button with just a subject and at least one valid part). Rate limit 5 per 10 minutes, shared with the saved-draft test.
- `POST /emails/mailings/<id>/test/` (a saved draft) now checks the subject and parts even when the draft has no Who.

### Review fixes

- **Size:** `clean()` renders the parts once and refuses over 88 KB of HTML (`blocks.HTML_MAX`; the layout adds about 12 KB, so the email stays under Gmail's 102 KB clip, which would hide the unsubscribe link). Error under `errors.blocks["_"]`: "This email is too long for some inboxes ... Shorten it." Send and Schedule use the same check.
- **Part numbers:** errors are numbered by the part's original position, even when an earlier part has an unknown type.
- **Local links** (`localhost`, `127.0.0.1`, ...) are refused unless DEBUG is on.
- **Picture address:** pictures are now `/email-image/<id>.<ext>` (so Cloudflare, which caches by file extension, will cache them). The old `/email-image/<id>/` still works, and parts saved before the change keep using it. The view is rate limited per IP (600 a minute). The upload response `url` uses the new form.
- **Preview** is rate limited (120 a minute per person). The Caddyfile System block limits request bodies to 5 MB (Control keeps its own 600 MB block; Caddy 2 `request_body { max_size }` syntax, the same as Control's, not run here because Caddy is not installed on this machine).

## Sending gate follows the mail provider

`notifications/ses.py`: the Amazon SES production gate now applies only when `EMAIL_BACKEND` is `notifications.backends.SesBackend` (DEBUG no longer matters). Console, in-memory, file and dummy backends are mode `dev` (allowed, printed or kept). Any other backend (SMTP through Postmark) is mode `provider`: allowed, no Amazon numbers read or shown, and the banner says "Emails are sent for real through <EMAIL_HOST> (not Amazon SES)." (host only, never credentials). `ses_status()` has a new `provider` text (empty in other modes). The Overview panel is titled "Email provider" with no "Check now" button in this mode.
