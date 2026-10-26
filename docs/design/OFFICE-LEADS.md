# Spa 99 Office: Leads, richer person page, richer dashboard (design brief)

Decision: PROJECT.md row 2026-10-26 ("tie every answer to that email … The Office gets much more detail Barry can use"). Look: `docs/design/OFFICE.md` (light Office, round 2) applies in full; this brief only adds. Rules that bind every line below:

- **C5** (`docs/features/office-counting-rules.md`): every *figure* (a count, a share, a top answer) comes from the stored snapshot for that page and range. *Lists* (rows of people or events) may query, paged and indexed. Nothing is summed on page load.
- **U2/U3** (`docs/features/user-rules.md`): Office level sees everything here and acts on nothing. Export CSV, "Export his data" and delete are Admin and up, checked on the server; the buttons are not rendered below Admin.
- **BRAND.md**: tokens only, never a one-sided border, stripe or side shadow. Leads, People and Gold pages use brand colours on the light shell (OFFICE 7). The Dashboard may use the data palette (OFFICE 2.2).
- **Journey** (`docs/features/journey.md`): a lead is a `JourneySession.lead_email` (with `lead_at`, `lead_privacy_version`). When the same address registers, everything attaches to the account and he stops being a lead.

Design read: a calm daylight ledger. Barry should be able to open one person and know, in ten seconds, what he wants, how warm he is and how he found us. Dials: variance 3, motion 3, density 5 on lists (phone 4), 4 elsewhere.

**No new colour tokens.** Everything reuses `--office-*` and brand tokens. Proposed additions are layout values only, marked **proposed** in section 6.

---

## 1. Words

| Term | Meaning on screen |
|---|---|
| **Lead** | Someone who gave his email at the journey and has no account. Shown by his email |
| **Registered** | Has an account (registered interest). Shown by his name |
| **Applied Gold** | Has a Gold application (with or without an account), not yet decided |
| **Gold member** | Approved Gold application |
| **Hot lead** | A lead with High Gold potential, no account, no Gold application |
| **Went on to register** | Leads from the range whose address now has an account |

Status pill (one per person, the furthest he has gone): Lead → Registered → Applied Gold → Gold member. A declined application shows Registered (or Lead) as the status and "Declined" on the Gold card only.

### 1.1 Status pills (new badge modifiers, existing `.o-badge` shape)

Text first, colour second. Figtree 600 `--office-text-xs`, 22px pill.

| Status | Look | Contrast |
|---|---|---|
| Lead | `--office-surface` fill, full 1px inset ring `--color-control-line`, espresso text | 12.19 |
| Registered | `--office-sunken` fill, espresso text | 10.13 |
| Applied Gold | Espresso fill, gold text | 6.17 |
| Gold member | Gold fill, espresso text | 6.17 |

Class names: `.o-badge--st-lead`, `--st-registered`, `--st-applied`, `--st-gold`. Potential badges stay as OFFICE 7.5 (High gold fill, Medium caramel tint, Low sunken). Where a row shows both, the potential badge always carries the word ("High potential", `.o-badge-ctx` visible) except in the desktop table, where the column head names it.

### 1.2 Key answers summary (one formatter, used in the Leads list, Hot leads, timeline and journeys list)

Two short lines, never a sentence:

- Line 1, time and frequency: "Evenings, late night · 2-3 a week". Short names: Early, Daytime, Evenings, Late night; Weekly, 2-3 a week, Most days, Now and then.
- Line 2, what and who: "Sauna, cold plunge, gym +2 · Alone". First three facilities in journey order, then "+N". Company: "Alone" or "With a friend".
- A skipped question is left out; a journey with no answers yet reads "No answers yet".
- Retired options keep their old label (journey rule).

---

## 2. Dashboard additions

Keep every existing card. Add three cards and one toggle. The range picker (Today · 7 days · 30 days) drives the new figures too.

### 2.1 Layout at 1440 (12 columns)

1. Greeting (unchanged).
2. The journey (8) | Gold waiting (4) (unchanged).
3. **Leads** (4) | **Hot leads** (8). *New row.*
4. What people want (12), now with an **Everyone · Leads** toggle.
5. Waiting for you (7) | Latest registrations (5) (unchanged).
6. **Recent activity** (7) | Site visitors over Page views, stacked (5).

Row 6 moves the two stat tiles down and stacks them in five columns; their content is unchanged (number, change line, sparkline). People come before traffic, because people are what Barry acts on.

### 2.2 Layout at 375 (one column, this order)

Range picker; greeting; The journey; Gold waiting; Waiting for you; **Leads**; **Hot leads**; **Recent activity**; What people want; Site visitors; Page views; Latest registrations.

