# Office outreach: guide, sticky notes, Barry's list, messages, leads tidy

Status: agreed 2026-11-03, building on `feature/office-outreach`. Decisions in PROJECT.md (2026-11-03 rows).

## 1. Send the Gold Card guide

- **The guide** is a PDF uploaded in **System** (a file field on the site settings or a small single-row model, default storage: S3 on live, `.private/media` locally). Replace any time; no release needed. The first file is `SPA99_Gold_Card_Guide.pdf` (local copy in `.private/incoming/`, git-ignored; Moishe uploads it on live).
- **Gold application, Decision card:** the **Add note** button becomes **Send guide**. It opens a short confirm (or a sheet with the editable message) and emails the applicant **from the site sender (hello@spa99.uk, `DEFAULT_FROM_EMAIL`)** with the PDF **attached**. Reply-To is the contact address.
- The email text is an **editable template** (System > Emails), key `gold_guide`, short and on brand.
- Allowed in **any** status (new, contacted, awaiting final, approved, declined). Sending is recorded in the application history ("Guide sent by X") through `gold.audit.record`, with a duplicate-submit guard like Respond.
- No guide uploaded: the button is disabled, with the hint "Upload the guide in System".
- Sent through the queue (`common.tasks.enqueue`), like the other Gold emails. Postmark tag `gold-guide`.

## 2. Sticky notes (one set per person: lead page, person page, Gold application)

- **Notes belong to the person, not the page** (Moishe, 2026-11-03). One note model keyed by the **lower-cased email**. The same notes show on the lead page, the person page and the Gold application of that person, and they carry over automatically when a lead registers (same email). Where the Office already links several addresses to one person (`office/profile.py` person identity: account email, linked lead emails, Gold application email), a page shows the notes of **all** that person's addresses; a new note is stored on the page's main address (account email if there is an account, else the lead or application email).
- Notes are their **own records**, not history items. Fields: email (lower-cased, indexed), text (≤ 1000), author, created_at, deleted_at, deleted_by, optional source link (gold application id) for the backfill.
- **Desktop (64em and up):** notes are **pinned** on the page as small sticky notes (a calm, on-brand "note" look: designer decides, brand tokens only), newest first, near the top of the page. An **Add note** button sits on the notes area (this is where Add note moves to, out of the Decision card).
- **Phone:** a **Notes** button (with the count) opens a sheet with the notes and Add note.
- **Delete:** an **x** appears on hover (always visible on touch screens), with a light confirm. A deleted note leaves the board; the **history keeps a record**: "Note deleted by X" with the note text, in the Gold application history or the person's timeline.
- Adding a note is **not** a history item any more (the note itself is the record).
- **Existing notes:** Gold `NOTE_ADDED` events become sticky notes through a **separate script with `--dry-run`** (management command `backfill_site_data` style rule: never in a migration). The old events stay in the audit table but are no longer shown as history lines once copied.
- Permissions: whoever can open the page sees the notes; adding and deleting need the same rights as the current Gold Add note (approver) or Admin and up (backend to confirm and say).

## 3. Leads: registered people leave the list

- An address that belongs to a registered account is **not a lead**. The Leads list, its count, tiles and CSV cover only addresses with no account. Registered people are in People.
- Remove the Show filter (lead / registered / all) and the `leads_show` default in System > Defaults. The Status column keeps applied / Gold where relevant.
- Snapshot figures that say "Leads" follow the same rule (rebuild after deploy if needed).

## 4. Barry's list (outreach)

- A new Office page: a list of people for Barry to approach. Its **name comes from System** (`outreach_list_name`, empty by default; while empty the Office shows "Approach list").
- **Add to list** button on: the lead page, the person page and the Gold application page (and a row action where it is cheap). Optional short reason when adding.
- One entry per person (by account, or by lead address, or by Gold application). Fields: who (link), reason, added by, added at, done_at, done_by.
- The page: name, contact (email, mobile if known), where from (Lead / Person / Gold), reason, added by and when. Actions: **Mark done** (moves to a Done filter) and **Remove**.
- Visible in the rail and the phone More sheet to everyone who can see Leads.

## 5. Message a lead or a person

- **Email** button on the lead page, the person page and the Gold page (beside WhatsApp; Respond on Gold opens WhatsApp or this pop-up): one text box, sent **From the logged-in person** (their sending address, hello@spa99.uk as the fallback) with Reply-To their address, through the queue. See `whatsapp.md` ("Email button").
- Editable template key `office_message` (the typed text goes inside the branded layout).
- Recorded in the person's or lead's timeline ("Message sent by X" with the text).
- An unsubscribed person can still get a one-to-one message (it is not marketing); the sheet shows "Unsubscribed from news" as a warning.
- Duplicate-submit guard.

