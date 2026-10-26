# Feature: Gold actions (Approve, Decline, Respond) and the audit trail

Decided 2026-10-26 (PROJECT.md, last row). Branch `feature/sales` (built alongside). Builds on `gold-application.md` and `gold-final-approval.md`; rules from `user-rules.md` U3 are unchanged.

## What Moishe asked

Every Gold application has three actions, in the Office and from the approver email: **Approve**, **Decline**, **Respond**. Every action is in a strong audit trail, shown on the application in the Office.

## Decisions (made in the build, change them if you disagree)

- **Who may act.** Only people with the Approver permission (or a superuser), as before. Office level without Approver sees the trail read only (no buttons; a direct POST answers 403). Final approvers (without Approver) still only Confirm or Send back; they cannot decline, respond or add notes.
- **Decline needs an internal reason** (at least 10 characters, at most 1000), shown in the trail. The applicant is **not** emailed unless the approver ticks **Email the applicant** (default OFF: whether declines get an email is still Moishe's decision). When ticked, the message box (prefilled from the editable template `gold_declined`, editable per decline, at most 2000 characters) is what is sent, and the send is logged.
- **Respond** sends the applicant a message (a question, say) by email using the editable template `gold_respond` (`{first_name}`, `{message}`). Reply-To is the site contact address (every Spa 99 email already has it), so replies reach the team. The status becomes **Contacted** (existing status) and the application stays open: it can still be approved or declined. Allowed while New, Contacted or Awaiting final approval (the last keeps its status). The full message is in the trail.
- **Add note** is internal only ("He replied by phone: ..."), logged as `note_added`, allowed in any status. This is how replies are recorded.
- **Email links.** The approver email now has **Approve**, **Decline** and **Respond** (plus View application). Approve stays the existing page (GET shows it, the tap POSTs; logged with channel `email_link`). **Decline and Respond cannot be one tap** (a decline needs a reason, a response needs a message): both open the application page in the Office with the form already open (`/gold/<id>/?do=decline` and `?do=respond`; Office sign-in first, then the role). There are no reason-less declines. The Office decline form was chosen over a one-tap decline with an automatic "Declined from email" reason because the audit trail is stronger. The "sent back" email gets Respond too. Final approver email: Confirm / Send back as before (logged with channel `email_link`).
- **Double submits.** State changes are idempotent by state (a second Approve or Decline finds the status already changed and writes nothing). Respond and Add note ignore an identical message from the same person on the same application within 60 seconds (one event, one email).
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

- `GET /gold/<id>/?do=decline|respond|note`: the detail page with that form open (anyone with a level can open the page; the forms only render for approvers).
- `POST /gold/<id>/decline/` (`reason`, optional `email_applicant=1`, `email_message`), `POST /gold/<id>/respond/` (`message`), `POST /gold/<id>/note/` (`note`). Validation errors answer 400 with the detail page re-rendered, the form open and its text kept; the errors are shown by the shared form-problems modal. Success redirects to the detail page with a toast.
- Existing: `approve/` (optional `channel=email_link` from the email's confirm page), `resend/`, `final/...` unchanged.

## Office page

Buttons Approve, Decline, Respond, Add note in the Decision card (only for approvers; the phone bar keeps its buttons). Decline, Respond and Add note open a dialog (the shared modal look). A **History** timeline (newest first) lists every event: when (London), who, what, the status change, the message (escaped, line breaks kept). Applications from before the trail existed fall back to the old status history list.

## Emails

Two new editable emails (System > Emails > Automatic emails): `gold_respond` and `gold_declined` (see `system-emails.md`).

## Tests

`gold/tests/test_actions.py`: every action writes the right event (actor, channel, statuses, message), decline needs a reason, respond sends with Reply-To and sets Contacted, events cannot be updated or deleted, erasure removes events, double submit makes one event. `office/tests`: a view-only Office user sees the trail and gets 403 on the actions; the email Respond and Decline links open the Office form.
