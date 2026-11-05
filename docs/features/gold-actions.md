# Feature: Gold actions (Approve, Decline, Respond) and the audit trail

Decided 2026-10-26 (PROJECT.md, last row). Branch `feature/sales` (built alongside). Builds on `gold-application.md` and `gold-final-approval.md`; rules from `user-rules.md` U3 are unchanged.

## What Moishe asked

Every Gold application has three actions, in the Office and from the approver email: **Approve**, **Decline**, **Respond**. Respond is no longer a form of its own: it goes to the **WhatsApp** or **Email** button (see "Respond" below). Every action is in a strong audit trail, shown on the application in the Office.

## Decisions (made in the build, change them if you disagree)

- **Who may act.** Only people with the Approver permission (or a superuser), as before. Office level without Approver sees the trail read only (no buttons; a direct POST answers 403). Final approvers (without Approver) still only Confirm or Send back; they cannot decline, respond or add notes.
- **Decline needs an internal reason** (at least 10 characters, at most 1000), shown in the trail. The applicant is **not** emailed unless the approver ticks **Email the applicant** (default OFF; confirmed by Moishe 2026-10-27). When ticked, the message box (prefilled from the editable template `gold_declined`, editable per decline, at most 2000 characters) is what is sent, and the send is logged.
- **Respond** (the approver email's link, and the old `/gold/<id>/respond/` URL) opens his WhatsApp chat when he has a mobile, otherwise his Gold page with the **Email** pop-up open: one text box, sent From the logged-in person with Reply-To their address (the old `gold_respond` template is unused). The first message sent by either route turns **New** into **Contacted** (a `responded` event, `meta` says `whatsapp` or `email`), once; the application stays open and can still be approved or declined. The text is in the trail and the timeline.
- **Send guide** (2026-11-03, replaces Add note on the Decision card): emails the applicant the Gold Card guide PDF (uploaded in System > Gold) from the site sender, template `gold_guide`, any status, logged as `guide_sent`. **Notes** are now sticky notes per person (`outreach.StickyNote`, see office-outreach.md); adding one is not a history line, deleting one logs `note_deleted` with the text. Old `note_added` events are copied by `backfill_sticky_notes` and hidden once copied.
- **Email links.** The approver email has **Approve**, **Decline** and **Respond** (plus View application). Approve stays the existing page (GET shows it, the tap POSTs; logged with channel `email_link`). **Decline cannot be one tap** (it needs a reason): it opens the application page with the form open (`/gold/<id>/?do=decline`; Office sign-in first, then the role). **Respond** (`?do=respond`) opens the chat or the Email pop-up as above. There are no reason-less declines. The "sent back" email gets Respond too. Final approver email: Confirm / Send back as before (logged with channel `email_link`).
- **Double submits.** State changes are idempotent by state (a second Approve or Decline finds the status already changed and writes nothing). Send guide and the Email pop-up ignore an identical request from the same person on the same application within 60 seconds (one event, one email; a failed send may be sent again).
- **Erasure (UK GDPR).** Events belong to the application: erasing the applicant deletes the application and, by cascade, all its events (reasons, messages and notes can hold personal text). No anonymous "erased" line is kept (the existing erasure path already reports counts to whoever ran it). The events are also part of the applicant's data export (what happened and the message text, not who on the team did it).

## Model: `gold.ApplicationEvent` (append-only)

| Field | Meaning |
|---|---|
| `application` | FK, CASCADE |
| `at` | when (UTC; shown in London time) |
| `actor` | FK to user, nullable, SET_NULL (null = the system or the applicant) |
| `actor_label` | name and email when it happened (kept if the account is deleted) |
| `action` | `submitted`, `approved`, `sent_for_final`, `final_confirmed`, `sent_back`, `declined`, `responded`, `note_added`, `invite_sent`, `invite_resent`, `email_sent`, `email_failed`, `status_changed_admin` |
| `channel` | `office`, `email_link`, `admin`, `system`, `shell` |
| `from_status`, `to_status` | status before and after (empty when it did not change) |
| `message` | the reason, message or note text |
| `meta` | JSON: `template`, `recipient`, `error`, `result` (invited or activated), `emailed` ... |

Never edited or deleted in the app: `save()` on an existing row raises, `delete()` and queryset `delete()`/`update()` raise (`AppendOnlyError`). Database cascade (an application erased) still works. Admin: read only inline on the application, no add, change or delete. One helper writes every row: `gold.audit.record(application, action, actor=None, channel=..., ...)`, inside the same transaction as the change it describes.

Recorded from every path: the application being saved (`submitted`), approve (Low goes to `sent_for_final`), final confirm, send back, decline, respond, notes, the admin "Approve and invite" and "Resend invite" actions, status changes made in the admin form (`status_changed_admin`, with who), invites sent and resent, and emails sent or failed (invite, respond, decline). Not recorded: views.

## Endpoints (Office host, POST, CSRF, Approver only unless noted)

- `GET /gold/<id>/?do=decline|note|email`: the detail page with that form open (anyone with a level can open the page; the forms only render for approvers). `?do=respond` redirects to his WhatsApp chat, or to `?do=email` when he has no mobile.
- `POST /gold/<id>/decline/` (`reason`, optional `email_applicant=1`, `email_message`), `POST /gold/<id>/note/` (`note`). The Email pop-up posts to the shared message endpoint (`message`), not to a Gold URL; `/gold/<id>/respond/` only redirects (any method). Validation errors answer 400 with the detail page re-rendered, the form open and its text kept; the errors are shown by the shared form-problems modal. Success redirects to the detail page with a toast.
- Existing: `approve/` (`token` from the email link marks it `email_link`), `resend/`, `final/...` unchanged.

## Office page

Buttons Approve, Decline, Send guide in the Decision card (only for approvers; the phone bar keeps its buttons), and the two reach out buttons, WhatsApp and Email, on the page. Decline and Send guide open a dialog; Email opens the one-box message dialog; notes are pinned sticky notes (the shared modal look). A **History** timeline (newest first) lists every event: when (London), who, what, the status change, the message (escaped, line breaks kept). Applications from before the trail existed fall back to the old status history list.

## Emails

Two new editable emails (System > Emails > Automatic emails): `gold_respond` and `gold_declined` (see `system-emails.md`).

## Tests

`gold/tests/test_actions.py`: every action writes the right event (actor, channel, statuses, message), decline needs a reason, the first WhatsApp or Email sets Contacted once, events cannot be updated or deleted, erasure removes events, double submit makes one event. `office/tests`: a view-only Office user sees the trail and gets 403 on the actions; the email Respond link opens the chat or the Email pop-up, and the Decline link opens the Office form.

## Hardening (review round, 2026-10-26)

- **Database trigger (migration `gold.0010`).** Any UPDATE of a `gold_applicationevent` row is refused by the database itself (so `_base_manager.update`, raw SQL and a shell cannot edit the trail). The single allowed update is Django's `ON DELETE SET NULL` of `actor_id` when a team member's account is deleted (nothing else changes; `actor_label` keeps who it was). **DELETE is still allowed**, because cascade and GDPR erasure need it, so a person with database access can still delete rows: the trigger stops edits, not deletes. Vendor-specific: SQLite (`CREATE TRIGGER ... RAISE(ABORT)`) and PostgreSQL (plpgsql function plus trigger) each have their own SQL; the PostgreSQL branch is not run by the local tests (SQLite only), CI's Postgres run exercises it.
- **Email-link channel.** The approver email's Approve link carries a signed per-application token (`?t=`, 14 days); the application page (`/gold/<id>/?t=`) keeps it in the Approve form and posts it back and only a valid token records channel `email_link`. A posted `channel` is ignored.
- **Admin status changes** are recorded whenever the stored status differs after saving, including a history Revert.
- A form error on an application someone else decided meanwhile redirects with "Already decided by someone else. Nothing was sent."
- Export includes the text emailed on a decline. Email sent or failed is logged for the approver, final, sent-back, invite, Gold-added, thank-you, respond and decline emails.


## Respond (2026-11-03, updated 2026-11-04)

Respond no longer has its own email form. With a mobile it opens the applicant's chat (`/gold/<id>/whatsapp/`); without one it opens the Email pop-up on his Gold page. The first message from either turns New into Contacted with a `responded` event (`meta {"whatsapp": true}` or `{"email": true}`). `/gold/<id>/respond/` and the approver email's `?do=respond` link redirect there. Send guide is unchanged. See `whatsapp.md`.
