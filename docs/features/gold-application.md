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

**Property profile**
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

**Subject:** Gold Card application: {Name} ({Potential} potential)

**1. Personal details:** name, email, mobile, date applied, application reference.

**2. Property profile:** link to property, company and role, size, where, BML relationship, referred by, **Potential: High/Medium/Low** with the reasons.

**3. What the site collected:** when he'd come, how often, facilities, company/guests, suggested tier, how he heard, journey timing (e.g. "completed in 3 min, visited twice before applying").

Button: **Open in Control**.

Clean, branded, readable on a phone. Applicant receives a short, calm acknowledgement ("Thank you. We'll be in touch.").

## Data

| Model | Holds |
|---|---|
| `GoldApplication` | UUID, `reference` (GC-XXXXXX), personal details, `property_link`, `size_range`, `location` (the "where"), company, role, `bml_relationship`, referred by, note, `spa_interest` (journey answers as readable text), linked journey session (and `user` if the same email registers), potential level + score + reasons, status (new / contacted / approved / declined, by hand in Control), internal notes, `email_sent_at` + `email_error`, `repeat_of`, marketing + privacy consent |
| `GoldRule` | One row per weight: group (property_link, size, where, bml, referred, threshold), match value, points, `is_property`. Thresholds are rows with group `threshold` and value `high` / `medium` |

- Engine: `gold/rating.py` `rate_potential(signals)`, shared by the application and the journey result (the journey passes `property_link` and `size`).
- Defaults (seeded, editable): owner/investor, developer, manager 5; works at a firm, agent, property lawyer 3; size 10-49 +1, 50-199 +2, 200+ +3; North London +1; works with BML +3; referred +1. High needs 6, Medium 3. So a bare owner is Medium and an owner with a portfolio of 10+ is High (matches journey.md "property link with scale").
- Endpoints (public, CSRF + rate limit 10 per hour per IP + honeypot `website`): `GET /gold/options/` (choices, plus prefill from the journey cookie / signed-in user), `POST /gold/apply/` (JSON or form post; 201 `{"reference"}` or 400 `{"errors"}`).
- Emails are queued (django-q2) as `gold.tasks.send_gold_emails(application_id)`: Barry (to + cc from Site settings, subject `Gold Card application: Name (High potential)`, suffix ` - repeat application` for repeats), then the applicant's acknowledgement. The three sections come from `gold.services.application_sections()` so Control can show the same. "Open in Control" links to `CONTROL_URL/gold/<id>/` (the Control page is built later). Resend (Barry only): `gold.services.resend_barry_email()`, also an action in the hidden admin.
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
