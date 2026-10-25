# Spa 99 — Rules and System Spec

Source: `Spa 99 - Rules and System Spec.pdf` v1.0, 16 Oct 2026 (255 rules, 53 scenarios). Built from the pricing proposal (14 Oct) and requirements record (16 Oct).

**Rules will change.** Every number here (hours, limits, windows, deadlines, holds, capacity) is a setting or a `Plan` field in Spa 99 Control, never a constant in code. Build to the rule ID, not to memory. Changes Moishe makes are logged in `PROJECT.md` and updated here.

## Status labels

| Label | Meaning |
|---|---|
| CONFIRMED | Confirmed in discussion. Build it. |
| BASELINE | From the pricing proposal. Build it unless changed. |
| PROPOSED | Proposed to close a gap. Build it configurable, get it signed off (section 19). |
| OPTIONAL | Not confirmed. Do not build yet. |
| VERIFY | Needs checking against the chosen hardware. |

**Phase column:** which phase first needs the rule. `1` = now.

## Project overrides

| Rule | Override | Date |
|---|---|---|
| LC-26 | Phase 1: Gold application needs no account and has no approval flow on the site. Barry is emailed. Approval route decided 2026-10-23: Barry approves in the admin, the applicant gets an invite link to set up an account (see docs/PROJECT.md and docs/features/gold-application.md, "Approval and invite"). | 2026-10-22 |
| ACC-07 | Phase 1: mobile collected but not SMS-verified. Email verification only. | 2026-10-22 |
| LC-28 | Approvers are the team members picked in System > Approval (not typed addresses); Low potential approvals need a final approver first (see LC-28a below). | 2026-10-25 |
| MEM-02 | Gold targets property people. Everyone can apply; property people are nudged. | 2026-10-22 |

## Glossary

| Term | Meaning |
|---|---|
| Spa day | 5am until 3am the next calendar morning. A 1am Tuesday visit belongs to Monday's spa day. |
| Slot | A two-hour reservation starting on the hour or half hour, e.g. 5:30–7:30. |
| Booking | One person's (or one host's) reservation of a slot. Guests attach to the host's booking. |
| Visit | What happens on site: first entry, re-entry, staying on after the slot ends. |
| Upcoming booking | A booking whose slot has not ended yet. Each tier has an upcoming-booking limit. |
| Allowance | Visits (Tier 1: 6, Tier 2: 8) and guest visits per membership month. |
| Membership month | From the member's anniversary at 5am to the next anniversary at 5am. |
| Band | On-site wristband, activated by face at the band station. Opens internal doors and the assigned locker. |
| Locker assignment | The locker tied to a person's visit. Follows the person, not the band. |
| Hold | A capacity place kept for someone not yet confirmed (guest invite, waitlist offer, checkout). |

---

## 00 General

| ID | Rule | Status | Phase |
|---|---|---|---|
| GEN-01 | All prices exclude VAT unless they say otherwise. Spa 99 is VAT registered. | CONFIRMED | 1 |

## 01 What we are building

| ID | Rule | Status | Phase |
|---|---|---|---|
| SCP-01 | Register interest by creating a full account (not a mailing list). No face photo at this stage. | CONFIRMED | 1 |
| SCP-02 | Browse memberships, options, amenities and spa information. | CONFIRMED | 1 |
| SCP-03 | Subscribe to a membership, once the subscription stage is open. | CONFIRMED | 2 |
| SCP-04 | Book a two-hour slot, add guests, join waiting lists, cancel within the rules. | CONFIRMED | 3 |
| SCP-05 | Face entry linked to a valid booking. | CONFIRMED | 4 |
| SCP-06 | Face-based wristband activation inside the spa. | CONFIRMED | 4 |
| SCP-07 | Wristband access to the assigned locker and customer internal doors. | CONFIRMED | 4 |
| SCP-08 | Should: iOS and Android apps. Not required at launch. | CONFIRMED | Later |
| SCP-09 | Could: wristband purchases in an internal shop. Separate from merch and vending. | OPTIONAL | Later |
| SCP-10 | Website is the single source of truth so apps later use the same API. Launch website only. | CONFIRMED | 1 |

**Release stages** (PROPOSED): A. Register interest (account, browse, Gold application) — as soon as built. B. Subscribe (checkout, card saved, no charge until opening) — when opening date is fixed. C. Book (bookings, guests, waitlist, single visits) — normal windows counted back from opening day. D. Open (entrance, bands, lockers live; first charges) — opening day, target January 2027.

| ID | Rule | Status | Phase |
|---|---|---|---|
| OPS-01 | Men only. | BASELINE | 1 |
| OPS-02 | The spa can run unmanned. Staff are elsewhere in the building and come when alerted. | CONFIRMED | 4 |
| OPS-03 | Staff do a physical check of the spa at closing. | CONFIRMED | 4 |
| OPS-04 | No phones inside. Nothing in the spa journey may need a phone. | CONFIRMED | 4 |
| OPS-05 | No overstay reminders and no overstay fees. | CONFIRMED | 3 |
| OPS-06 | Gym and massage room are part of the same visit. No separate booking or charge. | CONFIRMED | 1 |
| OPS-07 | Every tier gets the same customer-area door access. | CONFIRMED | 4 |
| OPS-08 | No cap on memberships sold. | CONFIRMED | 2 |
| OPS-09 | Everyone books. Nobody walks in. | BASELINE | 3 |

Not chosen yet: booking platform, payment processor (Stripe likely), hosting, SMS provider, face engine, entrance terminal, controllers, locker system, band technology, band collector, app technology, support. Candidates: Kisi, UniFi or Suprema BioStation 3, Gantner, Ojmar (ESS quote). None confirmed to work together.

## 02 Memberships and pricing

Table of values: see `PRICING.md`.

