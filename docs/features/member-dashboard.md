# Feature: Member dashboard (My Spa 99)

Branch `feature/member-dashboard`. Spec: `docs/design/MEMBER.md`. Decision: `PROJECT.md` 2026-10-23. Apps: `users` (views, `member.py` context), `pages` (`/book/`, sitemap), `plans` (one new SiteSettings flag).

## Routes (all signed in; staff too)

| Route | Name | Notes |
|---|---|---|
| `/account/` | `account` | Home |
| `/account/book/` | `account_book` | Book a visit |
| `/account/membership/` | `account_membership` | Membership |
| `/account/you/` | `account_you` | You |
| `/account/you/password/` | `password_change` | Change password (GET and POST); success goes to You |
| `/account/password/` | `password_change_old` | Old address, kept: 307 to the new one |
| `POST /account/emails/` | `account_emails` | Marketing consent: `marketing=1` on, anything else off. 20 a minute per person. Saves only on change, stamps `marketing_consent_at`, and the User history logs it. `Accept: application/json` gets `{"saved", "marketing"}`; otherwise a "Saved." message and a redirect to You |
| POST `/account/interest/` | `account_interest` | Saves the tier (`services.choose_tier`), message, redirects to Home (an invalid choice returns to Membership) |
| POST `/logout/` | `logout` | Sign out (GET is 405). Public site lands on Home with "You're signed out."; the staff hosts keep their own sign-in page |
| `/account/export/`, POST `/account/delete/` | | Unchanged; a wrong delete password returns to You |

**Who may open it** (rule book U1/U2): only a person holding a membership (an interest registration, which includes Gold) or a superuser (an empty membership is shown). Team members without a membership get a calm 200 page "No membership on this account" with a link to the website (not a 404); `users.views.member_area` guards every `/account/*` view, and the website menu shows "My Spa 99" only when `has_member_area` (context processor `users.context.member_area`), else "Sign in".

Sign in lands on `/account/` (`LOGIN_REDIRECT_URL`); a safe `next` wins. Verify and register already redirect to `account`.

## Context (users/member.py; every screen also gets the base set)

- Base: `greeting`, `site`, `opening` (SiteSettings.opening_label), `opening_date`, `verified`, `email`, `account_id`, `interest`, `interest_plan`, `is_gold`, `gold_since`, `status` (`gold` / `registered` / `none`), `status_name`.
- Home: base only.
- Book: `booking_lines` (their plan's line; Gold or no plan: every plan's), `hours` ([(label, text)]), `hours_summary`, `closure`, `stay_pills` (from `visit_pills()["stay"]`, same as The spa), `notify_booking_open`.
- Membership: `plan_tiles` (visible monthly plans, plan cards with `price_whole`, `price_inc`), `current_plan`, `vat_rate`, `suggested_plan` (latest finished linked journey, stored only), `suggestion_differs`.
- You: `full_name`, `mobile`, `marketing_consent`.

Templates are plain markup with stable hooks (`data-screen`, `data-tab`, `data-tile`, `data-status`, `data-verify-banner`, `data-reassurance`) on `users/member_base.html`; the frontend restyles them.

## Book a visit copy flag

`SiteSettings.notify_booking_open` (default off). Off: "Booking opens in {opening}." On: "You're on the list. We'll write to {email} when booking opens." Turn it on only once the "booking is open" email really is sent (Moishe has not confirmed). Unverified members see "Confirm your email so we can tell you when booking opens." either way.

## Website

Book is gone from the header (desktop and menu) and footer. Signed in shows "My Spa 99" (`/account/`), signed out "Sign in". `/book/`: signed in gets 302 to `/account/book/`; signed out keeps the teaser with "Already registered? Sign in" to `/login/?next=/account/book/`. `/book/` is out of the sitemap.

## Tests

`users/tests/test_member_dashboard.py` (screens, context, flag, login redirect, consent, menu, `/book/`, sitemap). Existing tests for the old single account page and password URL were moved to the new routes.

## Choosing a tier and signing out (2026-10-25)

- Every "choose this tier" link (compare/memberships page Continue, journey result, Gold page) goes to `/register/?plan=slug`. Signed out: the sign-up form with that plan picked. Signed in: a GET saves nothing; it shows a one-button confirm screen (`users/choose_confirm.html`) that POSTs to `account_interest`, which saves with `services.choose_tier(user, slug)` (saved / same / gold / invalid), shows a message and redirects to `/account/`. Already their tier or Gold: straight to `/account/` with a message. The member area's tier cards POST directly. Before, the GET redirected and dropped the plan (the loop). Gold members are never switched.
- Sign-up now requires a tier (form field `plan` required, "Choose a membership to continue.", also checked in `register.js`). Accounts made earlier without a tier still see "No membership chosen yet" and can choose.
- Sign out: POST form in the desktop rail ("Sign out", `data-member-signout`), at the end of You (phone and desktop), and in the public header and menu whenever someone is signed in (next to "My Spa 99" for members). The "no membership" page links to the memberships and has Sign out.
