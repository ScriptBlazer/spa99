# Feature: End-to-end run

Decided 2026-10-24 (PROJECT.md): instead of hundreds of tests, one run drives a real browser through the whole app like a person (front end and back end) with controlled data. Local only, not part of the live site or CI.

## What it does

`scripts/e2e.sh` makes a throwaway copy of the site, starts it, walks 24 scenarios with Playwright (Chromium) (nine user journeys, then fifteen beta-tester scenarios), writes a report with a screenshot of every step, and deletes the copy.

| # | Name | Covers |
|---|---|---|
| 1 | `visitor` | home, the spa, tour, the journey through to a suggested tier, privacy, terms; no console errors, no 5xx |
| 2 | `tier` | register interest in Tier 2, verification email link, sign in, `/account/` shows the tier, Book a visit opens |
| 3 | `gold_approved` | Gold application, approver email, one-tap approve link (Office sign-in first), invite email, new member is Gold on the dashboard |
| 4 | `gold_declined` | decline in the Office; declined state, not Gold, no account, no invite |
| 5 | `account` | change password, reset by email link, delete account, deleted account cannot sign in |
| 6 | `office_levels` | Office level sees but cannot approve, export or delete (buttons absent and direct requests answer 403); Admin exports the CSV and deletes a member but cannot approve; Approver approves; then `rebuild_metrics` and the Dashboard figures match the database |
| 7 | `system` | Developer unlocks System (password and lock code), changes a price, finds it in the audit log, `verify_audit_log` passes; an Admin is refused and gets 404 |
| 8 | `control` | every Control tab loads; every room card opens a panel with the right title; Back goes to the previous tab exactly once; a generated WAV is uploaded to the Library and deleted |
| 9 | `phone` | 375x812: home, journey start, register, `/account/` screens, Office dashboard, Control overview: no sideways scrolling |

### Beta-tester scenarios (10 to 24, `e2e/walks_beta.py`)

Decided 2026-10-24 (PROJECT.md): these try to break things, and expose bugs rather than adapt to them. Where a doc says what must happen, that is the assertion; where the docs are silent the assertion is the sensible behaviour (marked "judgement" below). A failing step here is a finding, not a test to loosen.

