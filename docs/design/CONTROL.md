# Spa 99 Control: design brief (DEMO, round 1)

Scope: a realistic, **non-functional demo** of the building control room at `control.spa99.uk` (branch `feature/control-demo`). Pretend values, every control works locally, nothing reaches hardware and nothing is saved on the server. Decisions: PROJECT.md rows 2026-10-23 (Control = building only; used remotely by a few admins; never on in-building tablets; parked until hardware is chosen; demo agreed 2026-10-23). Access: Admin level and up (`docs/features/user-rules.md` U2); everyone else gets the existing plain 404. Brand rules in `docs/BRAND.md` win over anything here.

**Design read.** An operations console for a few people looking after one building from home, often late (the spa is open until 03:00). The feel of a quiet hotel night desk or a Lutron/Crestron panel done well: dark, calm, legible at a glance, values big and exact, nothing flashing. Dials: variance 2, motion 3, density 6 (phone 5).

---

## 1. The look: dark

Pick: **dark operational**, in the brand's own darkness (espresso taken nearly to black), not a neutral tech black.

Why:
1. **Light is the thing being controlled.** On a dark surface, brightness and warmth can be shown as actual glow (a warm pool behind each room's name). On a light page that preview disappears.
2. **When it is used.** Opening and closing happen at 04:30 and 03:00, at home, on a phone in a dark room. A light screen at that hour is the wrong tool.
3. **Siblings, not twins.** Office is warm and light with soft cards; System is cool, light and hairline-dense. Control dark makes the three tools impossible to mix up while sharing fonts, the swan, gold and espresso.
4. **Status reads better.** Ok, warn and alert colours carry more clearly on dark, so state can stay small.

| | Office | System | **Control** |
|---|---|---|---|
| Shell | Warm light cream | Cool light grey | **Near-black espresso** |
| Separation | Tone and soft shadow | Hairlines | **Tone steps, no shadow, no lines on cards** |
| Corners | 14 to 20px cards | 4 to 6px | **12px cards, 6px controls, pill sliders and toggles** |
| Numbers | Big Signika | 13px mono | **Big Figtree tabular (values), Signika only for room names** |
| Base text | 16px | 13px | **14px** |
| Motion | Rings draw, cards rise | Feedback only | **Values glide on change (scenes), nothing on load** |

## 2. Tokens (Control only, proposed)

All in `common/static/common/css/control.css`, scoped to `body.control`, never `:root`, never in `tokens.css`. Control loads `fonts.css` and `tokens.css` (for fonts, `--ease-soft`, brand colours) and not `base.css`, `components.css`, Office or System CSS. No hex outside `control.css`.

### 2.1 Colour (contrast measured, WCAG 2.x)

| Token | Value | Use | Ratios |
|---|---|---|---|
| `--ctl-bg` | `#14100D` | Page | text 16.74, text-2 10.36, text-3 6.65 |
| `--ctl-surface` | `#1E1813` | Room cards, panels, drawer, top bar | text 15.54, text-2 9.62, text-3 6.17 |
| `--ctl-raised` | `#2A211A` | Inputs, segmented track, hover, scene buttons at rest | text 13.96, text-2 8.64, text-3 5.54 |
| `--ctl-selected` | `#3A2D23` | Current nav, active scene, selected segment | text 11.76, text-2 7.28, text-3 4.67 |
| `--ctl-text` | `var(--color-cream)` `#F5F2D8` | Values, room names, primary text | |
| `--ctl-text-2` | `#C9BFA8` | Labels, units, secondary lines | 7.28 or more everywhere |
| `--ctl-text-3` | `#A39883` | Timestamps, help text | 4.67 or more everywhere |
| `--ctl-accent` | `var(--color-gold)` `#E5AC6E` | Slider fill, toggle on, focus ring, active nav bar, primary button fill | text 6.62 to 9.42; `--ctl-bg` on gold 9.42 |
| `--ctl-control` | `#7A6A5C` | Input and segmented borders, toggle track off | 3.38 surface, 3.04 raised (not on selected) |
| `--ctl-track` | `#4A3B30` | Unfilled slider track (decoration; the thumb carries the 3:1) | 1.64 |
| `--ctl-ok` | `#86C99E` | Running, at target, "On" | 6.88 or more |
| `--ctl-warn` | `#E6C86E` | Off target, heating up, near capacity | 8.14 or more |
| `--ctl-danger` | `#F4A08E` | Alerts | 6.50 or more |
| `--ctl-demo` | `#93B8E6` | DEMO banner and badge only | `--ctl-bg` on it 9.23 |
| `--ctl-overlay` | `rgb(20 16 13 / 0.6)` | Drawer and dialog backdrop | |
| `--ctl-glow` | warmth colour at 0 to 0.28 alpha | Light preview pool on room cards (decoration) | |

Gold is the one accent. Blue appears only for DEMO, so "not real" never looks like brand. State is never colour alone: every badge has a word.

**Warmth scale** (decoration only, used by the glow and the warmth slider track): 2200K `#FF9A4A`, 2700K `--color-light-warm` `#FFA957`, 3000K `#FFC48A`, 4000K `#FFE2C2`. JS interpolates between these for the glow; nothing textual uses them.

### 2.2 Type, space, shape

```css
--ctl-font: var(--font-body);          /* Figtree for all UI, tabular-nums on every value */
--ctl-display: var(--font-display);    /* Signika: page titles and room names only */
--ctl-fs-xs: 0.75rem;   /* 12px meta, badges */
--ctl-fs: 0.875rem;     /* 14px base */
--ctl-fs-md: 1rem;      /* 16px card values, drawer labels; phone inputs */
--ctl-fs-lg: 1.25rem;   /* 20px room names (Signika 500) */
--ctl-fs-xl: 2rem;      /* 32px drawer hero value (temperature) and status strip numbers */
--ctl-1: 4px; --ctl-2: 8px; --ctl-3: 12px; --ctl-4: 16px; --ctl-5: 24px; --ctl-6: 32px;
--ctl-radius: 6px;       /* buttons, inputs, segmented */
--ctl-radius-lg: 12px;   /* cards, drawer, panels */
--ctl-top-h: 56px; --ctl-strip-h: 64px; --ctl-tab-h: 64px; --ctl-drawer-w: 440px;
--ctl-content-max: 1360px;
--ctl-glide: 2000ms;     /* a scene moving values */
--ctl-quick: 160ms;      /* control feedback */
```

Weights 400, 500, 600. No uppercase except the DEMO badge. Shape rule: 12px for containers, 6px for anything you press or type in, pills only for slider tracks, toggle tracks and badges.

## 3. Shell and navigation

```
+----------------------------------------------------------------------------------+
| DEMO  Pretend building. Nothing here controls real hardware.     [Reset demo]    |  32px
+----------------------------------------------------------------------------------+
| [swan] Control   Rooms  Schedule  Screens               Sat 24 Oct 21:14  [MW v] |  56px
+----------------------------------------------------------------------------------+
| 17 of 25 in   |  17 bands active  |  21 lockers in use  |  1 alert              |  64px status strip
+----------------------------------------------------------------------------------+
| Scenes: [Opening] [Daytime] [Evening*] [Closing] [Cleaning]                      |
| room cards grid ...                                                              |
```

- **IA**: three destinations. **Rooms** (`/`, home, with the scene bar), **Schedule** (`/schedule/`), **Screens** (`/screens/`). A room opens in a drawer, deep-linkable as `/?room=dry-sauna`. Scenes are not a page: they act on the Rooms page where you see the effect.
- **Top bar** (`--ctl-surface`, sticky under the banner): gold swan 20px + "Control" Signika 500 18px; nav as text tabs 14px 500 `--ctl-text-2`, current `--ctl-text` with a 2px gold bar under it and `aria-current="page"`; right: building clock (24-hour, Europe/London, updates each minute, `--ctl-text-2`), initials disc opening a menu: name, level ("Admin"), "Open Office", "Sign out".
- **Phone (below 48em)**: top bar keeps swan, "Control", clock. Nav moves to a bottom tab bar (`--ctl-tab-h` + safe area, `--ctl-surface`): Rooms, Schedule, Screens, each a Phosphor icon 24px over 12px 600 label. No kiosk or install prompt anywhere (never on in-building tablets).
- Page titles are visually hidden on Rooms (the strip is the header), visible on Schedule and Screens (Signika 500 `--ctl-fs-xl`).

## 4. The DEMO banner

- Full-width 32px band at the very top of every page including sign-in, `--ctl-demo` fill, `--ctl-bg` text 13px. Left: badge "DEMO" (12px 600 uppercase, 0.08em tracking, 1px `--ctl-bg` border, radius 999px) then "Pretend building. Nothing here controls real hardware." Right: "Reset demo" (text button, underline on hover) which clears local state after a one-line confirm ("Put every room back to its starting values?" Cancel / Reset).
- Not sticky on phone (saves height), sticky on desktop. Cannot be dismissed. Document title: `DEMO · Rooms · Control`.
- Every value that looks live carries no other "fake" marker: the banner covers it.

## 5. Live status strip

Four cells, one row at desktop, 2 by 2 on phone (each 56px). `--ctl-surface` row, cells divided by space only. Each cell: number 32px 500 tabular `--ctl-text`, label 12px `--ctl-text-2` under it.

| Cell | Example | Rule |
|---|---|---|
| In the building | **17** of 25 | Capacity from `SiteSettings.capacity`. "of 25" in `--ctl-text-2`. Warn text "Nearly full" from 23. Closed hours: "Closed" and 0. |
| Wristbands active | **17** | Tracks people in (bands out = people in, plus or minus 1 staff band). |
| Lockers in use | **21** of 60 | Lockers total is a fixture value, marked as a guess in the fixture. |
| Alerts | **1** | 0 = "No alerts" in `--ctl-ok`. Above 0: danger number and the cell is a button opening the alert list popover. |

Numbers change in place without animation (data you read should not move for style). `aria-live` off on the strip; the alerts cell announces new alerts once via a polite live region.

## 6. Rooms overview

Grid: `repeat(auto-fill, minmax(300px, 1fr))`, 16px gap, max 1360px; 4 across at 1440, 1 column at 375. Order = Facility `order`, with **Reception and lounge** first (arrival). Above the grid, the **scene bar** (section 8).

### 6.1 Room card

```
+----------------------------------------------+
|  ( warm glow pool, top-left )                |
|  Dry sauna                       [At target] |
|  86°C                     target 85°C        |
|                                              |
|  Lights   [====o-----]  60%   2700K          |
|  Music    Evening, low     [===o---] 35      |
|  Screen   none                               |
|  3 people                                    |
+----------------------------------------------+
```

- `--ctl-surface`, radius 12px, padding 20px, min height 232px, no border. The whole card is a button opening the drawer (hover: background to `--ctl-raised`, 160ms; press scale 0.99). Inline controls inside are not nested in the button: the card has a header button (name) covering the card via a stretched pseudo-element, and the two inline controls sit above it with `position: relative; z-index: 1`.
- **Glow**: a radial gradient behind the top-left 60% of the card, colour from warmth, opacity `0.04 + brightness × 0.24`. Lights off = no glow. Decoration only, `aria-hidden`.
- **Header**: room name Signika 500 20px; status badge right (pill 22px, 12px 600, tinted fill at 16% of its colour, text in the colour): "At target" ok, "Heating" warn, "Cleaning" text-2, "Closed" text-3, "Alert" danger.
- **Climate line** (saunas, plunge only): current value 32px 500 tabular, target 12px `--ctl-text-2` right. Wet sauna adds humidity ("94% humidity"). Plunge shows water temperature. Others skip the line and the card is shorter.
- **Rows** (14px, label 72px column `--ctl-text-2`): Lights: compact slider (brightness) + value + warmth in K; Music: playlist name and a compact volume slider; Screen: what it shows or "none"; Occupancy: "3 people" / "Empty". Rooms without music or screen omit the row (no "n/a").
- Inline on the card: **brightness** and **volume** sliders only. Everything else in the drawer.

### 6.2 Rooms in the fixture

From visible Facility rows in order, plus one non-Facility zone. Capabilities per slug:

| Room | Climate | Lights | Music | Screen |
|---|---|---|---|---|
| Reception and lounge (fish tank) | none (shows tank water 25°C as a read-only line) | yes | yes | Welcome |
| Dry sauna | 85°C target | yes | no (speaker-free heat) | no |
| Wet sauna | 45°C, 95% humidity | yes | no | no |
| Cold plunge | 12°C water | yes | yes | no |
| Showers | none | yes | yes | no |
| Relaxing zone | none | yes | yes | Ambient (or off) |
| Massage room | none | yes | yes | no |
| Gym | none | yes | yes | Notices |
| Kitchenette | none | yes | yes | Menu |

Targets reuse the spa page placeholder facts (80 to 90°C, about 45°C, 12°C) so the demo matches the site.

## 7. Room drawer

Right drawer `--ctl-drawer-w`, `--ctl-surface`, radius 12px on the left corners, full height, backdrop `--ctl-overlay`. Phone: full-height sheet. Focus moves to the title, trapped, Esc and backdrop close and return focus to the card. URL gets `?room=slug` (replaceState).

Order, top to bottom, groups separated by 24px and a 15px 600 group title:
1. **Header**: room name Signika 500 `--ctl-fs-xl`, status badge, occupancy line, close button (36px, `x` icon).
2. **Presets** (segmented, 4 options): Bright, Day, Calm, Off. A preset sets lights and music for this room only; the segment shows the matching preset or none if values were changed by hand.
3. **Climate** (if any): big current value; target stepper (minus / value / plus, 36px buttons, step 1°C; humidity step 5%); heater toggle "Heating" On / Off. Changing the target makes the current value creep toward it at the drift rate (section 10), so the badge goes "Heating" then "At target".
4. **Lights**: toggle "Lights" On/Off; Brightness slider 0 to 100%; Warmth slider 2200K to 4000K, step 100, track painted with the warmth scale.
5. **Music**: toggle On/Off; playlist as a choice list (radio rows, 44px): Quiet morning, Daytime, Evening, low, Late, very low; Volume slider 0 to 100. Choosing, not a select.
6. **Screen** (if any): radio rows Welcome, Today's hours, Menu, Notices, Off, with the preview tile (section 11) above.
7. Footer note 12px `--ctl-text-3`: "Saved in this browser only."

Changes apply instantly (no Save). The card behind updates live.

## 8. Scenes

- **Scene bar** above the grid: label "Scene" 12px `--ctl-text-2`, then five scene buttons in a row (scrolls sideways on phone, no wrap): Opening, Daytime, Evening, Closing, Cleaning. Right of them: "Now: Evening · since 18:00" 12px `--ctl-text-3`.
- **Scene button**: 40px, radius 6px, `--ctl-raised`, 14px 500, padding 0 16px. Active: `--ctl-selected` fill, `--ctl-text` 600, 2px gold bar at its bottom inside the radius, `aria-pressed="true"`. Hover (fine pointer) `--ctl-selected`, 160ms.
- **Apply**: press, no confirm (it is a demo; the real one will confirm). The button goes active instantly; every affected value glides to its target over `--ctl-glide` with `--ease-soft`, rooms 60ms apart in grid order (reads as the building changing room by room). A toast bottom right: "Evening applied to 9 rooms." with "Undo" (6 s, pauses on hover/focus, `role="status"`). Undo glides back.
- Changing any value by hand after a scene shows "Now: Evening, changed" (no warning colour).

Scene targets (fixture, one table; per-room exceptions in brackets):

| Scene | Lights | Warmth | Music | Climate | Screens |
|---|---|---|---|---|---|
| Opening (04:30) | 70% | 3000K | Quiet morning, 25 | heaters on, ramp to target | Welcome / hours |
| Daytime (08:00) | 80% (relax 40%) | 3000K | Daytime, 30 | targets | as set |
| Evening (18:00) | 50% (relax 25%) | 2700K | Evening, low, 25 | targets | as set |
| Closing (02:30) | 35% | 2400K | Late, very low, 15 | heaters off | "Closing at 03:00" notice |
| Cleaning (03:00) | 100% | 4000K | off | heaters off, plunge stays 12°C | off |

## 9. Schedule

Page title "Schedule", line under it 14px `--ctl-text-2`: "Automatic changes through the day. Opening hours come from the Office and are read only here."

### 9.1 Day timeline (desktop)

- One horizontal lane per day, **05:00 to 05:00** (the 03:00 to 05:00 nightly closure visible at the right end). Hours ticked every hour, labels every 3 hours (12px `--ctl-text-3`, tabular). Lane 56px high, `--ctl-surface`, radius 12px.
- **Open periods** from OpeningRule: Daytime 05:00 to 18:00 and Evening 18:00 to 03:00 as `--ctl-raised` bands labelled 12px inside. **Closed** periods (nightly 03:00 to 05:00, Shabbos and Yom Tov) as a diagonal hatch of `--ctl-track` on `--ctl-bg` with "Closed" 12px `--ctl-text-2`. Read-only: no handles, a lock icon and the title "From opening hours in the Office".
- **Events** are 12px markers on the lane (a 2px vertical line plus a 28px pill label above: "Opening", "Saunas heat", "Daytime", "Evening", "Closing", "Cleaning"). Default events: 04:15 Saunas heat, 04:30 Opening, 08:00 Daytime, 18:00 Evening, 02:30 Closing, 03:00 Cleaning. Pills that would collide stack on a second row.
- **Now line**: 1px gold vertical across today's lane with a "21:14" tag, moves each minute (no animation, it just redraws).
- Clicking an event opens a popover (240px, anchored, `transform-origin` at the marker): scene name, time, what it changes (one line), toggle "Runs" On/Off (local only), "Run now" which applies the scene (section 8). Event times are not draggable in the demo.

### 9.2 The week

Seven lanes, Sunday to Saturday, starting today. **Friday** lane ends at "Closes 2 h before candle lighting" and **Saturday** opens "1 h after Shabbos ends", from the `close_before_candles` / `open_after_end` offsets. Candle-lighting times are not synced yet (Phase 3): the fixture uses a clearly labelled example time and the lane says "Example time, real times come with the calendar sync." Active one-off Closure rows appear as hatched blocks with their name. Events falling in a closed block are drawn at 40% opacity and labelled "Skipped, closed".

### 9.3 Phone

The lanes become a vertical list per day: day header (sticky, 32px), then rows "04:30 Opening", 44px each, with closed spans as hatched rows ("Closed 15:58 Fri to 19:20 Sat, example times"). Tapping a row opens the same popover as a bottom sheet.

## 10. Simulation (JS)

`control/static/control/js/control-demo.js`, plain JS, no library. State: the fixture JSON plus any local overrides from `localStorage["spa99.control.demo.v1"]` (versioned; unknown versions are dropped). No fetch, no POST, no HTMX writes.

- **Drift** (every 5 s, one timer): temperatures wander within ±0.4°C of target (plunge ±0.2), humidity ±2%. If heating toward a new target: saunas +1°C per 15 s, plunge −0.1°C per 15 s. Values update in place, no animation.
- **People** (every 20 to 40 s, random): ±1 in a random open room, total kept within 0 to capacity and following a day curve (quiet at 05:00, busy 19:00 to 22:00). Bands follow people; lockers follow people ×1.2, rounded. Closed hours: everything goes to 0 over a few ticks.
- **Alerts** (one every 3 to 6 minutes, at most 2 open): from a short fixture list, calm wording: "Cold plunge water 13.6°C, above target.", "Gym speaker not responding.", "Kitchenette screen offline." Each resolves on its own after 1 to 2 minutes or by "Mark as seen". The room card gets the "Alert" badge while open.
- **Scenes and presets**: numbers tween over `--ctl-glide` (requestAnimationFrame, `--ease-soft` curve); slider fills move with `transform: scaleX()`; glow fades with opacity. Hand-dragged sliders are instant.
- **Pause** all timers when the tab is hidden; on return, jump straight to fresh values (no catch-up animation).
- **Reduced motion**: scenes and presets apply instantly; drift, people and alerts still update (they are data, not motion); toast fades only.
- The sim clock is the real London time, so the active period, scene and now line match the real day.

## 11. Screens

Page title "Screens", line: "What each screen in the building is showing."

- Grid of screen cards (`minmax(320px, 1fr)`): Reception, Lounge, Relaxing zone, Gym, Kitchenette. Each card: a **16:9 preview tile** on top (radius 6px), then screen name 16px 600, room 12px `--ctl-text-2`, content choice as a segmented control (Welcome · Hours · Menu · Notices · Off; phone: radio rows), a power toggle.
- **Preview tiles** are real miniature HTML in the site's brand (not images, not div wireframes): rendered at 1280×720 inside the card and scaled with `transform: scale()` to fit, `aria-hidden` with a text summary below for screen readers.
  - Welcome: espresso, gold swan, "Welcome to Spa 99" Signika, "Beyond Luxury".
  - Hours: today's hours from OpeningRule ("Open until 03:00").
  - Menu: kitchenette drinks list (fixture: Tea, Coffee, Fresh mint, Still and sparkling water).
  - Notices: one editable notice line (text input under the tile, 80 characters, local only), e.g. "The cold plunge is being cleaned until 14:00."
  - Off: `--ctl-bg` with "Off" 12px `--ctl-text-3`.
- Changing content cross-fades the tile (opacity, 240ms; instant under reduced motion).

## 12. Components

- **Slider** (native `<input type="range">`, restyled): track 6px pill `--ctl-track`, fill `--ctl-accent` drawn by a pseudo-element scaled with `transform: scaleX(var(--v))`, thumb 20px circle `--ctl-text` with a 1px `--ctl-bg` ring; compact (cards) 4px track, 16px thumb, hit area 32px (44px under `pointer: coarse`). Value shown beside it in tabular 14px, `aria-valuetext` with units ("60 percent", "2700 kelvin"). Arrow keys step 1 (warmth 100), PageUp/Down 10, Home/End. Focus ring 2px gold, offset 3px, on the thumb.
- **Toggle**: same pattern as System's `sys-toggle` (a real checkbox drawn as a track with a knob, state word beside it), restyled: track 36×20 `--ctl-control`, on `--ctl-accent`, knob 16px `--ctl-text` (on: knob `--ctl-bg`), knob moves with `transform`, 160ms `--ease-soft`. Word "On"/"Off" 14px `--ctl-text-2`. Class `ctl-toggle`.
- **Segmented**: 36px, `--ctl-raised` track, radius 6px, selected segment `--ctl-selected` with `--ctl-text` 600; radios underneath, arrow keys move.
- **Room card, scene button, timeline**: sections 6.1, 8, 9.1.
- **Badge**: pill 22px, 12px 600, colour text on 16% tint of the same colour, always a word.
- **Toast**: bottom right 360px (phone full width minus 16px, above the tab bar), `--ctl-raised`, radius 12px, slides up 8px plus fade, 200ms in, 160ms out.
- **Icons**: Phosphor (MIT, already in `icons.svg`), add `lightbulb`, `speaker-high`, `monitor`, `thermometer`, `drop`, `users`, `warning`, `clock`, `lock-simple`, `x`, `squares-four`, `calendar-blank` (exists). Used on the phone tab bar, drawer group titles and the alert cell only.

## 13. Data source

- **`control/demo.py`** (new, Python, no models, no migrations): `demo_state()` returns one dict built from real rows so names match the site:
  - rooms: visible `Facility` rows in `order` (name, slug), plus `{"slug": "reception-lounge", "name": "Reception and lounge"}` first; capabilities and targets from a `ROOM_CAPS` dict keyed by slug (section 6.2). Unknown new slugs get lights and music only, so a new room never breaks the demo.
  - hours: active `OpeningRule` rows (periods, nightly closure, Shabbos offsets) and active `Closure` rows in the next 7 days.
  - capacity from `SiteSettings.capacity`; lockers total, playlists, scene targets, alert texts, menu items, example candle-lighting time from constants in the module, each commented "DEMO value".
  - starting values for "now" computed from the current London time (the scene that should be active, a plausible occupancy).
- Views render it once into the page with `{{ state|json_script:"ctl-demo" }}`; the JS owns everything after that. Views are GET only; Control host routing as today, `@login_required` plus the Admin level check (plain 404 otherwise).
- Later, the real `venue` app replaces `demo_state()` with live device state behind the same shape, so templates and components survive.

## 14. Copy

Short and exact, sentence case, no exclamation marks. Values with units always: `86°C`, `94% humidity`, `60%`, `2700K`, `21:14`. Name things as the site does ("Dry sauna", not "Sauna 1"). Empty: "Empty", "No alerts", "Off". No "Oops", no "Submit".

## 15. Acceptance checklist

1. Control loads only `fonts.css`, `tokens.css`, `control.css` and `control-demo.js`; every colour is a `--ctl-*` token scoped to `body.control`; no hex outside `control.css`.
2. DEMO banner on every page including sign-in, blue with dark text, with working "Reset demo" (confirm, then starting values); title prefix `DEMO ·`.
3. Non-admins and signed-out visitors get the existing plain 404; Admin, Developer and Superuser get in.
4. Nothing is sent to the server after page load (Network tab: no XHR, fetch or POST); state survives reload via localStorage; Reset clears it.
5. Status strip: four cells, capacity from Site settings, "Nearly full" from 23, alerts cell opens the list; numbers change without animation.
6. Rooms grid matches visible Facility rows in order plus Reception and lounge first; hiding a Facility in the Office removes its card; climate lines only on saunas and plunge.
7. Card: glow follows brightness and warmth (off = none); inline brightness and volume work without opening the drawer; the card opens the drawer by click, Enter or Space.
8. Drawer: presets, climate stepper and heater, lights, music choice list, screen choice with preview; Esc, backdrop and close return focus; `?room=` deep-links; phone shows a full sheet.
9. Scenes: five buttons, `aria-pressed`, values glide about 2 s room by room, toast with working Undo; hand change shows "changed".
10. Schedule: 05:00 to 05:00 lanes, read-only open and closed bands from OpeningRule and Closure, Friday and Saturday Shabbos spans with the "example time" note, events with popover (Runs toggle, Run now), now line; phone list version.
11. Screens: five cards with real miniature brand previews, content and power changes cross-fade, notice text editable locally.
12. Simulation: drift every 5 s, people every 20 to 40 s following the day, at most 2 alerts that resolve; timers pause when the tab is hidden.
13. Reduced motion: scenes, presets and preview changes are instant; data still updates; no transforms anywhere.
14. Contrast: only the pairs in 2.1; focus ring visible on every control; sliders and toggles have `aria-valuetext` or state words; no state shown by colour alone.
15. Keyboard: full Tab order; sliders take arrows, PageUp/Down, Home/End; segmented and radio rows take arrows.
16. Phone 375: banner, top bar, 2 by 2 strip, one-column cards, sideways scene bar, bottom tabs with safe area, 44px touch targets, inputs 16px, no page-level horizontal scroll.
17. Screenshots at 375 and 1440 of Rooms (Evening active), Rooms with a drawer open, a scene mid-glide, Schedule (today and week), Screens, and the alert popover, sent for design review.
