# Feature: Control (building control room), DEMO

Status: **demo built 2026-10-24** on branch `feature/control-demo`. Design: `docs/design/CONTROL.md` (the spec and its 17 point checklist). Decisions: PROJECT.md rows 2026-10-23 and 2026-10-24. Who may open it: Admin level and up (`docs/features/user-rules.md` U2); everyone else gets the plain 404.

## What is real and what is demo

| Real | Demo (pretend) |
|---|---|
| Access: sign-in, `common.levels` Admin and up, plain 404 otherwise, change password | Every temperature, humidity, light level, music, screen, wristband, locker and alert |
| Room names and order: visible `Facility` rows (Reception and lounge is added first). Hide a room in the Office and its card goes | What each room can do (`ROOM_CAPS` in `control/demo.py`), scene targets, presets, playlists, menu, alert wording |
| Capacity: `SiteSettings.capacity` | Lockers total (60, a guess), the busy-ness curve and each room's share of people |
| Opening hours and closures: active `OpeningRule` and `Closure` rows (periods, nightly closure, Shabbos offsets) | Candle-lighting and Shabbos end times (example 17:58 and 18:20; real times come with the Phase 3 calendar sync) and the six schedule events |
| The clock: real London time picks the active scene, "closed" and the now line | "Run now", scenes, presets and toggles change values in this browser only |

Nothing here is sent to hardware and nothing is saved on the server. The pages are GET only (a POST gets 405). The only forms are Sign out and Change password. There is no fetch, XHR, beacon or HTMX request after load (a test reads `control.js` for this).

## How it works

- `control/demo.py` `demo_state()` builds one dict from the real rows plus values marked "DEMO value". The view adds display strings (`control/present.py`) so the page is a complete static snapshot without JavaScript, then prints the dict once with `json_script` (`#ctl-demo`).
- `common/static/common/js/control.js` (one ES module) owns the state after that: sliders, toggles, presets, scenes that glide about 2 s room by room with an Undo toast, drift every 5 s, people every 20 to 40 s following the day curve, at most 2 alerts, one timer that pauses when the tab is hidden. Reduced motion makes scenes and presets instant (data still updates).
- State is saved in `localStorage["spa99.control.demo.v1"]` (versioned; unknown versions are dropped; live readings older than 10 minutes are replaced by fresh ones). "Reset demo" clears it and reloads, so starting values come from the current hours and rooms.
- Styles: `common/static/common/css/control.css`, every colour a `--ctl-*` token scoped to `body.control` (the DEMO banner also appears on the Control sign-in page, so it carries its own tokens). Fonts and brand tokens come from `fonts.css` and `tokens.css` only.
- Routes (Control host): `/` Rooms (`?room=slug` opens the drawer, also without JavaScript), `/schedule/`, `/screens/`, `/password/`. Sign-in, health and the hidden admin route are unchanged.
- The control sign-in page shows the DEMO banner (without Reset, there is nothing to reset before signing in).

## Plugging real hardware in later

The shape of `demo_state()` is the contract. When the hardware is chosen, a `venue` app replaces the DEMO parts of `demo_state()` with live device state (same keys: `rooms[].lights/music/heater/cur/hum/people`, `screens`, `alerts`) and `control.js` swaps its local changes for requests to `venue` endpoints (set light level, apply scene, set screen). Scenes will then confirm before applying (the demo applies at once). Alerts come from device and door events instead of the fixture. Candle-lighting times come from the calendar sync. Templates and CSS survive unchanged.

## Not done / notes

- Events fire their scene at their time when "Runs" is on and the tab is open (demo only); nothing runs while the tab is closed.
- The "Ambient" screen content from the brief is not a choice: Relaxing zone starts as Off.
- Screenshots for design review (checklist 17) need a browser session with an Admin sign-in.
