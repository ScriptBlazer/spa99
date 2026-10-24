# Feature: Control (building control room), DEMO with a real Library

Status: **v2 built 2026-10-24** on branch `feature/control-demo`. Design: `docs/design/CONTROL.md` (v2, the spec and its 20 point checklist). Decisions: PROJECT.md rows 2026-10-23 and 2026-10-24. Who may open it: Admin level and up (`docs/features/user-rules.md` U2); everyone else gets the plain 404.

## What is real and what is pretend

| Real (stored on the server) | Pretend (this browser only, `localStorage`) |
|---|---|
| Access: sign-in, `common.levels` Admin and up, plain 404 otherwise, change password | Every temperature, humidity, light level, wristband, locker and alert |
| **The Library**: uploaded audio, video and pictures, posters, waveforms, names, artists, tags, playlists and their order and picture timings, who uploaded and when, deletion | Zones, what plays where, position, queue, volume, shuffle, repeat, mute; the Spotify connection and its sample playlists |
| Room names and order: visible `Facility` rows (plus the built-in Hallway and Changing room) | What each room can do (`ROOM_CAPS`), scenes, presets, screens and what they show, screen schedules |
| Capacity: `SiteSettings.capacity`; opening hours and closures: `OpeningRule` and `Closure` | Lockers total (60, a guess), the busy-ness curve, each room's share of people |
| The clock: real London time picks the active scene and "closed" | "Run now", scenes, presets, toggles change values in this browser only |

Nothing pretend is sent to the server. Reset demo clears the browser state only; Library files and playlists are never touched. The only network code is in `libdata.js` and `upload.js` (the Library), plus `app.js` fetching the next tab's HTML (GET) when you change tab; a test enforces this.

## Pages (Control host)

`/` Overview (floor plan), `/rooms/`, `/music/` (`?zone=`), `/screens/` (`?screen=`), `/schedule/`, `/library/` (`?item=id`, `?tab=playlists`, `?playlist=id`), `/password/`. `?room=slug` opens a room on `/` and `/rooms/`. Six tabs on desktop; on a phone five bottom tabs (Overview, Rooms, Music, Screens, More; More holds Schedule, Library, Reset demo and the account links).

- **Overview**: the floor plan (SVG, `control/plan.py`) follows Moishe's real drawing, Panorama Interior "99 Vale Road, Proposed ground floor lighting", Rev 04. Each controllable room is a link, lit by its light state (brightness and warmth), re-lit live while a slider moves. Right column: building numbers, Playing (one row per zone), the six screens. At 85em and wider a tapped room opens in the right column; narrower it opens in the side panel; on a phone in a sheet at peek height (the plan stays visible above it). The phone plan is the same geometry transposed.
- **Rooms**: cards with the real room photo re-lit by stacked opacity layers (night, lamps, pool, warm, cool; only opacity changes). Light and Warmth sliders on the card; lights and climate live in the room panel; music and screens only link to their own tab.
- **Music**: five zones, player (artwork, title, artist, source, scrub, shuffle, repeat off/all/one, previous, play/pause, next, volume, mute), reorderable queue (pointer drag or handle plus arrow keys), source picker (Library playlists and tracks, or Spotify demo), Group all / Ungroup, Mute all with Undo, Edit rooms, and **Listen here** which plays the real Library file in this browser (silent and simulated otherwise, advancing at the real durations). Mini player on every other tab.
- **Screens**: six screens with live previews (real video, pictures, playlists at their real timings, or the built-in slides as scaled HTML), at most 3 videos playing at once and only while on screen; panel with play/pause, previous/next, loop, power, Slides or Library chooser, This screen / All screens, and an optional schedule (up to four changes) that also shows on the Schedule tab.
- **Schedule**: v1 lanes plus a "Screens" lane with the screen changes.
- **Library**: grid and list, filters, search, multi-select (add to playlist, tag, delete), item panel (real player, rename, artist, tags, details, used in, delete with a warning), playlists (cover mosaic, rename, add items, drag and keyboard reorder, per-picture seconds, play in a zone, show on a screen), upload by button or by dropping files anywhere on the page, upload tray (two at a time, per-file progress, cancel, retry), storage meter.

Without JavaScript the pages read as a static snapshot (plan, cards, zone and screen lists, the file list) and the Library accepts a plain form upload (`next=page` on the upload endpoint redirects back with a message). Players, the chooser and the rest need JavaScript.

## How it works

- `control/demo.py` `demo_state()` builds one dict from real rows plus DEMO values (rooms, zones, screens, Spotify samples, scenes). The view adds display strings (`control/present.py`) and the plan (`control/plan.py`), then prints the state once with `json_script` (`#ctl-demo`).
- Browser code: `common/static/common/js/control.js` is the entry; the parts are in `common/static/common/js/control/` (plain ES modules, hashed imports through `SpaStaticFilesStorage`): `app.js` (boot, tab changes without a reload so music and uploads carry on, shell keys), `state.js` (pretend state and `localStorage["spa99.control.demo.v2"]`, versioned), `lights.js` (rooms, scenes, plan, simulation, alerts), `music.js` and `music-model.js` (queue rules with no DOM, tested under node), `screens.js`, `library.js`, `libdata.js`, `upload.js`, `panel.js`, `sortable.js`, `core.js`.
- Styles: `common/static/common/css/control.css`, every colour a `--ctl-*` token scoped to `body.control`. Fonts and brand tokens from `fonts.css` and `tokens.css` only. Icons: Phosphor regular, added to `common/static/common/img/icons.svg` (the six Control icons that already existed there in the light weight got `-r` regular twins so the tab bar is one weight).
- **Photo lamps layer**: Pillow is not installed in this project, so the "lamps map" images of the brief are not generated. Each room instead has two or three soft warm radial gradients (`present.LAMPS`) blended with `screen` over the dimmed photo. Same layer and opacity rule; a real lamps map can replace it later.