| ID | Rule | Status | Phase |
|---|---|---|---|
| MEM-01 | No discounts and no packages for now. | BASELINE | 1 |
| MEM-02 | Gold is for selected customers or potential customers. Anyone can apply on the website; Barry approves. | BASELINE | 1 |
| MEM-03 | The aim is that most paying members pick Tier 2. | BASELINE | 1 |
| MEM-04 | "Today + 3" means the current spa day plus the next 3 spa days (4 days you can book). Tier 1 is today or tomorrow. | CONFIRMED | 3 |
| MEM-05 | Closed days still count as days in the window. Windows count spa days, not open days. | PROPOSED | 3 |
| MEM-06 | A member who has used the month's visits can buy a single visit at £99 + VAT. Single-visit rules apply and it counts as one of their upcoming bookings. | PROPOSED | 3 |

## 03 The spa day and opening hours

| ID | Rule | Status | Phase |
|---|---|---|---|
| CAL-01 | A spa day runs 5am to 3am the next calendar morning. | CONFIRMED | 1 |
| CAL-02 | Closed 3am to 5am every day for cleaning and set-up. No bookings, no visits. | CONFIRMED | 1 |
| CAL-03 | Daytime is 5am to 6pm. Evening is 6pm to 3am. | CONFIRMED | 1 |
| CAL-04 | Times 00:00–02:59 belong to the previous spa day. | CONFIRMED | 3 |
| CAL-05 | Times 03:00–04:59 belong to the spa day about to open. At 4am Tuesday, "today" is Tuesday. | CONFIRMED | 3 |
| CAL-06 | The one-per-day rule, booking windows and grace periods all use spa days. | CONFIRMED | 3 |
| CAL-07 | Close Friday 2 hours before candle lighting. Open Saturday night 1 hour after Shabbos ends. Same for Yom Tov. | BASELINE | 1 |
| CAL-08 | The normal 3am–5am closure still applies on Saturday night. | BASELINE | 3 |
| CAL-09 | Source times from Hebcal for London. Load 12 months ahead, show in admin, admin can override any single day. | CONFIRMED | 3 |
| CAL-11 | A two-hour slot must start and end inside one open period. It may not run into any closure. | CONFIRMED | 3 |
| CAL-12 | Daytime products (Tier 1, single visit) must end by 6pm: latest start 4pm. | CONFIRMED | 3 |
| CAL-13 | With a 3am close the latest start is 1am. | CONFIRMED | 3 |
| CAL-14 | Starts stay on the half-hour grid even when closing is at an odd minute. Friday close 1:33pm → latest start 11:30am. | CONFIRMED | 3 |
| CAL-15 | Saturday-night opening at an odd minute (5:50pm): first start is the next half hour (6pm). Entry from 5:50pm via early entry (BK-09). | PROPOSED | 3 |
| CAL-16 | Clock-change nights: no slot may overlap 1am–2am on the last Sunday of March or October. Store UTC, display local. | PROPOSED | 3 |
| CAL-17 | If a closure is added after bookings exist: spa cancels them, returns allowances and guest visits, refunds single visits in full, tells customers by SMS and email. | PROPOSED | 3 |

(There is no CAL-10 in the source.)

## 04 Booking

| ID | Rule | Status | Phase |
|---|---|---|---|
| BK-01 | A slot lasts 2 hours for scheduling and capacity. | CONFIRMED | 3 |
| BK-02 | Slots start every 30 minutes: 5:00–7:00, 5:30–7:30, 6:00–8:00 … | CONFIRMED | 3 |
| BK-03 | Capacity is 25 places, checked across the whole two-hour slot, not just the start. | CONFIRMED | 3 |
| BK-04 | Each guest takes a place for the same two hours. | CONFIRMED | 3 |
| BK-05 | Holds also take a place: pending guest invites, waitlist offers, checkout in progress. | PROPOSED | 3 |
| BK-06 | 25 is a booking target, not a door limit. A valid booked customer always gets in. | CONFIRMED | 4 |
| BK-07 | Staying longer does not take any future capacity. | CONFIRMED | 3 |
| BK-08 | Book at least 10 minutes before the start. At 2:20pm, 2:30pm is bookable; at 2:21pm the next is 3pm. | CONFIRMED | 3 |
| BK-09 | First entry from 10 minutes before the start. | CONFIRMED | 4 |
| BK-10 | Arrival allowed any time during the slot. Late arrival does not move the end or add capacity. | CONFIRMED | 4 |
| BK-11 | Customers may stay as long as they like. Bands keep working until they leave or 3am. | CONFIRMED | 4 |
| BK-12 | Edges: book if now ≤ start − 10:00. Enter if start − 10:00 ≤ now < end. Scan at exactly 4:00:00pm on a 2–4pm slot is refused. | PROPOSED | 3 |
| BK-13 | One booking per person per spa day, counting own bookings and guest visits. | CONFIRMED | 3 |
| BK-14 | No back-to-back or second bookings on the same spa day. Re-entry inside the slot is the same booking. | CONFIRMED | 3 |
| BK-15 | After a valid cancellation the person may book a different slot that same spa day. | PROPOSED | 3 |
| BK-16 | A person cannot be host and guest on the same spa day, nor accept a guest invite on a day they hold a booking (or the reverse). | PROPOSED | 3 |
| BK-17 | Windows are counted in spa days from the current spa day (MEM-04, CAL-05). | CONFIRMED | 3 |
| BK-18 | A window opens at the start of each spa day (5am). At 5am Monday, Tier 2 can first book Thursday. | PROPOSED | 3 |
| BK-19 | The window comes from the tier active now. Daytime/evening and allowance come from the tier active on the visit's spa day. | PROPOSED | 3 |
| BK-20 | Upcoming limits: Tier 1: 1. Tier 2: 2. Tier 3: 3. Gold: 3. Single visit: 1. | CONFIRMED | 3 |
| BK-21 | A booking counts as upcoming until its scheduled slot ends, whatever time they arrive or leave. | CONFIRMED | 3 |
| BK-22 | When a slot ends, the place frees and a new booking can be made inside window and allowance. | CONFIRMED | 3 |
| BK-23 | A valid cancellation frees the place straight away. | CONFIRMED | 3 |
| BK-24 | A host booking with guests is one booking for the host. | CONFIRMED | 3 |
| BK-25 | Being a guest does not count against the guest's own upcoming limit. One-per-day still applies. | CONFIRMED | 3 |
| BK-26 | A visit is charged to the membership month in which it takes place, not when booked. | CONFIRMED | 3 |
| BK-27 | A visit is reserved from allowance when booked, given back on valid cancellation, used on attendance or no-show. | PROPOSED | 3 |
| BK-28 | A booking is refused if that month's remaining allowance (after reserved visits) is zero. | PROPOSED | 3 |

