# Feature: Gold Card application

Phase 1. Apps: `gold`, `journey`, `notifications`, `common`.

## What it is

The Gold Card is free and by application. It is for **property** people: owners and investors, developers, managers (block, estate, portfolio), people working at property or management firms, agents and brokers, property lawyers. Everyone can apply; property people are nudged to (see `journey.md`). Medical, general law etc. are not targeted.

Phase 1: the application **does not create an account** and there is **no approval flow on the site**. Barry decides outside the system for now. (Overrides LC-26 for Phase 1.)

## Entry points

- Journey result: Gold panel (High potential) or subtle line (Medium).
- Gold Card page in the menu.
- Direct link (for sharing by BML).

Answers already given in the journey are reused, never asked twice.

## Application questions (mostly taps, editable in Control)

**Personal**
- First and last name, email, mobile

**About you** (screen 1, 2026-10-23: "About you." / "A few taps, so we know you.")
- What do you do? Property · Finance · Business owner · Law · Medical · Tech · Creative · Other (the options are the journey's `industry` question; Other has an optional short text). Required, prefilled from the journey. Nobody should feel "this isn't for me": the next two questions appear only when he picks **Property**, and the server drops them for everyone else.

**Property profile** (only if Property: link and size; the rest is for everyone)
- Your link to property: Owner / investor · Developer · Manager · Work at a property or management firm · Agent / broker · Property lawyer · None of these
- Size: number of units or properties (ranges: 1–9, 10–49, 50–199, 200+) or portfolio value range
- Where: North London · Rest of London · Rest of UK · Abroad
- Company and role (short text, optional)
- Do you work with BML? Yes · Not yet · No
- Referred by (optional)

**Spa interest** (from the journey if done, otherwise a short version)
- When, how often, facilities, alone or with someone

**Anything else** (optional note)

Privacy notice link and marketing opt-in as in sign-up.

**Look** (2026-10-23, `docs/design/GOLD-APPLY-ROUND5.md`): espresso stage (card still, "Apply for the Gold Card", ledger About you / Your visits / You) beside a raised gold-deep panel. `gold-apply.js` sets `data-step` on the wrapper so the ledger follows the current screen; nothing else in the flow changed.

## Potential rating

Automatic **High / Medium / Low**, points-based, weights editable in Control.

| Signal | Default points |
|---|---|
| Owner/investor, developer, manager | High base |
| Works at property/management firm, agent | Medium base |
| Property lawyer | Medium base |
| None of these | Low |
| Size 50–199 / 200+ | + / ++ |
| North London | + |
| Works with BML | ++ |
| Referred by someone | + |

Thresholds for High/Medium/Low are settings. The rating and its reasons are stored with the application.

## Email to the approver (System > Emails)

To every Approver (team members picked in System > Approval, each at their account email or their chosen address since 2026-10-25), cc the CC list (`SiteSettings.gold_approver_cc`, edited in System > Emails; never hard-coded; no approvers = no approver email). The typed `gold_approver_emails` list is retired. Sent on submit.

**Subject:** Gold Card application: {Name} ({Potential} potential). The wording is a row in Notification templates (`gold_approver`, `gold_approver_repeat`, `gold_ack`), edited in the hidden admin for now. Dates in the email are 22/10/2026

**1. Personal details:** name, email, mobile, date applied, application reference.

**2. About him:** what he does, then link to property (only if given), company and role, size, where, BML relationship, referred by, **Potential: High/Medium/Low** with the reasons.

**3. What the site collected:** when he'd come, how often, facilities, company/guests, suggested tier, how he heard, journey timing (e.g. "completed in 3 min, visited twice before applying").

Buttons (2026-10-23): **Approve** and **View application** (secondary), both absolute links to the Office host (`OFFICE_URL`) holding only the application id: Approve opens `/gold/<id>/approve/confirm/`, View opens `/gold/<id>/`. Text version has plain links. Nothing changes on a GET: the confirm page needs Office sign-in (the person returns to it after sign-in) and the Owner, Manager or Approver role (Viewer gets 403), shows name, potential, a property line and the applied date, and one big "Approve and send invite" button that POSTs (CSRF) to the existing `gold_approve`. Already decided applications show their state instead of the button; `approve_and_invite` stays idempotent (row lock, second approval is SKIPPED). After the tap the person lands on the detail page with the success message. Office sign-ins last 30 days (set on the session at Office sign-in only; the public site keeps Django's 14 days).

Recipients (2026-10-25: approvers are team members set in System > Approval; the old typed `SiteSettings.gold_approver_emails` is retired, see `docs/features/gold-final-approval.md`). The CC and contact stay in System > Emails (2026-10-23, replacing the env vars): `gold_approver_cc`, `contact_email` (the site and Reply-To use `SiteSettings.contact_address`: the stored address, else the one inside `DEFAULT_FROM_EMAIL`). Only `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` and the mail transport stay in env. `manage.py import_email_settings_from_env --dry-run` copies old env values once (blank fields only). If the approver list is empty nothing is sent to the approver, a warning is logged once and the application shows "email not sent"; the applicant's thank-you still goes. Email template key `gold_barry` is now `gold_approver` (`gold_approver_repeat`); old rows keep working until `manage.py backfill_site_data` renames them (`--dry-run` first).

**Barry's Office account** (Moishe creates it; no password is ever in a command or file): `manage.py setup_roles`, then `manage.py create_office_user --email <barry's email> --role approver --first-name Barry` (prompts for the password twice). Or in the hidden admin: add a user with "Staff status" ticked and put him in the Approver group. Add his email under System > Emails (Gold approver emails).

Clean, branded, readable on a phone. Applicant receives a short, calm acknowledgement ("Thank you. We'll be in touch.").

## Data

| Model | Holds |
|---|---|
| `GoldApplication` | UUID, `reference` (GC-XXXXXX), personal details, `industry` + `industry_other`, `property_link` and `size_range` (empty unless the industry is Property), `location` (the "where"), company, role, `bml_relationship`, referred by, note, `spa_interest` (journey answers as readable text), linked journey session (and `user` if the same email registers), potential level + score + reasons, status (new / contacted / approved / declined, by hand in Control), internal notes, `email_sent_at` + `email_error`, `repeat_of`, marketing + privacy consent |
| `GoldChoice` | The answers offered on the form and in the journey: group (property_link, size, where, bml), stable value, label, order, active. Retire by unticking; old applications keep their value and label |
| `GoldSignalSource` | Which journey question feeds which Gold signal: signal, journey question key, optional answer value, the value it gives (e.g. `property_law` = `yes` gives `property_lawyer`), order, active |
| `GoldRule` | One row per weight: group (property_link, size, where, bml, referred, threshold), match value, points, `is_property`. Thresholds are rows with group `threshold` and value `high` / `medium` |

- Industry rules: `industry` is required. When it is not Property, `property_link` and `size_range` are ignored (dropped), never required. When it is Property, `property_link` is required. A lawyer (`law`) whose journey said "is it property law: yes" is still stored as `property_lawyer`. The rating is unchanged: a non-property applicant just gets no property points.
- Engine: `gold/rating.py` `rate_potential(signals)`, shared by the application and the journey result (the journey passes `property_link` and `size`).
- Defaults (seeded, editable): owner/investor, developer, manager 5; works at a firm, agent, property lawyer 3; size 10-49 +1, 50-199 +2, 200+ +3; North London +1; works with BML +3; referred +1. High needs 6, Medium 3. So a bare owner is Medium and an owner with a portfolio of 10+ is High (matches journey.md "property link with scale").
- Endpoints (public, CSRF + honeypot `website`; 10 *valid* applications per hour per IP (a form mistake does not use one up) plus a generous cap of 120 posts an hour of any kind): `GET /gold/options/` (choices, plus prefill from the journey cookie / signed-in user; `industry` `{question, options: [{value, label}], other_value, other_label}`; `property_when` `{question: "industry", any_of: ["property"]}` says when to show `property_link` and `size_range`; prefill has `industry`, `industry_other` and, only for Property, `property_link` / `size_range`), `POST /gold/apply/` (JSON or form post; 201 `{"reference"}` or 400 `{"errors"}`).
- Emails are queued (django-q2) as `gold.tasks.send_gold_emails(application_id)`: the approver (the System > Emails approver list + CC, subject `Gold Card application: Name (High potential)`, suffix ` - repeat application` for repeats), then the applicant's acknowledgement. The three sections come from `gold.services.application_sections()` so Control can show the same. Resend (approver only): `gold.services.resend_approver_email()`, also an action in the hidden admin.
- A second submit within 2 minutes with the same email returns the first application and sends nothing new.
- Stage switch `register_interest_open` also closes Gold applications.

## Edge cases

- Same email applies twice: second application linked to the first and flagged, Barry still emailed with "repeat application".
- Applicant later registers interest with the same email: linked automatically.
- Email sending fails: application is still saved; Control shows "email not sent" with a resend button.

## Acceptance checks

- Application saved with all answers and the journey link.
- Potential rating matches the weights; changing weights in Control changes new ratings.
- Email to Barry (mocked in tests) has the three sections in order, with cc.
- No account is created.

## Approval and invite (decided 2026-10-23, built 2026-10-23, ADM-05)

- Applying needs no account (Phase 1 override of LC-26 is kept).
- When Barry approves an application, the applicant is emailed an invite: a one-time, signed link that expires after 14 days (resend from Control/admin).
- The link opens account setup with name, email and mobile prefilled from the application; the applicant only sets a password (email counts as verified because the link went to it).
- The new account is linked to the application, Gold is active at once, there is no payment step, and the Gold month starts on the approval date (LC-27).
- Declined applicants get no account. A Gold applicant who already has an account just gets Gold added on approval (no invite needed).

### Built (2026-10-23)

- **Admin actions** on Gold applications (Django admin, staff with the Gold application change permission): "Approve and invite" and "Resend invite (the old link stops working)". Declined and already approved applications are skipped with a message. Approving sets `status = approved`, `approved_at` (the Gold month starts here, LC-27) and `approved_by`.
- **Invite**: model `GoldInvite` (application, `expires_at` 14 days, `sent_at`, `used_at`, `revoked_at`). The link is `/gold/invite/<token>/`; the token is the signed invite id, and the row decides if it still works (expired, used or replaced by a resend all look the same: one friendly "This link can't be used" page, 410). The email task takes only the invite id and builds the link when sending, so no token is stored in the queue. Invite status (sent, expires, used) shows read-only under the application in the admin and in its own read-only list.
- **Setup page**: name and email come from the application and are read-only. He sets a password, gives his date of birth (18+, the same field and validator as registration), and accepts the men-only policy and privacy notice (marketing optional). His mobile is shown read-only; if it is not a valid UK mobile or is already on another account, the field becomes editable with the usual message. Opening the link uses nothing up (the page is never cached). POST creates the user (email marked verified), links the application, the journey session and other applications with that email, activates Gold, signs him in and goes to the account page with a welcome message. Rate limited (20 a hour per IP), CSRF protected. Erasing a person also erases the invites and the queued invite emails; the export lists approval and invite dates.
- **Gold on the account**: his `InterestRegistration.plan` becomes the `gold` plan (the only place a member's plan lives in Phase 1; memberships arrive in Phase 2). The account page says "Your Gold Card is active since <approval date>" and hides the interest picker, and the interest endpoint will not replace Gold.
- **Existing account**: no invite; Gold is added, the application is linked, and the short "Your Gold Card is active" email is queued.
- **Emails**: Notification rows `gold_invite` (button "Set up your account") and `gold_active`, subjects editable. Created by `seed_phase1` and `backfill_site_data` (create-if-missing).
- Not built: a Control screen for approvals (admin only for now), declining from an action (set the status by hand), expiring Gold after a month (Phase 2 memberships).

## Built (2026-10-25): approvers from the team and final approval

Approvers are team members (System > Approval), not typed addresses. A Low potential approval first goes to a final approver (`awaiting_final`), who confirms (the normal approval and invite run) or sends it back with a note (every approver is emailed; the next approval goes straight through). Statuses, fields, emails, links, endpoints and context shapes are in `docs/features/gold-final-approval.md`, "Built (2026-10-25)".