## 6. Gold rules (not final)

- The guide (2026-11) changes the Gold Card: £199 per person per year; visits are earned through qualifying business (FM £2,500 invoices = 1 visit; ANPR new car park = 1 visit; lending £200,000 = 1 visit); approved by the CEO. The site copy still describes the old Gold. **No change yet**: Gold is hidden (System > Plans, Visible off). To revisit when Moishe finalises.

## Answer given to Moishe (2026-11-03)

Registering needs a membership pick. The choices are the visible monthly plans in System > Plans (not hard-coded); that a pick is required is in code (`users/forms.py`, `plan` field).

## Deploy steps

See `docs/GO-LIVE.md`, section "Next release (Office outreach ...)": snapshot, migrations, the post-deploy order and the rollback.

## Acceptance checks

1. Send guide: email queued with the PDF attached, From = `DEFAULT_FROM_EMAIL`, Reply-To = contact; history line added; double submit sends once; disabled with no guide.
2. Sticky notes: add, show pinned (desktop) and in the sheet (phone), delete leaves a history record with the text; non-permitted users get 403.
3. Backfill dry run lists the Gold notes it would copy and changes nothing; the real run copies each once (re-run copies nothing).
4. Leads: an address with an account never appears in the list, the CSV or the count.
5. Barry's list: add from all three pages once (second add says it is already there), mark done, remove; page title follows the System name.
6. Message: email queued, timeline entry, unsubscribed warning shown.
7. Works on SQLite and Postgres; tests mocked; CI green.

---

# Round 2 (agreed 2026-11-03, same branch)

## R1. Sort by clicking a table header
- Every Office list table: Leads, People (renamed Registered), Gold, Approach list, Invited, Chats. Click a header to sort by it; click again to reverse. The active header is highlighted with a small arrow; `aria-sort` set. Sorting is **server side** over the whole list (paging keeps working), URL params `sort=<key>&dir=asc|desc`, whitelisted keys per list, unknown keys fall back to the list default.
- Columns built from several values (summary, answers, badges) are not sortable. Real columns are: name, email, mobile, best fit / membership, potential, source / from, reason, added / last seen / first seen / registered date, status, visits, etc. (per list, backend decides which are cheap and portable).
- Leads' existing sort select is replaced by the headers; the System default `leads_sort` stays as the default order.
- SQLite and Postgres alike (no Postgres-only collations; nulls last).

## R2. Renames
- Leads column "Suggested" becomes **Best fit** (also CSV header label and filter label).
- **People becomes Registered** everywhere people see it (nav, phone tab bar, titles, headings, buttons, empty states, dashboard tiles that say People). URLs stay `/people/`.

## R3. Long text wraps everywhere
- Nothing sticks out of its box: history, timeline, notes, reasons, chats, messages, emails, addresses (long email addresses too). A shared rule in `common` CSS (overflow-wrap: anywhere on text containers in cards and tables).
- Long reasons (Approach list) and long history/timeline messages show **2-3 lines** with "Read more" (reuse the note clamp pattern). Reason max stays 300 characters; typing more is refused with the count shown.

