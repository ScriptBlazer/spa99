# Feature: Register (accounts)

Phase 1. Apps: `users`, `journey`, `notifications`, `common`.

## What it is

A real account, created now, without payment (LC-09, ACC-03). Called "Register" in Phase 1 (the button, heading and page title say "Register"; "Register for Tier 2" on a chosen plan). When payments open (Stripe, Phase 2), the same flow becomes "Join" by changing wording in Control and switching on the payment step. No rebuild.

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

- Rules are defined once in `common/validators.py` and mirrored in one reusable JS module (`common/static/common/js/validate.js`). Server always re-checks. The JS has no wording or limits of its own: `{% validation_config %}` (a `json_script` from `common.validators.client_config`) hands it the Python messages (password wording is read from the live password validators), the minimum age and the lengths. The mobile number is also checked by the server (`GET /validate/mobile/`, debounced) so the page can never accept a number the server refuses; `?plan=` in the sign-up link is used only for a plan people can register interest in (`Plan.interest_allowed`, plan cards carry `interest_allowed`).
- Submit button: instant "working" state, disabled until done, no double submits (server is idempotent too).
- Errors keep everything typed.

## Account page (Phase 1, superseded: now the member dashboard, see `member-dashboard.md`)

- "You're registered for Tier 2 interest" with the option to change interest.
- Profile: name, email, mobile, change password.
- Account ID (shareable, for future guest invites, ACC-05).
- Placeholders that look finished: Visits, Bookings, Membership — "Opening January 2027".
- Privacy: download my data, delete my account (confirm modal).

## Data

| Model | Holds |
|---|---|
| `users.User` (custom) | UUID, email (unique, login), first/last name, mobile (E.164, unique when set), DOB, `email_verified_at`, marketing consent + timestamp, privacy accepted version + timestamp, `men_only_accepted_at`, public account ID. No status field |
| `users.InterestRegistration` | One per person (`user.interest`): plan of interest, source (journey / direct), linked journey session, created at. Changing interest updates it; history keeps the old plan |

- One account per email; mobile unique when present (ACC-10).
- Later phases attach `Membership`, `PaymentMethod`, face identity and bookings to the same `User` without changing it.
- Services (`users/services.py`): `register_interest`, `email_is_registered`, `verify_email`, `resend_verification`, `request_password_reset`, `reset_password`, `set_interest`, `export_user_data`, `delete_user_data`. The form is `users.forms.SignUpForm` (rules from `common/validators.py`; `data-validate="required name|email|mobile|password|dob"` switch on the JS mirror).
- A second click within 2 minutes (same email and password, still unverified) returns the same account and sends nothing new.
- Stage switch `register_interest_open` (Site settings) closes sign-up; the wording ("Register" / "Join") is `site_settings.wording`.
- Gold applications made earlier with the same email are linked to the new account.
- GDPR delete removes the account, interest (and its history), Gold applications, the email-log rows for the address (those sent to the person and, through `EmailLog.subject_email`, those about them sent to someone else, such as Barry's Gold email), the django-q task records of their email jobs (done, failed and waiting; the email tasks return a plain status, never the log row) and login events. Journey sessions are kept for the statistics but anonymised (unlinked, cookie value replaced, referrer and typed text cleared, also in history).

## Routes (public site; templates are unstyled placeholders for the frontend to replace)

| Route | Purpose |
|---|---|
| `GET/POST /register/` | Sign-up form (`?plan=tier-2` preselects; falls back to the journey's suggestion). Honeypot field `website` |
| `GET /register/sent/` | "Check your email" |
| `GET /register/check-email/?email=` | `{"registered": true/false}` only, rate limited |
| `GET /verify/<token>/` | Verify (24h, single use) and sign in; a replay says "already confirmed" and signs nobody in |
| `POST /verify/resend/` | New link (signed-in user or the address just registered); same answer for everyone, rate limited |
| `GET/POST /forgot-password/`, `/reset/<uid>/<token>/` | Password reset (1h, single use) |
| `/login/`, `/logout/` | Public sign-in (10 attempts / 5 min / IP), also on Control |
| `GET /account/`, `POST /account/interest/`, `GET /account/export/`, `POST /account/delete/` | Account page, change interest, download my data, delete my account (asks for the password) |
| `GET/POST /account/you/password/` (the old `/account/password/` redirects) | Change password (current password, then the sign-up rules; 10 tries an hour per IP; stays signed in) |
| `GET /validate/mobile/?mobile=` | `{"valid": true}` or `{"valid": false, "message"}`; the same `phonenumbers` check as sign-up, rate limited (30 a minute). The page calls it debounced |
| `GET/POST /verify/<token>/` | GET shows a "Confirm my email" button and changes nothing (mail scanners cannot use the link); POST confirms and signs in |

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
- Switching "Register" to "Join" is a setting/wording change in Control.