| # | Name | What it does | Expected |
|---|---|---|---|
| 10 | `beta_gold_declined` | A declined applicant signs in, registers a tier with the same email, applies again | Sign-in fails (no account); registering gives the tier, never Gold; the old application stays declined; re-applying gives one waiting application next to the declined one (judgement: the old application is backdated a day first, a real re-apply comes days later and the 2-minute double-click rule would otherwise swallow it); no approval or invite email ever. The decline email is undecided: the run only records which emails the applicant got |
| 11 | `beta_gold_links` | Approve link signed out, as Office level without Approver, twice, after a decline; invite link twice | Signed out: asked to sign in. Office level: 403. Second tap and second approve request: nothing happens, one approval, one invite email. After a decline: refused, stays declined. Invite link second time: 410, no password form |
| 12 | `beta_gold_duplicates` | The same email again, in CAPITALS, with spaces (within the double-click window) | One application, one email to the approver, one thank-you (judgement: a re-apply after the window is a "repeat", by design) |
| 13 | `beta_signup` | Same email twice, in other capitals; verify link twice; tampered link; sign in before verifying | One account; verify replay says "already confirmed"; tampered link 400 "not valid"; unverified members may sign in and see the confirm banner (register-interest.md) |
| 14 | `beta_passwords` | Reset for a known and an unknown email; reset link twice; 11 wrong passwords; forgot-password six times | Same words for both emails, no email to an unknown address; used link 400; the 11th wrong password is 429 "Too many attempts" and the right password is refused too; the 6th forgot-password is 429 (these two run on the strict server) |
| 15 | `beta_delete_reregister` | Tier member becomes Gold on the existing account, deletes the account, registers the same email again | Old Gold application gone; new account is a clean Tier 1, no Gold, old password refused |
| 16 | `beta_access` | Member, Office level, signed-out people on the Office, Control and System addresses | Plain 404 for members and for Office level on Control; System sign-in refused and pages 404; signed out: `/account/`, Office and Control show the sign-in page, System 404; a website session does not carry to the Office |
| 17 | `beta_gold_lock` | Gold member looks for, and forces, a tier change | No tier controls on any member screen; a direct and an injected POST change nothing |
| 18 | `beta_journey` | Refresh mid-way, Back, Forward, Start again, jump by address to the result and to the last screen | Progress and answers kept; no stuck loading; restart clears and stays cleared after a refresh; the result cannot be reached without the required answers (sent back to screen 1 with the hint) |
| 19 | `beta_bad_input` | Register and Gold apply with empty, bad email, bad mobile, 300-character name, emoji, `<script>alert(1)</script>` (also direct to the server) | Clear messages, nothing saved; emoji accepted; hostile text appears as plain text on the member dashboard, in the Office People list and person page, the Gold detail and confirm pages, and is escaped in the verify and approver emails; any alert/confirm/prompt dialog fails the walk-through. There is no contact form, so none to test |
| 20 | `beta_double_submit` | Double-click Register and Send; three simultaneous requests for each | Exactly one account or application (and one email) |
| 21 | `beta_counting` | Staff journey, Googlebot journey, then a normal visitor journey, with `rebuild_metrics` and the Dashboard | Staff and bot change nothing; the visitor adds exactly one started and one finished |
| 22 | `beta_system_refusals` | Wrong lock code and wrong password five times; negative, letter and oversized prices | Same refusal each time, System stays locked, five `unlock_failed` audit events, the audit chain verifies; bad prices answer 400 with a message and the price is unchanged |
| 23 | `beta_library_refusals` | Text file named .mp3, 1.5 MB WAV, a valid WAV into a full Library (strict server) | Refused with the app's messages in the page and by the server (415, 413, 413); nothing stored |
| 24 | `beta_emails` | Every email the run produced | Subject and both parts present, Reply-To set, no `{{`, `{%`, `{name}`, `None`, `[`, `TODO`, `undefined`, no greeting without a name; every link absolute and on the right host (approve and view links on the Office, everything else on the website); the key links are identical in the text and HTML parts; every link answers 200 or a redirect (a spent one-time link may answer 400 or 410). Run it last, with the others: alone it finds nothing |

The strict server: `scripts/e2e.sh` starts a second server (`e2e/settings_strict.py`) on the next free port, with the same database, mail and media, real (in-memory) rate limits and tiny Control Library limits (audio over 1 MB refused, a Library of about 2 KB). Only walk-throughs 14 and 23 use it; if it is not running they say "SKIPPED" and the rest still runs.

Every walk-through also ends with two checks: no HTTP 5xx and no console errors (browser errors or script errors) anywhere in it. The beta scenarios that make the site refuse things on purpose allow Chrome's own "status of 4xx" console lines; walk-throughs 19 and 20 add a third check, no JavaScript dialog opened. The first failed step ends that walk-through (the rest depend on it); the others still run.

About 25 accounts exist per full run: 4 team accounts made by the run (Office, Admin, Office + Approver, Developer) and members made through the real forms (register, Gold invite), named `beta-*@example.com` for the beta scenarios; several Gold applicants never become accounts. Aim: a full run under four minutes (not measured yet). Team accounts are the only ones made outside the site (`e2e/dbtool.py`, the same `apply_level` the Team screen uses).

## How to run

Once:

```
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
```

Then:

```
scripts/e2e.sh                      # everything
scripts/e2e.sh --headed             # watch the browser
scripts/e2e.sh --keep               # keep .private/e2e (database, emails, media, server log) afterwards
scripts/e2e.sh --only gold_approved # one walk-through by name (or number: --only 3, or several: --only 2,5)
scripts/e2e.sh --list               # names and numbers
```

