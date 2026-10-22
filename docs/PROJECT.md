# Spa 99 — Project

Read this first, every session. Then the current feature doc, `SPA99_RULES.md` and `BRAND.md`.

## 1. What Spa 99 is

- Men-only luxury spa at 99 Vale Road, London N4 1PR. Part of BML Group. Brand line: "Beyond Luxury".
- Opening target: January 2027 (date not fixed).
- Owner contact: Moishe (moishe.berkowitz@bmlgroup.co.uk). Gold Card decisions: Barry (barry@bmlgroup.co.uk).
- Domain: `spa99.uk` (DNS on Cloudflare, registered at GoDaddy).

## 2. The end goal

One system that runs the whole spa, split into clean parts:

| Part | What it does | When |
|---|---|---|
| Customer website | Brand, amenities, memberships, guided journey, register interest, account | **Phase 1** |
| Insights | Statistics on demand, facilities, tiers, industries, drop-off | **Phase 1** |
| Spa 99 Control (custom admin) | Change plans, prices, hours, questions, content; see people and stats | **Phase 1** |
| Gold applications | Property-focused application, potential rating, email to Barry | **Phase 1** |
| Payments | Stripe. Saved card, first charge on opening day | Phase 2 (could come within days) |
| Memberships | Subscriptions, monthly anniversaries, tier changes, grace | Phase 2 |
| Bookings | Slots, capacity, guests, waitlist, single visits, credits | Phase 3 |
| Access | Face entry, vestibule, wristbands (RFID), lockers, 3am reset | Phase 4 |
| Venue control | Lights, music, doors, signage from admin | Later |
| Apps | iOS and Android on the same API | Later |

Phase 1 is built so every later part plugs in without rewrites (see section 5).

## 3. Phase 1 scope (now)

**In:**
- Stunning, visuals-led website: home, the spa (amenities), memberships, Gold Card, booking (placeholder), privacy, terms.
- Guided journey: a few comfortable screens of taps, sliders and short answers. Every answer saved as it happens, from the first tap, even if the visitor never finishes. Ends with a suggested tier and why. See `features/journey.md`.
- Register interest: a real account (full sign-up, password, login), email verification, simple account page. No payment details. See `features/register-interest.md`.
- Gold Card application: separate, property-focused, no account, no approval flow on the site. Emails Barry. See `features/gold-application.md`.
- Spa 99 Control: custom admin in the brand look (not Django admin). See `features/admin.md`.
- Statistics dashboard inside Control.

**Out (placeholders only, look finished, say "coming soon"):**
- Booking a slot, payments, membership checkout, visits left, guests, waitlist.

**Nothing hard-coded.** Tiers, prices, VAT, allowances, hours, closures, journey questions, suggestion logic, Gold rating weights, site copy and images are all data, changed in Control. Rules and prices will change often.

## 4. Stack

| Layer | Choice |
|---|---|
| Backend | Django (always) |
| Frontend | Django 5.2 LTS templates + HTMX + small vanilla JS modules, shared JS in `common/static` |
| Background jobs | Database-backed task queue + scheduler (no Redis) |
| Admin | Spa 99 Control on `control.spa99.uk` |
| Database | SQLite locally at `.private/db.sqlite3`. Managed PostgreSQL on live via `DATABASE_URL` |
| Live hosting | AWS instance, Docker + Caddy (HTTPS). Managed PostgreSQL |
| Media | S3 (`django-storages`), `dev/` and `prod/` folders. Falls back to local storage if S3 settings are missing |
| Static | WhiteNoise `CompressedManifestStaticFilesStorage` |
| Email | Amazon SES sends (provisional). Reply-To `hello@spa99.uk` (Microsoft 365 shared mailbox) |
| Payments | Stripe (Phase 2) |
| History | `django-simple-history` on every model |
| Errors | Sentry when `SENTRY_DSN` is set |
| Fonts | Signika (headlines), Figtree (body/UI). Google Fonts, self-hosted |

