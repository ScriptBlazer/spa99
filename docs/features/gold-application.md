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

## Email to Barry

To `barry@bmlgroup.co.uk`, cc `moishe.berkowitz@bmlgroup.co.uk` (recipients editable in Control). Sent on submit.

**Subject:** Gold Card application: {Name} ({Potential} potential). The wording is a row in Notification templates (`gold_barry`, `gold_barry_repeat`, `gold_ack`), editable in Control. Dates in the email are 22/10/2026

**1. Personal details:** name, email, mobile, date applied, application reference.

**2. About him:** what he does, then link to property (only if given), company and role, size, where, BML relationship, referred by, **Potential: High/Medium/Low** with the reasons.

**3. What the site collected:** when he'd come, how often, facilities, company/guests, suggested tier, how he heard, journey timing (e.g. "completed in 3 min, visited twice before applying").

Button: **Open in Control**, NOT in the email yet. Control has no Gold page, so a link would 404 (review 2026-10-22). TODO: when Control gets `/gold/<id>/`, add `control_url` back to `gold.services.barry_email_context()` and the button to `gold_barry.html` / `.txt`. Until then Barry finds the application by its reference.

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
- Emails are queued (django-q2) as `gold.tasks.send_gold_emails(application_id)`: Barry (to + cc from Site settings, subject `Gold Card application: Name (High potential)`, suffix ` - repeat application` for repeats), then the applicant's acknowledgement. The three sections come from `gold.services.application_sections()` so Control can show the same. The email has no "Open in Control" link until Control has a Gold page (see the TODO above). Resend (Barry only): `gold.services.resend_barry_email()`, also an action in the hidden admin.
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
