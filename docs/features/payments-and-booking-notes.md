# Payments and booking: robustness notes

Status: **notes for later phases** (Stripe payments, booking system). Decided by Moishe 2026-10-29: "no double payments, no double bookings". Read this before building either phase.

## What already exists (payment window branch)

- Per member: sale snapshot (sale, %, months, locked at), payment status, invite/reminder sent times, `sale_expired_at`.
- A subscription record. Its `source` is `manual` (staff set it up for direct payers) or `stripe` (later). There is one active subscription per member, enforced by a DB constraint.
- `mark_paid()` / lock-in is a single service with an idempotency key. Stripe webhooks must call it and must never write the fields directly.

## Payments (Stripe phase)

1. **Idempotency keys on every Stripe call** that creates something (Checkout Session, Customer, Subscription). The key comes from our own record, e.g. `sub-<registration id>-<window id>`. Retries and double clicks then return the same object.
2. **Checkout Session per attempt, reused.** If a member has an open, unexpired session, send them back to it. Never create a second one.
3. **The webhook is the source of truth**, not the success page. Use `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed` and `customer.subscription.updated/deleted`.
   - Verify the signature (`STRIPE_WEBHOOK_SECRET`).
   - Store each event id in a `StripeEvent` table with a unique id, and skip any event already seen. Stripe sends events more than once and out of order.
   - Do the work in a transaction with `select_for_update()` on the member's subscription row.
4. **Unique constraints in the database:** `stripe_customer_id`, `stripe_subscription_id`, `stripe_event_id`, and one active subscription per member. A lost race fails safely instead of duplicating.
5. **The button disables on click, and the server is idempotent anyway.** UI guards alone never count.
6. **Money is stored in integer pence** with a currency, never floats.
7. **Manual subscriptions:** the agreed price is for the record and invoicing. Stripe must never charge a member who has an active manual subscription. Check this before creating a session.
8. **Reconciliation job, nightly:** compare active Stripe subscriptions against ours and flag mismatches in System. Report only; it does not fix automatically.
9. **Refunds and cancellations** go through one service and are audited. Follow the cancel and pause rules in `SPA99_RULES.md`.
10. **Tests mock Stripe.** Cover: a duplicate webhook does nothing, out-of-order events end in the correct state, a double submit creates one session, and a manual subscription blocks checkout.

## Booking (booking phase)

1. **One slot, one booking, enforced in the database.**
   - Use a unique constraint on (resource, slot start) for exclusive resources.
   - For capacity slots, use a row lock on the slot (`select_for_update()`) and a count check inside the transaction.
   - Never "check then insert" without a lock.
2. **Holds:** a short hold (e.g. 5–10 minutes) while the member confirms. Holds expire with a job and are never extended silently.
3. **Idempotency on confirm:** the form carries a one-time token, so a second POST returns the same booking.
4. **A member cannot double book** overlapping times. This is a server-side check inside the same transaction.
5. **Lockers** are assigned at booking (as the assistant already tells visitors). Assignment uses the same lock as the slot.
6. **Cancellations and no-shows** follow `SPA99_RULES.md`. Every state change is audited.
7. **Times:** store UTC and show Europe/London. Test the clock-change weekends.
8. **SQLite vs Postgres:** `select_for_update()` is a no-op on SQLite. SQLite serialises writes, so the same code stays safe on both. Run the concurrency tests in CI on Postgres.

## General

- All money and booking writes go through services, never views or admin saves.
- Every create action is audited (who, when, source).
- Backfills are scripts with a dry run, never migrations.