**Capacity check:** for a new booking at start T, for every 30-minute step from T to T+2h, count bookings + guests + holds overlapping that step. If any step would exceed capacity, the start is full.

**Do not build:** a hard stop at 25 at the door; forcing people out or switching bands off at slot end; overstay reminders; fixed two-hour blocks only.

## 05 Guests

| ID | Rule | Status | Phase |
|---|---|---|---|
| GST-01 | Tier 3: 1 guest visit a month. Gold: 2. No other tier has guests. | CONFIRMED | 3 |
| GST-02 | A guest attaches to the host's booking, same slot. Never standalone. | CONFIRMED | 3 |
| GST-03 | Add guest shows only when the host has guest visits left that month. | CONFIRMED | 3 |
| GST-04 | Gold may use both guest visits on the same booking. | PROPOSED | 3 |
| GST-05 | A guest can be added up to 10 minutes before the start, if a place is free. | PROPOSED | 3 |
| GST-06 | Guest visits do not roll over. They reset on the monthly anniversary. | CONFIRMED | 3 |
| GST-07 | Every guest has their own account. Existing accounts reused, never duplicated. No face yet → added when accepting first guest visit. | CONFIRMED | 3 |
| GST-08 | Knowing someone's ID never lets them in by itself. The guest must accept. | CONFIRMED | 3 |
| GST-09 | Invites go by SMS and email and show in the guest's account. Accept is one tap after login. | PROPOSED | 3 |
| GST-10 | A pending invite holds a place for 30 minutes, or until 10 minutes before the start, whichever is first. | CONFIRMED | 3 |
| GST-11 | Not accepted in time → place and host's guest visit released. | CONFIRMED | 3 |
| GST-12 | Host may re-invite after expiry if the slot is still bookable and has a place. | PROPOSED | 3 |
| GST-13 | Host need not be there, but guest only enters during the host's slot. Each enters by face, own band. | CONFIRMED | 4 |
| GST-14 | Guest visit comes from the host's guest allowance, never the guest's own membership. | CONFIRMED | 3 |
| GST-15 | A member with no visits left can still come as someone's guest. | CONFIRMED | 3 |
| GST-16 | Guest no-show: host's guest visit used. No other penalty. | CONFIRMED | 3 |
| GST-17 | Host no-show: host's normal tier rules apply, even if the guest came. | CONFIRMED | 3 |
| GST-18 | Guest came, host never did: email the host after the slot. Phase 2. | OPTIONAL | Later |
| GST-19 | Cancelling the host booking cancels the guest place and any pending invite. | CONFIRMED | 3 |
| GST-20 | A valid host cancellation gives the guest visit back. | CONFIRMED | 3 |
| GST-21 | Before the host's deadline, host can remove a guest or guest can decline. Guest visit returned. | PROPOSED | 3 |
| GST-22 | After the host's deadline, the guest cannot be removed. Not coming = guest no-show. | PROPOSED | 3 |

Ways to add a guest: (1) enter an account ID; (2) pick a past guest; (3) register a new guest (host enters name, mobile, email; guest gets a link to create an account, then accepts).

## 06 Cancellations and no-shows

| ID | Rule | Status | Phase |
|---|---|---|---|
| CXL-01 | Tier 1, Tier 2, single visit: cancel up to 10 hours before start. | CONFIRMED | 3 |
| CXL-02 | Tier 3 and Gold: cancel up to 5 hours before start. | CONFIRMED | 3 |
| CXL-03 | After the deadline customers cannot cancel. The button is hidden. | CONFIRMED | 3 |
| CXL-04 | A booking made inside its own cancellation window can never be cancelled. | CONFIRMED | 3 |
| CXL-05 | Edge: cancel allowed if now ≤ start − deadline. Exactly 10:00:00 before is allowed. | PROPOSED | 3 |
| CXL-06 | Show the deadline at checkout and on the booking ("Free to cancel until 4:00am Tue" / "This booking can't be cancelled"). | CONFIRMED | 3 |
| CXL-07 | A no-show is recorded when the slot ends and that person never entered. | CONFIRMED | 3 |
| CXL-08 | Coming late, inside the slot, counts as attending. | CONFIRMED | 3 |
| CXL-09 | Host and guest are judged separately. | CONFIRMED | 3 |
| CXL-10 | Replacing a band is not an entry. It cannot undo a no-show or restart a visit. | CONFIRMED | 4 |
| CXL-11 | Penalty starts from the first no-show. No three-strikes, no fine. | CONFIRMED | 3 |
| CXL-12 | Existing bookings stay valid. The shorter window applies to new bookings only. | CONFIRMED | 3 |
| CXL-13 | Upcoming limit unchanged. Only days ahead change. | CONFIRMED | 3 |
| CXL-14 | A second no-show in the same month changes nothing more. | PROPOSED | 3 |
| CXL-15 | Waitlist entries outside the reduced window are removed, with an email. | PROPOSED | 3 |

No-show cost: Tier 1/2 visit used. Tier 3 window → today + 1 until next anniversary. Gold window → today + 3 until next Gold anniversary. Single visit: used, no refund, no credit. Guest: host's guest visit used.

**Do not build:** a "late cancel" that frees the place but charges a visit; three-strike counters or fines; refunds or credits for single-visit no-shows.

## 07 Waiting list