## Library (real uploads, simulated playback)

- Models (`control/models.py`): `MediaAsset` (uuid, title, artist, kind audio/video/image, file, poster, ext, mime, size_bytes, duration_seconds, width, height, tags JSON list, peaks JSON list, uploaded_by, created_at, change history without the peaks), `Playlist` (uuid, name, kind music/screens) and `PlaylistItem` (playlist, asset, position, `seconds` for pictures). A music playlist takes audio only, a screens playlist video and pictures. Migrations `0001`, `0002_library_ui`.
- Storage: default storage at `control/media/<uuid>.<ext>` and `<uuid>-poster.jpg` (the uploaded name is never used). S3 prod/ or dev/ prefix on live (private, signed URLs, 1 hour), `.private/media` on the Mac (served at `/media/` on the Control host in DEBUG only). Deleting an asset deletes both files; deleting a playlist keeps the files.
- **Accepted types (one list, shown in the page and enforced by content, `control/media_rules.py`)**: audio MP3, M4A, WAV; video MP4 (H.264) and WebM; pictures JPG, PNG, WebP. AAC and OGG audio are refused (the brief's list); HEIC and AVIF pictures get "HEIC pictures can't be shown on screens. Save it as JPG and try again." Limits per file: audio 50 MB, video 500 MB, picture 20 MB (`CONTROL_MAX_*_MB`); **the whole Library 10 GB (`CONTROL_LIBRARY_MAX_GB`, optional, default 10)**, refused with "The Library is full. Delete something to make room." (507). The browser checks the same rules first with the brief's messages.
- Tags: audio always carries `music`; video and pictures always carry `screens` and never `music`; extra tags are free words (up to 8).
- Big files: Django streams uploads over 2.5 MB to a temp file; live Caddy `request_body max_size 600MB` on the Control host and gunicorn `--timeout` 300 s. Uploads are limited to 40 per 10 minutes per IP.
- Endpoints (Control host; writes are POST with CSRF, JSON or form body, JSON replies; errors are `{"error": "..."}`):

| Path | Does |
|---|---|
| GET `/library/` | the page |
| GET `/library/assets/?kind=&tag=&q=` | list and filter; each asset has `url`, `poster_url`, `peaks`, `artist`, `uploaded_by` and `playlists` (used in); also `library: {used_bytes, max_bytes}` |
| POST `/library/assets/upload/` | multipart `file`, optional `title`, `tags`; with `next=page` (plain form) it redirects back |
| POST `/library/assets/<id>/update/` | `title`, `artist` (audio), `tags` |
| POST `/library/assets/<id>/duration/` | `duration_seconds`; video also `width`, `height`, `poster` (jpg file, up to 1 MB); audio also `peaks` (8 to 400 numbers 0 to 1). JSON or multipart |
| POST `/library/assets/<id>/delete/` | delete row and files |
| GET `/library/playlists/?kind=` | playlists with ordered items (`seconds` per item) |
| POST `/library/playlists/create/`, `<id>/update/`, `<id>/delete/` | `name`, `kind` |
| POST `/library/playlists/<id>/items/add/`, `remove/`, `reorder/` | `asset_id`; `item_id`; `item_ids` (all, in the new order) |
| POST `/library/playlists/<id>/items/seconds/` | `item_id`, `seconds` 4 to 60 (pictures only) |

- Browser side after an upload: the file is stored first, then the browser reads length (and video size), decodes audio for 200 waveform peaks, grabs a video poster frame at 1 s (or 10%), and posts those to the duration endpoint, so the server needs no ffmpeg.
- Where "used in" comes from: playlists from the server; screens and music queues from this browser's pretend state. A deleted file makes screens show Welcome and stops music ("This file was deleted").
- Not done: audit-log (System) events for Library changes (needs a new event kind and migration in `system`; asset changes are in the model history and the admin); no virus scan; on live, uploads go through Django (the brief recommends a presigned S3 POST for video; local-first for now).

## Plugging real hardware in later

The shape of `demo_state()` is the contract. When the hardware is chosen, a `venue` app replaces the DEMO parts of `demo_state()` with live device state (same keys: `rooms[].lights/heater/cur/hum/people`, `zones`, `screens`, `alerts`) and the modules swap their local changes for requests to `venue` endpoints. Scenes will then confirm before applying. Alerts come from device and door events. Candle-lighting times come from the calendar sync. Real Spotify replaces the connect hand-off. Templates and CSS survive.

## Tests

`SENTRY_DSN= .venv/bin/python manage.py test control` (Python: access, state, plan geometry, pages, Library rules; it also runs `node --test control/tests/js` for the queue rules and `node --check` on every module). The browser behaviour was exercised with a throwaway jsdom harness (not committed): plan lighting, panels, scenes with Undo, players, queue reorder, source picker, Spotify demo flow, screens chooser and schedule, Library grid, filters, selection, item panel, playlists, upload tray, tab changes.

## Not done / notes

- **Not checked in a real browser** (the sandbox blocks Chrome): layout, the SVG plan drawing, photo relighting, drag with a pointer, View Transitions, audio playback and the phone sheet were checked by reading and by jsdom only. Screenshots at 375 and 1440 still need a browser session with an Admin sign-in.
- Spotify starts connected (demo) so Music has something playing on first open; Disconnect and Connect both work.
- Events fire their scene at their time when "Runs" is on and the tab is open (demo only); screen schedule changes the same way. Nothing runs while the tab is closed.
- Hallway and Changing room are built into the demo state (not `Facility` rows), so the Office cannot hide them.
