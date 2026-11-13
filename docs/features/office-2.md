# Office 2 (plan, 2026-11-05)

Status: agreed with Moishe, building on `feature/office-2`. One branch, one push. Sources: Moishe's list and the meeting with Barry (5 Nov). Mostly the phone view; some of it on computer too. The WhatsApp chat is saved on `archive/whatsapp-chat`. Email chat research is on `feature/email-chat` and is not part of this.

## Home
- Phone: no greeting, no range bar (it stays on All). Also hide Gold applications, Waiting for you and Hot leads. Keep Leads, Recent activity and the rest.
- Three cards with two rings each:
  1. **Waiting for approval:** Gold and memberships, worded so it is clear they wait.
  2. **Approved:** Gold and memberships.
  3. **Revenue:** Gold and memberships, a 12-month estimate.
- Everything is tappable: Waiting rings open the approval lists, Approved rings open the approved lists on Registered and Gold, Revenue opens the Revenue page.
- Computer: the cards side by side.

## Membership approval (Barry's view only)
- Approve moves to Approved, Decline moves to Declined. **The customer's membership and emails never change.**
- All existing registered people start unapproved, except Gold he approved. New registrations join as waiting.
- Registered page shows approved people, says how many are left to approve, and links to the approval list.
- Gold approval works as it does today.

## Phone tabs
Five, no More: Home, Approach list, Analytics, Leads, Revenue. Assistant hidden on phone only, stays on computer.

## Revenue page
Estimated annual. Gold = count x 199. Memberships = each member's actual price including a kept sale price. **All prices are excluding VAT.** Show ex and inc VAT, by plan and tier, monthly and yearly, members counted, average per member, and possible revenue from those waiting. Clearly labelled an estimate.

## VAT wording
Gold shows £199 + VAT everywhere it appears, in the Office and on the public site. Moishe has decided this is fine (2026-11-05); membership prices already read excluding VAT.

## Leads
- Shows everyone with no account, not archived and not on the Approach list. No number filters: new leads must give a mobile, and existing ones with none move to Archived after the group email.
- Top cards: Leads and Registered only, true totals, tappable. Hot leads goes.
- Add to Approach list is one tap: no box, no reason (Moishe, 2026-11-05).
- Added to the Approach list = gone from Leads. From the list he can go back to Leads or to Archive.
- Phone: scrolling loads more by itself with a loading animation until the end. Show More no longer hidden behind the nav. Applies to every long list.
- Whole rows tappable everywhere, with visible tap feedback.

## Approach list
- Registering removes him from Leads and the Approach list automatically (replaces the Registered tab there).
- Emailing one person keeps him on the list, tagged Emailed, with a filter.

## Registered list (computer and phone)
- Separate Membership and Gold tables, with filters.
- The Gold column shows only people who applied and are not yet approved. An approved Gold member does not show it.
- Every registered count is the true total, no "moved on from leads".

## WhatsApp
- Remove the WhatsApp tab, chat, templates, media, voice, Link it, push and PWA notifications from the Office. Installing the Office as an app stays.
- The WhatsApp button opens `wa.me` to that person. Mobile needed; otherwise the Details row to add one.
- Live chats: copy kept in the RDS snapshot, tables dropped (they hold foreign keys to users that would block deleting staff and members).
- 020 number: nothing answers it. Moishe accepts this (2026-11-05). Both Twilio webhooks go; Moishe clears them at Twilio.
- System > Settings WhatsApp number must be the old number.