| ID | Rule | Status | Phase |
|---|---|---|---|
| WL-01 | Join only for a slot you could book now: window, hours, allowance. | CONFIRMED | 3 |
| WL-02 | You need room under your upcoming limit to join. | CONFIRMED | 3 |
| WL-03 | Eligibility re-checked just before an offer is sent. | CONFIRMED | 3 |
| WL-04 | Offers go by SMS and email together. | CONFIRMED | 3 |
| WL-05 | An offer holds the place 10 minutes. Not accepted → next person. | CONFIRMED | 3 |
| WL-06 | Gold first, then everyone else in join order. | CONFIRMED | 3 |
| WL-07 | Accepting is always an explicit tap. Never book anyone automatically. | CONFIRMED | 3 |
| WL-08 | Gold among themselves: join order. | PROPOSED | 3 |
| WL-09 | Joining does not use an upcoming booking, but accepting needs room for one. | PROPOSED | 3 |
| WL-10 | Up to 3 waitlist entries at a time, one per spa day. | PROPOSED | 3 |
| WL-11 | A host with guests waits as a party. Offer only when the whole party fits. | PROPOSED | 3 |
| WL-12 | Last offer 20 minutes before start (10-min offer + 10-min notice). | PROPOSED | 3 |
| WL-13 | Single-visit customers can join. They pay (or use a credit) on accept. | PROPOSED | 3 |
| WL-14 | Booking another slot that spa day, or losing eligibility, removes the entry. | PROPOSED | 3 |
| WL-15 | Entries removed automatically when the slot starts. | PROPOSED | 3 |

Freed places come only from cancellations before the deadline, expired invites, expired offers and spa-side cancellations.

## 08 Membership lifecycle

| ID | Rule | Status | Phase |
|---|---|---|---|
| LC-01 | The membership month runs from the member's own start date. Start 14 Nov → renews 14 Dec, 14 Jan. | CONFIRMED | 2 |
| LC-02 | The month changes at 5am on the anniversary date. | CONFIRMED | 2 |
| LC-03 | Unused visits and guest visits expire at renewal. No rollover. | CONFIRMED | 2 |
| LC-04 | Start on 29th/30th/31st: in shorter months renew on the last day, then return to the original day. | CONFIRMED | 2 |
| LC-05 | Membership starts automatically after payment. No staff approval. Face added at first booking. | CONFIRMED | 2 |
| LC-06 | Memberships bought before opening start on the opening date. That date is the anniversary. | CONFIRMED | 2 |
| LC-07 | Save the card at checkout (zero-value check); first payment at 5am on opening day. | PROPOSED | 2 |
| LC-08 | If opening moves, start dates move and members are told. No cancel before the first charge (LC-14a). | CONFIRMED | 2 |
| LC-09 | Registering interest never asks for payment details. | CONFIRMED | 1 |
| LC-10 | Upgrades and downgrades take effect at the next renewal. No mid-month changes, no pro-rata. | CONFIRMED | 2 |
| LC-11 | Until then the current tier's price, visits, hours and window stay. | CONFIRMED | 2 |
| LC-12 | On downgrade, list bookings after renewal the new tier wouldn't allow. Confirming cancels them and returns allowance. | CONFIRMED | 3 |
| LC-13 | A scheduled change can be undone any time before renewal. | PROPOSED | 2 |
| LC-14 | Cancelling stops the next renewal. Access continues to the end of the paid month. | CONFIRMED | 2 |
| LC-14a | Minimum one paid month. No cancel option before the first month is paid, including before opening. | CONFIRMED | 2 |
| LC-15 | On confirming cancellation, bookings after the paid-through date (and guests) are listed and cancelled. | PROPOSED | 3 |
| LC-16 | A cancellation can be withdrawn before the paid month ends. | PROPOSED | 2 |
| LC-17 | While unpaid: no new bookings. | CONFIRMED | 3 |
| LC-18 | Existing bookings can still be attended during grace. | CONFIRMED | 3 |
| LC-19 | A visit in progress is never interrupted. Band and locker keep working. | CONFIRMED | 4 |
| LC-20 | Grace lasts to the end of the next spa day. Fails 14 Nov → entry until 3am 16 Nov. | CONFIRMED | 3 |
| LC-21 | When grace ends: entry blocked, unpaid future bookings and guests cancelled. | CONFIRMED | 3 |
| LC-22 | Paying restores normal booking. Cancelled bookings are not restored. | CONFIRMED | 3 |
| LC-23 | Retry the card at failure, then daily for 7 days. Customer can update the card any time. SMS + email at failure and when grace is ending. | PROPOSED | 2 |
| LC-24 | Still unpaid after 7 days: membership ends. Paying late keeps the original anniversary. | PROPOSED | 2 |
| LC-25 | A failed first payment (opening day) follows the same grace rules. | PROPOSED | 2 |
| LC-26 | Gold needs Barry's approval. Applicants must already have an account. **Overridden for Phase 1: no account needed.** | CONFIRMED | 1 |
| LC-27 | Gold's month starts on the approval date. Guest visits and penalties reset on that anniversary. | CONFIRMED | 2 |
| LC-28 | Barry (and one named deputy) approve or decline in admin. Applicant emailed either way. | PROPOSED | 2 |
| LC-28a | Gold approvers are team members with the Approver permission (Office level or higher), set in System > Approval, each emailed at their account email or another address. An approval of a Low potential application waits for a final approver (Admin level or higher), who confirms or sends it back; after a send-back the next approval goes through at once. Without a final approver, Low is approved as normal. Added 2026-10-25 (docs/features/gold-final-approval.md). | CONFIRMED | 1 |
| LC-29 | Gold can be revoked any time. Future bookings and guests cancelled; a visit in progress is not interrupted. | PROPOSED | 3 |

## 09 Single visits and credits

