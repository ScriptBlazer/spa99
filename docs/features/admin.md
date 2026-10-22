# Feature: Spa 99 Control (custom admin) and statistics

Phase 1. Apps: `control`, `insights`, plus each app's `services.py`.

## What it is

A custom back office in the Spa 99 look. Not the regular Django admin (that stays hidden as a superuser fallback). Everything that might change lives here, so rules and prices never need a developer.

Mobile-usable, fast, calm. Same shared buttons, modal, messages and validation as the site (`common`).

## Sections (Phase 1)

| Section | What you can do |
|---|---|
| **Dashboard** | Today's key numbers and the statistics below |
| **People** | Registrations: search, filter, open a person (details, interest tier, journey answers, history). Export CSV. GDPR export and delete |
| **Gold** | Applications list with potential, status, notes; open one to see the same three sections Barry gets; change status; resend email |
| **Journey** | Questions and options: add, edit, reorder, hide. Plan points and Gold points per option. Suggestion rules and tie-break. Preview the journey |
| **Plans** | Tiers and single visit: name, price ex VAT, visits, hours (daytime/any), booking window, upcoming limit, cancel hours, guests, perks, shown on site yes/no, order. VAT rate setting |
| **Hours** | Daytime/evening times, daily closure, Shabbos/Yom Tov rule offsets, one-off closures, capacity. (Used by the site now, by bookings later) |
| **Content** | Site copy and images per page/section; facilities and their descriptions; "Register interest" vs "Join" wording; booking placeholder text |
| **Gold rules** | Potential weights and thresholds; which answers count as property |
| **Notifications** | Gold alert recipients; email templates preview; send log |
| **Settings** | Opening date (when set), stage switches (register interest / subscribe / book), contact details |
| **Team** | Users who can access Control and their role |

Every change is recorded (who, when, before and after) via `django-simple-history` and shown on the item (ADM-11).

## Roles (Phase 1, to approve)

| Role | Can |
|---|---|
| Owner | Everything |
| Manager | Everything except Team and Gold status |
| Viewer | Read-only: dashboard, people, Gold |

Roles are Django Groups. Checks on every view. `python manage.py setup_roles [--dry-run]` creates or refreshes `Owner`, `Manager`, `Viewer` (idempotent). Proposed permissions, to approve: Owner has every permission on the project apps plus groups; Manager has everything on the project apps except groups/permissions, with People (`users.User`) and Gold applications view-only at model level (Control does the field-level edits, since Django cannot split "Team" from "People" on the same model); Viewer has `view_` on people, interest, Gold applications, journey sessions and answers. Every model is also registered in the hidden Django admin (superuser fallback).

## Data as built (Phase 1 backend)

| App | Models |
|---|---|
| `plans` | `Plan` (slug, kind monthly / free_by_application / one_off, price ex VAT, visits per month (empty = unlimited), hours daytime / any, booking window days, upcoming limit, cancel hours, guests per month, no-show result, `perks` list of key / label / value, short description, highlight, order, visible), `SiteSettings` (singleton: VAT rate, capacity 25, slot length 120, slot step 30, booking notice 10, opening date, stage switches, wording, contact email, Gold alert to / cc, privacy version), `OpeningRule` (periods daytime 5:00-18:00 and evening 18:00-3:00, daily closure 3:00-5:00, Shabbos / Yom Tov offsets 120 before and 60 after; Hebcal times arrive in Phase 3), `Closure` (one-offs), `Facility` (image goes to default storage, S3 on live) |
| `content` | `Page`, `Section` (key, heading, body, image, CTA, order, visible) |
| `journey`, `gold`, `users` | see their feature docs |
| `notifications` | `EmailLog` (to, cc, subject, template, status, error, sent at) |

All of them have history except `EmailLog` and `LoginEvent`, and are registered in the hidden Django admin.

## Statistics (Insights)

Filters: date range, source, completed vs not.

| Card | Shows |
|---|---|
| Funnel | Visitors → started journey → each screen → result → registered / applied for Gold. Drop-off per screen |
| Demand by time | How many want early morning / daytime / evening / late night, weighted by frequency → expected visits per period per week |
| Facilities | % interested in each facility (e.g. how many want the gym at all) |
| Tier mix | Suggested vs chosen tiers; projected monthly revenue using current prices |
| Company | Alone / sometimes / often with someone (guest demand) |
| Industries | Breakdown; property share; Gold potential spread |
| Sources | Heard via, referrer, UTM |
| Trend | Registrations and Gold applications per day/week |

All figures are live queries on saved answers (no third-party analytics). Built in `insights/services.py` (one function per card, bots excluded) and served as JSON by `GET /insights/summary/?from=YYYY-MM-DD&to=YYYY-MM-DD&source=&completed=yes|no` on the Control host (Owner, Manager, Viewer or superuser; anonymous is sent to login, others get 403). Frequency weights for "expected visits per week" are `Option.weight` on the frequency options. Charts in the brand palette, readable in light backgrounds, accessible.

## Later sections (planned, not built)

Memberships, payments, bookings and capacity, guests and waitlist, access (entries, bands, lockers, alerts, closing check), venue control (lights, music, signage, doors).

## Acceptance checks

- Changing a plan price in Control updates the site immediately and is recorded in history.
- Adding a journey option shows it on the next visit; hiding one keeps old answers.
- Statistics match the raw data.
- A Viewer cannot change anything (403 on every write).
- Works at 375px and 1440px.