### 2.3 Leads card (figures, from the snapshot)

`.o-card`, title "Leads" (`.o-h3`). Two stacked blocks separated by `--space-4` (no rule):

- **New leads.** Number Signika 500 `--office-stat` espresso, tabular. Under it "gave their email" (`--text-sm` espresso 500), then the change line (count wording, OFFICE 10: "+5 on last week", "Same as yesterday").
- **Went on to register.** Number `--text-xl` Signika 500, then muted "of 14 leads have registered". Under it a 10px pill bar, clay on `--office-clay-track`, length = registered / leads (same build as the old funnel bar, `scaleX`, min 6px). No percent on the Dashboard (OFFICE rule 4 and section 10); the percent lives on the Leads page (3.2).
- Quiet link at the bottom: "See all leads" to `/leads/?range=<current>`.

Colours: the lead mark is teal (leads are the people who finished the journey without an account), the registered bar clay. No new hue.

Empty (0 leads in range): number "0", line "No new leads in this range.", the second block hidden.

Cohort rule (for the backend): "went on to register" counts leads whose `lead_at` is in the range and whose address has an account now. Stored in the snapshot as `leads_new`, `leads_new_previous`, `leads_registered`.

### 2.4 Hot leads card (a short list, may query)

`.o-card` with `.o-card-head`: "Hot leads" + `.o-count` (gold fill) with the stored `hot_leads` count. Up to five rows, newest first, using the `.o-latest-row` pattern (64px, 14px radius, sunken on hover, no rules):

- Left top: the email, Figtree 600 espresso, one line, ellipsis.
- Left bottom (muted `--text-sm`): "Suggested Tier 2 · Property, developer".
- Right: High potential badge over muted relative time ("2 days ago").
- Whole row links to his person page.

Footer quiet link: "See all hot leads" to `/leads/?potential=high&status=lead`. Shown when the count is over 5.

Phone: same rows; the badge moves under the email line to keep the email readable.

Empty: "No hot leads right now. They appear when someone with a strong Gold profile leaves his email."

No action buttons (Office level is view only, and contacting leads is not decided; see 7).

### 2.5 Recent activity card (a short list, may query)

Title "Recent activity". Not tied to the range: always the latest ten events. Rows 52px, 4px apart, 14px radius, sunken on hover, whole row links to the person:

- A 28px `--office-sunken` disc with a 16px line icon for the event type (from `_icons.html`; espresso).
- Text, one line on desktop (wraps to two on phone): subject in Figtree 600, then the event in Figtree 400, then at most one muted detail after a middle dot.
- Right: muted relative time, tabular ("12 min ago", "Yesterday, 18:40").

Subject: his name with the surname initial if he has an account ("Daniel R."), otherwise his email.

| Event | Copy |
|---|---|
| Lead | "d.rowe@mail.co gave his email · Suggested Tier 2" |
| Registered | "Daniel R. registered · Tier 3" |
| Verified | "Daniel R. confirmed his email" |
| Gold applied | "Daniel R. applied for Gold · High potential" |
| Gold approved | "Daniel R. was approved for Gold · by Barry" |
| Gold declined | "Daniel R. was declined for Gold" |
| Plan changed | "Daniel R. changed plan · Tier 2 to Tier 3" |
| Came back | "d.rowe@mail.co came back and finished the journey again" |

Footer: nothing (the person pages hold the full history). Empty: "Nothing has happened yet."

The rows refresh with the HTMX range swap only because they live in the same response; there is no polling and no live ticker.

### 2.6 What people want: Everyone · Leads

Add a small segmented control (`.o-seg .o-seg--sm`, two items, 40px hit area) at the card's top right, left of the plus. "Everyone" is today's view. "Leads" swaps the same tiles and the open list to the leads-only facts (stored in the snapshot as `insights_leads`, same shape as `insights`, one vote per lead). Swap is the existing 240ms text cross-fade; the bars morph as on a range switch.

Empty for Leads: "Facts appear once leads finish the journey."

---

## 3. Leads list (new page)

Route `/leads/`, nav item **Leads** between People and Gold, line icon "envelope" (new symbol in `_icons.html`, same 1.5 stroke). Phone tab bar becomes five tabs (75px each at 375, still over 44px); labels: Dashboard, Analytics, People, Leads, Gold. Office level and up see it.

One row per email address (not per journey).

### 3.1 Layout

Same skeleton as People (`people.html`): `.o-filters` bar, `.o-totalline`, `.o-tablecard` with `.o-list`, phone cards, bottom sheet for filters, "Show more" paging. New things are the summary strip and the two-line cells.

