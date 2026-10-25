# Feature: Sales

Decided 2026-10-25 (PROJECT.md). Not built yet. Own branch after Approval and Emails.

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
