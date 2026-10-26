# Feature: Privacy notice and Terms of use

Branch `feature/legal-pages` (2026-10-23). Apps: `content` (text, renderer), `pages` (`/privacy/`, `/terms/`), `plans` (privacy version).
Not legal advice: a solicitor must review both texts before launch (see Launch blockers).

## How it is built

- **Copy is data.** Both pages are `content` rows (pages `privacy` and `terms`). The first version lives in `content/legal.py`; `seed_phase1` creates the rows on a new install and `backfill_site_data` (`--dry-run` first) writes them on an existing one. After that, edit the rows in Control, never the file. Run `backfill_site_data` on live after deploy.
- **Rows:** `body` (title + intro), `updated` (the date shown, "26 October 2026"), `part_1` ... `part_N` (numbered parts, in order; each becomes a Contents entry and an anchor from its heading), `contact`. Privacy also has `ico` and `hosting` (empty until known).
- **Body format** (`content/legal.py` docstring, rendered by `content/legal_render.py`, tag `{% legal_text %}`): a line is a paragraph; `- ` a list item; `### ` a small heading; `[words](/path/)` a link (only `/`, `https://`, `mailto:`); `{contact}` the contact email from Site settings (`SiteSettings.contact_address`, never typed in the text); `{opening}` the opening time; `{version}` the privacy version; `{ico}` / `{hosting}` the fill-later rows. Everything typed is escaped.
- **Fill-later values:** while `ico` or `hosting` is empty, dev (`DEBUG`) shows a dashed red marker, e.g. "[ICO registration number — to add before launch]". Live never shows a marker: a line with `({hosting})` loses the brackets, a line where the token stands alone (the ICO sentence) is left out.
- **Privacy version:** `SiteSettings.privacy_version` is now `2026-10-26` (model default and backfill, which changes it only while it is still `draft-1`). It is stored on each person who accepts the notice (`User.privacy_accepted_version`, `GoldApplication.privacy_accepted_version`) and shown on the page ("Version 2026-10-26"). Existing records keep `draft-1`, which is correct: that is what they accepted. When the notice changes in a way people should accept again, change both the `updated` row and the version (hidden admin, Site settings).
- **Design:** one reading column at `--measure`; title group reveals (7B hero), long text never animates. Phone: an open, collapsible Contents list, then the parts. Desktop (64em): article centred, Contents a sticky left rail; `legal.js` marks the part being read (`aria-current`, one IntersectionObserver). Print: header, footer and Contents hidden, link addresses printed. Existing tokens only, no new ones.
- **Tests:** `pages/tests/test_legal.py`.

## Sources of each statement (Privacy notice)