| ID | Rule | Status | Phase |
|---|---|---|---|
| SV-01 | £99 + VAT (£118.80). Daytime only: slot must end by 6pm. | CONFIRMED | 3 |
| SV-02 | Book today or tomorrow. One upcoming booking. One per spa day. 10-minute notice. | CONFIRMED | 3 |
| SV-03 | Same account as everything else. Face added at first booking if missing. | CONFIRMED | 3 |
| SV-04 | Pay at booking. Slot held 10 minutes during checkout. | PROPOSED | 3 |
| SV-05 | Cancel at least 10 hours before → a credit, never a refund. | CONFIRMED | 3 |
| SV-06 | Credit lasts 30 days from cancellation, and the visit must happen inside those 30 days. | CONFIRMED | 3 |
| SV-07 | Expiry: 3am at the end of the spa day 30 days after the cancellation's spa day. | PROPOSED | 3 |
| SV-08 | Cancelling a credit-paid booking returns the credit with its original expiry. | PROPOSED | 3 |
| SV-09 | Credits are personal: not transferable, not split, single visits only, no cash. Oldest first. | PROPOSED | 3 |
| SV-10 | No-show: visit used. No refund, no credit. | CONFIRMED | 3 |

## 10 Accounts and face identity

| ID | Rule | Status | Phase |
|---|---|---|---|
| ACC-01 | Anyone can make a full account without buying anything. | CONFIRMED | 1 |
| ACC-02 | No face at sign-up. Face taken or uploaded at first booking or first guest acceptance. | CONFIRMED | 3 |
| ACC-02a | No booking or guest acceptance is confirmed until the account has a face. | CONFIRMED | 3 |
| ACC-03 | No payment details at sign-up. | CONFIRMED | 1 |
| ACC-04 | The same account is used for memberships, single visits and guest invites. | CONFIRMED | 1 |
| ACC-05 | Every account has a shareable ID for guest invites. | CONFIRMED | 1 |
| ACC-06 | An account alone gives no right to enter. | CONFIRMED | 4 |
| ACC-07 | Fields: first name, last name, email (verified by link), mobile (verified by SMS code), date of birth. **Phase 1: email verification only.** | PROPOSED | 1 |
| ACC-08 | Minimum age 18. | PROPOSED | 1 |
| ACC-09 | Men-only policy shown and accepted at sign-up. | PROPOSED | 1 |
| ACC-10 | One account per email and per mobile. A face matching an existing account is flagged for staff, not blocked. | PROPOSED | 1 |
| ACC-11 | Separate, explicit consent for face data. Face template deleted within 30 days of account closure. | PROPOSED | 3 |
| ACC-12 | Photo check: one face, eyes visible, good light, no hat or sunglasses. Retake if it fails. | PROPOSED | 3 |
| ACC-13 | Members can retake their face photo from their account. | PROPOSED | 3 |

Legal: face data is special-category biometric data under UK GDPR. Needs a DPIA, lawful basis, privacy notice and retention rule before collecting. Check the men-only policy with a lawyer.

## 11 Entry, exit and re-entry

| ID | Rule | Status | Phase |
|---|---|---|---|
| ENT-01 | Face is the only normal way in. No band, PIN, QR or card at the front door. | CONFIRMED | 4 |
| ENT-02 | Face scan checks: account, paid status, accepted booking (own or guest) for today, entry window. | CONFIRMED | 4 |
| ENT-03 | One shared double-door vestibule, one person at a time, entry and exit. | CONFIRMED | 4 |
| ENT-04 | Passing through the vestibule marks the person inside and records attendance. | CONFIRMED | 4 |
| ENT-05 | Failed face match: retry up to 3 times, then Call staff. Staff check ID and can open once, remotely. Logged. | PROPOSED | 4 |
| ENT-06 | No face scan on the way out. Exit is by returning the band. | CONFIRMED | 4 |
| ENT-07 | Bands stay on site. The band must be dropped in the collector to leave. | CONFIRMED | 4 |
| ENT-08 | Dropping the band deactivates it at once. Passing out marks the person outside. | PROPOSED | 4 |
| ENT-09 | Lost band at exit: replacement at the band station, then drop it. Or Exit help. | PROPOSED | 4 |
| ENT-10 | Fire alarm or emergency releases every door, independent of the software. | VERIFY | 4 |
| ENT-11 | Leaving during the slot keeps the right to come back until the slot ends. | CONFIRMED | 4 |
| ENT-12 | Re-entry is by face, then a new band at the station. | CONFIRMED | 4 |
| ENT-13 | Re-entry is the same booking. No new visit, no allowance used. | CONFIRMED | 4 |
| ENT-14 | After the slot ends, someone who leaves cannot come back on that booking. | CONFIRMED | 4 |
| ENT-15 | Someone inside after the slot keeps full internal access until they leave or 3am. | CONFIRMED | 4 |
| ENT-16 | Re-entry uses the same window as first entry (from 10 minutes before start). | PROPOSED | 4 |

**Keep these apart in the data model:** account · payment status · booking (scheduled two hours) · attendance and inside/outside · ongoing visit after slot end · re-entry rights · active band · locker assignment. Returning or replacing a band never cancels a booking or releases a locker by itself.

**Do not build:** an exit face scanner; bands as a second way in; customers taking bands home.

## 12 Wristbands

| ID | Rule | Status | Phase |
|---|---|---|---|
| BND-01 | Bands kept on site. Band station identifies by face, then they tap a band to link it. | CONFIRMED | 4 |
| BND-02 | The band opens customer internal doors and the person's assigned locker. | CONFIRMED | 4 |
| BND-03 | One active band per person. A new band switches the old one off immediately. | CONFIRMED | 4 |
| BND-04 | The station needs a valid booking or an ongoing visit. An account alone is not enough. | CONFIRMED | 4 |
| BND-05 | Valid = entry window open now (start − 10 min to end), or inside on an ongoing visit. | PROPOSED | 4 |
| BND-06 | Lost band: face at station, new band. Same visit, locker, doors. | CONFIRMED | 4 |
| BND-07 | Replacement works after the slot has ended, for someone still inside. | CONFIRMED | 4 |
| BND-08 | A replacement never starts a visit, extends a slot, records attendance or refreshes allowance. | CONFIRMED | 4 |
| BND-09 | Bands do not stop working because the slot ended. | CONFIRMED | 4 |
| BND-10 | All bands switched off at 3am. | PROPOSED | 4 |
| BND-11 | The old band must be refused at every door and locker, including when the network is down. | VERIFY | 4 |

**Do not build:** a confirmed entry before band activation; two working bands for one person.

