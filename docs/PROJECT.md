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
- No `DEPLOY.md` and no in-repo `RULES.md`: the BML originals live in OneDrive `Developer/Structure`. Deploy notes are in `README.md`.
- No `docker-compose.dev.yml`: nothing runs in Docker locally.
- Generic `REGISTRY` / `IMAGE_NAME` / `IMAGE` instead of `DOCKERHUB_*`, so the registry can be chosen later (open question 7).
- `config/settings/test.py` added (dev settings with in-memory media, plain static storage, sync jobs, no `.env` files).
- `LoginEvent` is append-only and has no `HistoricalRecords` (intentional: it is itself the log). `EmailLog` is the same.
- Messages (`common/_messages.html`) do not auto-dismiss, against BML RULES section 26: an error or confirmation stays until it is closed, so nobody misses a "not saved" notice. (Revisit with Moishe.)
- Gold answer choices and the journey-to-Gold mapping are rows (`GoldChoice`, `GoldSignalSource`), but the signal names themselves (`property_link`, `size`, `where`, `bml`) and the `GoldApplication` columns they fill stay in code: a new kind of question needs a new column, so that is a development change, not a Control one.

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
| 7 | Container registry: AWS ECR (recommended) vs Docker Hub | Before first deploy |

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
| 2026-10-22 | User holds person data only; no status field. Interest and membership are separate records. |
| 2026-10-22 | Motion spec adopted (BRAND.md section 7): soft easing, hero 0.8s, scroll reveals 1s at 15% visible, 12px rise (8px phone), hover 1.01 / press 0.99. Plain CSS + one small script. Impeccable and the Superpowers plugin not installed; two Superpowers habits (root-cause debugging, verify before done) written into the agents instead. |
| 2026-10-22 | Gold potential defaults: owner/investor, developer, manager 5 points; firm, agent, property lawyer 3; size 10-49 +1, 50-199 +2, 200+ +3; North London +1; works with BML +3; referred +1. High needs 6, Medium 3, so a bare owner is Medium and High needs some scale. The journey gets a conditional property-size question so High is reachable from it (hide it in Control if unwanted). |
| 2026-10-22 | A Gold application points at the journey session (`session.gold_applications`); the session has no Gold field. A sign-up later with the same email links earlier Gold applications to the account. |
| 2026-10-22 | GDPR delete: account, interest, Gold applications and email-log rows for the address, and login events are erased (with their history rows). Journey sessions are kept for the statistics but anonymised (unlinked, cookie value replaced, referrer and typed text cleared). |
| 2026-10-22 | Emails are sent by queued tasks that carry only ids; links and tokens are built at send time, so no token is stored in the queue or the database. `EmailLog` records every send (no body) and has no history (it is itself the log). |
| 2026-10-22 | Email backend is chosen by `EMAIL_BACKEND`: console in dev, in-memory in tests, SMTP by default in prod, or `notifications.backends.SesBackend` (boto3, server IAM role). No django-ses dependency. SES is unverified until the first live send (open question 2). |
| 2026-10-22 | Rate limiting is a small cache-based limiter in `common.ratelimit` (no extra package). The default cache is per process, so with several gunicorn workers the real limit is a multiple; switch `CACHES` to the database or Redis for a hard limit. |
| 2026-10-22 | Verification links are signed (24h) and single use because `email_verified_at` is checked: a replayed link signs nobody in. Password reset uses Django's token generator with a 1 hour timeout (single use because the password hash changes). |
| 2026-10-22 | Double-clicking Register creates one account: a repeat of the same email and password within 2 minutes while unverified returns the same account and sends no second email. Same rule (2 minutes, same email) for Gold applications. |
| 2026-10-22 | Seed data (`seed_phase1`) only creates what is missing and never overwrites edits made in Control. It lives in the `plans` app and is never part of a migration. |
| 2026-10-22 | Roles `Owner`, `Manager`, `Viewer` are created by `setup_roles` (proposed permissions, to approve): Manager cannot manage groups, and people and Gold applications are view-only at model level (Control does field-level edits). |
| 2026-10-22 | Journey cookie `spa99_journey`: first party, HttpOnly, SameSite=Lax, one year. Sessions flagged as bots (user agent or honeypot) are excluded from the statistics. |
| 2026-10-22 | Moishe's review of the first build: forms good; marketing pages too static, sections too tall. New direction: immersive Apple-style scroll storytelling. Each section fits one screen (100svh), pinned sections with scroll-scrubbed image zoom/cross-fades, line-by-line text reveals, full-screen looping hero video (still image fallback), small living details. GSAP + ScrollTrigger self-hosted (free licence) replaces the "no animation library" rule. Reduced motion keeps a calm static version. The restrained motion spec still applies to forms, journey and account. |
| 2026-10-22 | No React for the website. Three.js (self-hosted) allowed for two moments: a WebGL water/steam hero effect and a scroll-driven 3D walk into the dry sauna on The spa page (based on the three.js concept model in `docs/design/reference/dry-sauna-concepts.html`, restyled in the Spa 99 palette). Lighter fallback on phones and reduced motion. |
| 2026-10-22 | Hero video will be AI-generated (fal.ai), 2-3 seamless 6-10s loops to choose from. Moishe leaves the creative choices to the team. Dry sauna imagery and 3D moment use Concept B (stone wall: heater centred on split-stone wall, one wide stepped aspen bench). |
| 2026-10-22 | Immersive spec (`docs/design/IMMERSIVE.md`) answers, chosen by the team at Moishe's request: generate all three hero video concepts and pick the best (water wall A preferred); generate the six missing room renders, cold plunge first; smooth scrolling on desktop mouse only, behind a switch; gentle snap per room on desktop; text over images allowed on a dark band keeping AA; Visit us line "Ring once. We'll be expecting you."; header transparent over dark first screens, hides on scroll down; 16:9 extended render 08 for the desktop living still. |
| 2026-10-22 | Review fixes: personal data is erased everywhere. `EmailLog.subject_email` links an email to the person it is about (Barry's Gold email), email tasks return a status string (never the log row), and delete/export cover those rows plus the person's django-q records. |
| 2026-10-22 | Facts and copy are data: address and opening time in Site settings (`address_*`, `opening_text`, `opening_label`), `{opening}` placeholder in site copy, legal page parts as content rows, Shabbos line on the opening rule, facility alt text on the Facility, Gold perk phrases inside the perk, email subjects as Notification templates, journey result wording from content rows and the result JSON. Existing installs are updated by `backfill_site_data --dry-run`, not a migration. |
| 2026-10-22 | Live checks agree with the server: the page gets its messages and limits from Python (`{% validation_config %}`), and the mobile number is checked by the server (`/validate/mobile/`, rate limited). Under-age wording is now the server's "You must be 18 or over." |
| 2026-10-22 | Shared device: a journey session is used only by an anonymous browser or its owner; the `spa99_journey` cookie is dropped on logout and, if foreign, on login. The journey result is stored by `POST /journey/result/`; a GET changes nothing. `furthest_step` cannot jump past the next screen. |
| 2026-10-22 | Client IP: Caddy trusts Cloudflare ranges only and writes `X-Client-IP` from `CF-Connecting-IP`; the app reads it (`CLIENT_IP_HEADER`, prod default `X-Client-IP`). |
| 2026-10-22 | The email verification link shows a "Confirm my email" button; the click (POST) confirms and signs in, so mail scanners cannot use it up. Change password added to the account page. Gold rate limit counts valid applications only. "Register interest" is offered only for plans with `interest_allowed` (visible monthly memberships). |
| 2026-10-22 | Media order: pages built first on interim images (living still 08, door-white for cold, type-only frames for missing rooms). Hero video, steam overlay and renders N1-N6 made with the fal connection after a session restart; ffmpeg (Homebrew) used for encoding. |
| 2026-10-22 | Moishe's review of the new Home: text and buttons at the bottom of every screen feel too big and odd. Text groups now sit vertically centred, left aligned, with the actions right under them; marketing heading sizes one step smaller (hero max 96px, 2xl max 48px); the veil follows the text (IMMERSIVE section 0). |
| 2026-10-22 | Moishe: keep our own dark, editorial scroll direction (not like everyone else), but Home feels plain, empty, too zoomed in, and the scroll is too slow and pins in the wrong places. Next pass: use the architect's provided 3D renders (`02 Launch/Pics/Provided 3D renders`) wide, so rooms are visible; richer layered scenes; far fewer pins and faster scroll. |
| 2026-10-22 | Moishe: lots of small text, neatly placed, feels luxury. Scenes get editorial detail: small captions, labels, facts, room notes, coordinates and hours in fine type around the images and big headings (still AA, still calm). |
| 2026-10-22 | Moishe: small text, but don't overdo it. Images bleed off one side of the screen: an image on the right runs off the right edge with a slight radius on its left corners only (mirror for the left). No plain square boxed images like the current The spa page. |
| 2026-10-22 | Capacity is not shown on Home. Later (members' dashboard, with bookings/access): show live occupancy, how many members are in the spa now. The wooden tub with steps in the architect renders 09/10 is the cold plunge: use it (`cold-tub`) for "Then cold." and the cold plunge room until a dedicated render exists. |
| 2026-10-22 | Moishe likes the round 2 Home ("much better"). For the remaining pages he wants: smaller sections (not every section a full screen), tiers side by side left to right with select-a-tier and compare (compact), much more information, modern details (pills/chips), small image boxes like the "Escape the everyday" ad (`02 Launch/Ads`). He dislikes most current images, especially the architect renders: new images to be made with fal in the look of the ad's renders (warm wood sauna, dark gym with gold swan, travertine relaxation with loungers, reception with lit "SPA 99" desk). No CSS library: plain CSS with brand tokens stays. |
| 2026-10-22 | Section size: compact sections (content height, not forced full screen) on the other marketing pages; Home keeps its round 2 shape, but its Gold Card and Opening sections become compact and richer (still too empty and big). Team decision at Moishe's request ("not sure, feels too large"). |
| 2026-10-22 | The reception feature is now a large fish tank, not a water wall. The fish tank render (`Provided 3D renders/Fish Tank.jpeg`) is the Home feature/hero image until new fal images are made. Overrides the brand image rules for this image: it shows people in robes and blue water. The hero video concepts (HERO-VIDEO.md) move from the water wall to the fish tank. |
| 2026-10-22 | Moishe: round 2 cut too much motion (design itself good). Bring back: (1) Home hero opens full screen (fish tank image) with heading and button on it; on scroll the image shrinks into the frame on the right (the Window effect, short pin) or something equally striking; (2) the Home Gold Card swan drawing itself as you scroll (scrubbed), loved it. Generally a bit more scroll animation than round 2, without long slow pins. |
| 2026-10-22 | Main call to action renamed "Find your membership" → "Tailor your membership" (header, Home, journey). Copy changes on existing databases use `manage.py replace_copy "<find>" "<replace>" --dry-run`. |
| 2026-10-22 | Memberships page: tiers as tall columns side by side (left to right), the whole column is selectable, one single "Continue" button for the chosen tier (Phase 1: continues to register interest with that tier). Compare stays available, compact. |
| 2026-10-22 | Memberships page data: `Plan.tagline/image/render/image_alt`, perk `pill` key, pills/compare/preselect built in services from rows (nothing typed in templates). `plan_pills` lives in `plans.services` (not `pages`) so `plan_display` can include it without a circular import. Existing DBs updated by `backfill_site_data`, never a migration. |
| 2026-10-22 | Memberships: Tier 2 preselected on arrival; page colour cream (not espresso). |
| 2026-10-22 | The spa room facts: show placeholder temperatures and facts for now (typical values, e.g. dry sauna 80-90°C, wet sauna about 45°C, cold plunge about 8-10°C), marked as placeholders in the seed; real values connected later. |
| 2026-10-22 | The spa: only the dry sauna 3D walk gets a pin; the door opening shrinks into its frame on normal scroll (no pin). 3D sauna walls pale aspen (as concept B), not darker cedar. Walk length 1.4 screens (team's call: Moishe found slow scroll tiring). |
| 2026-10-22 | 3D walks: separate short walks per room (Moishe leans separate; team decides the order). Build one reusable room-walk engine with the dry sauna first, then the wet sauna as a second separate walk; other rooms only if the first two feel good. Each walk about 1.4 screens, desktop only, its own pin; phones and reduced motion keep the images. |
| 2026-10-22 | The spa page data: `Facility.display/image_name/image_focus/detail_image/detail_image_name/detail_alt/facts` (schema-only migration; `FACILITY_IMAGES` code map removed). `pages.services.spa_sections()` groups rooms so hiding or reordering never breaks the page; `visit_pills()` builds the step pills from plans and hours. Control rejects image names missing from the manifest and facts over 4 or 32 characters. |
| 2026-10-22 | Facility facts are soft only until Moishe confirms temperatures and times: none seeded (no 80 to 90°C, 45°C, 10 to 15 minutes). Wording from OPS-06 ("Part of your visit") only. Massage line no longer says "by appointment" (OPS-06: part of the same visit, no separate booking). The spa intro uses a `{rooms}` placeholder (count of visible rooms in words) instead of the hard-coded "Eight"; the spa closing button is "Tailor your membership". Existing databases updated by `backfill_site_data`, exact old wording only. |
