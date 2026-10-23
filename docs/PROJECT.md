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
| 2026-10-22 | Home Gold Card section went from too big to too small. Target the middle: about 85% of a screen at 1440, swan about half the screen tall, heading one step up, pills and link kept, the scrubbed swan draw kept. |
| 2026-10-22 | Gold Card: a 3D floating gold card (brushed/polished gold metal, real reflections, embossed swan and SPA 99) that turns on scroll. Used in the Home Gold section and the Gold Card page hero. Rotation of the object is allowed here (overrides the "no rotation" motion rule for this object only; text never rotates). Three.js on capable desktops; a CSS 3D card with a moving sheen on phones and weaker devices; a still image under reduced motion. |
| 2026-10-22 | 3D Gold Card turns over to show its back only on the Gold Card page hero (half turn as you scroll away); on Home it only swings. |
| 2026-10-22 | Moishe: the Home hero image shrinking to the right is very smooth; the same effect on The spa (door) jumps. Fix The spa door to match Home's smoothness (same method; a short pin is allowed there if that is what makes it smooth). |
| 2026-10-22 | Moishe: Memberships much better but missing elegance, still feels generic, not "wow". Try light drop shadows, thinner and taller tier columns. Designer to find what lifts it. |
| 2026-10-22 | Gold Card page card: when it turns on scroll an edge hides behind the next section (breaks the floating feel: it must never be clipped or covered, it floats above sections); at some angles it gets too dark (keep a minimum brightness); the card is a bit too clean/empty: add a fraction more premium detail (e.g. fine guilloché or engraved line pattern, a thin bevelled border inset, a small chip or hologram-style swan seal, micro text) without clutter. "Almost there." |
| 2026-10-22 | Moishe approved the Gold Card look ("all good"). Next session: fal.ai media (fish tank hero video loops and stills, room renders in the look of the "Escape the everyday" ad: N1-N6 incl. cold plunge, fal clean-up jobs in IMMERSIVE-R2 5.4, SPA-PAGE and MEMBERSHIPS-R2 image prompts), then Gold Card page, Book and Visit us redesigns, then a full reviewer pass of feature/phase1-site. |
| 2026-10-22 | Hero video: Moishe will supply the video himself; no fal hero video generation. fal is used for stills (room renders, clean-ups) only. |
| 2026-10-22 | Images: replace every site image except the hero with new realistic fal images. No people. The Spa 99 logo (swan + "SPA 99") appears on a wall or in the background where it fits naturally, fed to fal from the real logo file (never AI-drawn letters). Any water wall or waterfall becomes the fish tank, in the look of Moishe's two references (`docs/design/reference/fal/fish-tank-ref-1.webp`, `-2.webp`): travertine frame, backlit swan on the wall, green wall, long bench with sage cushions, warm cove light. Overrides the earlier "keep the architect renders" choices. |
| 2026-10-22 | Hero video supplied by Moishe (`Software Files/media/fish-tank-loop.mp4`, 13s slow push-in on the fish tank). Made seamless with a 1s cross-fade at the loop point (12s), audio removed, encoded to the HERO-VIDEO.md files in `content/static/content/video/` (portrait is a 608x1080 crop on the tank). The Home hero now plays it over the still. |
| 2026-10-22 | fal access: the manager agent tools allowlist was removed (Moishe ran the edit), so the manager gets every tool including fal. fal tools now load in the session. The fal hero video is not needed (Moishe supplies the video). |
| 2026-10-22 | Hero loop: Moishe picked option B, a 3s cross-fade (10s loop: source 3-10s, then a fade from 10-13s into 0-3s, so the end meets the start). Re-encoded to the same files (AV1 1.0 MB / H.264 2.2 MB landscape, 0.5 / 1.0 MB portrait). Moishe is happy with the hero; no more work on it. |
| 2026-10-22 | Moishe dislikes most current site images. Keep `lockers` (he likes it). `gym` is "okayish": replace it last, only if the new one is clearly better. Every other image is replaced with fal per `docs/design/FAL-IMAGES.md`, cold plunge first. |
| 2026-10-22 | Dry sauna image: Moishe finds it "quite ok" but the room looks small (a cabin seen through the door). The new fal version keeps its look (warm wood, glowing bench lines, the swan on the glass) but shows a bigger, wider sauna taken from inside, with more benches. |
| 2026-10-22 | Moishe: every render on the site is recreated as a realistic photo, with the fish tank replacing any water wall or waterfall. Method: fal edit of each current render (same room, layout and logo placement, now photoreal), so the ones he likes (lockers, gym, dry sauna) keep their design. Dry sauna also made bigger. Not redone: `fish-tank` (hero still), `gold-card` (3D), `hero` (unused). `cold-tub` is replaced by the new `cold-plunge`. |
| 2026-10-22 | Realistic set is live in the site (no preview round, Moishe's call). 13 renders turned into photos with fal (nano-banana 2.1 edit, same layout); fish tank on arrival, lounge and reception; dry sauna made bigger; cold plunge = option 1 (finished from the real tub photo), also built as `cold-tub` until Control points the Facility at `cold-plunge`. Old images backed up in `.private/img-backup-2026-10-22-renders/` (and in git before this commit). fal originals in `.private/fal-renders/` (the sandbox blocks writing to OneDrive: copy them to `Software Files/media/fal-renders/`). `build_images.py` now rebuilds only the names found in the folder given. Known issue: `reception` (not shown on any page) has made-up wayfinding signs; redo before using it. |
| 2026-10-22 | New room photos live (no preview round): `wet-sauna` (travertine steam room), `massage-room`, `kitchenette`, made with fal in the same look (style taken from the new dry sauna, loungers and lounge photos; swan from `mark-gold.png`). Facilities now use `wet-sauna`, `cold-plunge`, `massage-room`, `kitchenette`; existing databases updated by `backfill_site_data` (fills empty names, swaps `cold-tub`/`lounge` only while still unchanged). The swan type tile stays as the fallback for any room with no picture. Home kitchenette preview still uses `lounge` (now with the fish tank). |
| 2026-10-23 | Moishe's site walk-through (round 3). Home hero video: liked, keep. Remove the old fish tank still with people from the hero completely (it flashes for a split second on reload); the hero uses the video poster frame only. |
| 2026-10-23 | Header: "Sign in" must not be underlined at rest. Remove "Tailor your membership" from the header (it stays in page sections). |
| 2026-10-23 | Home: the cold plunge picture shows as missing (check after a server restart). "What's inside" must not repeat the dry sauna already used in "Heat, slowly": use a different picture there. |
| 2026-10-23 | Lounge image: the fish tank is too square. Redo it very wide (about 3 m, a long landscape tank) with the long bench and sage pillows in front, as in the hero video. Needs fal. |
| 2026-10-23 | Gold Card (Home and Gold Card page): the inner border must be there from the first frame, not appear after scrolling or a second later. Otherwise approved. |
| 2026-10-23 | Sign-in page is generic and unimpressive: redesign it in the site's premium look. |
| 2026-10-23 | The spa page: the full-screen gold swan door is too zoomed in; replace it (wider view, or a video like Home, Moishe to make it; team to recommend the shot). Drop the line "Eight spaces, one quiet visit.": more text in the opening, and the text changes as you scroll (one line fades out as the next comes in, e.g. 5am to 3am, men only, rooms, one visit). |
| 2026-10-23 | The spa page: the kitchenette is shown much smaller than the gym; give it a proper size. |
| 2026-10-23 | Gold Card page: the card hero is good, but the rest of the page feels plain and unpremium: redesign below the card. |
| 2026-10-23 | Memberships: layout is liked, but it needs more freshness and premium detail without breaking it. The plus icon should turn and become an X (not a minus). A stray border sometimes shows around text (possibly a focus outline glitch): find and remove it. |
| 2026-10-23 | The spa opener: Moishe will make a video like the Home hero: a slow push-in through the gold swan door into the warm corridor, about 10 s, no people (shot brief in docs/design/SPA-DOOR-VIDEO.md). Until then a wider realistic photo of the doorway replaces the zoomed-in door. |
| 2026-10-23 | The spa: the kitchenette becomes a normal tile (same size as wet sauna, cold plunge, showers), not a small companion. |
| 2026-10-23 | Review 2026-10-22 should-fix items are done in this round. Exception: the placeholder temperatures and times stay on The spa page for now (overrides the 2026-10-22 "none seeded" entry; still placeholders until Moishe confirms real values). |
| 2026-10-23 | Amenities: every visit includes swan towels, a swan robe, swan slippers and toiletries in the swan bottles. The site shows them (Moishe: "would make it a lot more premium", "it's missing a lot"): a relaxation/amenities section on The spa page with the mock-up photos (`01 Branding/Assets`, copied to `docs/design/reference/amenities/`), framed nicely, plus a mention elsewhere where it fits (Home, Memberships). Clean the mock-ups (no candles, stones, plants) or remake them with fal in the same look. |
| 2026-10-23 | SUPERSEDED same day, see next row. |
| 2026-10-23 | Moishe: no "coming soon" and no merchandise framing. The branded items (towels, robe, slippers, toiletries, tote bag, steel bottle) are woven into The spa as part of the experience, as if they exist: atmosphere and detail images between the rooms, not a shop. Goal: more vibe, not just room after room. Selling merch stays a later item (EXT-01). |
| 2026-10-23 | Live email and mobile checks are POST with CSRF (no addresses or numbers in URLs or access logs); email failure logs show the email-log id, never the address. |
| 2026-10-23 | Barry's Gold application email has no Control link until Control is built (it 404'd). `docs/features/admin.md` now says plainly that Control is not built; the Django admin is the only editor today. |
| 2026-10-23 | The spa: the kitchenette tile sits in the same row as wet sauna, cold plunge and showers (order moved to just after showers; existing databases reordered by backfill only while still in the seeded order). |
| 2026-10-23 | Moishe: the branded items are not only small frames. Use them big too: try the robe hanging (or the slippers) as The spa hero image, full-bleed, and large detail images through the page; "the robe gives it a crazy kind of vibe", nicer than a generic spa room. The team may experiment freely on The spa page. Home stays more or less as it is (small additions only). The door push-in video stays an option for later; the opener is now an open choice between the robe still and the door. |
| 2026-10-23 | Gold perk "Each merch release" stays visible as it is (Home Gold pills and the Gold Card page). Overrides the briefs' default of hiding it. |
| 2026-10-23 | Round 3 briefs accepted with the team's recommended options: The spa opens on the robe hero (door photo and Moishe's door video stay a later switch; if made, it loops with a 3 s cross-fade like Home); opener pin 80% of a screen; the new sign-in look also on Forgotten password, Reset password and Check your email; Home gets only a small slippers inset (dropped if it crowds the caption at 1440). Briefs: SIGN-IN, GOLD-PAGE-R3, MEMBERSHIPS-R3, SPA-OPENER, SPA-DOOR-VIDEO, AMENITIES. |
| 2026-10-23 | Dev only: runserver sends CSS/JS with `Cache-Control: no-cache` (patched in `common/apps.py` when DEBUG). The browser had been showing stale copies of the unhashed `@import` files, so new pages looked broken (likely also the "weird border" glitch Moishe saw). Live is unaffected (hashed manifest files). Breaks the "no monkeypatching" norm on purpose, dev only. |
| 2026-10-23 | Moishe: use his own mock-ups as they are, no remaking (he likes them): robe, towel on the bench, towel on the rail, slippers, toiletries, tote, steel bottle are live (`robe`, `towel-bench`, `towel-rail`, `slippers`, `toiletries`, `tote`, `bottle-gym`, plus `-portrait` crops). Overrides the brand image rule for these (some show a candle, plants or stones). fal is only for: (1) the lounge, redone with a very wide fish tank (about 3 m) and the long bench with sage pillows in front; (2) widening the same robe photo for the desktop opener (it is only 768x1376, so it is soft full-screen; outpaint/upscale, never redraw). Nothing else is remade. |
| 2026-10-23 | Tailor your membership: reopening it no longer jumps to the last suggestion. It starts at question 1 with the earlier answers ticked; a small "See my last suggestion" link stays. The result button "Change my answers" becomes "Start again" (clears the answers, back to question 1). Remove the stray outline round the big tier name on the result (shows on load and refresh, goes on click). |
| 2026-10-23 | Tailor your membership: "Your time" and "What draws you" say "Choose at least one." and Continue stays disabled until one is chosen (more allowed). The whole form needs more class (premium polish, same flow); "Company" is fine in content but the UI needs lifting too. |
| 2026-10-23 | Gold application, screen 1: "Your property." becomes "About you." It asks "What do you do?" (the journey industries); the property questions (link, size) show only when he picks Property. Nobody should feel "I don't own property, this isn't for me". The Gold rating keeps working. |
| 2026-10-23 | Images: overrides "only two fal jobs" from earlier today. (1) `relaxing-zone`: zoom out (wider view), and the loungers get proper thick comfortable pads with a pillow each; keep the room look. (2) `massage-room`: luxury massage chairs instead of the massage bed (picture only; the room is still called "Massage room"). Old files kept as *-old.png. |
| 2026-10-23 | Done: `lounge` redone as a fal edit of the old render (nano-banana-pro edit; refs: the hero poster frame and both fish tank refs, then bria eraser to remove a ghost glass panel in the tank). Very wide reef tank set flush in travertine, long cream bench with sage pillows in front, rest of the room kept; no logo, no people. Home R4 frame focus set to 28% 55% so the whole tank shows. `robe` widened to 16:9 with bria expand (the original pixels untouched, only the sides added) and upscaled 2x with SeedVR (4896x2752; swan and "SPA 99" checked unchanged). Opener end frame focus moved to the robe (CSS `--focus` 78% 40%, JS window focus x 0.73); the kit thumbnail focus is now `100% 38%` in the seed (an existing database keeps 66% 38% until changed in the admin or by backfill). `robe-portrait` stays the old portrait original (phone opener). Old files kept as `lounge-old.png` and `robe-old.png`. |
| 2026-10-23 | Done: `relaxing-zone` = fal edit (thick cushioned loungers, bolster pillows, caramel throws, logo kept) then bria/expand outpaint to zoom out (4224x1792). `massage-room` = fal edit with two cream leather and walnut massage chairs (3712x4608); alternative with reclined chairs kept as `.private/fal-renders/massage-room-alt.png`. Old files kept as *-old.png. "Choose at least one" (Question.min_choices, editable in admin) overrides the journey's "every question skippable" rule for "When would you come?" and "What would you use?" only. |
| 2026-10-23 | Moishe's walk-through (round 4). Liked: Home (apart from below), Memberships, Gold Card page, Sign in. Book is fine for now. Visit us is plain: leave it for now, a little more flair later. |
| 2026-10-23 | Home: remove the slippers inset (round 3 addition) completely. The opening date reads "Launching January 2027" (not the bare month), wherever the date stands alone. |
| 2026-10-23 | The spa opener: keep the robe and the scroll that isolates it, but redo the picture's left side. The massage beds (Barry will not like them) become a steamy wet sauna behind a glass door, so the robe hangs just outside it. Same for `robe-portrait`. Never redraw the robe. |
| 2026-10-23 | Massage room picture: a row of massage chairs side by side, all facing the same way. Two chairs facing each other read as a couples room, wrong for a men-only spa. |
| 2026-10-23 | The spa: remove the full-width, zoomed-in towel band before "Heat". The relaxing zone on The spa must show the new picture (cushioned loungers). The towel in the closing "Arrive" part is too zoomed in: show it wider. |
| 2026-10-23 | The spa amenity wording: keep the pictures, change the words. No promises of amenities ("in every shower", toiletries, "on the way out", slippers). Short mood lines about comfort and luxury only. The slippers moment ("Soft underfoot") is toned down and flows with the page, no fuss. |
| 2026-10-23 | Tailor your membership: Company has two answers only, "Alone" and "Sometimes with someone" ("Often with someone" goes: even Gold has only two guest visits a month, GST-01). "How did you hear about us?": A friend, BML member, Social media, Other (Instagram and Walking past go; old answers keep their label). "How did you hear about us?" can be tapped again to clear the choice (the only question where that failed; Moishe, same day). |
| 2026-10-23 | Follows from Company having two answers: guest visits are Tier 3 and Gold only (GST-01), so "Sometimes with someone" now leans to Tier 3 (it takes over the old "Often" points and the evenings-with-guests rule). New amenity wording (no promises): opener 4 note "Take your time. Nothing here is rushed."; shower moment "Between rounds." / "Warm water, cool stone and a moment to yourself."; slippers moment "Unhurried." / "From the lockers to the loungers, at your own pace."; tote moment "Until next time."; the kit row heading "The details." (was "Every visit includes"); step 2 "Arrive." / "Leave the day at the door."; Home date "Launching {opening}.". |
| 2026-10-23 | Register interest page: the form is neat but dated ("looks like a doctor's prescription"). Keep the colours; make it modern and premium with more elements and a background (picture, texture or layered composition), same fields and flow. |
| 2026-10-23 | Done: `robe` and `robe-portrait` redone with fal (nano-banana-pro edit): the massage room on the left is now a misted glass steam room with steam drifting out towards the robe; robe, hook and wall kept. Previous versions kept as `robe-beds.png` / `robe-portrait-beds.png`. `massage-room` is now a row of three massage chairs facing the camera (the facing pair kept as `massage-room-facing.png`, a diagonal row as `massage-room-alt.png`). |
| 2026-10-23 | Home hero: new video `fish-tank-loop-v2.mp4` (16 s slow push-in) replaces the first. It plays once, then holds on its last frame with a barely visible slow drift: no restart, no cross-fade (the zoom jump on restart looked wrong). Supersedes the 2026-10-22 loop option B for Home. Register interest caption shows "Launching January 2027" like Home. |
| 2026-10-23 | Moishe (round 5): remove the Pause/Play control from Home and The spa. Breaks WCAG 2.2.2 (moving content over 5 s should be pausable) on purpose: the hero now stops after 16 s and the remaining drift / living-still motion is very slow and stops under reduced motion. |
| 2026-10-23 | Home "Then nothing at all." picture (`relax-loungers`): give the loungers the same thick cushions and pillows as the new relaxing zone (fal edit, same room). |
| 2026-10-23 | "Launching" is a small label, not part of the date: all caps, small size, wide letter-spacing, above "January 2027." (Home, and the register caption). The date heading goes back to "{opening}.". |
| 2026-10-23 | The spa pills: remove "Sit on a towel" (dry sauna); cold plunge temperature pill reads "12°C" (other pills stay; still placeholders until confirmed); showers pill "Between rounds" becomes "Warm rain, cool stone". Massage picture: the chairs stand along the right wall facing the left wall, spaced apart, same camera angle. The Arrive "Towels" thumbnail must read as a folded towel (it showed only the logo). Then commit and push. |
| 2026-10-23 | Done (round 5): `relax-loungers` edited with cushions, bolsters and throws (old kept as relax-loungers-old.png). `massage-room`: two chairs along the right wall facing the left wall, a clear gap between (the row of three kept as massage-room-row.png). |
| 2026-10-23 | Memberships "every visit" line loses the amenity list: "Every visit: every room, as long as you like.". Journey: "Sometimes with someone" never gets Tier 1 and wins ties for Tier 3 (guest visits are Tier 3 and Gold only, GST-01). |
| 2026-10-23 | PR #4 (feature/phase1-site, rounds 3 to 5) merged into main by Moishe. Run `migrate` then `backfill_site_data` (dry run first) on any existing database. |
| 2026-10-23 | No release tags or release talk yet: the site is still far from release. Merges into main are normal work; tags start when Moishe says. |
| 2026-10-23 | New feature branch `feature/virtual-tour` (from main after PR #4). Virtual tour: its own page "Virtual tour" at `/tour/`. First rooms: lounge (fish tank), dry sauna, wet sauna, relaxing zone, gym. Look-around inside each room (drag, or tilt on a phone) and tap a doorway to move to the next room. |
| 2026-10-23 | Moishe: no fal for the tour. The team builds the 3D rooms itself in three.js (self-hosted, already used for the Gold Card), in the look of the site's room photos (travertine, oak, warm light, the gold swan). Supersedes the 2026-10-22 scroll-driven "3D walk" plan on The spa; the old concept model `docs/design/reference/dry-sauna-concepts.html` is a starting reference. |
| 2026-10-23 | Virtual tour brief (`docs/design/VIRTUAL-TOUR.md`) accepted. Lounge stays a tour-only room; not added to The spa for now. Menu label "Virtual tour". Moishe sends the stacked logo (swan above "SPA 99") as SVG for the relaxing zone and gym walls; until it arrives the build uses the swan mark alone there. Sage pillows, moss and the blue tank water may use colours outside the brand palette (3D objects only). |
| 2026-10-23 | Stacked logo added: `common/static/common/img/logo-stacked-gold.svg` (brand two-tone: swan #E5AC6E, swirls, eye and "SPA 99" #BB8855) and `logo-stacked-espresso.svg`, composed from the existing vector paths to match Moishe's "Spa 99 Logo" PDFs (01 Branding/Logos). Used on the relaxing zone and gym walls in the tour. |
| 2026-10-23 | Virtual tour lounge layout (Moishe): standing at the fish tank, to its right is more lounge seating (not the dry sauna); to its left is the reception desk; the rooms (saunas etc.) are deeper in to the left. The tour must follow the real floor plan (`OneDrive/BML/Spa 99/Plans/99 VALE ROAD - SHVITZ-LIGHTING REV4.pdf`), not invented adjacencies. |
| 2026-10-23 | Virtual tour review fixes: tone mapping is `LinearToneMapping`, set explicitly (ACES filmic is not in the vendored build; the look approved in the browser was Linear by fallback), default exposure 0.8; tour pages set `@view-transition { navigation: none }` (the cross-document transition was skipped mid-load); built rooms capped at three; tour durations now use tokens (BRAND section 8); unused `--color-reef-*` tokens dropped (tank colours live in the lounge room code); budget caps raised (see VIRTUAL-TOUR 4.2). |
| 2026-10-23 | Moishe (overnight): until he wakes, the team makes all decisions, runs what it needs, and merges finished branches into main (via git, since gh cannot run in the sandbox), tests first. |
| 2026-10-23 | "Launching" label (Home opening band, register caption): bolder (600), one step bigger (`--text-base`), wider letter-spacing (new derived token `--tracking-launch` 0.3em). Still a label, clearly smaller than "January 2027.". |
| 2026-10-23 | The spa opener: only the first line in the hero ("Open 5am to 3am." / "Every day. Closed for Shabbos and Yom Tov."), then straight to the room chips. Lines 2 to 4 and the ticks removed from the hero (rows kept in the database, may be used elsewhere later); pin shortened to Home's length (0.35 phone, 0.5 desktop) so nobody stops mid-scroll. |
| 2026-10-23 | Home 3D Gold Card: less shiny, with depth. Darker studio walls and slightly lower exposure on Home only, and the reflections dim and brighten as the card turns on scroll (darker, moodier moments, never black). The Gold Card page keeps its look. |
| 2026-10-23 | Moishe: the Gold Card application form looked dated next to the new register page. Redesigned as register's premium sibling ("the private room", `docs/design/GOLD-APPLY-ROUND5.md`): espresso stage on the left with the gold card still, the label and a three-part ledger (sticky on desktop), the form on a raised gold-deep panel with a gold progress line. Same steps, fields, wording, endpoints and logic. CSS is a `.gold-apply` block at the end of `journey.css`; no token changes. |
| 2026-10-23 | Audit after PRs #5, #6, #7: every branch and commit is in main, all changes present, 250 tests pass, no pending migrations or backfill. The old stash `stash@{0}` (round 4 snapshot) holds nothing missing from main. Workflow from now on: every change on its own feature branch, never on main; Claude does all the work, testing and pushing; Moishe only merges, by clicking the GitHub link Claude gives (Claude's permission system blocks merging into main, and `gh` cannot run in its sandbox). New branch `feature/tour-fixes` for the tour corrections. |
| 2026-10-23 | Tour fixes (Moishe, round 2). Real order of the building, from the lounge: the reception desk comes out from the LEFT wall (moved left from where it was, attached to that wall); behind reception is a plain wall. Behind that wall, one after the other: gym, then kitchenette, then lockers (not shown). At the far end beyond the gym: dry sauna to the left, wet sauna to the right. The tour follows that chain: lounge to gym (passage beside reception), gym to the saunas at its far end (dry left, wet right). The relaxing zone's place was not given: it stays reachable from a lounge doorway on the right and from the room list (team assumption, to confirm). |
| 2026-10-23 | Tour rooms: relaxing zone gets a TV on the left wall, facing the loungers. Gym gets lots of equipment (several treadmills, bikes, a rower, a rack with dumbbells, benches, a cable machine). Dry and wet saunas much bigger, benches on all three walls; the dry sauna has a proper stove with visible glowing coals and a wooden bucket with coals/stones on the floor (no ice bucket inside); the wet sauna gets a visible steam outlet. The lounge tank room is otherwise approved. |
| 2026-10-23 | Tour adds two rooms (Moishe): kitchenette after the gym, then the massage room (the massage chairs, a TV and a fireplace), then the two saunas (dry left, wet right). Tour chain: lounge to gym to kitchenette to massage room to dry/wet sauna; relaxing zone from the lounge's right side. A fireplace is fine inside the tour (the old no-fireplace rule was for the generated photos). |
| 2026-10-23 | Lounge correction (Moishe, with reference `docs/design/reference/tour/lounge-reception-corridor.jpg`): the reception desk stays where it is on the left wall but extends along so it reaches the wall opposite the fish tank (it sits in that corner). The way to the rooms is a long corridor opening in that same wall as the desk (the wall opposite the tank), beside the desk, NOT in the fish tank wall. The reference shows a water wall where ours is the fish tank, and "BML SPA" where ours is the stacked Spa 99 logo. Everything else in the tour is approved. |
| 2026-10-23 | Gold application: the card picture beside the form is cropped to the card itself (rounded corners, soft shadow), so the still's flat studio background no longer shows as boxes against the page glow (Moishe: "weird box shadow"). |
| 2026-10-23 | Gold Card stays "apply without an account" (LC-26 Phase 1 override kept). Approval route (to build with approvals, ADM-05): Barry approves, the applicant gets an invite email with a one-time link (expires after 14 days, Barry can resend) that opens account setup with name, email and mobile prefilled from the application; they set a password, Gold is active at once, no payment step, the Gold month starts on the approval date (LC-27). Declined applicants never get an account. |
| 2026-10-23 | Back-office split (Moishe): **Control** = the control room for the building only (lights, music, speakers and sound, screens, and later doors, bands, lockers, sauna controls). **Office** (name chosen by the team; Moishe: "whatever you want to call it") = the business dashboard: statistics, people, Gold applications and approvals, plans, hours, copy, notifications, settings, team. Members keep "Your account". One Django project and database, separate apps (`office`, `control`) on separate subdomains (`office.spa99.uk`, `control.spa99.uk`) via the existing host routing. Nothing of Control was built beyond a placeholder, so only the plan docs and routing change; to do on its own branch. Barry will approve Gold from his email: an Approve button opening a one-tap confirm page in the Office (sign-in still required, sessions last weeks). |
| 2026-10-23 | Forms (Moishe): the new register-page form style (filled cream fields with the label inside, raised cream panel, caramel section heads, the register look) becomes the one universal style for every form: register interest, Gold application, Gold invite account setup, sign in, forgotten/reset password, account settings and any other form. Done as shared form components, not page-by-page copies. Built on `feature/gold-invite` with the invite page (same templates). |
| 2026-10-23 | Office users (Moishe): developers, admins and Barry. Control stays the building control room. |
| 2026-10-23 | Wording (Moishe): every visible "Register interest" on the site becomes "Register" (nav, buttons, headings, page titles, emails, copy rows). "Register interest in {plan}" becomes "Register for {plan}". The URL `/register/` and internal names stay; the rules' release stage name "Register interest" stays in the docs. |
| 2026-10-23 | Control is parked until the building's hardware is installed (lights, music, screens, doors, saunas); it stays the placeholder at `control.spa99.uk`. Build the **Office** now (`office.spa99.uk`, for developers, admins and Barry): a dashboard with key figures (journeys filled in, registrations, Gold applications, site visitors, and more) plus a rich analytics section in a premium, Apple Watch-like style (rings, sparklines, smooth charts), using a good self-hosted chart library. |
| 2026-10-23 | **Rule (project-wide, Moishe): no figure is calculated on the fly.** Every count, total and statistic shown anywhere (Office dashboard, analytics, and later member and booking pages) is stored in the database and kept up to date as events happen (counters updated in the same transaction as the event), with scheduled roll-ups into daily/weekly/monthly tables, and a rebuild command (with a dry run) to recompute from source if ever needed. Pages only read stored figures. |
| 2026-10-23 | Site visitors are counted by our own counter, no cookies and no personal data: page views and daily unique visitors via an anonymous daily hash (rotating salt, never stored raw IP or user agent), aggregated into daily tables. No cookie banner needed; everything stays in our database. |
| 2026-10-23 | Moishe: commit locally as we go; push a branch to GitHub only when the whole feature is ready (reviewed, tested, checked in the browser), then send the merge link. |
| 2026-10-23 | Moishe: ask him before every push to GitHub. Commit locally as we go; when a feature is ready, tell him and push only after his yes. |
| 2026-10-23 | Office design brief accepted (`docs/design/OFFICE.md`): Chart.js 4.6.1 (MIT, self-hosted UMD) on Analytics only; Dashboard rings and sparklines as server-rendered SVG. Team decision under Moishe's "really cool, Apple Watch" brief: in the Office only, rings, sparklines and the approve tick may draw in, numbers may count up on first load, and charts animate (reduced motion: all static). Ring goals are stored settings. |
| 2026-10-23 | Workflow (Moishe): one working branch at a time. All work of a round goes on that branch (no extra branches or separate worktree sessions); when the round is ready the team asks Moishe, pushes once, he merges once, then the next branch is opened. This round stays as it is (Office on `feature/office`, the spa hero video on its own branch); the one-branch rule starts with the next round. |
| 2026-10-23 | Moishe: when he asks for something that does not belong to the current branch, the team tells him and suggests holding it for the next branch (logged as a to-do) rather than mixing it in. |
| 2026-10-23 | The spa hero video (Moishe): his clip `Software Files/media/Vapour.mp4` (the robe with steam, 16 s) becomes The spa opener, looping with a slight fade at the end of each loop. The fade is baked into the file (the last 1.5 s cross-fade into the first frames, 14.5 s loop), so the native `loop` restarts invisibly. Files `content/static/content/video/spa-hero-*` (landscape 1920x1080, portrait 608x1080 cropped round the robe, H.264 + AV1, no audio, first-frame posters). It plays inside the opener window and keeps playing in the shrunk frame; pauses off screen or with the tab hidden; reduced motion or Save-Data show the poster only; no Pause control. The poster replaces the robe photo in the opener (an upload on `intro` still wins, without the video). |
| 2026-10-23 | Home hero: new clip `fish-tank-loop-v3.mp4` (less zoom) replaces v2 and LOOPS again with a soft 2 s cross-fade baked into the file (14 s loop); the play-once/hold/drift behaviour is removed. Supersedes the earlier "play once, then hold" row. |
| 2026-10-23 | The spa hero video (Vapour): reversed at Moishe's request so the steam drifts from the steam room towards the robe; the robe is frozen (a still laid over the video with a soft edge) because the AI clip's robe fabric shimmered ("jittery"); loops with a 1.5 s baked fade. |
| 2026-10-23 | Gold Card flat (Moishe): contrast pass. Cause: not the three rebuild (same 0.186.1, only exports added) but the approved studio itself (walls 0.9, big fills, weak strip, env 0.5, so no real dark parts). One `LOOK` block in gold-card-3d.js now has dark walls and fills (deep bronze, never black) and much brighter strip, key and rim (14/5/12); Home keeps darker and moodier with the same peaks. Needs browser tuning by the coordinator. See GOLD-CARD-3D.md 7.5. |
| 2026-10-23 | Gold Card retuned by eye on the real 3D render: off-axis lights (the strip no longer sits behind the camera, which made it flat), a soft base panel for the resting gold, glossier face, stronger swan relief. Darker and lighter at once, per Moishe. |
| 2026-10-23 | Fixed: (1) site-wide "dead button": validate.js re-submitted inside the real click/Enter dispatch, which browsers silently ignore; it now waits one task. (2) Gold Card: the 3D canvas fade read "1200ms" as 1200 s, so the flat CSS card showed (with doubled text) for ~20 minutes; now a 0.4 s fade. Swan shows complete from the first frame (no outline drawing in); word engraving softened (bump 1.8). |
| 2026-10-23 | Moishe: Gold Card page card has no swing-in. It loads straight in its resting pose (-12 degrees, swan complete) with a 0.4 s fade; the scroll half turn stays. Home card unchanged ("perfect"). |
| 2026-10-23 | Moishe: no flash of the flat card on refresh. On the Gold Card page hero (desktop, 3D capable) the flat CSS card stays hidden until the 3D card has faded in; it shows only if 3D cannot run (gate fails, load error, or a 5 s safety timer). The hero 3D now loads at once instead of after page load + idle. |
| 2026-10-23 | Moishe: Office goes light; Dashboard and Analytics may use a muted colourful palette (Office-only tokens); People and Gold keep brand colours; public site colours unchanged; Dashboard shows plain counts (people started / finished the journey) instead of percent-of-goal. Brief: `docs/design/OFFICE.md` (light, round 2). |
| 2026-10-23 | Moishe: three staff front ends, one Django backend. `office.spa99.uk` = numbers and Gold approvals (Barry, no system settings). `control.spa99.uk` = the building only (lights, music, screens, rooms), used remotely by a few admins, never on in-building tablets. New `system.spa99.uk` = dev-only (superuser role): prices, stay periods, RFID and Face ID rules, access windows, sales and offers. Own host via the existing host routing, own sign-in, password asked again on entry, full change log (who, old, new, when) with undo; admins never see a link to it. Same database and hardware connections (no second codebase). Built after Control. Supersedes "prices, hours, content changed in Control" for business rules. |
| 2026-10-23 | Funnel and rings count people once per day via the anonymous daily visitor hash, so each step nests (visitors >= started >= finished >= registered). Session counts kept for drop-off. |
| 2026-10-23 | Dashboard and Analytics show 'what people want' insights from a stored insights table written by the roll-up; nothing computed on page load. |
| 2026-10-23 | Moishe: one robust counting rule set for every Office figure, in `docs/features/office-counting-rules.md` (C1-C5). A person = their account once known, else one browser (journey cookie chain, a restart stays the same person); no IP stored. Bots, staff hosts and staff accounts never counted. Journey figures and answers count people (one vote per person, latest finished journey); visitors stay cookieless unique-per-day. All figures on a page come from one stored snapshot written in the background, so they always agree. Replaces the per-day hash "people" counts. |
| 2026-10-23 | Moishe: resilience plan for live hosting (later, not now): one codebase kept; safe health-checked deploys (old version stays if `/health/` fails); separate containers for the public site and the staff hosts (Office, Control, System) from the same code; a branded "back shortly" page from Caddy when the app is down, but NOT yet: for now Moishe wants to see errors properly, also on live. Never `DEBUG=True` on live (it exposes secrets); errors are shown through staff-only error reporting instead. |
| 2026-10-23 | Moishe: Sentry for error logs on live (he creates the account and project; we wire `sentry-sdk` with the Django integration, DSN from env `SENTRY_DSN`, off when unset, environment tag dev/prod, no personal data sent: `send_default_pii=False`). A staff-only error page is optional, low priority. Later branch. |
| 2026-10-23 | Sentry built (`feature/sentry`): all from env (`SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `APP_VERSION`, trace/profile rates), off when no DSN, dev can send for testing; Django + logging integrations, django-q failures arrive via its ERROR log; `before_send` strips cookies, sensitive headers, bodies, sensitive query strings and keys, emails; user id plus staff/host tags only; noise ignored; `manage.py sentry_test`; startup line shows `sentry=`. Details in `docs/features/foundation.md`. |
| 2026-10-23 | Moishe: the 3D Gold Card also runs on capable phones and tablets (Home and the Gold Card page), same look as desktop. Gate keeps reduced motion, Save-Data, real-GPU WebGL2 and memory/cores when reported; dpr cap 2 on small screens, renders only on screen. Weaker phones keep the flat card. The hero's flat card stays hidden until 3D on every screen; the 5 s fallback only fires if 3D never started. |
| 2026-10-23 | Barry's one-tap Gold approval built: Approve and View buttons in his email open a confirm page in the Office (sign-in, Owner/Manager/Approver), one tap approves and sends the invite; Office sign-ins last 30 days. |
| 2026-10-23 | Dev: background jobs run inline on Moishe's Mac (Q_CLUSTER sync, `Q_SYNC=0` to test the real queue), so emails print straight to the runserver terminal with no worker to start. Live keeps the real worker. |
| 2026-10-23 | Email recipients, senders and mail settings come only from env (GOLD_APPROVER_EMAILS, GOLD_APPROVER_CC, CONTACT_EMAIL, DEFAULT_FROM_EMAIL, SERVER_EMAIL, EMAIL_*); nothing hard-coded; prod refuses to start without DEFAULT_FROM_EMAIL. An Approver role in the Office (Gold only). |
| 2026-10-23 | Moishe: on the account page, a Gold holder's Membership tile reads "Gold member" (others keep "Opens January 2027"). |
| 2026-10-23 | Moishe: build **System** (`system.spa99.uk`, dev-only) before Control's room controls (hardware systems not chosen yet). System holds the business rules we already have: plans/tiers and pricing (VAT), hours and closures, Gold rules, journey settings, opening date and stage switches, email recipients (Gold approver, CC, contact), team and roles, plus a light admin dashboard. Look: compact and dense (small boxes, small controls), different from the Office; a CSS library is allowed. Change: Gold approver/CC/contact recipients move from env to System settings (devs only); secrets and mail transport (SMTP/API keys, From address, database) stay in env. Branch `feature/system`. |
| 2026-10-23 | System foundations built (branch `feature/system`): app `system`, host `SYSTEM_DOMAIN` (dev `system.localhost`, prod `system.spa99.uk`), noindex; superusers or the new `System` group only, everyone else a plain 404; password asked again to unlock (15 idle minutes, rate limited); a change log (`SystemChange`) built from django-simple-history with one-click undo; pages: dashboard (stored figures), change log, emails, settings, team (plans, hours, Gold rules and journey screens next). Gold approver, CC and contact email moved from env to `SiteSettings` (`GOLD_APPROVER_EMAILS`, `GOLD_APPROVER_CC`, `CONTACT_EMAIL` env vars removed; one-off `import_email_settings_from_env`). |
| 2026-10-23 | System rule sections built (server side): Plans and pricing (edit, add, hide; no delete), Hours and closures (opening rules, capacity, closures with logged delete), Gold rules, Journey (questions, options, suggestion rules). Every save goes through the System change log with undo; server-side validation with field errors; `risky_fields` in each page context for the frontend's confirm step. |
| 2026-10-23 | System follow-ups: Stay-unlocked ping, change-log grouping with Undo all (`SystemChange.batch_id`), server-side search, range and person filters, dashboard failed jobs / Gold waiting / stale flag, undo links on save toasts, `SYSTEM_ENV_LABEL` setting. Plan hide/show endpoint removed (the Visible toggle in the row does it, logged). |
| 2026-10-23 | Moishe: System never locks while in use; it locks after N minutes without activity (also after leaving the site), N and the max sign-in hours editable in System Settings > Security (defaults 15 min, 12 h). One switch component for all on/off settings. |
| 2026-10-23 | Moishe: System keeps the save bar that appears only when there are unsaved changes (no always-visible Save button). Prices are plain money boxes, 2 decimals, no arrows. |
| 2026-10-23 | System audit log: every change and security event (sign-in, failures, unlock, lock, roles, undo, export) with who, IP, browser and a plain sentence; append-only and hash-chained (verify_audit_log); grouped, filterable, exportable. |
| 2026-10-23 | System dashboard: Run now for roll-up and snapshot; own last-run times. |

| 2026-10-23 | Moishe: the private secrets file moves to `SPA99_PRIVATE_DIR/Secrets/.env` (OneDrive, `Software Files/Secrets/.env`). The older `env/.env` is still read if Secrets/.env is missing. Load order unchanged. The project `.env` copy is removed so OneDrive is the one source on his Mac. |
| 2026-10-23 | Email (team recommendation, Moishe agreed): the website sends through **Amazon SES** (existing `notifications.backends.SesBackend`, server IAM role, no keys in env) from `hello@spa99.uk`, with production access requested once (no per-recipient verification). The `hello@spa99.uk` **mailbox stays in Microsoft 365** for receiving and replying (SES cannot be an inbox). DNS at go-live: SES domain verification + 3 DKIM records, one SPF record including both Microsoft and Amazon, DMARC. MX stays Microsoft. |
