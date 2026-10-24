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

## Library (real uploads, simulated playback)

Status: server side built 2026-10-24 (page `/library/` is minimal, data-* hooks only; the designer's UI comes later). Admin level and up, plain 404 otherwise.

- Models (`control/models.py`): `MediaAsset` (uuid, title, kind audio/video/image, file, ext, mime, size_bytes, duration_seconds, width, height, tags as a JSON list, uploaded_by, created_at, change history), `Playlist` (uuid, name, kind music/screens) and `PlaylistItem` (playlist, asset, position; unique per playlist, an asset may appear twice). A music playlist takes audio only, a screens playlist video and images.
- Storage: default storage at `control/media/<uuid>.<ext>` (the uploaded name is never used; the extension comes from the sniffed type). S3 prod/ or dev/ prefix on live (private bucket, signed URLs, 1 hour), `.private/media` on the Mac (served at `/media/` on the Control host in DEBUG only). Never inside the container. Deleting an asset deletes the file; deleting a playlist keeps the files.
- Validation (`control/media_rules.py`): type found from the first bytes: mp3, aac, m4a, wav, ogg; mp4 and webm; jpg, png, webp. Anything else is 415 with a plain message. mp4 with only a non-h264 codec marker (hvc1, hev1, av01, vp09) in its header is refused (a cheap check, not a full decode). Limits per kind, settings `CONTROL_MAX_AUDIO_MB` 50, `CONTROL_MAX_VIDEO_MB` 500, `CONTROL_MAX_IMAGE_MB` 20; over the limit is 413. Image width and height are read from the header; duration is reported by the browser (no mutagen/ffprobe installed).
- Big files: `FILE_UPLOAD_MAX_MEMORY_SIZE` stays 2.5 MB so Django streams larger uploads to a temp file; `DATA_UPLOAD_MAX_MEMORY_SIZE` does not count files. Live: Caddy `request_body max_size 600MB` on the Control host, and gunicorn `--timeout` 300 s (`GUNICORN_TIMEOUT`) so a slow 500 MB upload is not killed at the default 30 s. Uploads are limited to 40 per 10 minutes per IP.
- Endpoints (Control host; writes are POST with CSRF, JSON or form body, JSON replies; errors are `{"error": "..."}`):

| Path | Does |
|---|---|
| GET `/library/` | minimal page |
| GET `/library/assets/?kind=&tag=&q=` | list and filter (each has `url`) |
| POST `/library/assets/upload/` | multipart `file`, optional `title`, `tags` |
| POST `/library/assets/<id>/update/` | `title`, `tags` |
| POST `/library/assets/<id>/duration/` | `duration_seconds` (video also `width`, `height`) |
| POST `/library/assets/<id>/delete/` | delete row and file |
| GET `/library/playlists/?kind=` | playlists with ordered items |
| POST `/library/playlists/create/`, `<id>/update/`, `<id>/delete/` | `name`, `kind` |
| POST `/library/playlists/<id>/items/add/` | `asset_id` (appended) |
| POST `/library/playlists/<id>/items/remove/` | `item_id` (positions close up) |
| POST `/library/playlists/<id>/items/reorder/` | `item_ids`, all of them in the new order |

- Not done: audit-log (System) events for Library changes (it needs a new event kind and migration in `system`; asset changes are in the model history and the admin); a Library icon (the tab borrows `speaker-high`); no virus scan.

## Plugging real hardware in later

The shape of `demo_state()` is the contract. When the hardware is chosen, a `venue` app replaces the DEMO parts of `demo_state()` with live device state (same keys: `rooms[].lights/music/heater/cur/hum/people`, `screens`, `alerts`) and `control.js` swaps its local changes for requests to `venue` endpoints (set light level, apply scene, set screen). Scenes will then confirm before applying (the demo applies at once). Alerts come from device and door events instead of the fixture. Candle-lighting times come from the calendar sync. Templates and CSS survive unchanged.

## Not done / notes

- Events fire their scene at their time when "Runs" is on and the tab is open (demo only); nothing runs while the tab is closed.
- The "Ambient" screen content from the brief is not a choice: Relaxing zone starts as Off.
- Screenshots for design review (checklist 17) need a browser session with an Admin sign-in.
