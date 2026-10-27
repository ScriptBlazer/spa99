# Office: Leads, the person page and lead figures

Decided 2026-10-26 (PROJECT.md last row). Look: `docs/design/OFFICE-LEADS.md`. Counting: `office-counting-rules.md` (C1 to C5 still rule every figure). Permissions: `user-rules.md` U3.

## Words

A **lead** is one lower-cased email address given at the journey gate (`JourneySession.lead_email`, with `lead_at` and `lead_privacy_version`). **Registered** = that address has an account. Staff addresses and bot sessions are never leads (C2).

## Linking (journeys and Gold applications follow the email)

- `users.services.link_earlier_data(user)` runs when an account's email is **verified** (`verify_email`), and when a Gold invite creates a verified account. It links every `JourneySession` with `lead_email__iexact = account.email` and `user IS NULL` (any browser, any case), and every unowned `GoldApplication` with that email. Sessions already linked to anyone are never taken. Idempotent. One save per session, so history records the link. The log line has counts and the account id only.
- Registering alone proves nothing: it still links only the same browser's session (as before) and the Gold applications (as before). Other browsers' leads wait for the verify.
- A visit that leaves the address of an existing, already verified account is not linked (nobody proved it was him). The account's person page shows these under `unlinked_journeys`; they count as the email person (C1).
- If an account later **changes its email** (no such flow exists yet), old leads are not re-linked silently; only a new verification of the new address links what was left with it.
- After linking, `snapshots.request_refresh()` queues the debounced refresh (C5), so the person counts once. `save_lead` also requests a refresh (a new lead moves the figures).
- Counting (C1, 2026-10-27): the same email is one person before and after registering; see `office-counting-rules.md`.

## Stored figures (nothing computed on page load)

Built by the snapshot job from `insights.people.Figures` (new fields: `leads`, `lead_votes`, `registered_emails`).

- Dashboard snapshot keys (per range): `leads_new` (leads whose first `lead_at` is in the range), `leads_new_previous`, `leads_registered` (those whose address has an account now), `hot_leads` (current count), `insights_leads` (same shape as `insights`; one vote per lead that has not registered, from the latest finished journey in the range).
- A new snapshot page `leads` for ranges 7d, 30d, 90d, all: `leads_new`, `leads_registered`, `registered_share_bp`, `hot_leads`, `leads_total` (unfiltered, current leads). Read with `selectors.leads_summary(range)`.
- Short live lists on the Dashboard (LIMIT reads, in `dashboard()`): `hot_lead_rows` (5) and `activity` (10: lead given, registered, verified, journey finished, Gold applied, Gold approved or declined; `{kind, at, who, label, detail, href}`).
- Dashboard query bound in tests raised from 20 to 30 (it is fixed, and the test still proves it does not grow).

## Leads list `/leads/` (Office level and up)

One row per address, driven by that address's latest session (DB-side `Exists` and `Subquery` over `Lower(lead_email)`; no Postgres-only functions; `nulls_last` ordering is portable). Filters (URL): `q` (part of the address), `range` 7d/30d/90d/all (by last seen, default 30d), `show` lead (default) / registered / all, `tier`, `potential`, `industry`, `gold=yes`, `sort` last_seen / first_seen / potential / visits, `page` (25 a time, one extra row fetched, no count). The count line comes from the snapshot only when no filter is on. Row keys: `id` (opaque), `email`, `first_seen`, `last_seen`, `journeys`, `tier`, `potential`, `score`, `industries`, `answers`, `summary` (two lines), `source{host,utm_*,label,campaign,device}` (first visit), `status` (lead, registered, applied, gold), `registered`, `account_id`, `gold_applied`, `unsubscribed` (the address is on `EmailOptOut`, or its account has `marketing_consent` off; the list labels it "Unsubscribed" under the address, nothing is hidden), `href`.

`/leads/export.csv` (same filters): Admin and up (403 below). The export is logged (account id, never the addresses).

## Lead and person pages

- `/leads/<session id>/`: the id of any of his sessions (opaque UUID; never the address). Unknown id, a session without an address, or a bot: 404. If the address has an account now it redirects to `/people/<account>/`. Context `person` = `office.profile.lead_profile`. `/leads/<id>/export/` (JSON, Admin+) and POST `/leads/<id>/delete/` (Admin+) clear the address from his journeys with `journey.services.erase_lead` (answers stay without it; Gold applications are not touched).
- `/people/<id>/`: `lists.person_detail` keeps its old keys and adds `profile.account_profile`.
- Shared keys in `person`: `journeys[]` (every answer: `answers[{key, question, options, text, skipped, display, answered_at}]`, suggested plan and reasons, Gold potential, score and reasons, source, lead email and consent), `tier{suggested, picked, match, ...}`, `gold{potential, score, reasons, applications[{..., events[]}]}`, `source`, `consent{lead[], account, unsubscribed, gold[]}` (`unsubscribed` is true when any of the person's addresses is on `EmailOptOut`, so it works for a lead with no account; the Consent card shows "Unsubscribed" in Marketing emails), `timeline[]` (newest first; kinds journey_started, lead_given, journey_finished, registered, verified, plan_changed, marketing_changed, gold_applied, gold_event, email). Account only: `unlinked_journeys[]`.
- The view adds `timeline_days` (grouped by day, 20 events), `timeline_more`, `timeline_next`; `?tl=N` with HTMX returns only `_timeline.html`.

## GDPR

`export_user_data` already included lead sessions by email; after linking they carry full answers. `delete_user_data` anonymises linked sessions and clears the address everywhere (`erase_lead`). `manage.py lead_data` is unchanged.

## Choices made

- No `Lead` table and no event table (the brief suggested them): the list and timeline read the existing tables. Trade-off: `Lower(lead_email)` is not indexed, so very large lead tables would want a stored lower-cased column or a `Lead` model later (that would need a backfill script with a dry run, never a migration).
- No migration was needed (`OfficeSnapshot.page` is free text).