## R4. Delete a Gold application
- Admin and up only, on the Gold application page, with a confirm ("Delete G-1234? This removes the application and its history. It cannot be undone."). Deletes the application and its events. Notes (they belong to the person's email) stay. The deletion is recorded in the System change log (who, when, reference, applicant email). For tests and junk.

## R5. Approach list: Registered tab
- Tabs **Open / Registered / Done**. An open entry whose person now has a verified account shows under Registered with a tag "Registered 4 Nov" (date the account was verified). Barry marks him done as usual. Done shows everything marked done. Counts per tab.

## R6. Archived leads
- **Archive** button on the lead page (and a row action where cheap): the lead leaves Leads, its counts and tiles, and the auto email (if not sent yet). Kept in the system. An **Archived** view (a filter on Leads) lists them with **Move back**. Optional short reason. Recorded in the lead's timeline ("Archived by X", "Moved back by X").
- An archived lead who registers simply becomes a Registered person (archive no longer matters).
- Same permission as other writes (`can_edit`).

## R7. Next-morning email to new leads, from Barry
- **Who:** every new lead (gave his email at the journey gate, which carries the tick "Spa 99 may email me about opening"). Once per address, ever.
- **When:** the next 10:00 Europe/London at least 8 hours after the email was given (2:00 sign-up: 10:00 the same day; 9:30: 10:00 the next day; 23:00: 10:00 next day). DST-safe.
- **Skipped** at send time if: he has a verified account by then, he is archived, the address is opted out (EmailOptOut / unsubscribed), it hard-bounced before, or the switch is off. Skips are logged, not retried.
- **From:** a sender set in **System** (new settings: "Automatic emails sender name" and "address", e.g. Barry Lobenstein / barry@spa99.uk). Validate the address is on the site's sending domain (same domain as DEFAULT_FROM_EMAIL); empty = the switch cannot be turned on. Reply-To = that same address (replies reach Barry).
- **Text:** editable template (System > Emails), key `lead_next_morning`, with {first_name} where known (often not known) and the unsubscribe link/header like other marketing-type emails. Postmark tag `lead-next-morning`.
- **Switch:** System setting "Send the next-morning email to new leads", **off by default**.
- **Timing is set in System** (Moishe, 2026-11-03): "Send at" (time of day, London, default 10:00) and "At least ... hours after" (default 8, 0 to 48). The due time is the next "Send at" that is at least that many hours after the email was given. Changing them applies to leads not sent yet (due time recomputed at send-check time, or stored and recomputed on save: backend decides, simplest correct).
- **How:** a scheduled job (django-q schedule, the same mechanism the rollups use) runs every 15 minutes and sends what is due; each send is recorded (per address: due_at, sent_at or skipped_at + why) so it never sends twice, even with two workers (row lock / unique constraint).
- Shown on the lead page timeline ("Next-morning email sent" or "skipped: archived").

## Acceptance (round 2)
1. Sorting works on every list both ways, with paging, on SQLite and Postgres.
2. Renames visible everywhere; no "People" left in Office UI copy (URLs unchanged).
3. A 2000-character note, reason or history line wraps inside its box at 375 and 1440.
4. Gold delete: Admin only (403 otherwise), confirm, gone from lists, change log row written.
5. Approach list: an entry moves to Registered when his account is verified; Done unaffected.
6. Archive / Move back: hidden from Leads and counts, visible in Archived, timeline lines written.
7. Next-morning email: due time maths (incl. DST change days), sent once, every skip rule, sender from System, switch off = nothing sent. Tests mocked.

## R8. Delete a note at once, restore from history (Moishe, 2026-11-03)
- The note x deletes **immediately, no confirm** (notes only; every other delete keeps its confirm). A short toast "Note deleted" appears.
- The history/timeline line "Note deleted by X" (with the text) gets a **Restore** button (`can_edit`): it brings the note back on the board (clears deleted_at/deleted_by, keeps its original author and date) and writes "Note restored by X". Restoring twice does nothing.

---

# Launch button (agreed 2026-11-03, same branch)

**System > Launch**: one page, one big button, that switches everything for opening in one go and explains every change first.

## What Launch switches (all four, Moishe 2026-11-03)
1. **Memberships page public** (`memberships_public` on): the page, its links and prices open to everyone; Register no longer needs the questions.
2. **Email gate off** (`journey_email_gate` off): the questions show the suggested membership and price without asking for an email. (Consequence shown on the page: no new leads from the questions after launch, so the next-morning email stops getting new people.)
3. **Wording: Join** (`join_wording` = `join`).
4. **Open payments** (`plans.payments.open_now`): every registered member gets the "set up your membership" email and the window (System > Defaults days). Big step, cannot be taken back.

## The page
- Before launch: a plain list of **every change**, each as "Now → After launch" with one line of what visitors and members will notice. It is built from the live settings, so a step already in its after-state shows "Already on" and is skipped.
- **Checks** above the button (warn, never block unless noted): visible monthly plans with prices; payment emails present in System > Emails; `ONLINE_PAYMENTS_LIVE` false shows the existing warning ("members will be told we will be in touch"); a payment window already scheduled or open shows (Launch then does not open another); how many members will be emailed (count).
- **Button**: "Launch Spa 99". Confirm dialog: type `LAUNCH` to enable the final button. Developer level (same as other risky System changes) and the System unlock, like other risky switches.
- **On press**: all setting changes in one transaction, then `open_now` (it has its own lock and is idempotent). Each change is written to the System change log as normal; plus one "Launched Spa 99" entry. `SiteSettings.launched_at` and `launched_by` are stored.
- **After launch**: the page shows "Launched on 12 Jan 2027 at 10:04 by Moishe" and the list of what changed. No "un-launch" button: each switch can still be changed on its own page (payments cannot be unsent; the page says so).
- The System dashboard "Stage switches" panel gets a line "Launch: not yet / Launched 12 Jan".

## Acceptance
1. One press flips the three settings and opens payments once (double click or two tabs: once).
2. Already-on steps are skipped and shown as such.
3. Non-Developer or locked: 403 / unlock prompt.
4. Change log rows written; launched_at set; page shows the after-state.
5. Tests mocked (no emails really sent).

## R9. Edit a note by clicking it (Moishe, 2026-11-03)
- Clicking (or Enter on) a note's text turns it into the same inline editor as Add note, pre-filled; Save (Ctrl/Cmd+Enter) or Cancel (Esc). Only for people with `can_edit`; others see the note as now. The delete x and Read more keep working.
- Saving keeps the note's author and date, sets `edited_at`/`edited_by`, and the meta line reads "Moishe, 3 Nov · edited". Same 1000-character limit; empty text is refused (delete instead). No change = nothing saved.
- The history keeps the old text: a `NoteEvent` "Note edited by X" with the previous text in the person/lead timeline, and a Gold event `note_edited` where the delete line goes today. No Restore on edit lines (out of scope).

---

# Email flexibility (agreed 2026-11-03, same branch / PR #42)

Moishe wants automatic emails fully editable in System.

## E1. Shared footer (all emails)
- System > Emails gets a **Footer** tab: three lines, each editable, with a live preview (desktop/phone) like the email edit screen:
  - Brand line (default "Beyond Luxury"),
  - Address line (default "{site_name}, {address}"),
  - Contact line (default "Questions? Reply to this email or write to {contact_email}.").
  Placeholders: {site_name}, {address}, {contact_email}. A blank line = that line is left out. Reset to default per line.
- Stored in one row (SiteSettings fields or a small single-row model), history + change log like other System edits. db_default on every new column (rollback rule).
- The **unsubscribe link and "why you get this" notice are never editable or removable** (legal); they stay under the footer.

## E2. Per email (each automatic email's edit screen)
- **Footer:** Shared footer / Shared without the contact line / Custom (its own three lines, same placeholders).
- **Sender:** Site sender (hello@, `DEFAULT_FROM_EMAIL`, Reply-To the contact address) / Person sender (the "Automatic emails sender" name+address set in System > Emails; Reply-To the same). Person sender needs that address set, else the screen says so and it falls back to the site sender at send time (logged).
- **Heading** (the big line at the top; blank = the default) and **button text** (only for emails that have a button; blank = default).
- Defaults keep today's behaviour exactly; `lead_next_morning` defaults to Person sender + shared footer without the contact line (replaces the hard-coded `NO_CONTACT_LINE`).
- Preview and "send me a test" use all of these. Reset puts everything back to the defaults.
- Emails whose layout is a real application (non-editable specs, e.g. the Gold approver emails with their own .txt) are out of scope; the screen already says they are not editable.

## Acceptance
1. Footer edits show in every automatic email (html and text) and in previews; blank line removed; unsubscribe/notice always present where they were.
2. Per-email footer modes, sender choice (From/Reply-To headers), heading and button overrides work in send, preview and test.
3. No change in any email's output until someone edits (defaults = current output; snapshot-style test on a few emails).
4. Next-morning email unchanged from today's behaviour by default.
5. Change log rows; db_default on new columns; tests mocked.

---

# Bounced lead emails (agreed 2026-11-03, on feature/whatsapp)

When a lead's email address has a **permanent bounce** (it is on the suppression list as a bounce; spam complaints do not count):
- **Leads list:** the row shows a tag **Possible fake**. A Leads filter is optional, only if cheap.
- **Lead page:** a clear notice near the top: "This email bounced, so it may not be real. Remove the lead if it looks like spam, or correct the address if it's a typo and resend the follow-up."
- **Correct the email** (`can_edit`, audited in the timeline): updates the address on his journeys. It is also reachable without a bounce: the lead page's Details row (Reach out card) has Email, Change, which opens the same dialog titled "Change the email" (see whatsapp.md, Details rows); the first name and mobile Change are there too. Refused if that address already belongs to another lead or an account (say whose). The bounced address stays on the suppression list. The tag goes because the new address is clean.
- **Resend follow-up:** after a correction, one button sends the next-morning email to the new address straight away (from the System sender, once per address, recorded in his timeline). Works with the automatic switch off, but needs a sender address set; otherwise the button explains. No resend while the address is still bounced.
- **Remove the lead** stays as it is today, and Archive stays available.
- Figures: a Possible fake lead still counts until removed or archived.
- Tests mocked.