| Statement | Source |
|---|---|
| Controller, company number, office, BML Group | PROJECT.md 2026-10-23 (legal owner); PROJECT.md section 1 |
| Browsing collects nothing identifying; visitor counter (daily salt, one-way hash, no IP or UA stored, wiped next day, referrer host only) | `insights/visitors.py`, `insights/rollup.py` (deletes `VisitorHash`/`VisitorSalt` older than today), `office-counting-rules.md` C3 |
| Journey answers, saved from the first tap, typed text | `journey/seed.py` (questions incl. `industry_other`, `heard_via_other`), `journey.md` |
| Journey context: referrer (up to 500 chars), UTM tags, device type, timings | `journey/models.py` `JourneySession`, `journey/services.py` `create_session` (user agent only turned into a device type, not stored) |
| Account fields, hashed password, men-only, privacy version, marketing consent, account ID, verification | `users/models.py`, `users/forms.py` (mobile required), `register-interest.md` |
| Sign-in records with IP and browser | `common/models.py` `LoginEvent` |
| Gold application fields, rating, decision, invite (14 days, single use) | `gold/models.py`, `gold/invites.py` `INVITE_DAYS`, `gold-application.md` |
| Email records | `notifications/models.py` `EmailLog` |
| Team activity with IP and UA | `system/models.py` `SystemChange`, `SystemEvent`; `system.md` |
| Lawful bases | Proposed by us from the purposes above (solicitor to confirm) |
| Rating never decides alone | Approval is a person's action (`gold-application.md`, Approve button) |
| Marketing by consent, change in My Spa 99 | `POST /account/emails/` (`member-dashboard.md`) |
| Rate limits use the IP briefly (cache, hashed key, minutes) | `common/ratelimit.py`; covered by "limits on repeated attempts" |
| Cookies: `csrftoken` (1 year, Django default), `sessionid` (2 weeks, Django default; Office/System sign-ins have their own limits), `messages` (Django default message storage, browser session), `spa99_journey` (1 year, HttpOnly, removed on sign out) | `config/settings/base.py`, `journey/views.py` `COOKIE_MAX_AGE`, `users/views.py` `_forget_journey_cookie` |
| Gold form kept in the browser tab (sessionStorage) | `common/static/common/js/gold-apply.js` |
| No analytics or marketing cookies, no browser Sentry | grep of the codebase; `foundation.md` ("Server side only: no browser SDK") |
| Processors: AWS S3 + SES (London, `eu-west-2`), Sentry (no PII by design), Microsoft 365 mailbox | `README.md` env table, `AWS_SES_REGION_NAME`, `foundation.md` Sentry section, PROJECT.md 2026-10-23 email decision |
| Sentry reports: no names, emails or IPs (scrubbed, `send_default_pii=False`), but the user id (account's internal number) and the User-Agent header are sent | `common/observability.py`, `foundation.md` Errors and Sentry |
| Change history (earlier versions of account, registration, Gold application; password excluded) | `django-simple-history` on every model (PROJECT.md stack); `users/models.py` `excluded_fields=["password"]` |
| Erasure removes the change history: User, InterestRegistration and GoldApplication history rows are deleted; JourneySession and Answer history are anonymised (user, key, person key, referrer, typed text cleared) | `users/services.py` `delete_user_data`, `_anonymise_sessions`; `gold/services.py` `delete_applications` |
| What happens without the details (Art. 13(2)(e)): journey optional, registration and Gold need the form's fields, news optional | `users/forms.py`, `gold/forms.py` |
| Tour display choices in sessionStorage (`tour-low`, `tour-tilt-no`, `tour-hint`) | `common/static/common/js/tour/engine.js` |
| Team sign-ins up to 30 days | `OFFICE_SESSION_AGE` (System: 12 hours) |
| Sentry stores in the EU | Brief from Moishe (foundation: EU region). Confirm the Sentry organisation was created in the EU region |
| Gold applications emailed to the approver list (may work for BML Group) | `SiteSettings.gold_approver_emails`, `gold/tasks.py` |
| Self-service export (includes Gold score, reasons, consents, internal notes when present; journey suggestion detail, all UTM tags, Gold score, finish time) and delete, what delete removes, journeys anonymised | `users/services.py` `export_user_data`, `delete_user_data`; `account_you.html` |
| ICO contact (ico.org.uk/make-a-complaint, 0303 123 1113) | ICO public details |

Terms of use: company facts as above; men-only and 18+ (`MINIMUM_AGE`, ACC-08/09; the register form's "Our policy" link points here); no payment in Phase 1 (PROJECT.md section 3); Gold by approval, no account until approved, 14-day single-use link (`gold/invites.py`); images are renders and the tour is illustrative (BRAND.md section 5); liability wording is standard UK consumer wording (Consumer Rights Act 2015 does not allow excluding death/injury by negligence or fraud).

## Proposals (for Moishe and the solicitor; not built)

Retention periods in the notice are **proposals**. Nothing deletes on these schedules yet. Before launch, either build the clean-up jobs or change the text:

| Data | Proposed | Today in code |
|---|---|---|
| Account | While kept; unused 3 years: write, then delete | Kept until the person deletes it |
| Account with email never confirmed | 90 days | Kept |
| Journey answers with no account | 2 years, then deleted | Kept forever |
| Gold applications not approved | 1 year after the decision | Kept |
| Sign-in records (`LoginEvent`) | 1 year | Kept |
| Email records (`EmailLog`) | 2 years | Kept |
| Emails in the Microsoft 365 mailbox | 2 years after last contact | Mailbox policy not set |
| Visitor counter hashes and salt | Next day | Built (roll-up) |
| Sentry error reports | 90 days | Sentry plan default; set it in Sentry |
| Change history (simple-history rows) | 2 years, or until the account is deleted | Kept forever; erased with the account. Needs a pruning job (e.g. `django-simple-history`'s `clean_old_history --days 730`) |
| Team activity (`SystemChange`, `SystemEvent`) | 2 years | `SYSTEM_AUDIT_RETENTION_DAYS=0` keeps forever; set `730` and schedule `prune_audit_log` |
| Journey email (`JourneySession.lead_email`, the gate before the suggestion) | 2 years after given, or until unsubscribe / withdrawn consent / registration | Not enforced yet: needs a clean-up job; export and erase by hand with `manage.py lead_data` |
| Backups | Replaced within 35 days | Live backups not set up yet (local script keeps 30) |

Other proposals:
- **Hosting provider:** the notice names it through the `hosting` row (live shows "Website hosting: the servers ..." until filled). PROJECT.md says an AWS instance; if that stays, fill in "Amazon Web Services" and consider merging the two AWS lines.
- **Where it is kept:** the notice says the Amazon services run in London. If the database host is outside the UK, add a sentence.
- **Microsoft 365:** may process data outside the UK; the notice covers this with the general safeguards sentence. Check the tenant's data location.
- **Re-acceptance:** the notice promises an email when a change matters. There is no "accept the new version" step on sign-in; build one if the solicitor wants it.
- **Profile edits:** members cannot edit their name or mobile themselves yet; the notice routes correction requests to the contact email.

## Update 2026-10-26 (version `2026-10-26`)

- Address in both texts is now "BML House, 99c Vale Road, London N4 1PR".
- Privacy: the journey email gate (email + answers linked to it, consent tick, basis consent, withdraw by unsubscribe link or contact address, two-year retention row, erased with the account or by `lead_data`), and one line that the team may email Gold applicants with questions (the Respond emails, also in the Gold data list and logged as emails).
- Text and version are new in `content/legal.py` and the model default (migration `plans/0019`). New installs get them from the seed; the local DB was updated once through the models in a shell. Existing live rows would need the same one-off (live starts clean). Older acceptances keep `2026-10-23`.
- The solicitor still has to review the text (open item 3 below), including the two-year journey-email period. The unsubscribe link in emails is not built yet (the notice describes it, so build it before the first marketing email).

## Launch blockers

1. **ICO registration number:** done 2026-10-26: BML Spa 99 Limited, ZC284282 (in the seed and the privacy `ico` row). Hosting: "Amazon Web Services, London region" (2026-10-26).
2. **Hosting provider name:** fill the privacy `hosting` row once chosen.
3. **Solicitor review** of both texts, the lawful bases and the retention periods.
4. **Retention:** build the clean-up jobs for the proposed periods (including the change history), or change the text to what is true.
5. **Sentry:** confirm the EU region, "Prevent storing of IP addresses" on, and 90-day retention.
6. Run `backfill_site_data` on live after deploy (writes the text and the privacy version).