**Deviations from BML `RULES.md`** (Moishe's instruction for this project):
- Local dev uses SQLite, no Docker or Postgres on the Mac. CI tests against Postgres.
- Main doc is `docs/PROJECT.md` (BML calls it `OVERVIEW.md`).

## 5. How the code is split

One Django project, apps by area. Apps only talk to each other through their `services.py`. `common` imports from nobody.

| App | Owns | Phase |
|---|---|---|
| `common` | Base models (timestamps, UUIDs), validators, permission mixins, shared JS/CSS (validation, buttons, modal, messages), settings loader, audit helpers | 1 |
| `users` | Custom User, login, email verification, password reset, account page, GDPR export/delete | 1 |
| `plans` | Tiers, prices, VAT rate, perks, facilities, opening hours, closures — all as editable data | 1 |
| `journey` | Visitor sessions, questions, options, answers, suggestion rules, results | 1 |
| `gold` | Gold applications, property questions, potential rating, Barry email | 1 |
| `content` | Site pages, sections, copy, images | 1 |
| `notifications` | Email templates, sending, send log | 1 |
| `insights` | Read-only statistics queries for the dashboard | 1 |
| `control` | Spa 99 Control UI (views only, calls other apps' services) | 1 |
| `memberships` | Subscriptions, anniversaries, allowances, grace | 2 |
| `payments` | Stripe customers, payment methods, charges, webhooks | 2 |
| `bookings` | Slots, capacity, guests, waitlist, credits | 3 |
| `access` | Face identity, entry events, bands, lockers, closing | 4 |
| `venue` | Lights, audio, signage, door control (may become its own service) | Later |

**Shapes that must hold from day one:**
- Custom User (`users.User`), UUID public IDs, a shareable account ID (ACC-05).
- Person data separate from membership, booking, attendance, band and locker (see SPA99_RULES "Keep these apart").
- Plans are rows, not code. A tier is a `Plan` record with price, visits, hours, window, limits, cancel hours, guests and perks as fields.
- Prices: `DecimalField`, ex VAT, VAT rate stored as a setting. History kept on every change.
- All times stored UTC, shown Europe/London. Spa-day logic (5am to 3am) lives in one shared helper.

## 6. Build standards

- Settings split: `config/settings/base.py`, `dev.py`, `prod.py`.
- Short views; logic in `services.py`. Permissions on every view; public views marked with a comment.
- Manifest static storage. `/health/` endpoint. Migrations run on container start.
- No backfills in migrations: separate management command with `--dry-run`.
- Tests mocked, no real APIs. Test models, DB and logic, not buttons. Sensible number of tests.
- GitHub Actions runs tests against a Postgres service container.
- Code works on SQLite and Postgres. Flag anything Postgres-only.
- Git: branch per feature, PR into `main`, tags `1.2.3` (no "v"). Moishe handles repos, hosting and deploys.
- Instant feedback on every button and field; no double submits; one shared modal; friendly error pages.
- Guidance, not a bible: break one when it clearly helps, and say so in one line.

## 7. Private files and settings

How to run it locally: see `README.md` ("Local development" lives there: venv, runserver, worker, tests, backup/restore, env keys).

- Code: `"/Users/moishe/Documents/My Apps/spa99-software"`
- Private folder (`SPA99_PRIVATE_DIR`): `"/Users/moishe/Library/CloudStorage/OneDrive-Personal/BML/Spa 99/Software Files"`
  - `env/.env` (secrets), `db-backups/`, `media/`. Only important things. Always quote the path.
- Settings load order: real env vars → `SPA99_PRIVATE_DIR/env/.env` → project `.env` → dev defaults.
- Private folder missing → fall back to git-ignored `.private/`. Never crash locally or in CI.
- Working SQLite DB never in OneDrive. `scripts/backup_db.sh` copies to `db-backups/` dated, keeps last 30. `scripts/restore_db.sh` restores with a confirm prompt.
- Prod refuses to start without a real `SECRET_KEY` and `DATABASE_URL`.
- `.env.example` committed; secrets never committed.
- One startup log line: which env source and which database (no secrets).

## 8. Privacy (UK GDPR)

- Privacy notice linked from every form and the journey.
- Journey answers are saved before sign-up: disclosed in the privacy notice; tied to a first-party session cookie only.
- No third-party trackers in Phase 1. Consent banner only if a non-essential cookie is added.
- Marketing consent is a separate, unticked opt-in.
- People can export and delete their data (account page + Control).
- No face data in Phase 1 (ACC-02: face is taken at first booking). A DPIA is needed before Phase 4.
- Men-only policy: legal check before launch (spec section 10).

## 9. Email

- Mailbox: `hello@spa99.uk`, a shared mailbox in BML's Microsoft 365 (created 22 Oct 2026). Members open it in Outlook.
- DNS on Cloudflare: MX, SPF (`~all`), autodiscover, DMARC (quarantine) in place. DKIM records added; Microsoft toggle pending sync.
- Website sending: Amazon SES from a subdomain (SPF/DKIM records added when built), `From: Spa 99 <hello@spa99.uk>` or `noreply@`, `Reply-To: hello@spa99.uk`.
- No personal spa99.uk addresses. Internal alerts go to bmlgroup.co.uk addresses.

## 10. Open questions

| # | Question | Needed by |
|---|---|---|
| 2 | SES confirmed, or Microsoft 365 sending? | Before email build |
| 5 | Welcome email wording | Before email build |
| 6 | Legal: privacy notice, terms, men-only policy wording | Before launch |

## 11. Decisions log

Newest at the bottom. Every decision Moishe makes is logged here the same session, dated.

| Date | Decision |
|---|---|
| 2026-10-22 | Agent team set up: manager, designer, frontend, backend, reviewer. |
| 2026-10-22 | Opening target January 2027 (spec) wins over December (requirements record). |
| 2026-10-22 | Face photo is not taken at sign-up; it is taken at first booking (ACC-02). No biometrics in Phase 1. |
| 2026-10-22 | Rules and prices will change often. Nothing hard-coded: everything editable in a custom admin. |
| 2026-10-22 | Custom admin ("Spa 99 Control") in the brand look, not the regular Django admin. Django admin kept hidden as a superuser fallback. |
| 2026-10-22 | Phase 1 = stunning website + guided journey + register interest + Gold application + admin + statistics. Booking is a placeholder ("opening soon"). |
| 2026-10-22 | Journey is short and comfortable: grouped questions, mix of taps and short answers, not a chat, not one question per page. Every answer saved as it happens. |
| 2026-10-22 | Register interest creates a real account with full sign-up and password. Wording "Register interest" for now; later "Join" with payment. |
| 2026-10-22 | Live field feedback while typing (password rules, email format, duplicate email). Shared validation in `common` (Python + one reusable JS file). |
| 2026-10-22 | Gold Card is for property: owners/investors, developers, managers, people at property or management firms, agents, property lawyers. Everyone can apply; property people are nudged. Medical, other law etc. not targeted. |
| 2026-10-22 | Gold application does not create an account and has no approval flow on the site. Barry gets an email. (Overrides LC-26 "applicants must already have an account" for Phase 1.) |
| 2026-10-22 | Gold nudge is a mix: High potential sees a prominent Gold panel next to the tier result; Medium sees a subtle line; Low sees nothing. Property people still get a tier suggestion too. |
| 2026-10-22 | Gold potential is an automatic High/Medium/Low rating from property type, size and BML link. Weights editable in Control. |
| 2026-10-22 | Gold email to barry@bmlgroup.co.uk, cc moishe.berkowitz@bmlgroup.co.uk. Sections: personal details; property profile + potential; what the site collected (spa interest). |
| 2026-10-22 | Ordinary sign-ups send no email to Moishe or Barry. Seen in Control and stats. |
| 2026-10-22 | Verification by email only. SMS later. |
| 2026-10-22 | Payments will be Stripe (Phase 2). |
| 2026-10-22 | Launch on AI renders; more can be made with fal.ai. Real photography later. |
| 2026-10-22 | Domain spa99.uk, DNS moved to Cloudflare (registration stays at GoDaddy). |
| 2026-10-22 | Email: SES for sending (provisional), replies to `hello@spa99.uk` shared mailbox in BML Microsoft 365. No personal spa99.uk aliases. |
| 2026-10-22 | Fonts: Signika for headlines, Figtree for body/UI (Google Fonts, replacing JUST Sans). |
| 2026-10-22 | Sign-up asks date of birth (18+ check) and a men-only policy acceptance tick (ACC-07/08/09). |
| 2026-10-22 | Anonymous journey answers are kept indefinitely (statistics). Personal data still follows GDPR export/delete. |
| 2026-10-22 | Live hosting: AWS instance (Docker + Caddy), uploaded media in an S3 bucket, managed PostgreSQL. |
| 2026-10-22 | A welcome email is sent after email verification. |
| 2026-10-22 | Hardware direction (not final): Suprema face terminals at entrance and band station, Gantner software/hardware for RFID wristbands, doors and lockers; auto vestibule (first door closing opens the second), exit by wristband into a collector; wristband payments maybe later. Audio probably WiiM; screens probably iiyama ProLite LH7564UHS-B1AG; lights and audio controlled from admin later. Nothing built for these yet, but the structure must allow them cleanly. |
| 2026-10-22 | Django 5.2 LTS, Python 3.13. Fresh project following BML RULES.md (not bml-starter). |
| 2026-10-22 | Frontend: Django templates + HTMX + small vanilla JS. Design guided by the taste skills (design-taste-frontend etc.), applied without React/Tailwind. |
| 2026-10-22 | Background jobs: database-backed queue (works on SQLite and Postgres, no Redis). |
| 2026-10-22 | Spa 99 Control lives on its own subdomain: control.spa99.uk. |
| 2026-10-22 | Media: S3 with `dev/` and `prod/` folders. If S3 settings are missing, save locally and never crash. Site images uploaded in Control go to S3 (never inside the container). |
| 2026-10-22 | Architecture for later: device brands behind adapters in `integrations/` (with fakes for dev/tests); an on-site bridge service syncs access lists from AWS and talks to devices so the door works offline; every on-site action stored as an event; one JSON API for site, bridge, screens and apps. |
| 2026-10-22 | S3 bucket `spa99-media` in the BML AWS account, region London (eu-west-2). Private, versioning on, SSE-S3. Bucket policy denies everyone except root, `user/moishe.berkowitz`, `user/spa99-dev` (local dev, dev/ only) and `role/spa99-server` (EC2). CloudFront exception to add when site images are served. |
| 2026-10-22 | GitHub: private repo on Moishe's personal account (Moishe is not a BML org owner; other devs are). Transfer to BML org later if wanted; transfer keeps history. |
| 2026-10-22 | Background jobs: django-q2 (ORM broker) for queue and scheduler; recurring jobs registered by `manage.py register_schedules`, run by a `worker` compose service. |
| 2026-10-22 | Control host routing: requests for `CONTROL_DOMAIN` use `config.urls_control`, others `config.urls`. Locked by default with Django's `LoginRequiredMiddleware`; public views use `@login_not_required` with a comment. |
| 2026-10-22 | `users.User` has a UUID primary key and a separate 8-character unambiguous `public_id` for guest invites (ACC-05). Emails stored lowercase with a case-insensitive unique constraint. |
| 2026-10-22 | Tests run on `config.settings.test` (dev settings plus in-memory media, plain static storage, synchronous jobs). `manage.py test` selects it automatically. |
