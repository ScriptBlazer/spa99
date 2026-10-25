# Feature: Gold approvers from the team, and final approval

Decided 2026-10-25 (PROJECT.md). Built 2026-10-25 on branch `feature/approval` (backend and minimal templates; the System Approval page is styled by the frontend after).

## Approvers from the team

- **Team shows it, Approval sets it.** System > Team no longer has an Approver toggle: it only shows a read-only label per person (Approver, Final approver). Adding or removing approvers and final approvers happens only in System > Approval (logged as role changes). Team > Add no longer asks Approver yes/no.

- The approver list is the team members with the **Approver** tick (rule book U2: Office level or higher). No typed approver emails any more.
- New System section **Approval**, a full section of its own (Developer level, behind the unlock). Emails keeps only email settings (CC, contact address, templates). Approvers are picked here with a multi-select of team members (searchable dropdown, chips for the chosen ones; not every name listed on the page). Choosing one sets their Approver tick; removing clears it (both logged, same as Team).
- Per approver: **Send to their account email** (ticked by default). Untick → a box for another address (validated, logged).
- `gold_approver_emails` is retired; a one-off script with `--dry-run` maps existing addresses to accounts where they match (never a migration). Gold approver CC and contact email stay in Emails.

## Final approval

- New Team tick **Final approver**, only for Admin level and above (Admin, Developer, Superuser), never Office. Shown on the Approval section like approvers, with the same email choice.
- Trigger: an approver approves an application whose potential is **Low**. The application becomes **Awaiting final approval**; the applicant is not told and no invite is sent.
- Final approvers get an email (and see it in the Office Gold list) with two actions: **Confirm approval** (then the normal approval runs: invite/active email) or **Send back for review** (automatic reason "Low potential, are you sure?" plus an optional note). No decline.
- Sent back: the application returns to the approvers' waiting queue and **every approver gets an email again**: "{name} was approved, but the potential is Low. Are you sure?" plus the final approver's note. An approver can decline, or approve again; **a second approval goes through immediately** (no second final approval).
- Every step is in the audit log (who, when, note). If no final approver exists, Low approvals go through as today and the Office shows a warning to set one.

## Built (2026-10-25)

**Roles.** `common.levels`: `FINAL_APPROVER_GROUP = "Final approver"`, `can_hold_approver`, `can_hold_final_approver` (Admin and above), `is_final_approver` (group on top of Admin+, or a superuser; a superuser may act but is only emailed when they hold the group), `held_roles(user) -> (approver, final)`. `setup_roles` creates the group. Recipients (`gold.approval.approvers()` / `final_approvers()`) are active people holding the group whose level still allows it.

**Delivery.** `gold.ApproverDelivery` (user one-to-one, `use_account_email` default True, `other_email`). Lives in `gold` because the Gold emails read it; no history table (the address is personal data; the change is in the System audit log); erased with the account and exported in the person's data. No row = account email. One setting covers both roles. Removing someone's last approval role deletes the row.

**Retired.** `SiteSettings.gold_approver_emails` is no longer used for sending (column kept, help text says deprecated; removed from the Emails form, template and code view). `SiteSettings.approver_list` is gone. Gold approver CC and contact email stay in Emails. `manage.py import_approvers_from_emails [--dry-run]` maps the old addresses to accounts (exact, case-insensitive) and gives the Approver group where the level allows; it lists addresses with no account or no team level; safe to run twice; never a migration.

**Statuses and fields (`GoldApplication`).** New status `awaiting_final` ("Awaiting final approval"; `status` widened to 20 characters). New fields `final_requested_at`, `final_requested_by`, `sent_back_at`, `sent_back_by`, `sent_back_note` (max 1000, optional). `final_review_done` is derived: `sent_back_at is not None`. Every step is a history row (who, when, the note), shown in the Office history ("Sent for final approval by X", "Sent back by X").

**Flow (`gold.approval`).** `approve()`: potential Low, not yet sent back and at least one final approver exists -> `awaiting_final` (not approved, no invite or active email; Office says "Sent for final approval."); otherwise the normal approval. `final_confirm()` runs the normal approval (`invites.approve_and_invite(..., from_final=True)`; the plain approval refuses an `awaiting_final` application). `send_back()` -> the status it had before the approval (`final_previous_status`, new/contacted), fields set, `gold_sent_back` emailed to every approver; the next approval goes straight through; decline stays possible. Final approvers cannot decline, and nobody declines while it awaits final approval. No final approver: Low is approved as before and the Office views get `final_approver_missing`. The Django admin "Approve and invite" goes through the same `approve()` (a new Low application goes to final approval; an `awaiting_final` one is skipped).