**1440, top to bottom**

1. Summary strip (3.2), three tiles in a row.
2. Filter bar (3.3).
3. Total line: "312 leads" (stored counter, unfiltered) or, when filtered, "Filtered" + "Clear". No filtered count (it would be a sum on page load).
4. Table card (3.4). 25 rows, then "Show more".

**375**

Summary tiles as a horizontal row of three compact tiles (number over label, no change line); search + "Filters" button opening the sheet; cards (3.5).

### 3.2 Summary strip (figures, from the snapshot for the chosen range)

Three tiles, `--office-sunken` panels, radius 14px, padding `--space-3`/`--space-4`, no shadow (they sit outside a card, so tone is enough):

| Tile | Number | Line |
|---|---|---|
| Leads | 41 | "gave their email" |
| Went on to register | 9 | "22% of these leads" |
| Hot leads | 6 | "High potential, not registered" |

Percent is allowed here (this is a working list, not the Dashboard). If Moishe wants the Dashboard rule everywhere, the line becomes "9 of 41". Hot leads tile links to the filtered list.

### 3.3 Filters

In the bar, left to right (desktop), all in the URL, remembered for the session:

- Search: "Search email" (`.o-search`, 16px input). Matches part of the address.
- Range: segmented 7 days · 30 days · 90 days · All (by last seen). Default 30 days.
- Show: segmented **Not registered** (default) · Registered · All. "Registered" lists former leads who now have an account, so Barry can see what converted.
- Suggested tier: select "All tiers", then plans in order.
- Gold potential: segmented All · High · Medium · Low.
- Industry: select "All industries", then the industry options.
- "Applied for Gold" chip (`.o-chip`, a checkbox).
- Sort: select "Last seen" (default) · "First seen" · "Highest potential" · "Most visits".
- Export CSV (Admin+ only), secondary `.btn-sm`, right. Exports the filtered rows with every column in 3.4 split into plain fields (answers as separate columns), plus consent version and timestamps.

Phone: search + Filters button; the sheet holds every other control stacked, "Show results" primary at the bottom. Export sits at the bottom of the sheet for Admin+.

### 3.4 Desktop table

Rows 68px (two-line cells), zebra `--office-row-alt`, hover sunken, 14px row radius, no rules. Whole row links to the person page (first cell holds the real link).

| Column (head) | Content | Width guide |
|---|---|---|
| Lead | Email (Figtree 600, ellipsis) over muted "First seen 12 Oct" | 24% |
| Wants | The two-line summary (1.2), `--text-sm`, line 2 muted | 24% |
| Suggested | "Tier 2" | 8% |
| Potential | Potential badge | 9% |
| Industry | "Property, developer" / "Finance, law" (muted after the first) | 12% |
| Source | Referrer host or UTM source over muted campaign ("instagram.com" / "spring-launch"); "Direct" when none | 11% |
| Visits | Journeys count, tabular, right ("3") | 4% |
| Status | Status pill (1.1) | 8% |
| Last seen | Right, tabular: "Today, 18:40", "Yesterday", "23 Oct" | auto |

At 64em to 80em, Industry and Visits drop (`.o-only-wide`), their content moves into the Lead cell's second line ("First seen 12 Oct · 3 visits").

### 3.5 Phone cards

One surface card per lead (radius 20px, `--office-shadow-1`, padding `--space-3`, 8px apart):

- Row 1: email (600, ellipsis) left, status pill right.
- Row 2: potential badge (with "potential") and "Suggested Tier 2".
- Row 3: muted line 1 of the summary; row 4: muted line 2.
- Row 5: muted "Seen 2 days ago · instagram.com".

### 3.6 Empty and busy

- No leads at all: "No one has left an email yet. Leads appear when someone finishes the journey without an account."
- Filters match nothing: "No leads match that. Try fewer filters." + "Clear".
- Busy over 300ms: the table card dims to 0.6 (existing `aria-busy`).

---

## 4. Person page (one template for accounts and leads)

Extend `person.html`. Two routes, one page:

- `/people/<id>/` for an account (as today).
- `/leads/<public id>/` for a lead. The id is an opaque key, never the email (addresses must not land in URLs and logs). If the address has since registered, the lead URL redirects to the account page.

Back link: "‹ People" or "‹ Leads", by where he came from (fallback by type).

### 4.1 Header (no card)

