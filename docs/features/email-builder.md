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
