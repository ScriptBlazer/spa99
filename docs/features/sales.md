# Feature: Sales

Decided 2026-10-25 (PROJECT.md). Built on `feature/sales` (see Built below).

## Setting a sale (System only)
- New System section **Sales** (Developer level, behind the unlock, logged with undo).
- A sale: name ("Christmas sale"), % off (1 to 90), which plans (tick Tier 1, 2, 3, single visit), starts at, ends at (London time), months at the sale price for someone who registers during it (e.g. 3).
- Preview on the site before it starts; **End now** button. Only one sale live at a time (overlaps refused).

## On the website
- A slim bar at the top of every public page while the sale is live: "Christmas sale · 20% off Tier 2 and Tier 3 · ends in 3d 04h 12m". Calm, on-brand (no flashing, no red, no seconds racing in big digits); the countdown ticks quietly, switches to hours and minutes on the last day. Dismissible for the visit.
- Appears at the start time and disappears at the end time on its own (pages read the sale on each request; the countdown ends client-side too).
- Registering during the sale stores the sale on the registration (name, %, months), so the price is kept when billing opens. The register and membership screens say the price they keep.

## Notes
- Payment is not taken yet: the sale price is recorded now and applied when billing starts.
- Everything logged (created, edited, ended).

## Built (backend)
- **`plans.Sale`** (in the plans app: it is pricing data for `Plan` rows): name, `percent_off` 1-90, `plans` (M2M), `starts_at`, `ends_at`, `months_at_price` 1-36, `ended_early_at`, `created_by`, simple-history. Window = `starts_at` to `ended_early_at` or `ends_at` (start inclusive, end exclusive). `Sale.clean()`: ends after start, at least one plan (existing rows), no overlap with another sale's window (an ended-early sale frees the rest of its time; one ended before it started has no window). No DB constraint (works on SQLite and Postgres); `plans.sales.save_sale` / `end_now` re-check inside a transaction under a row lock on the SiteSettings singleton (`select_for_update`, ignored by SQLite, which serialises writers).
- **Live-edit locks:** an upcoming sale is fully editable; a live one: name, end time and plans only (`percent_off`, `months_at_price`, `starts_at` locked in the form and in `Sale.clean`); an ended sale is read-only. Plans are logged as their own direct change (not undoable, history has no M2M).
- **`InterestRegistration`** gains `sale` (FK, SET_NULL), `sale_name`, `sale_percent_off`, `sale_months`, `sale_locked_at` (a snapshot: editing or deleting the sale never changes it). **Snapshot rule** (`plans.sales.snapshot_fields`, used by sign-up and `set_interest`): registering, or changing plan, while a sale is live and covers the chosen plan copies it; a person already holding a snapshot who moves to another plan the same sale covers keeps it (even after the sale ended); moving to a plan no sale covers clears it (history keeps it); nothing is added once the sale has ended; choosing the same plan again changes nothing. No backfill, no data in migrations.
- **System > Sales** (`/sales/` on the System host, Developer + unlock, 404 for everyone else): list (live, upcoming, past), new, edit (row token: 409 "Changed since you opened it"), **End now** (POST; an upcoming sale is cancelled instead), **preview link** (POST, signed, valid an hour; opening `/?sale_preview=<token>` on the public site shows that sale's bar in that browser's session for an hour). All saves go through the change log (section "Sales"). Undo of End now uses the normal change-log undo: refused if the freed time was taken or the original end has passed.
- **Public bar:** `sale_bar` template variable (lazy), public host only. **Member screens:** `kept_price` in the member context, `register_sale` on the register and choose-a-tier screens (the live sale only, never a preview).
- Money: `plans.sales.sale_price(plan, sale_or_percent, vat_rate=None)`, whole pence, half up.

## Built (frontend)
- **Bar:** slim bar above the header on every public page while a sale is live (`common/_sale_bar.html`, `sale-bar.css/js`): name, % off, plans, a quiet countdown (hours and minutes on the last day), dismissible for the visit, removed at the end time on its own. The tour page has no bar (deviation).
- **Price lines:** Memberships and Register show a calm sale line under the full price for covered plans (no strike-through). Choosing a plan the sale does not cover, or leaving a covered one, asks for a confirm only when it would lose the kept price (deviation: no confirm otherwise).
- **Kept price:** My Spa 99 membership page says what they keep ("You keep 20% off Tier 2 for 3 months from your first payment").
- **System > Sales:** list, new/edit with live preview of the bar and prices, locked fields on a live sale, End now with confirm, "Start now" (the server uses its own now, so a stale page never gives a past-start error).
- **Preview link:** signed, single-use, valid an hour; the first browser that opens it sees the bar for an hour ("End preview" link in the bar). Later opens of the same link do nothing.
- Wording for plan lists: "all memberships", "all memberships and single visits", "single visits".