- Name Signika 500 `--text-2xl` (desktop) / `--text-xl` (phone). A lead shows his email as the name (with `overflow-wrap: anywhere`).
- Muted line: account: "Registered 23 Oct 2026 · lead since 19 Oct"; lead: "Lead since 19 Oct 2026 · last seen today, 18:40".
- Badges row: status pill; account type in words ("Member, Tier 2", "Gold member", "No account", "Team" for staff); Verified / Not verified (accounts only, as today); potential badge.

### 4.2 Layout

**1440: 8 / 4.** Main column: Their answers, Gold potential, Timeline, All journeys. Rail: Details (accounts), Source, Consent, Data (Admin+). The rail is not sticky (it is long).

**375: one column**: header; Their answers; Gold potential; Timeline; Details; Source; Consent; All journeys; Data last.

The existing "Membership" card folds in: plan into Their answers (picked tier), registered date into the header, "Came from" into Source.

### 4.3 Their answers (card)

Title "Their answers". Muted sub-line: "From his latest finished journey, 23 Oct, 18:40". If he never finished: "From his latest journey, not finished. He stopped at Your time."

1. **Suggested and picked**, two sunken panels side by side (stacked on phone), radius 14px:
   - "Suggested" label muted, plan name Signika 500 `--text-lg`, then the three suggestion reasons as a muted list ("Evenings suit you").
   - "Picked" label muted, plan name, then one muted line: "Took the suggestion", "Chose differently", or for a lead "Not yet" (panel text muted, no plan name).
2. **The answers**, `.o-rows` label/value, plain labels:

| Label | Example value |
|---|---|
| When he'd come | Evenings, late night |
| How often | 2-3 times a week |
| What he'd use | Wet sauna, cold plunge, gym, massage room |
| Company | Sometimes with a friend |
| Work | Property (developer, 50-199 properties), finance |
| Property law | Yes (only when asked) |
| In his words | "Run a small fund" (the free text, in quotes) |
| Heard about us | A friend |

Skipped answers show "Skipped" muted. Questions he was never shown are left out.

Empty: "He has not answered any questions yet."

### 4.4 Gold potential (card)

Title "Gold". Top: potential badge, then muted "Score 7. High is 6 or more." Under it "Why", a short list from the stored suggestion detail ("Property developer", "50-199 properties", "Finance"). Then his applications as today (`.o-linkrow`: reference, potential, status, chevron).

Empty application: "He has not applied for Gold." For a High lead add one muted line: "A strong profile for Gold."

### 4.5 Timeline (card)

Title "Timeline". Newest first. Reuse the Gold history pattern (`.o-timeline`, `.o-tl` sunken tiles, `.o-tl-line`, `.o-tl-meta`): no vertical rail line, no side stripes. Group by day with a small muted day heading (`.o-subhead`: "Thu 23 Oct"). Each tile: what happened (600), a muted change or detail, then meta "18:40 · by Barry · email" (who and channel only when there is one).

| Event | Line | Detail |
|---|---|---|
| Journey started | "Started the journey" | "Mobile · from instagram.com" |
| Journey finished | "Finished the journey" | Summary (1.2) and "Suggested Tier 2"; link "See answers" jumps to that journey in All journeys and opens it |
| Journey left | "Left the journey at Your time" | Only when a later visit did not finish |
| Email given | "Gave his email" | "Consent to opening emails, privacy version 3" |
| Registered | "Registered" | "Tier 3" |
| Verified | "Confirmed his email" | |
| Plan changed | "Changed plan" | "Tier 2 to Tier 3" |
| Gold applied | "Applied for Gold" | "High potential"; links to the application |
| Gold events | Each history event of the application, same wording as `_gold_history.html` | |
| Email sent | "Email sent: Confirm your email" | "Delivered" or, in `--office-danger` text with the warning icon, "Not delivered" |
| Marketing | "Opted in to emails" / "Unsubscribed" | |

Shows the latest 20; "Show earlier" (secondary `.btn-sm`) loads 20 more by HTMX. Each event is one indexed row (see 5), so this is a list, not a figure.

Empty is impossible (a person always has at least one event); if the data predates the event log: "History starts on 26 Oct 2026."

### 4.6 All journeys (card)

Title "All journeys" with the count in muted text ("3"). One `<details>` row per journey, newest first, 56px summary rows, 14px radius, sunken on hover and when open, no rules:

- Summary: date and time (600), then muted "Finished · Suggested Tier 2 · Mobile" or "Stopped at What draws you · Mobile". Chevron right, turns to down when open (no rotation animation; icon swaps).
- Open: the answers as `.o-rows` (same labels as 4.3), plus muted facts "Visits on this journey 2 · From instagram.com · utm spring-launch".