## 13 Lockers

States: FREE → ASSIGNED (person inside, open or shut) → RESERVED (left, locker locked) / released (left unlocked) → 3AM RESET (unlock, staff check) → FREE at 5am. FAULTY lockers are never assigned. Opening a locker inside never moves it out of ASSIGNED.

| ID | Rule | Status | Phase |
|---|---|---|---|
| LKR-01 | The band station assigns a free locker automatically and shows its number. | CONFIRMED | 4 |
| LKR-02 | The locker follows the visit, not the band. A new band opens the same locker. | CONFIRMED | 4 |
| LKR-03 | Customers do not pick their own locker. | CONFIRMED | 4 |
| LKR-04 | Fit more than 25 lockers (people stay past their slot). Number set from the floor plan. | PROPOSED | 4 |
| LKR-05 | No free locker: band still works for doors, screen says staff are coming, staff alerted. | PROPOSED | 4 |
| LKR-06 | The locker stays assigned for the whole visit, including while open. | CONFIRMED | 4 |
| LKR-07 | Opening a locker inside never releases it. | CONFIRMED | 4 |
| LKR-08 | On leaving, a locker left unlocked is released. | CONFIRMED | 4 |
| LKR-09 | On leaving, a locker left locked stays reserved until they return or 3am. | CONFIRMED | 4 |
| LKR-10 | Coming back during the slot with a new band gets the same locker. | CONFIRMED | 4 |
| LKR-11 | The slot ending never releases a locker someone inside is using. | CONFIRMED | 4 |
| LKR-12 | A reserved locker gives no right to come back in after the slot. | CONFIRMED | 4 |
| LKR-13 | Slot ends with the person outside and locker locked: alert staff, SMS the customer how to collect. | PROPOSED | 4 |
| LKR-14 | Collecting after the slot: customer contacts staff; staff open and hold items. Unclaimed at 3am → lost property. | PROPOSED | 4 |
| LKR-15 | Confirm the chosen lock reports locked/unlocked. If not, another release rule is needed. | VERIFY | 4 |
| LKR-16 | Staff acknowledge an alert in admin within 5 minutes, or it escalates to the manager by SMS. | PROPOSED | 4 |
| LKR-17 | Staff can unlock remotely from admin if hardware allows. Every unlock logged. | PROPOSED | 4 |
| LKR-18 | Faulty lockers are never assigned until staff mark them working. | PROPOSED | 4 |

Terminal "My locker won't open" (after face check): A. Things inside → keep assignment, alert staff (app, SMS, email), show "Staff are on their way". B. Broken, empty → assign another free locker, mark old faulty. B with no free locker → treat as A (PROPOSED).

**Do not build:** releasing a locker because it was opened; asking "Are you coming back?" on exit; free choice of locker.

## 14 Closing at 3am

| ID | Rule | Status | Phase |
|---|---|---|---|
| CLS-01 | Lockers released at 3am. Staff physically check the spa at closing. | CONFIRMED | 4 |
| CLS-02 | 2:45am: closing message on screens and audio. Staff begin the walk-round. | PROPOSED | 4 |
| CLS-03 | 3:00am: every visit ends, every band off, every locker unlocked. | PROPOSED | 4 |
| CLS-04 | Staff check each locker, move left items to lost property, mark faults. | PROPOSED | 4 |
| CLS-05 | Staff tap Reset complete in admin. Only then do lockers become free for 5am. | PROPOSED | 4 |
| CLS-06 | A software reset must never hand out a locker that is still locked or full. | CONFIRMED | 4 |
| CLS-07 | If Reset complete is not tapped by 4:45am, alert the manager. | PROPOSED | 4 |

## 15 Facilities and doors

| Space | Area | Access |
|---|---|---|
| Entrance | 48.64 m² | Face (vestibule) |
| Changing room | 20.15 m² | Band |
| Shower / cold plunge | 25.16 m² | Band |
| Wet sauna | 15.20 m² | Band |
| Dry sauna | 14.97 m² | Band |
| Relaxing zone | 17.56 m² | Band |
| Gym | 12.97 m² | Band, same visit |
| Massage room | 8.93 m² | Band, same visit |
| Kitchenette | 9.88 m² | Band |
| Hallway | 9.04 m² | – |
| Accessible WC / 2 small WCs | 4.86 / 1.15 m² each | – |
| Plant rooms, electrical, dry riser | 6.45 / 11.04 / 3.13 / 6.21 m² | Staff only |

| ID | Rule | Status | Phase |
|---|---|---|---|
| FAC-01 | All customers get the same internal access, whatever their tier. | CONFIRMED | 4 |
| FAC-02 | Staff and service areas use separate staff credentials. | CONFIRMED | 4 |
| FAC-03 | Which doors have readers is set by a confirmed door schedule, not room labels. | PROPOSED | 4 |
| FAC-04 | Emergency door behaviour is outside the booking rules and must always fail safe. | CONFIRMED | 4 |

Plan: `99 VALE ROAD - SHVITZ-LIGHTING REV4.pdf`, drawing 99.VR.PR.GF rev 04, 10 Sep 2026, Panorama Interior. Do not scale; dimensions to be checked on site.

## 16 Merch, food, events and extras

| ID | Rule | Status | Phase |
|---|---|---|---|
| EXT-01 | Merch sold on the website and on site. Not in vending. Small brand items: water bottle, tote bag. | BASELINE | Later |
| EXT-02 | Gold gets each new release free. | BASELINE | Later |
| EXT-03 | Gold: one of each item per release, claimed in the account within 60 days, collected on site. | PROPOSED | Later |
| EXT-04 | Vending: food, snacks and drinks whenever the building is open. No booking, no staff. | BASELINE | – |
| EXT-05 | Vending not linked to accounts or bands at launch. | PROPOSED | – |
| EXT-06 | Leil Shishi: Thursday evening chef's meal added while booking an evening slot. £45 + VAT, included for Gold. | OPTIONAL | Later |
| EXT-07 | Leil Shishi: Tier 2, Tier 3 and Gold only. | OPTIONAL | Later |
| EXT-08 | Leil Shishi food cost unknown. Capacity, deadline, guests and cancellation open. | OPTIONAL | Later |
| EXT-09 | Do not build Leil Shishi until confirmed. Leave room for a booking add-on in the data model. | PROPOSED | 3 |
| EXT-10 | Gold perk: BML members' events. | BASELINE | 1 |
| EXT-11 | Events handled outside the booking system at launch. | PROPOSED | – |
| EXT-12 | Band payments in an internal shop: later phase. | OPTIONAL | Later |

