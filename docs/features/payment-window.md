# Feature: Payment window

Decided 2026-10-29 (PROJECT.md). Branch `feature/payment-window`. **Status: built (no card payments: Stripe is the next phase and plugs into `mark_paid` and `Subscription`).**

## What it is
No payment is taken at registration. When Spa 99 is ready, staff open payments from **System > Payments**. Every registered member gets one calm email and a window (default 14 days, System > Defaults) to set up a paid membership; one gentle reminder a few days before it closes. Members who registered during a sale keep its price (stored on their registration) if they set up inside the window. After it closes unpaid, the sale price ends, the snapshot stays on the row, the account stays, and they can join at the normal price. Wording is a suggestion, never a threat.

## Data (`plans`, `users`)
- **`plans.PaymentWindow`** (history): `status` draft | scheduled | open | closed | cancelled (`cancelled` is an addition: a scheduled opening that was called off), `scheduled_for`, `opened_at`, `closes_at` (end of the last day, London time), `closed_at`, `window_days`, `opened_by`, `reminder_sent_at`, `is_active`. One active (scheduled or open) window: conditional unique index on `is_active`.
- **`InterestRegistration`** gains `payment_status` not_started | invited | paid | lapsed, `payment_source` (stripe | manual), `payment_invite_sent_at`, `payment_reminder_sent_at`, `paid_at`, `sale_expired_at`. Status changes are in its history.
- **`plans.PaymentNotice`**: one email owed per (window, member, kind invite|reminder), unique; doubles as the send queue (queued, sending, sent, skipped, failed).
- **`plans.PaymentMark`**: idempotency record (`idempotency_key` unique) for `mark_paid`.
- **`plans.Subscription`** (history): `registration`, `plan`, `source` manual | stripe, `status` active | cancelled, `start_date`, `agreed_price_ex_vat` (record and invoicing only; may differ from list), `billing_note`, `external_id` (nullable, unique: Stripe later), `created_by`, `cancelled_at/by`. One active per member: conditional unique constraint.
- **`plans.PaymentStaffAlert`**: unique (window, day).
- **System > Defaults**: `payment_window_days` (14, 3-60), `payment_reminder_days_before` (3, 1-30), `payment_staff_alert_days_before` (7, 1-60), `staff_alert_emails` (comma list, up to 5, validated, empty in code).

## Rules (`plans/payments.py`)
- **Who is in it:** active accounts with a confirmed email, any plan (Gold included). Unconfirmed members are not emailed (an unproven address is not his); they are counted on the page and join the window when they confirm (the job picks them up).
- **Open now** (`open_now`): under a lock, finds an open window and does nothing (so a double click or two tabs open once); else opens (a scheduled one is converted), creates one invite notice per member, marks them `invited`, queues the send. **Schedule** (`schedule`, London time, at least a minute ahead) / **cancel schedule** / **close early**.
- **Send**: background slices (paced like group sends, SES gate checked, suppression guard and `EmailLog` through `send_templated`). A notice is claimed (queued to sending) before sending, so two workers never send twice; a dead send is marked failed, never retried.
- **Job** `plans.tasks.tick` (every 5 minutes, `register_schedules`): opens a due scheduled window; for an open one: closes it at `closes_at`, adds members who confirmed since, starts the one reminder when due (skipped if the window is shorter than the reminder lead), warns staff, sends what is queued.
- **Close**: invited and unpaid members become `lapsed`; those holding a sale get `sale_expired_at`. Paid members (online or manual) are untouched. Queued emails are skipped. Idempotent. Kept price is hidden once expired (`kept_price` returns None), the snapshot is never deleted. No email on close.
- **`mark_paid(registration, source, key=None)`**: idempotent on `key`; sets paid, source and `paid_at`; for the Stripe webhook later (pass the event id). `lock_in` is the same call for a set-up that is not a card payment.

## Emails (System > Emails, editable, seeded by `seed_phase1`)
`payment_window_open` ({first_name}, {closes_on}, {sale_line}, button to the member area), `payment_window_reminder` (same), `payment_staff_alert` (to the alert addresses only).

## Staff lapse warnings
From `payment_staff_alert_days_before` until it closes, while launch-price holders are invited but not set up: once a day (unique window + day) an email lists them with links to their Office pages, to **only** the addresses in System > Defaults > Payment alert emails. Empty field: no email, the in-app notice still shows (Office dashboard for Admin and up, System > Payments) with a gentle "No alert email set" flag on Payments and Defaults. `seed_phase1` fills `moishe@spa99.uk` only when the field is empty (`INITIAL_STAFF_ALERT_EMAIL`, one line). No address is in app code.

