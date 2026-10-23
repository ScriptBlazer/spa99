# Office counting rules (the one source of truth for every Office figure)

Decided 2026-10-23 (PROJECT.md). Replaces every earlier counting approach in `office.md` where they differ. Every figure on Dashboard and Analytics follows these rules; nothing else.

## C1. What a "person" is

- **Known person:** once someone registers or signs in, all their journeys belong to their account. One account = one person.
- **Anonymous person:** one browser. The journey already keeps an essential first-party cookie (needed to save progress). A restart in the same browser keeps the same person: the new journey session stores the first session's `person_key` (carried over on restart). No new cookie, no IP.
- Different devices or browsers before sign-in count as different people. That is the honest limit without tracking; it is said in the Office help text.
- When a session gets linked to an account, its person becomes the account (counts merge from then on, also in rebuilds).

## C2. Who is never counted

Bots (`is_bot`), the staff hosts (Office, Control, System), and journeys by staff accounts (`is_staff`).

## C3. The figures

| Figure | Counts | Source (rebuildable?) |
|---|---|---|
| Visitors | Unique per day: salted daily hash of IP + browser, never stored, wiped daily. A range shows the sum of daily uniques ("unique visitors per day"). Everyone who starts the journey that day is counted as a visitor too | Visitor counter (not rebuildable) |
| Started the journey | People (C1) with a journey started in the range | `JourneySession` (yes) |
| Finished the journey | People with a journey finished in the range | `JourneySession` (yes) |
| Registered interest | Registrations created in the range (one per account) | `InterestRegistration` (yes) |
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