## 17 Admin, staff and messages

| ID | Rule | Status | Phase |
|---|---|---|---|
| ADM-01 | See and manage memberships, anniversaries, scheduled tier changes, cancellations, payment status, grace. | CONFIRMED | 2 |
| ADM-02 | See visits used, guest visits, credits and no-show penalties per member. | CONFIRMED | 3 |
| ADM-03 | Set opening hours, Shabbos and Yom Tov times, one-off closures, capacity (25), half-hour grid. | CONFIRMED | 1 |
| ADM-04 | See bookings, guests, pending invites, waitlist offers, attendance, who is inside, re-entry rights. | CONFIRMED | 3 |
| ADM-05 | Approve or decline Gold applications. | CONFIRMED | 2 |
| ADM-06 | See each person's active band and locker; switch off or replace a band. | CONFIRMED | 4 |
| ADM-07 | Receive locker alerts; mark lockers faulty or fixed. | CONFIRMED | 4 |
| ADM-08 | Run the closing check and reset. | CONFIRMED | 4 |
| ADM-09 | Set who receives staff alerts. | CONFIRMED | 1 |
| ADM-10 | Look into failed entries, failed enrolments, payment problems and odd states. | CONFIRMED | 2 |
| ADM-11 | Every manual override is logged with who, when and why. | PROPOSED | 1 |

Roles (PROPOSED): Owner (Barry): everything incl. Gold approval and revocation. Manager: everything except Gold; overrides; settings. Staff on duty: alerts, remote open/unlock, lockers, closing check, lost property. Support (read only): look up customers, bookings, payments.

Customer messages (PROPOSED): booking made/cancelled — email. Guest invite — SMS + email + in account. Waitlist offer — SMS + email (CONFIRMED). Payment failed / grace ending / bookings cancelled — SMS + email. Credit issued / expiring in 7 days — email. Locker left locked after slot — SMS. Spa-side cancellation — SMS + email. Optional: guest came, host didn't — email. **Nothing is ever sent telling someone to leave.**

## 18 Scenario book (test cases)

