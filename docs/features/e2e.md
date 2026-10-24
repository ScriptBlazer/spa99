# Feature: End-to-end run

Decided 2026-10-24 (PROJECT.md): instead of hundreds of tests, one run drives a real browser through the whole app like a person (front end and back end) with controlled data. Local only, not part of the live site or CI.

## What it does

`scripts/e2e.sh` makes a throwaway copy of the site, starts it, walks nine user journeys with Playwright (Chromium), writes a report with a screenshot of every step, and deletes the copy.

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

Every walk-through also ends with two checks: no HTTP 5xx and no console errors (browser errors or script errors) anywhere in it. The first failed step ends that walk-through (the rest depend on it); the others still run.

About 10 accounts exist per full run: 4 team accounts made by the run (Office, Admin, Office + Approver, Developer) and 6 members made through the real forms (register, Gold invite); two Gold applicants never become accounts. Team accounts are the only ones made outside the site (`e2e/dbtool.py`, the same `apply_level` the Team screen uses).

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

- Rate limits are off (`e2e/settings.py` uses a dummy cache): one robot IP signs in far more often than a person. Rate limits are not covered here.
- Background jobs run inline (`Q_SYNC=1`), so emails exist as soon as the page answers.
- Dev settings (DEBUG on, static files from source), not the production Docker and Caddy setup.

## Where the app differs from the brief (checked, not assumed)

- Declining sends no email, by design ("He will not be invited"). Walk-through 4 checks the applicant got only the thank-you email and no approval or invite.
- The Gold "approval email" is the invite email ("Your Spa 99 Gold Card is approved"); the new member sets a password from it.
- The member screen is named **Book** in the tabs; its page title is "Book a visit".
- The Dashboard figures are stored snapshots. Walk-through 6 runs `rebuild_metrics` (and `--dry-run` must report 0 differences) before comparing the Registered interest ring and Gold waiting to the database.
- Walk-through 6 uses a direct POST with a valid CSRF token as the "refused" proof. Both a CSRF failure and a permission failure answer 403 here, so the same direct request is also made as the Approver and must succeed (302).

## Files

`scripts/e2e.sh` (workspace, server, run, cleanup), `e2e/settings.py`, `e2e/run.py` (runner), `e2e/walks.py` (the nine walk-throughs), `e2e/kit.py` (steps, screenshots, error collection, sign-in, register, journey, Gold helpers), `e2e/mailbox.py`, `e2e/dbtool.py` (team accounts and database facts, in a child process because Playwright's sync API blocks Django's database calls), `e2e/report.py`. `requirements-dev.txt` adds `playwright`.

## Not verified at build time

Playwright could not be installed where this was written, so the browser steps were written against the real templates and scripts but had not been run. The setup, settings guard, server start, email reading and cleanup were run. Expect to tune a few selectors on the first real run; the report names the failing step and attaches its screenshot.
