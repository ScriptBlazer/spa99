"""The Control demo state (docs/design/CONTROL.md v2). No models, no writes. (The Library has its own models: views_library.py.)

`demo_state()` returns ONE dict built from real rows (visible Facility names and order, OpeningRule, active Closure,
SiteSettings.capacity) plus clearly marked DEMO values. The page prints it once with json_script and control.js owns it
after that. Later the real `venue` app replaces the DEMO parts behind the same shape (docs/features/control.md).

Everything marked "DEMO value" is pretend.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from plans.models import Closure, Facility, OpeningRule, SiteSettings

LONDON = ZoneInfo("Europe/London")
STATE_VERSION = 2
RECEPTION = {"slug": "reception-lounge", "name": "Reception and lounge"}
# Built-in demo rooms (not Facility rows): the Hallway (GF11) that links everything, and the Changing room (GF09). The real
# plan is the Panorama Interior ground floor lighting drawing, Rev 04 (control/plan.py).
HALLWAY = {"slug": "hallway", "name": "Hallway"}
CHANGING = {"slug": "changing-room", "name": "Changing room"}

LOCKERS_TOTAL = 60  # DEMO value: a guess until the lockers are specified
LANE_START = 5 * 60  # lane runs 05:00 to 05:00 (the nightly closure then sits at the right end)
EXAMPLE_CANDLES = time(17, 58)  # DEMO value: example candle lighting, real times come with the Phase 3 calendar sync
EXAMPLE_HAVDALAH = time(18, 20)  # DEMO value: example end of Shabbos
DEFAULT_PERIODS = [("Daytime", time(5, 0), time(18, 0)), ("Evening", time(18, 0), time(3, 0))]  # DEMO fallback if no rule rows
DEFAULT_CLOSURE = (time(3, 0), time(5, 0))  # DEMO fallback
AMBIENT = {"temp": 24, "water": 18}  # DEMO value: where a switched-off sauna or plunge settles

MENU_ITEMS = ["Tea", "Coffee", "Fresh mint", "Still and sparkling water"]  # DEMO value
SCREEN_OPTIONS = [("welcome", "Welcome"), ("hours", "Hours"), ("menu", "Menu"), ("notices", "Notices")]  # the built-in slides
DEFAULT_NOTICE = "The cold plunge is being cleaned until 14:00."  # DEMO value

# DEMO value: share of the building's people per room, and the busy-ness of each hour (fraction of capacity).
WEIGHTS = {"reception-lounge": 10, "hallway": 4, "changing-room": 10, "dry-sauna": 18, "wet-sauna": 10, "cold-plunge": 6, "showers": 6, "relaxing-zone": 20,
           "massage-room": 6, "gym": 14, "kitchenette": 10}
CURVE = [0.32, 0.20, 0.10, 0.0, 0.0, 0.08, 0.12, 0.20, 0.28, 0.32, 0.32, 0.30, 0.32, 0.36, 0.36, 0.40, 0.44, 0.52, 0.60,
         0.72, 0.76, 0.70, 0.64, 0.48]  # hour 0 to 23; 03:00 to 05:00 is closed

LIGHTS_ONLY = {"lights": True, "music": True, "screen": None, "climate": None, "tank": None}

# DEMO value: what each known room can do (section 6.2). Temperatures reuse the spa page placeholder facts.
ROOM_CAPS = {
    "hallway": {**LIGHTS_ONLY, "screen": "hallway"},
    "changing-room": dict(LIGHTS_ONLY),
    "reception-lounge": {**LIGHTS_ONLY, "screen": "reception", "tank": {"target": 25.0, "drift": 0.1}},
    "dry-sauna": {**LIGHTS_ONLY, "music": False,
                  "climate": {"kind": "temp", "label": "Temperature", "unit": "°C", "target": 85, "step": 1, "min": 60, "max": 100,
                              "drift": 0.4, "tol": 1.5, "decimals": 0, "rate": 1.0, "heater": "Heating"}},
    "wet-sauna": {**LIGHTS_ONLY, "music": False,
                  "climate": {"kind": "temp", "label": "Temperature", "unit": "°C", "target": 45, "step": 1, "min": 30, "max": 60,
                              "drift": 0.4, "tol": 1.5, "decimals": 0, "rate": 1.0, "heater": "Heating",
                              "humidity": {"target": 95, "step": 5, "min": 60, "max": 100, "drift": 2}}},
    "cold-plunge": {**LIGHTS_ONLY,
                    "climate": {"kind": "water", "label": "Water", "unit": "°C", "target": 12, "step": 1, "min": 4, "max": 20,
                                "drift": 0.2, "tol": 0.5, "decimals": 1, "rate": 0.1, "heater": "Chiller"}},
    "showers": dict(LIGHTS_ONLY),
    "relaxing-zone": {**LIGHTS_ONLY, "screen": "relaxing-zone"},
    "massage-room": dict(LIGHTS_ONLY),
    "gym": {**LIGHTS_ONLY, "screen": "gym"},
    "kitchenette": {**LIGHTS_ONLY, "screen": "kitchenette"},
}

# DEMO value: the screens in the building and where they hang (six, section 8 of the brief).
SCREENS = [
    ("reception", "Reception", "reception-lounge", "welcome"),
    ("lounge", "Lounge", "reception-lounge", "hours"),
    ("hallway", "Hallway", "hallway", "welcome"),
    ("gym", "Gym", "gym", "notices"),
    ("relaxing-zone", "Relaxing zone", "relaxing-zone", None),
    ("kitchenette", "Kitchenette", "kitchenette", "menu"),
]

# DEMO value: music zones (section 7.1). A room belongs to one zone; the saunas have no speakers.
ZONES = [
    {"id": "lounge", "name": "Lounge", "rooms": ["reception-lounge", "kitchenette", "hallway"]},
    {"id": "wet-area", "name": "Wet area", "rooms": ["cold-plunge", "showers", "ice-bucket", "changing-room"]},
    {"id": "relaxing-zone", "name": "Relaxing zone", "rooms": ["relaxing-zone"]},
    {"id": "massage-room", "name": "Massage room", "rooms": ["massage-room"]},
    {"id": "gym", "name": "Gym", "rooms": ["gym"]},
]
ZONE_START = {"lounge": ("warm-room", 1, 42), "wet-area": ("low-light", 0, 75)}  # DEMO value: (playlist, track, seconds in)
ZONE_VOLUME = {"lounge": 30, "wet-area": 25, "relaxing-zone": 20, "massage-room": 15, "gym": 55}  # DEMO value
SPOTIFY_ACCOUNT = "Spa 99 Music"  # DEMO value: no Spotify account is used

# DEMO value: sample "Spotify" playlists. Names and artists are invented, nothing here is real music or real artwork.
# (title, artist, seconds). The covers are typographic tiles drawn by the page.
SPOTIFY = [
    {"id": "warm-room", "name": "Warm Room", "tracks": [("Amber Hour", "Halden Quay", 212), ("Slow Brass", "The Lantern Room", 247), ("Velvet Weather", "Iselin Marr", 198), ("Low Sun", "Quiet Harbour", 263), ("Cedar and Smoke", "Oona Falk", 231), ("Winter Light", "Halden Quay", 189)]},
    {"id": "low-light", "name": "Low Light", "tracks": [("Night Shift", "Night Shift Quartet", 245), ("Candle Room", "Iselin Marr", 221), ("Hush", "Tamsin Vale", 176), ("Late Tide", "Quiet Harbour", 284), ("Soft Static", "The Lantern Room", 203), ("Blue Hour", "Oona Falk", 258)]},
    {"id": "slow-morning", "name": "Slow Morning", "tracks": [("First Steam", "Tamsin Vale", 192), ("Porcelain", "Halden Quay", 226), ("Kettle Song", "Fenwick and Rye", 169), ("Open Window", "Iselin Marr", 241), ("Morning Salt", "Quiet Harbour", 207), ("Clean Linen", "Oona Falk", 215)]},
    {"id": "gym-tempo", "name": "Gym Tempo", "tracks": [("Rack and Pulse", "Fenwick and Rye", 188), ("Iron Weather", "Marlow Drift", 201), ("Third Set", "The Lantern Room", 176), ("Chalk Dust", "Marlow Drift", 194), ("Last Rep", "Tamsin Vale", 183), ("Cooldown Lap", "Halden Quay", 222)]},
    {"id": "kitchen-radio", "name": "Kitchen Radio", "tracks": [("Mint and Honey", "Fenwick and Rye", 174), ("Saturday Cups", "Tamsin Vale", 198), ("Small Talk", "Marlow Drift", 163), ("Warm Plates", "Iselin Marr", 187), ("Tea Time Static", "Quiet Harbour", 209), ("Steady Hands", "Oona Falk", 176)]},
    {"id": "after-hours", "name": "After Hours", "tracks": [("Closing Time Slow", "Night Shift Quartet", 296), ("Lamp Oil", "Oona Falk", 252), ("Empty Corridor", "Quiet Harbour", 238), ("Last Train Home", "Halden Quay", 271), ("Dim", "Tamsin Vale", 214), ("Sleep Number", "The Lantern Room", 305)]},
]

# DEMO value: scene targets (section 8). `lights` None = leave lights alone. `heaters` "on"/"off" = every sauna heater
# and the plunge chiller where noted; None = leave. `screens` maps screen id (or "*") to content.
SCENES = [
    {"key": "opening", "label": "Opening", "time": "04:30", "lights": 70, "warmth": 3000,
     "music": {"on": True, "vol": 25}, "heaters": "on",
     "screens": {"reception": "welcome", "lounge": "hours"},
     "text": "Lights up, quiet music, heaters on, screens to Welcome and Hours."},
    {"key": "daytime", "label": "Daytime", "time": "08:00", "lights": 80, "warmth": 3000, "exceptions": {"relaxing-zone": 40},
     "music": {"on": True, "vol": 30}, "heaters": "on", "screens": {},
     "text": "Bright and warm, daytime music, heaters at target."},
    {"key": "evening", "label": "Evening", "time": "18:00", "lights": 50, "warmth": 2700, "exceptions": {"relaxing-zone": 25},
     "music": {"on": True, "vol": 25}, "heaters": "on", "screens": {},
     "text": "Softer light, evening music, heaters at target."},
    {"key": "closing", "label": "Closing", "time": "02:30", "lights": 35, "warmth": 2400,
     "music": {"on": True, "vol": 15}, "heaters": "off",
     "screens": {"reception": "notices", "lounge": "notices"}, "notice": "Closing at 03:00",
     "text": "Low light, very quiet music, heaters off, a closing notice on the screens."},
    {"key": "cleaning", "label": "Cleaning", "time": "03:00", "lights": 100, "warmth": 4000,
     "music": {"on": False}, "heaters": "off", "chiller_stays": True, "screens": {"*": "off"},
     "text": "Full light, music paused and screens off, heaters off (the plunge stays cold)."},
]
SAUNAS_HEAT = {"key": "saunas-heat", "label": "Saunas heat", "time": "04:15", "lights": None, "music": None, "heaters": "on",
               "screens": {}, "hidden": True, "text": "Turns the saunas on so they are at temperature for opening."}
EVENT_ORDER = ["saunas-heat", "opening", "daytime", "evening", "closing", "cleaning"]

ALERT_POOL = [  # DEMO value: calm wording, one fixture list
    {"id": "plunge-warm", "room": "cold-plunge", "text": "Cold plunge water 13.6°C, above target."},
    {"id": "gym-speaker", "room": "gym", "text": "Gym speaker not responding."},
    {"id": "kitchen-screen", "room": "kitchenette", "text": "Kitchenette screen offline."},
]

PRESETS = [  # DEMO value: a preset sets the lights of one room
    {"key": "bright", "label": "Bright", "lights": {"on": True, "bright": 100, "warmth": 4000}},
    {"key": "day", "label": "Day", "lights": {"on": True, "bright": 80, "warmth": 3000}},
    {"key": "calm", "label": "Calm", "lights": {"on": True, "bright": 35, "warmth": 2400}},
    {"key": "off", "label": "Off", "lights": {"on": False}},
]

WARM_STOPS = [2200, 2700, 3000, 4000]  # the glow colours are CSS tokens --ctl-warm-<K>


def minutes(t):
    return t.hour * 60 + t.minute


def clock_text(total_minutes):
    total_minutes %= 1440
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def lane_pos(minute_of_day):
    """Minutes into the 05:00 to 05:00 lane."""
    return (minute_of_day - LANE_START) % 1440


def pct(lane_minutes):
    return round(lane_minutes / 14.4, 3)


def occupancy_fraction(minute_of_day):
    hour, rest = divmod(minute_of_day, 60)
    a, b = CURVE[hour % 24], CURVE[(hour + 1) % 24]
    return a + (b - a) * rest / 60


def _scene_by_key():
    return {s["key"]: s for s in SCENES + [SAUNAS_HEAT]}


def active_scene_key(minute_of_day):
    """The newest scene event at this time of day (a scene stays until the next one)."""
    best, best_delta = SCENES[0]["key"], 99999
    for scene in SCENES:
        delta = (minute_of_day - minutes(time.fromisoformat(scene["time"]))) % 1440
        if delta < best_delta:
            best, best_delta = scene["key"], delta
    return best


def _rules():
    rules = list(OpeningRule.objects.filter(active=True))
    periods = [(r.label, r.start_time, r.end_time) for r in rules if r.kind == OpeningRule.PERIOD and r.start_time and r.end_time]
    closure = next(((r.start_time, r.end_time) for r in rules if r.kind == OpeningRule.DAILY_CLOSURE and r.start_time and r.end_time), None)
    before = next((r.offset_minutes for r in rules if r.kind == OpeningRule.CLOSE_BEFORE_CANDLES and r.offset_minutes is not None), None)
    after = next((r.offset_minutes for r in rules if r.kind == OpeningRule.OPEN_AFTER_NIGHTFALL and r.offset_minutes is not None), None)
    return periods or DEFAULT_PERIODS, closure or DEFAULT_CLOSURE, before, after


def _span(start_min, end_min):
    """(start, length) in lane minutes for a wall-clock span that may run past midnight."""
    start = lane_pos(start_min)
    length = (end_min - start_min) % 1440 or 1440
    return start, min(length, 1440 - start)


def _event_rows(events):
    """Stack pills that would collide onto extra rows (estimated width by label length; pills near the end hang leftwards)."""
    placed = []  # (row, lo, hi)
    for event in sorted(events, key=lambda e: e["pos"]):
        width = (len(event["name"]) * 7 + 28) / 1100 * 100
        at = event["pct"]
        end = at > 70
        lo, hi = (at - width, at) if end else (at, at + width)
        row = 0
        while any(r == row and lo < h and l < hi for r, l, h in placed):
            row += 1
        placed.append((row, lo, hi))
        event["row"], event["end"] = row, end
    return max((e["row"] for e in events), default=0) + 1


def _week(now, periods, closure, before, after):
    first_day = now.date() if minutes(now.time()) >= LANE_START else now.date() - timedelta(days=1)
    closures = list(Closure.objects.filter(active=True, ends_at__gte=timezone.now(), starts_at__lte=timezone.now() + timedelta(days=8)))
    scenes = _scene_by_key()
    days = []
    for i in range(7):
        date = first_day + timedelta(days=i)
        lane_open = datetime.combine(date, time(LANE_START // 60, LANE_START % 60), LONDON)
        lane_close = lane_open + timedelta(days=1)
        bands = []
        for label, start, end in periods:
            s, length = _span(minutes(start), minutes(end))
            bands.append({"label": label, "start": s, "len": length, "pct": pct(s), "wpct": pct(length), "range": f"{clock_text(minutes(start))} to {clock_text(minutes(end))}"})
        closed = []
        s, length = _span(minutes(closure[0]), minutes(closure[1]))
        closed.append({"kind": "nightly", "label": "Closed", "start": s, "len": length, "pct": pct(s), "wpct": pct(length),
                       "text": f"Closed {clock_text(minutes(closure[0]))} to {clock_text(minutes(closure[1]))}"})
        notes = []
        weekday = date.weekday()  # Friday 4, Saturday 5
        if weekday == 4 and before is not None:
            close_at = minutes(EXAMPLE_CANDLES) - before
            s = lane_pos(close_at)
            closed.append({"kind": "shabbos", "label": "Closed", "start": s, "len": 1440 - s, "pct": pct(s), "wpct": pct(1440 - s),
                           "text": f"Closed from {clock_text(close_at)}", "note": f"Closes {before // 60} h before candle lighting ({clock_text(close_at)}, example time)."})
            notes.append(f"Closes {before // 60 if before % 60 == 0 else before} {'h' if before % 60 == 0 else 'min'} before candle lighting, {clock_text(close_at)}. Example time, real times come with the calendar sync.")
        if weekday == 5 and after is not None:
            open_at = minutes(EXAMPLE_HAVDALAH) + after
            length = lane_pos(open_at)
            closed.append({"kind": "shabbos", "label": "Closed", "start": 0, "len": length, "pct": 0, "wpct": pct(length),
                           "text": f"Closed until {clock_text(open_at)}"})
            notes.append(f"Opens {after // 60 if after % 60 == 0 else after} {'h' if after % 60 == 0 else 'min'} after Shabbos ends, {clock_text(open_at)}. Example time, real times come with the calendar sync.")
        for c in closures:
            starts, ends = max(c.starts_at, lane_open), min(c.ends_at, lane_close)
            if starts < ends:
                s = int((starts - lane_open).total_seconds() // 60)
                length = int((ends - starts).total_seconds() // 60)
                closed.append({"kind": "closure", "label": c.name, "start": s, "len": length, "pct": pct(s), "wpct": pct(length), "text": c.name})
                notes.append(f"{c.name}: closed.")
        events = []
        for key in EVENT_ORDER:
            scene = scenes[key]
            minute = minutes(time.fromisoformat(scene["time"]))
            pos = lane_pos(minute)
            skipped = any(c["kind"] != "nightly" and c["start"] <= pos < c["start"] + c["len"] for c in closed)
            events.append({"key": key, "name": scene["label"], "time": scene["time"], "pos": pos, "pct": pct(pos), "skipped": skipped, "text": scene["text"]})
        rows = _event_rows(events)
        phone = [dict(e, type="event") for e in events] + [dict(c, type="closed", pos=c["start"]) for c in closed]
        days.append({"index": i, "date": date.isoformat(), "label": "Today" if i == 0 else f"{date:%A}", "short": f"{date:%a} {date.day} {date:%b}",
                     "today": i == 0, "bands": bands, "closed": closed, "events": events, "rows": rows, "notes": notes,
                     "list": sorted(phone, key=lambda item: (item["pos"], item["type"])),
                     "skipped": ", ".join(e["name"] for e in events if e["skipped"])})
    return days


def _distribute(total, slugs):
    """Spread `total` people over rooms by weight (largest remainder), deterministic."""
    weights = {slug: WEIGHTS.get(slug, 5) for slug in slugs}
    whole = sum(weights.values()) or 1
    raw = {slug: total * w / whole for slug, w in weights.items()}
    counts = {slug: int(v) for slug, v in raw.items()}
    for slug in sorted(slugs, key=lambda s: raw[s] - counts[s], reverse=True)[: total - sum(counts.values())]:
        counts[slug] += 1
    return counts


def _rooms():
    rows = [RECEPTION, HALLWAY, CHANGING] + [{"slug": f.slug, "name": f.name} for f in Facility.objects.filter(visible=True).order_by("order", "name")]
    return rows


def _room_target(room_caps, scene, slug):
    """What a scene sets in one room (None parts are left alone)."""
    out = {}
    if scene.get("lights") is not None and room_caps["lights"]:
        out["lights"] = {"on": True, "bright": scene.get("exceptions", {}).get(slug, scene["lights"]), "warmth": scene["warmth"]}
    if scene.get("heaters") and room_caps["climate"]:
        out["heater"] = scene["heaters"] == "on" or (scene.get("chiller_stays") and room_caps["climate"]["kind"] == "water")
    return out


def demo_state(now=None):
    """The one dict the Control pages print. `now` is for tests."""
    now = (now or timezone.now()).astimezone(LONDON)
    site = SiteSettings.load()
    capacity = site.capacity
    periods, closure, before, after = _rules()
    week = _week(now, periods, closure, before, after)
    minute = minutes(now.time())
    lane_now = lane_pos(minute)
    today = week[0]
    open_now = not any(c["start"] <= lane_now < c["start"] + c["len"] for c in today["closed"])
    scene_key = active_scene_key(minute)
    scene = _scene_by_key()[scene_key]

    total = round(capacity * occupancy_fraction(minute)) if open_now else 0
    room_rows = _rooms()
    counts = _distribute(total, [r["slug"] for r in room_rows])

    rooms = []
    for row in room_rows:
        caps = ROOM_CAPS.get(row["slug"], dict(LIGHTS_ONLY))
        target = _room_target(caps, scene, row["slug"])
        lights = {"on": True, "bright": 60, "warmth": 2700, **target.get("lights", {})}
        climate = caps["climate"]
        room = {"slug": row["slug"], "name": row["name"], "caps": caps, "lights": lights, "music": {"trim": 100},
                "heater": target.get("heater", True), "people": counts[row["slug"]]}
        if climate:
            room.update({"target": climate["target"], "base": climate["target"] if room["heater"] else AMBIENT[climate["kind"]],
                         "cur": climate["target"] if room["heater"] else AMBIENT[climate["kind"]]})
            if climate.get("humidity"):
                room["hum_target"] = climate["humidity"]["target"]
                room["hum"] = climate["humidity"]["target"] if room["heater"] else 40
        if caps.get("tank"):
            room["tank"] = caps["tank"]["target"]
        rooms.append(room)

    visible_slugs = {r["slug"] for r in rooms}
    screens = []
    for sid, name, room_slug, content in SCREENS:
        if room_slug not in visible_slugs:
            continue
        content = content or "off"
        if scene.get("screens", {}).get(sid) or scene.get("screens", {}).get("*"):
            content = scene["screens"].get(sid) or scene["screens"]["*"]
        screens.append({"id": sid, "name": name, "room": room_slug, "show": {"t": "slide", "k": "welcome" if content == "off" else content},
                        "power": content != "off", "loop": True, "playing": True,
                        "notice": scene.get("notice") if scene.get("notice") and content == "notices" else DEFAULT_NOTICE})

    speakers = {r["slug"] for r in rooms if r["caps"]["music"]}
    zones, placed = [], set()
    for zone in ZONES:
        members = [slug for slug in zone["rooms"] if slug in speakers]
        placed.update(members)
        if members:
            zones.append({"id": zone["id"], "name": zone["name"], "rooms": members, "vol": ZONE_VOLUME.get(zone["id"], 25)})
    left = [r["slug"] for r in rooms if r["slug"] in speakers and r["slug"] not in placed]
    if left:
        zones.append({"id": "other", "name": "Other rooms", "rooms": left, "vol": 25})

    pool = [a for a in ALERT_POOL if a["room"] in visible_slugs]
    alerts = [dict(pool[1] if len(pool) > 1 else pool[0], since=clock_text(minute - 12))] if pool else []
    last_period = periods[-1]
    return {
        "v": STATE_VERSION,
        "now": {"min": minute, "clock": clock_text(minute), "date": f"{now:%a} {now.day} {now:%b}", "lane": lane_now, "open": open_now},
        "capacity": capacity, "lockers_total": LOCKERS_TOTAL, "open": open_now, "people": total,
        "curve": CURVE, "weights": WEIGHTS, "ambient": AMBIENT, "lane_start": LANE_START,
        "rooms": rooms, "screens": screens,
        "scenes": SCENES + [SAUNAS_HEAT], "active_scene": scene_key,
        "zones": zones, "zone_start": {k: list(v) for k, v in ZONE_START.items()}, "spotify": [
            {"id": p["id"], "name": p["name"], "field": i % 6, "tracks": [{"title": t, "artist": a, "dur": d} for t, a, d in p["tracks"]]}
            for i, p in enumerate(SPOTIFY)], "spotify_account": SPOTIFY_ACCOUNT,
        "opens_at": clock_text(minutes(periods[0][1])),
        "screen_options": [{"key": k, "label": v} for k, v in SCREEN_OPTIONS], "presets": PRESETS,
        "alerts": alerts, "alert_pool": pool, "menu": MENU_ITEMS, "default_notice": DEFAULT_NOTICE,
        "hours_line": f"Open until {clock_text(minutes(last_period[2]))}",
        "hours_detail": [f"{label} {clock_text(minutes(start))} to {clock_text(minutes(end))}" for label, start, end in periods],
        "week": week, "warm_stops": WARM_STOPS,
        "axis": [{"label": clock_text(LANE_START + 180 * i), "pct": 12.5 * i} for i in range(9)],
        "now_pct": pct(lane_now),
    }
