# Feature: Gold approvers from the team, and final approval

Decided 2026-10-25 (PROJECT.md). Not built yet. Own branch after `feature/system-code-view`.

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