## Manual membership set-up (Office person page, Admin and up, audited)
For members who pay directly. Creates a `Subscription` (source manual) and calls `mark_paid(..., "manual")`, so the sale price is kept and the close job never lapses them. Edit and cancel later (history on the subscription; cancelling returns the member to invited/not started; nothing is charged or refunded). Events `setup_manual`, `setup_cancelled` in the audit log.

## Screens
- **System > Payments** (Developer, unlock): status, dates, email counts, member counts (registered, sale holders, invited, paid online, set up manually, at risk, lapsed), Open payments now (confirm: "This emails N members"), Schedule for, Cancel schedule, Close early. Events `payments_opened`, `payments_scheduled`, `payments_closed`, `payments_cancelled` (section Payments).
- **Site copy**: Register, My Spa 99 membership and the "check your email" page: "No payment is taken now. When we open, you'll have 2 weeks to set up your membership." plus "For a special discount, WhatsApp us" (SiteSettings.discount_contact_url; left out when blank).
- **Office**: People list columns and filters "Sale price" (holds, none, ended, at risk) and "Payment"; person page card "Sale price and payment" (name, %, months, locked at, kept/ended, payment status and history, manual membership); CSV export (Admin+) has sale and payment columns.
- GDPR: export includes payment state, notices and subscriptions; erasing a person cascades them and removes subscription history.

## Not Postgres-only
Plain ORM, conditional unique constraints, `select_for_update` (ignored by SQLite), `bulk_create(ignore_conflicts)`. Run on SQLite locally; CI covers Postgres.

## Env vars
None new.

## Update 2026-10-29: two sale modes, Gold, restore
- **Before payments open:** a sale is register-only; the price is kept for the window (snapshot), as above.
- **After payments open (window open or closed):** a new registrant gets the `payment_window_open` email when they confirm their email (the job picks them up), so they can set up straight away. **No personal window, no due date, no lapse timer, no reminder** (`payment_due_at` stays empty; the close and lapse logic only touch members who have one). A sale running then does **not** snapshot a kept price (`plans.sales.snapshot_fields` and `register_offer` check `payments.opened_ever()`); the sale price is applied at checkout in the Stripe phase. Until then staff use the manual set-up, which records the agreed price. The email's `{window_line}` ("You have until ... ") is empty for them. Register copy after opening: "Payments are open. Set up your membership from your member area." Edge: someone who registered before opening but confirms later, while the window is still open, shares the window's end.
- `InterestRegistration.payment_due_at`: the member's own due date (the window's end for those invited at opening; a restored price gets a new one). The close job (`lapse_due`), the reminder and the staff warnings all use it. Early close lapses everyone who has one.
- **Gold members** are in the window, the counts, the emails and the alerts like everyone (Gold pricing). Manual set-up allows the Gold plan.
- **Restore a lapsed sale price** (Office person page, Admin and up, reason required): clears `sale_expired_at`, sets a new due date (now + window days), puts a lapsed member back to invited; event `sale_restored` (who, why, when) in the audit log.
- **Imported invitees** follow the normal rule: a snapshot only if they register while a sale runs and before payments open; nothing else grants it.

## Review fixes (2026-10-29)
- Cancelling a manual set-up: window open, back to invited with the window's end (none for someone who registered after opening); window closed, a sale holder gets their own due date; payments never opened, not started.
- Editing a manual membership is audited (`setup_edited`, old and new values; the billing note text stays on the subscription). The audit log carries the member's account ID (`public_id`), never an email; the restore reason is stored on the registration (`sale_restore_reason`) and its history, erased with the member.
- The job keeps running while the next window is only scheduled. Reminders use the newest invite's window and a restore clears the old reminder. A member confirming after an early close does not share the closed window's end.
- Staff warnings compare London dates (first alert on day 7) and go out from 09:00 London time. `staff_alert_emails_on` (default on) stops the emails without clearing the field; the seed fills the field only the first time (`staff_alert_seeded`).
- `ONLINE_PAYMENTS_LIVE = False` (settings): System > Payments warns before opening; the member pages say "we'll be in touch, or WhatsApp or email us"; set-up members see "Your membership is set up". The open email's first line is `{opening_line}`.
