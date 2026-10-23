# Round 3: backend contract for the frontend (2026-10-23)

Services in `pages/services.py`, views in `pages/views.py`. Built by the backend; templates and CSS are the frontend's.

## /the-spa/ (view `spa`)
- `opener_lines`: list (0-5) of `{statement, note}` from `spa.opener_1..5`, placeholders `{hours} {closure} {rooms} {Rooms}` filled from data. A line missing a value is skipped; a note sentence missing a value is dropped.
- `opener`: `{upload, name, portrait, is_door, alt}`. `alt` = the upload's own alt (`intro.image_alt`) if uploaded, else per name (robe, door-gold, door-wide), else a generic one; templates use it, never their own text. Order: upload on `spa.intro.image` > `opener_image` row name > `robe` > `door-gold`. `name` is a built picture or `''` (then show the brand tile). `portrait` = `<name>-portrait` if built. `is_door` for the door focus values. Until `robe` is built it resolves to `door-gold`.
- `sections`: room sections plus `{"kind": "moment", "moment": {...}}` items placed by rule (`place_moments()`): towel first; shower after the first tiles row (else after the first feature, else last); slippers after the first feature after the shower position (else last).
- moment: `{key, heading, body, pictures}`; key `towel` | `shower` | `slippers`. picture: `{name, focus, alt, upload, has_image, portrait}`. `shower` has `toiletries` then `towel-rail`. Check `picture.has_image` per picture. A moment is left out when its row heading is empty or none of its pictures exist (today: none exist, so the page looks as before).
- `tote`: same moment shape (`moment_tote`) or `None`; placed by the template in the closing band.
- `arrive_kit`: `{heading, items: [{label, name, focus, has_image}]}` (max 5); `has_image` False means the swan tile.
- Unchanged: `room_count`, `visit_pills`, `next_from`, `hours`, `hours_facts`, `facilities`.
- Gym inset: `facility.detail_image_name` = `bottle-gym` (blanked by `facility_cards()` until built).
- `{% door_video as dv %}` (pages_media): same shape as `hero_video`, `None` until `spa-door-*` files exist. Use only when `opener.is_door`.

## /gold-card/ (view `gold_card`)
- `gold`: `{figures, pills, perks}` or `None` if the Gold plan is hidden. figures `{value, label, number, suffix}` (`number` for count-up, `None` for words); pills: strings; perks `{name, note}` (no waitlist, no `public: false`; "Each merch release" is public, no note).
- `hours_facts` (`range`, `hours`) for "Any time, {range}.". `groups` unchanged. Rows: `holds_lead`, `apply_note`.

## /memberships/
- `every_visit`: `{text, items, pictured, cta_label, cta_url}` or `None`. Mounts from `pictured` only; with none, sentence and link only.

## Sign-in shell
- `{% load pages_tags %}{% signin_shell as shell %}` on public Sign in, Forgotten password, Reset password, Check your email (never on Control). `shell`: `{heading, lead, caption, upload, name ("lockers"), alt, has_image, address_line}`; `alt` = the upload's alt, else the lockers alt; `address_line` parts joined " · " on desktop, one per line on phone.

## Content rows added
signin: `intro`, `caption`. spa: `opener_1..4`, `opener_image`, `moment_towel|shower|slippers|tote`, `arrive_kit`, `step_2_pills` (new wording). gold: `holds_lead`, `apply_note`. memberships: `every_visit`.

## Image names still to be made (fal)
`robe` (+ `robe-portrait`), `towel-bench`, `toiletries`, `towel-rail`, `slippers` (+ `-portrait`), `tote`, `bottle-gym`, and the kit items. See AMENITIES.md for prompts and sizes.