Exit code is 0 only if every step passed. A summary prints in the terminal; the full report is `.private/e2e-report/index.html` (git-ignored, kept; also `results.json`, `server.log`, `setup.log` and `shots/`). Each run replaces the previous report.

## It never touches the dev database

- The workspace is `.private/e2e/` (git-ignored), deleted afterwards unless `--keep`. It holds the SQLite file, the media folder, the email folder, the server log.
- `scripts/e2e.sh` sets `DJANGO_SETTINGS_MODULE=e2e.settings`, `SPA99_SKIP_ENV_FILES=1` (the settings loader then reads environment variables only: no OneDrive `.env`, no project `.env`), `SPA99_PRIVATE_DIR` to the workspace, `DATABASE_URL=sqlite:///<workspace>/db.sqlite3`, an empty `SENTRY_DSN`, `Q_SYNC=1`, a test `SECRET_KEY` and `SYSTEM_UNLOCK_CODE`, and unsets the AWS and SMTP variables.
- `e2e/settings.py` is a second guard: it refuses to start unless the database is a SQLite file inside `E2E_WORKSPACE`, whatever the environment says. It also sends email to files (`EMAIL_FILE_PATH`, read back by `e2e/mailbox.py` to follow verify, approve, invite and reset links) and stores media in the workspace.
- Seed data is the minimum the site needs: `migrate`, `setup_roles`, `seed_phase1`, `register_schedules`. No fake bulk data.
- The server is `runserver --noreload` on `127.0.0.1` at the first free port from 8765. The four hosts are `localhost`, `office.localhost`, `control.localhost`, `system.localhost` (Chromium resolves `*.localhost` to this Mac).

## Deliberate differences from the real site

- Rate limits are off on the main server (`e2e/settings.py` uses a dummy cache): one robot IP signs in far more often than a person. They are proven on the strict server instead (walk-through 14).
- Background jobs run inline (`Q_SYNC=1`), so emails exist as soon as the page answers.
- Dev settings (DEBUG on, static files from source), not the production Docker and Caddy setup.

## Where the app differs from the brief (checked, not assumed)

- Declining sends no email, by design ("He will not be invited"). Walk-through 4 checks the applicant got only the thank-you email and no approval or invite.
- The Gold "approval email" is the invite email ("Your Spa 99 Gold Card is approved"); the new member sets a password from it.
- The member screen is named **Book** in the tabs; its page title is "Book a visit".
- The Dashboard figures are stored snapshots. Walk-through 6 runs `rebuild_metrics` (and `--dry-run` must report 0 differences) before comparing the Registered interest ring and Gold waiting to the database.
- Walk-through 6 uses a direct POST with a valid CSRF token as the "refused" proof. Both a CSRF failure and a permission failure answer 403 here, so the same direct request is also made as the Approver and must succeed (302).

## Files

`scripts/e2e.sh` (workspace, server, run, cleanup), `e2e/settings.py`, `e2e/run.py` (runner), `e2e/walks.py` (walk-throughs 1 to 9), `e2e/walks_beta.py` (10 to 24), `e2e/settings_strict.py` (the second server), `e2e/kit.py` (steps, screenshots, error collection, sign-in, register, journey, Gold helpers), `e2e/mailbox.py` (also reads each part of an email and counts by subject), `e2e/dbtool.py` (team accounts and database facts, including Gold history, invites, audit events and ageing an application, in a child process because Playwright's sync API blocks Django's database calls), `e2e/report.py`. `requirements-dev.txt` adds `playwright`.

## Not verified at build time

Walk-throughs 10 to 24 were written in a sandbox that cannot start Chrome. Their server-side expectations (status codes, refusals, emails, escaping, limits, audit events, the strict server settings, the email checks on real emails, `scripts/e2e.sh` starting both servers) were proven without a browser through Django's test client and the email reader; the clicks and selectors were written against the real templates and scripts and have not run. Expect some selector tuning on the first real run.
