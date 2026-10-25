# Feature: System Emails (full section)

Decided 2026-10-25 (PROJECT.md). Not built yet. Own branch after `feature/system-code-view` (and after Approval, which takes the approver settings out of Emails).

## 1. Automatic emails
- List of every automatic email (verify, welcome, password reset, team invite, Gold ack/approver/invite/active, later booking emails): when it is sent, subject, last edited.
- Edit subject and wording in plain text with placeholders ({first_name}, {plan_name}, {opening}...), checked before saving (unknown placeholder = error). Live preview in the real email layout, desktop and phone width. **Send me a test** to the signed-in developer.
- Logged with undo like every System change. Contact address and Gold approver CC stay here.

## 2. Send to a group
- Groups built from data: everyone registered, by tier, Gold members, opted in to news, email not confirmed yet, registered in a date range, Gold applicants by status. Shows the count before sending.
- Marketing emails go only to people opted in (`marketing_opt_in`), always with a one-click unsubscribe link (and List-Unsubscribe header). Service messages (e.g. "booking opens") may go to all members, chosen explicitly per send.
- Write, preview, send a test, schedule or send now. Sent in batches by the background worker within the SES rate. Suppressed addresses are skipped.
- **Only when SES production access is approved** (read from AWS `GetAccount.ProductionAccessEnabled`, cached; System > Emails shows the state). Until then Send is disabled with a clear message.

## 3. Invites
- Paste or upload a list (CSV) of names and addresses; duplicates and existing members are flagged and skipped.
- Sends a "Register for Spa 99" invite with a personal link; tracks sent, opened link, registered.
- Same SES production rule as group sends.

## Notes
- Everything logged (who sent what to how many).
- Before the first bulk send, tell AWS (support case) that opted-in announcements are added, with unsubscribe and suppression handling, so the account stays in good standing.