**Emails** (`DEFAULT_SUBJECTS`, html + txt): `gold_final` ("Final approval: {name} (Low potential)"; buttons Confirm approval and Send back, absolute links on the Office host, CC list copied) and `gold_sent_back` ("{name} was approved, but the potential is Low. Are you sure?"; note, Approve, Decline, View). Both honour the suppression guard. Tasks: `gold.tasks.send_gold_final_email`, `send_gold_sent_back_email` (ids only; the signed link is made when the email is built).

**One-tap links.** `{OFFICE_URL}/gold/<id>/final/<token>/?do=confirm|send_back`. The token is signed (salt `spa99.gold.final`, 14 days) and holds the application id and the moment it was sent for final approval, so it dies when the application leaves `awaiting_final`. GET shows a page with both forms (nothing happens on GET); the buttons POST to `/gold/<id>/final/confirm/` and `/gold/<id>/final/send-back/` (field `note`, optional `token`). Bad, forged, expired, used or another application's token: 410 and a neutral page. Signed out: the Office login, then back. Not a Final approver (or superuser): 403; no team level: 404. The Office detail page posts to the same two URLs without a token (still needs the role and `awaiting_final`).

**Office.** Gold list: status badge "Awaiting final approval" (the Waiting list includes them; `?status=awaiting_final` also works, no tab yet) and a "Sent back" tag (`row.sent_back`). Detail context (`lists.gold_detail`): `awaiting_final`, `can_final`, `final_requested_by`, `final_requested_at`, `sent_back` (`None` or `{at, by, note}`), `note_max`; view context `final_approver_missing`; `office_can.can_final`. Hooks: `data-awaiting-final`, `data-sent-back`, `data-sent-back-note`, `data-final-confirm`, `data-final-send-back`, `data-final-approver-missing`.

**System Approval** (Developer level, unlocked, CSRF; nav "Approval" after Gold rules). `GET /approval/` context: `approvers`, `final_approvers` (each `{user, id, name, email, level, level_label, use_account_email, other_email, address, can_change, active}`), `approver_candidates`, `final_candidates` (`{id, name, email, level, level_label}`: active team members who may hold the role, are not chosen yet and whom the actor may change), `cc` (list), `cc_text`, `final_approver_missing`. Posts (redirect back with a toast): `POST /approval/approvers/add/` and `/approval/final/add/` (repeat the field `user`, all or nothing), `POST /approval/approvers/<id>/remove/`, `POST /approval/final/<id>/remove/`, `POST /approval/delivery/<id>/` (`use_account_email=1` when ticked, `other_email`). Each change writes a change-list row (section `approval`) and a `role_changed` event with a sentence ("Made X an approver", "Removed X as final approver", "X's approval emails now go to y"). Eligibility and U4 rules are checked on the server (`system/approval.py`).

**Team.** The Approver toggle is gone from Team add and access (a posted `approver` is ignored). `team.rows()` gives each person `approver`, `final_approver` and `role_labels` (read only labels). Changing a level keeps the roles the new level can hold. Merging accounts moves no roles (as before: levels never move in a merge).

Tests: `gold/tests/test_final_approval.py`, `system/tests/test_approval.py`, plus the updated Team, Gold, System and insights tests. Nothing here is Postgres-only (row locks use `select_for_update` on single rows, as the existing approval does).

### Review fixes (2026-10-25)

- The last final approver cannot be removed while applications are `awaiting_final` (refused with the count). A newly added final approver is emailed every application already waiting (`send_gold_final_email(id, only_user_id)`, queued on commit).
- The Office "no final approver" warning also shows on an `awaiting_final` detail.
- "N waiting" (nav badge, Gold list, dashboard, summaries, dashboard rows) counts `new`, `contacted` and `awaiting_final`, matching the Waiting list; still read from the stored counters.
- `add()` refuses the whole request when a picked id no longer exists, and returns False (toast "Nobody new to add.") when nobody was new. Team `set_access` drops an unused `ApproverDelivery` row. New field `final_previous_status` (migration `gold.0007`, schema only).