| Case | Situation | Expected | Rule |
|---|---|---|---|
| S01 | Tier 2 books 5:30–7:30am | Allowed | BK-02 |
| S02 | 20 booked 2–4pm, 5 booked 3–5pm; try 2:30–4:30 | Refused (3–4pm full) | BK-03 |
| S03 | 2:20pm, try 2:30pm | Allowed; at 2:21pm only 3:00pm+ | BK-08 |
| S04 | Tier 1 tries 4:30pm start | Refused, latest 4pm | CAL-12 |
| S05 | Friday close 1:33pm | Latest start 11:30am | CAL-14 |
| S06 | Tier 3 has 9am, tries 7pm same day | Refused | BK-13 |
| S07 | Tier 3 has Mon 8pm, tries Tue 1am | Refused (Monday's spa day) | CAL-04 |
| S08 | Tier 3 cancels 9am 12h ahead, books 7pm | Allowed | BK-15 |
| S09 | Tier 3 holds Mon/Wed/Fri; Mon 2–4pm ends | From 4pm a fourth can be booked | BK-21 |
| S10 | Tier 1 leaves 2:30 from 2–4pm | Upcoming until 4pm | BK-21 |
| S11 | 4am Tuesday, Tier 2 opens app | Can book Tue–Fri | CAL-05 |
| S12 | Booked 2–4pm, arrives 1:50pm | Let in | BK-09 |
| S13 | Booked 2–4pm, arrives 1:45pm | Refused until 1:50pm | BK-09 |
| S14 | Booked 2–4pm, arrives 3:50pm | Let in; slot still ends 4pm | BK-10 |
| S15 | Scans at exactly 4:00:00pm | Refused | BK-12 |
| S16 | 27 inside, booked person arrives | Let in | BK-06 |
| S17 | Leaves 2:30 locker locked, back 3:15 | Face, new band, same locker | ENT-11 |
| S18 | Stays to 5pm, leaves, back 5:20 | Refused | ENT-14 |
| S19 | Inside at 6pm on 2–4pm slot, loses band | New band, same locker, no new visit | BND-07 |
| S20 | Wants to leave, no band | Replacement then drop, or Exit help | ENT-09 |
| S21 | Three failed face scans | Call staff, ID check, open once, logged | ENT-05 |
| S22 | Tier 1 used all 6, Tier 3 friend invites | Allowed, host's guest visit | GST-15 |
| S23 | Host never comes, guest comes | Guest in; host no-show | GST-13, GST-17 |
| S24 | Invite 1:00pm for 4pm, no reply | Hold ends 1:30pm, released | GST-10 |
| S25 | Invite 1:45pm for 2pm | Hold ends 1:50pm | GST-10 |
| S26 | Guest never comes | Host's guest visit used | GST-16 |
| S27 | Tier 3 cancels 8h before | Guest place cancelled, guest visit returned | GST-19, GST-20 |
| S28 | Gold adds two guests | Allowed, three places | GST-04 |
| S29 | Tier 1 books 2h before | No cancel option | CXL-04 |
| S30 | Tier 1 cancels exactly 10h00m00s before | Allowed | CXL-05 |
| S31 | Tier 3 misses Tue, has Thu and Sat | Thu/Sat stay; new: today/tomorrow; limit 3 | CXL-12 |
| S32 | Gold misses a booking | New bookings today + 3 until anniversary | CXL-11 |
| S33 | Tier 3 joined 9am, Gold 10am; place frees | Offer to Gold | WL-06 |
| S34 | Offer not accepted in 10 min | Next eligible person | WL-05 |
| S35 | Place frees 15 min before start | No offer; open for normal booking until −10 | WL-12 |
| S36 | Gold + 2 guests waiting; 2 free | No offer | WL-11 |
| S37 | Tier 2 renews 14th; on 12th books 15th | Uses next month's allowance | BK-26 |
| S38 | Renewal fails 14 Nov; bookings 15 Nov 11pm and 17 Nov | 15th allowed; 17th cancelled at grace end unless paid | LC-20, LC-21 |
| S39 | Grace ends at 3am while inside | Nothing cut off | LC-19 |
| S40 | Tier 1 upgrades to Tier 3 on day 10 | Tier 1 until renewal | LC-10 |
| S41 | Tier 2 downgrades with evening booking after renewal | Shown; confirming cancels and returns visit | LC-12 |
| S42 | Old account, no face, first booking | Face photo required before confirm | ACC-02a |
| S43 | Joined 31 Jan | Renews 28 Feb (29 leap), then 31 Mar | LC-04 |
| S44 | Buys Tier 2 1 Dec, opening 10 Jan 2027 | Card saved, charge 10 Jan 5am, renews 10th | LC-06, LC-07 |
| S45 | Pre-opening member wants to cancel in Dec | No cancel option | LC-14a |
| S46 | Cancels 1 Mar, tries to book 2 Apr | Refused, by end of 31 Mar spa day | SV-06, SV-07 |
| S47 | Credit booking cancelled in time | Credit back, same expiry | SV-08 |
| S48 | Opens locker for a towel | Still assigned | LKR-07 |
| S49 | Leaves, locker unlocked | Released | LKR-08 |
| S50 | Leaves 3pm locker locked, slot ends 4pm | 4pm staff alerted, SMS to customer | LKR-13 |
| S51 | Locker won't open, belongings inside | Staff alerted, assignment kept | LKR terminal A |
| S52 | Locker won't open, empty | New locker, old faulty | LKR terminal B |
| S53 | Two inside at 3am | Visits end, bands off, unlock, staff see them out | CLS-03 |

## 19 Proposed answers to sign off

| # | Open point | Proposed answer | Rules | Signed off |
|---|---|---|---|---|
| 01 | Opening date and stages | Target Jan 2027, date set in admin; stages A–D | LC-06 | – |
| 02 | Exact time edges | Book if now ≤ start−10; enter if start−10 ≤ now < end; cancel if now ≤ start−deadline | BK-12, CXL-05 | – |
| 03 | Tier 2/3 window examples | Today + N spa days, opening at 5am | MEM-04, BK-18 | – |
| 04 | Do closed days count? | Yes | MEM-05 | – |
| 05 | One per day after cancelling | Allowed after valid cancel; no host + guest same day | BK-15, BK-16 | – |
| 06 | Gold two guests in one slot | Allowed | GST-04 | – |
| 07 | Guest removal | Before host deadline yes, after no | GST-21, GST-22 | – |
| 08 | Host notice when only guest came | Optional email, later | GST-18 | – |
| 09 | Single-visit no-show, credit re-cancel | Visit used; credit back same expiry | SV-08, SV-10 | – |
| 10 | Waitlist details | Max 3, one per day, party offers, last offer −20 min, pay on accept | WL-08–15 | – |
| 11 | Gold order and penalties on waitlist | Gold by join time; out-of-window entries removed | WL-08, CXL-15 | – |
| 12 | Pre-opening payment | Card saved, first charge 5am opening day | LC-07, LC-08 | – |
| 13 | Bookings after cancel / Gold revoke | Listed and cancelled; visits in progress never cut | LC-15, LC-29 | – |
| 14 | First payment fail and retries | Same grace; retry daily 7 days; then ends; anniversary kept | LC-23–25 | – |
| 15 | Automatic locker assignment | Yes | LKR-01 | – |
| 16 | 3am sequence | 2:45 warning, 3:00 end/off/unlock, staff check, Reset complete | CLS-02–07 | – |
| 17 | Items left after the slot | Staff alerted, SMS, collect via staff, lost property at 3am | LKR-13, LKR-14 | – |
| 18 | Faulty locker, no spare | Treat as "things inside" | LKR terminal | – |
| 19 | Staff alerts | Configurable list, push + SMS + email, 5-min ack then escalate, remote unlock logged | LKR-16, LKR-17 | – |
| 20 | Gold merch, meals, events, shop | Merch claim per release; Leil Shishi not built; events and shop later | EXT-03, EXT-09, EXT-11 | – |
| 21 | Account fields, age, duplicates | Name, verified email + mobile, DOB, 18+, one per email/mobile, face duplicates flagged | ACC-07–13 | Partly (email-only verification) |
| 22 | When stages open | Register interest now; subscribe once date fixed; booking by normal windows | SCP-10 | – |

## 20 Hardware checks before buying

| # | Check | What must work |
|---|---|---|
| H01 | Face-only front door | Works with chosen terminal and controller together |
| H02 | Remote enrolment | Photos taken/uploaded online are accepted and match well |
| H03 | Vestibule | One person at a time, both directions, tailgating detected |
| H04 | Band collector | Drop triggers deactivation; behaviour with no band |
| H05 | Instant band switch-off | Old band refused at every door and locker at once |
| H06 | Locker follows the person | Access survives band changes and exit/re-entry |
| H07 | Lock state | Lock reports locked/unlocked to software |
| H08 | Locker control | Auto-assign, reassign, faulty flag, bulk unlock at 3am |
| H09 | Offline | Behaviour with no internet or power; catching up after |
| H10 | Emergency | All doors release on alarm, independent of software |
| H11 | Real occupancy | Safe number on site, separate from the 25 target |
| H12 | Commercials | Licences, API access, costs, data export, code ownership, support |

Candidates: Kisi (controllers), UniFi or Suprema BioStation 3 (entrance), Gantner (lockers, internal access), Ojmar (ESS quote), custom one-person double-door vestibule. None confirmed to work together. The ESS quote (£38,211 ex VAT) is an estimate only.