## Emails
- Every automatic email and group send can choose its sender: a dropdown of staff with a @spa99.uk address, default hello@. Select, not type.
- Group send to all leads, default wording from Barry, editable: asks them to join, which he personally approves for special discounts and prices, to WhatsApp him, and to give the number they have WhatsApp on. Includes an add-your-number link. Unsubscribe link stays.
- After the send (Barry's method, 2026-11-05): leads the email reached with no mobile move to Archived, reason "Emailed, no number". Bounced ones stay in Leads with Possible fake. Leads with a mobile stay. Adding a number moves him to the Approach list. Lead totals drop accordingly.
- **Audiences (Moishe, 2026-11-05):** Leads with no number (all of them, no dates; Barry's invitation starts here) and All leads (with or without a mobile, optional dates; "Journey leads" before).
- **Add-your-number link:** a personal signed link to a small page with his email filled in. Saves the mobile, moves him to the Approach list. Refuses a taken number, tampered or expired link. No sign-in.

## Not doing
A link to the website from the Office. Bigger WhatsApp button on the website. A tag for people who registered without the questions. Business profile logo (Moishe, not code).

## Built (server side, 2026-11-05, `feature/office-2`)

Server side only; templates are minimal and working, and the frontend agent restyles them to `office-2-design.md`. Levels: **editor** = the Approver permission, or Admin level and up (superusers always); **reader** = any team level. "Fetch" means a request with `X-Requested-With: fetch` or `Accept: application/json`; every list endpoint below also answers a fragment (rows only) to an `HX-Request` header, as the other lists do. Every long list has `more_url` and `has_next` in its context, and `?page=N` loads the next rows, so the phone's auto-load needs no new endpoint.

### Choices made beyond the spec (also in PROJECT.md)
- **Approved, for Revenue:** a membership counts as approved when Barry's review says approved (`MembershipReview`); a Gold application counts when its status is approved. **Waiting:** membership with no row or waiting; Gold new, contacted or awaiting final. Declined counts in neither. A person on a Tier with a Gold application counts in both Waiting figures, but Revenue counts him once, at his Tier, while his Tier is not declined.
- **Who is in the membership lists:** registrations that are not on the Gold plan. Gold-plan members are the Gold table of Registered and are never in Approvals. The "of N registered" on the Memberships rings is the membership total (`counts.memberships.total`); the Registered tile is every registration (`registered_total`), Gold members included.
- **A member's price:** an active subscription's agreed price if there is one, else the kept sale price (while held), else the plan price; times 12.
- **Archive from the list, Back to Leads and Undo:** both take his entries off the list (the open one and any older Done ones, or a Done row would keep him out of Leads), so Undo is a POST that puts him back as ONE open entry with the same reason (and un-archives first). Older Done rows are not restored (their who and when are gone). Back to Leads and Archive show on open rows only.
- **Any entry on the approach list (open or done) keeps a lead out of Leads.** Registering takes him off the list only for entries still open and added before he registered; a done entry stays in Done.
- **Gold Respond with a mobile goes to wa.me, without one to the Email pop-up. Nothing marks New as Contacted on a wa.me click** (it proves nothing): an email sent from the pop-up still marks it, and there is an explicit "Mark contacted" POST.
- **Group send archiving is a per-mailing switch** (`Mailing.archive_no_number`, on by default only for Barry's starter, only for the leads group), so an ordinary newsletter to leads never moves anyone.
- **The leads group now equals the Leads list** (no account, not archived, not on the approach list), so the confirm count matches the Leads total.
- **Add-your-number link expires after 90 days.**
- **The Office installable app stays** (manifest and a service worker with no push, no cache and no fetch handler), now in `office`.
- **No stored Gold price copy needs a backfill:** the public price cell comes from the plan's fee (`£199 + VAT a year`), the fee note already read `+ VAT`, and no stored copy holds a literal price.

### Pages and endpoints (Office host)
| URL | Method, level | Context keys (and what it does) |
|---|---|---|
| `/` | GET, reader | `cards` (editor only, else `None`): `{waiting: {gold, memberships}, approved: {...}, revenue: {gold, memberships}, registered_total, leads_total}`; each ring is `{value, of}`; Revenue rings are pence excluding VAT and also carry `possible`. Format with `|pounds_compact`. The old `leads_registered` is gone. |
| `/approvals/` | GET, editor | `?status=waiting|approved|declined`, `?q=`, `?plan=`, `?page=`. `status`, `tabs [{status,label,count,active,url}]`, `counts {total,waiting,approved,declined}`, `rows [{id (user id), name, email, plan, plan_slug, month_pence (excl. VAT), sale, registered, status, decided_at, decided_by, href, approve_url, decline_url, undo_url}]`, `has_next`, `page`, `more_url`, `q`, `plan`, `plans`, `note`, `gold_waiting`, `gold_url`. Fragment: `_approvals_rows.html`. |
| `/approvals/<user id>/approve/`, `/decline/`, `/undo/` | POST, editor | Undo means back to waiting. Audited (`MembershipReviewEvent`: from, to, who, when). Never sends or changes anything for the member. A fetch gets `{ok, result (done|unchanged), status, name, row, counts, gold_waiting}`; otherwise a toast and a redirect (`from=<status>` returns to that tab). 404 for someone not on a Tier. |
| `/revenue/` | GET, editor | `revenue {vat_rate, gold_fee_pence, gold_fee_inc_pence, approved, waiting}`; each bucket has `count, year_ex, month_ex, year_inc, month_inc, avg_year_ex, avg_year_inc` (Decimal pence, exact: round only with `|pounds`) and `by_plan [{slug, name, kind (tier|gold), count, ...same figures}]` in plan order, Gold last. `waiting` is the Possible panel (never added to approved). Also `counts {memberships, gold}`, `empty`, `approvals_url`. |
| `/people/` | GET, reader | `?table=` (empty = both, `membership`, `gold`), plus the old filters. `tables [{key,title,rows,has_next,page,more_url,columns,empty}]`, `table`, first-table `rows/has_next/page/more_url/columns`, `counts {total,waiting,approved,declined,gold_members,registered_total}`, `approvals_line` (editor only: `{approved,waiting,declined,text,status,url}` or `None`), `total_registered`. Membership rows are approved people only; plan filters Membership only. Row `gold_application_id` is set only for an application that is not approved or declined; Gold rows have `gold_approved_at`. Fragment rows: `_people_rows.html` or `_people_gold_rows.html`. The CSV (`/people/export.csv`) still exports everyone. |
| `/leads/` | GET, reader | `tiles {leads_total, registered_total}` (true totals), `more_url`, `?emailed=1`, rows have `emailed_at` (empty when bounced: `bounced` is the Possible fake). Archived rows: `archived.by` reads "Group email" for the group send. Hot tile and the went-on-to-register figure are gone (`?hot=1` still works for the Home link). |
| `/outreach/` | GET, reader | Tabs are only `open` and `done` (`states`, `tabs`, `counts {open,done}`, `open_count`, `done_count`); `?state=registered` falls back to open. `?emailed=1`, `emailed` in context. Rows add `emailed_at`, `bounced`, `is_lead`, `to_leads_url`, `archive_url` (the last two empty for a person or Gold row, which keep `remove_url`). |
| `/outreach/<id>/to-leads/` | POST, editor | Back to Leads (lead entries only). Answer carries `undo {url, email, reason, archived}`. |
| `/outreach/<id>/archive/` | POST, editor | `reason` optional (300). Archives and takes him off the list. Same `undo`. |
| `/outreach/undo/` | POST, editor | `email, reason, archived`: puts him back on the list (un-archiving first). |
| `/gold/<id>/respond/` | GET, reader | 302 to `https://wa.me/<digits>` with a mobile, else to the Gold page with `?do=email`. |
| `/gold/<id>/contacted/` | POST, editor | Mark contacted (New becomes Contacted, audited as before). |
| `/leads/<id>/contact/`, `/people/<id>/mobile/`, `/gold/<id>/mobile/` | POST, editor | Add or fix a number or first name, unchanged in behaviour, now in `office.views_tools` (fetch answers `{ok, result, errors}`). |
| `/manifest.webmanifest`, `/sw.js` | GET, public | The installable app. |
| lead, person and Gold pages | | `whatsapp` context is now `{state ("mobile"|"none"), wa_link, has_mobile, mobile, first_name, edit_url, can_edit, can_add_number, reason}`. `_wa_button.html` is a plain link. |

Gone: `/whatsapp/...`, `/people|leads|gold/<id>/whatsapp/`, the push endpoints, `/twilio/...` webhooks, System > WhatsApp, the Notifications row of the person menu.

### Public site
| URL | Notes |
|---|---|
| `/add-number/<token>/` | GET and POST, no sign-in, noindex, rate limited (30 an 10 minutes an address, rolling). Context `state` (`form|done|used|ended`), `email` (read only), `form`, `mobile_countries`, `country`, `consent_text`, `whatsapp_url`. Tampered and expired links are both `ended` (400, same words, no address shown). A taken number is a plain error on `mobile`. A person who registered meanwhile, or who already has a number, is `used`: nothing changes. |

### System
- Automatic email edit form: `sender_user` select replaces the Site/Person radios (`form.sender_user`, `footer.sender_note`, `footer.reply_to`). Mailing form: `sender_user`, `archive_no_number`, `sender_note`. `GET /emails/mailings/<id>/confirm/` adds `moves {stay, archive, reason, bounced}` for a leads send that archives, and the From and Reply-To follow the chosen sender. Previews return `reply_to`. The starter "Barry's invitation" (`start=barry_invitation`) fills subject, news, leads and the switch; its button is `link: personal_add_number`; text placeholders `{whatsapp_number}` and `{add_number_link}` work for the leads group only.
- **For the frontend:** the group-send parts editor lists a button's link kinds in its own script; add `personal_add_number` ("Add-your-number link", each lead's own link) beside the two personal ones. The server already accepts it, needs no web address for it, and refuses it (and `{add_number_link}` / `{whatsapp_number}`) for any group but Journey leads. The Waiting/Approved/Declined `.o-seg--counts` tabs, the `data-press` feedback and the Home ring markup are not built server side.
- **Staff adding a number** to a lead the group email archived ("Emailed, no number") also moves him out of Archived to the approach list (`outreach.services._number_arrived`); a lead archived by a person is left where he is.
- The single "person sender" settings are removed from System > Emails. The old columns stay until the script has run: `manage.py migrate_person_sender --dry-run`.

### Models and settings
`office.MembershipReview` (one per `InterestRegistration`, status, by, at; no row means waiting), `office.MembershipReviewEvent` (audit), `mailings.Mailing.sender_user` and `archive_no_number`, `notifications.NotificationTemplate.sender_user`. New snapshot page `counts` in `OfficeSnapshot`. No new env vars; removed: `TWILIO_*`, `VAPID_*`, `FFMPEG_BIN`.

## Built, UI (2026-11-05, `feature/office-2`)

The pages follow `office-2-design.md`. What is where:

- **Phone Home:** `dashboard.html`, `_ring_fig.html`, `office-cards.css`. Three `o-pair` cards (Waiting, Approved, Revenue), two rings each, Gold left, Memberships right. Rings link as the design says; Revenue is one link card. `share_arcs`, `ring_of`, `ring_of_pounds` in `office_tags.py` draw and word them. Greeting, Gold applications, The journey (rings card), Waiting for you and Hot leads are hidden below `64em`, the page range bar is gone and `office-swap.js` (`phoneHome`) asks for `range=all` below `64em`, so a saved range cannot stick (the server remembers All in the session, as any range). The arcs draw once a session (`office-dashboard.js`, `data-draw`). The Office dashboard opens on All time by default on every screen (System: Dashboard: default range still changes it for a computer).
- **Phone tabs and menu:** `base.html`. Five tabs (Home, Approach, Analytics, Leads, Revenue) by CSS `order` on `data-nav-slot`; rail-only items carry `data-nav-wide`. No More sheet, no tab badges. `body[data-under-home]` lights Home on Approvals, Registered, Gold and Invited. Person menu: Registered, Gold (count), Invited, then Change password and Sign out. People without `can_see_all` keep a Gold tab. New icon `i-coin`; the chat-only icons are gone from the sprite.
- **Revenue:** `revenue.html`, `_revenue_grid.html`. Total card, one card per plan, the Possible panel in a different material, a note; a table replaces the plan cards from `64em`.
- **Approvals:** `approvals.html`, `_approvals_rows.html`, `office-approvals.js`. A table that becomes cards on a phone. A decision is sent in the background and the row is replaced in place by an Undo strip of the same height (measured without the press scale); counts update; a polite line announces it; a failure says so and changes nothing. Back to waiting on the other two tabs.
- **Registered:** `people.html`. The approvals line, a counts switch (All on a computer; Membership and Gold, one table at a time, on a phone), two tables, "Applied" tag only for a pending application. Each table's Show more carries its own `table=`.
- **Leads and Approach list:** two tiles, Emailed and Possible fake pills, Emailed chip, Back to Leads and Archive on each lead row with Undo (`office-tools.js`), the Archive dialog on the page, Add to list as a quiet link.
- **Lists that load themselves:** `office-more.js`, `_list_foot.html`, `_more_inner.html`, `office-press.css`. An IntersectionObserver on the Show more row (600px ahead), three breathing dots after 150ms (the word Loading under reduced motion), "That is everyone." from the server on the last page, "Could not load more." with Try again, bottom padding clears the tab bar. Applies at every width, to every long list, and only when one list is on screen (Registered's two stacked tables on a computer keep Show more). Show more stays as the no-script link. Back from a person: the loaded page count and scroll position are kept in `history.state` and restored; a filter change starts over. Rows that leave a list (decided, done, archived) are counted (`data-left`) and sent as `?shift=N`, which Approvals, Leads and the Approach list honour, so the next page does not skip anyone. Assistant answers rows for the fetch (`_chats_rows.html`).
- **The press:** `office-press.js`. `pointerdown` adds `.is-pressed` to the closest `[data-press]` (waits 40ms so a scroll never flashes it, then stays at least 120ms; `pointercancel` clears it). Controls inside a row do not press it. Rows with no link have no press.
- **WhatsApp button:** plain `wa.me` link beside Email (two columns on a phone, stacked in the computer rail); no mobile means Email fills the row with one muted line. All old chat CSS, JS, icons and nav are gone (grep clean).
- **System:** sender select styled in `system-emails.css`; the group send confirm shows who stays and who moves (`se-moves`); the parts editor lists `personal_add_number`; Team > Email has no Inbox field.
- **Add-your-number page:** `mailings/add_number.html` uses the sign-in form column (`signin-fields`); on a phone the picture steps aside so the button clears the fold at 375 by 667.

### Departures from the design
- Auto-load runs on a computer too (the brief asked for it), except where two lists are on screen.
- The approvals list is a table (cards on a phone) rather than a list of cards, so the same row and list code serves it.
- Each ring link covers the ring and its three lines; the card title is not a target.

### Seen and not seen
Seen in Chromium (`--single-process --no-zygote --disable-gpu`) against a throwaway server and database, at 375 and 1440: Home, Revenue, Approvals, Leads, Registered, Approach list, add-your-number, a lead page, the System group send form. No sideways scroll on any, no console errors other than the known view-transition message. Clicked on a phone size: range stays All, approve and undo (strip height, counts), Leads loads by itself and Back returns to the row, the pressed tone, add-your-number saved a number and moved the lead to the Approach list. Not seen: a real iPhone, the group-send confirm modal itself, the Back to Leads and Archive toasts, the bounce return, and the new e2e walks (see `e2e.md`).


## Leads: Possible fakes tab (2026-11-10)

- `?view=fakes` on Leads, a tab beside Archived with its count (stored in the counts snapshot as `fakes_total`). A lead is a possible fake when his address has a permanent bounce on the suppression list (a complaint does not count) and he is not marked genuine. The bounce webhook decides; no cron. Archived wins; a lead on the approach list is in neither.
- Main Leads, its total and the Home tile leave fakes out (`lead_queryset(fakes="out")`). Correcting the email takes him out of the tab by itself: the new address has no bounce row.
- Same search, sort and CSV as Archived. Mark as genuine (row and lead page, only while he is a fake and not archived; Archive's permission) and Undo on his page: see the bounce section of office-outreach.md. Hot leads, Home's new-leads figure and Analytics' leads total leave fakes out too (`fakes="out"`); only Analytics' new-leads count and the insights still include them.

## Activity (2026-11-11)

- `/activity/`, Developer level and above only: one read-only list of every staff action, filterable by staff member, type and dates. See office-activity.md.