Open/close is instant; the content fades in (opacity, 240ms, `--ease-soft`); reduced motion none.

Empty: "He has not started the journey."

### 4.7 Rail cards

**Details** (accounts only, as today): email, mobile, account ID, verified, last signed in, plus "Also gave" with any other addresses he left at the journey (muted).

**Source**: First seen (date), Came from (referrer host, "Direct" if none), Campaign (UTM source, medium, campaign as three rows, left out when empty), First page (path), Device, Heard about us (his answer). Empty values are left out; all empty: "Not recorded."

**Consent**:
- Journey email: "Given 19 Oct 2026, 18:39" over muted "Privacy version 3". Account without a journey email: "Not asked (signed in)".
- Marketing emails: "Yes, since 23 Oct" / "No" / "Unsubscribed 2 Nov". A lead: "Opening emails only (journey consent)".

**Data** (Admin+ only, unchanged copy for accounts): "Export his data" (secondary block), "Delete this person" (quiet danger). For a lead the same two, wired to the lead export and erase:
- Confirm title "Remove {email}?"; body "This clears his email from 3 journeys. The answers stay, without his email. It cannot be undone."; confirm "Remove for good"; cancel "Keep".

Office level sees no Data card (as today).

---

## 5. What this needs from the backend (for the server agent, not design)

1. Snapshot keys per range: `leads_new`, `leads_new_previous`, `leads_registered`, `hot_leads`, `insights_leads`; on the Leads page snapshot the same three tile figures for 7, 30, 90 days and All, plus the stored `leads_total` counter.
2. A per-email lead record (one row per address: first and last seen, journeys count, latest session, suggested tier, potential, industries, source, status, applied flag), updated on each journey event. The Leads list filters and sorts on it with indexes; no aggregation per request.
3. One event row per thing that happens to a person (lead, journey started/finished, registered, verified, plan change, Gold events, email sent, marketing change), keyed to the account or the lead record. It feeds Recent activity (latest 10) and the timeline (paged 20). Existing Gold history events can be read alongside instead of copied.
4. Lead person URL by opaque id; redirect to the account once registered.
5. Lead CSV export and per-lead export/erase from the Office (Admin+), reusing `journey.services.erase_lead` and the `lead_data` output.
6. Query count tests for the Dashboard, the Leads list and the person page stay flat as data grows.

---

## 6. Tokens

All existing: `--office-page`, `--office-surface`, `--office-sunken`, `--office-row-alt`, `--office-text`, `--office-muted`, `--office-gold-text`, `--office-danger`, `--office-caramel-tint`, `--office-teal` / `-track`, `--office-clay` / `-track`, `--office-shadow-1/2/3`, `--office-radius`, `--office-radius-lg`, `--office-pill`, `--office-stat`, `--office-text-xs`, brand `--color-gold`, `--color-cream`, `--color-espresso`, `--color-control-line`, `--space-*`, `--text-*`, `--ease-soft`.

**Proposed additions (layout only, Office CSS under `.office`, not `tokens.css`):**
- `--office-feed-dot: 1.75rem` (activity icon disc).
- `--office-row-h-2: 4.25rem` (two-line table rows on Leads).

No new colours.

---

## 7. Open points for Moishe

1. Leads → registered as a percent on the Dashboard breaks the "no percent on the Dashboard" rule; this brief shows "9 of 14" there and the percent on the Leads page. Say if he wants the percent on the Dashboard too.
2. Contacting leads from the Office (an email button) is not designed: the journey consent covers "emails about opening" only. Decide before adding any action.
3. Five phone tabs: if it feels crowded, Analytics could move into the person menu on phone.

---

## 8. Acceptance (frontend checks)

1. Dashboard at 1440 matches 2.1 and at 375 matches 2.2; no existing card removed; no horizontal scroll at 375.
2. Every figure on Dashboard and the Leads summary comes from the snapshot; query count flat with 10 and 10,000 leads.
3. Leads list: one row per email; default shows not registered; filters and sort in the URL and survive Back; "Show more" pages by 25; filtered views show no count.
4. Export CSV, "Export his data" and delete are absent for Office level and refused by the server.
5. Person page renders for an account and for a lead with the same sections; lead URL carries no email; a registered lead's URL redirects.
6. Status pills and badges match 1.1 and OFFICE 7.5; contrast as listed; no card, row or timeline item has a border or side stripe (the Lead pill ring is a full inset ring).
7. Timeline shows the event types in 4.5, newest first, grouped by day, 20 at a time.
8. Reduced motion: no fades, morphs or count-ups; final state at once.
9. Copy: no exclamation marks, British dates, the wording in this brief.
