# Feature: Register interest (accounts)

Phase 1. Apps: `users`, `journey`, `notifications`, `common`.

## What it is

A real account, created now, without payment (LC-09, ACC-03). Called "Register interest" in Phase 1. When payments open (Stripe, Phase 2), the same flow becomes "Join" by changing wording in Control and switching on the payment step. No rebuild.

## Flow

1. Visitor picks a tier (from the journey result or the memberships page) → sign-up opens with that tier selected. Can also come straight to sign-up with no journey.
2. Fields (one calm screen, grouped):
   - First name, last name
   - Email
   - Mobile (UK format by default, not SMS-verified in Phase 1)
   - Password (with show/hide)
   - Date of birth (must be 18+, ACC-08)
   - Men-only policy acceptance tick (ACC-09)
   - Privacy notice link; marketing opt-in (unticked, separate)
   - Interested tier (pre-selected, changeable)
3. Submit → account created, journey session linked, "Check your email" screen.
4. Verification email → link → verified → signed in → account page.
5. Unverified accounts can sign in but see a banner to verify; resend link available.

## Live feedback (as he types)

Shown right under the field, calm wording, no red shouting until he leaves the field:

| Field | Checks |
|---|---|
| Name | Required, sensible length |
| Email | Format; "already registered" check (debounced server call, returns only yes/no, rate limited) with a sign-in link |
| Mobile | UK format, normalised to E.164 |
| Password | Live checklist: length (min 10), not too common, not the email/name; strength meter |
| Date of birth | Valid date, 18 or over |

- Rules are defined once in `common/validators.py` and mirrored in one reusable JS module (`common/static/common/js/validate.js`). Server always re-checks.
- Submit button: instant "working" state, disabled until done, no double submits (server is idempotent too).
- Errors keep everything typed.

## Account page (Phase 1)

- "You're registered for Tier 2 interest" with the option to change interest.
- Profile: name, email, mobile, change password.
- Account ID (shareable, for future guest invites, ACC-05).
- Placeholders that look finished: Visits, Bookings, Membership — "Opening January 2027".
- Privacy: download my data, delete my account (confirm modal).

## Data

| Model | Holds |
|---|---|
| `users.User` (custom) | UUID, email (unique, login), first/last name, mobile (unique when set), DOB, email verified at, marketing consent + timestamp, privacy accepted version + timestamp, public account ID, status (interest / member later) |
| `users.InterestRegistration` | User, plan of interest, source (journey/direct), linked journey session, created at |

- One account per email; mobile unique when present (ACC-10).
- Later phases attach `Membership`, `PaymentMethod`, face identity and bookings to the same `User` without changing it.

## Emails

| Email | When |
|---|---|
| Verify your email | On sign-up; resend on request |
| Welcome | After verification (confirmed; wording to agree) |
| Password reset | On request |

From Spa 99, Reply-To `hello@spa99.uk`. Branded, plain and short. No email to Moishe or Barry for ordinary sign-ups.

## Security

- Django password hashing; login rate limited; failed logins logged.
- Verification and reset links signed, single use, expire (24h verify, 1h reset).
- Email-exists check gives no extra detail and is rate limited.

## Acceptance checks

- Live feedback appears while typing and matches server validation exactly.
- Duplicate email is caught before submit.
- Account created, linked to the journey session, verification email sent (mocked in tests).
- Export gives all of a person's data (account, interest, journey answers). Delete removes or anonymises it.
- Switching "Register interest" to "Join" is a setting/wording change in Control.
