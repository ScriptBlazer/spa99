# Office counting rules (the one source of truth for every Office figure)

Decided 2026-10-23 (PROJECT.md). Replaces every earlier counting approach in `office.md` where they differ. Every figure on Dashboard and Analytics follows these rules; nothing else.

## C1. What a "person" is

A journey session's person is the first that applies (decided 2026-10-27: the same journey email is always one person, also before he registers):

1. **Account:** the session is linked to a user, or anything connected to it is (see the connection rule below): its browser (`person_key`), its email, another browser that left the same email, another email left in the same browser. One account = one person. Linking happens when the email is verified; counts merge from the next snapshot, also in rebuilds.
2. **Email:** else, if the session left an email at the gate, the lower-cased address, whatever the browser. A session in the same browser that left none (for example one that started before the email was given) belongs to that email too. An address that belongs to an account but whose sessions are not linked (not verified yet) still counts as the email, not the account: nothing merges without a proven link.
3. **Browser:** else one browser (`person_key`). The journey keeps an essential first-party cookie (needed to save progress); a restart keeps the same `person_key`; "Not you? Use another email" on the result starts a new person (new `person_key`, no email carried), so a shared laptop counts two. With the journey email switch off nobody gives an email, so people count by browser (rule 3) and finishers do not appear as Leads. No new cookie, no IP.

- **Connection rule:** browsers and emails are joined (union-find in the snapshot job): a browser is joined to every email left in it, an email to every browser that left it. Everything connected is one person, and if any linked journey is in the group the person is that account (the latest link wins if there are several accounts). So two different addresses left in one browser are one person (one browser was always one person).
- A group whose email is a staff address is not counted.
- Different devices or browsers that never gave an email count as different people. That is the honest limit without tracking.

## C2. Who is never counted

Bots (`is_bot`), the staff hosts (Office, Control, System), and journeys by staff accounts (`is_staff`).

## C3. The figures

| Figure | Counts | Source (rebuildable?) |
|---|---|---|
| Visitors | Unique per day: salted daily hash of IP + browser, never stored, wiped daily. A range shows the sum of daily uniques ("unique visitors per day"). Everyone who starts the journey that day is counted as a visitor too | Visitor counter (not rebuildable) |
| Started the journey | People (C1) with a journey started in the range | `JourneySession` (yes) |
| Finished the journey | People with a journey finished in the range | `JourneySession` (yes) |
| Registered | Registrations created in the range (one per account) | `InterestRegistration` (yes) |
| Answers (facility, time, how often, who with) | One vote per person: each person's latest finished journey in the range | `JourneySession` answers (yes) |
| Suggested tier | Same: each person's latest finished journey | `JourneySession` (yes) |
| Picked tier | Registrations in the range by plan; denominator = all registrations in the range | `InterestRegistration` (yes) |
| Where people come from | Referrer site of visitors (host only) | Visitor counter (not rebuildable) |
| Drop-off by screen | Journey sessions (this one is about screens, not people) | `JourneySession` (yes) |

Started ≥ Finished always (same people). Registered can exceed Finished (someone can register without the journey); the funnel then shows its note instead of a fake percentage.

## C4. Time

- A day is a London day. "7 days" = today and the 6 days before. The previous period is the same length just before it.
- A person is counted in a range if the event (start, finish, registration) happened in it.

## C5. Where the numbers live (Moishe's rule: nothing calculated on page load)

- A background job (the hourly roll-up, plus a debounced refresh queued after each counted event) works out every figure from the source tables using C1-C4 and saves one **snapshot per page and range**. All figures on a page come from the same snapshot, so they always agree.
- Pages read one stored row (plus the two short "waiting" and "latest" lists). No sums, no counts at request time. Tests prove the query count does not grow with data.
- `rebuild_metrics` rewrites every snapshot from the source tables (visitors and referrers excepted).

## Leads (2026-10-26)

A lead is an email given at the journey gate; "new leads" counts addresses by the day of their first `lead_at`, "went on to register" counts those whose address has an account now. Journeys with that email join the account when the email is verified (see `office-leads.md`); counts merge from the next snapshot.

People are worked out in `insights/people.py` by the snapshot job only; run `rebuild_metrics` once to apply the 2026-10-27 rule to existing snapshots.
