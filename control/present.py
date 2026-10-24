"""Display strings for the server-rendered snapshot (the page works without JavaScript). The browser modules compute the same
strings live; keep the two in step (docs/features/control.md): the photo layer maths is `layers()` in control/lights.js."""
from django.templatetags.static import static

from . import demo

SLIDE_LABEL = {key: label for key, label in demo.SCREEN_OPTIONS}

# Room photos (content/static/content/img/<name>-800.webp and -480.webp). A room without one gets the swan pattern.
PHOTOS = {"reception-lounge": "lounge", "hallway": "corridor", "changing-room": "lockers", "dry-sauna": "dry-sauna", "wet-sauna": "wet-sauna",
          "cold-plunge": "cold-plunge", "showers": "showers", "relaxing-zone": "relaxing-zone", "massage-room": "massage-room",
          "gym": "gym", "kitchenette": "kitchenette"}

# The light sources of each photo, as percentages of the frame: (x, y, radius). Stand-in for the pre-made "lamps maps" of the
# brief (Pillow is not installed here): soft warm spots blended with `screen` over the dimmed photo, so lamps stay lit as the
# room dims. Tuned by eye against the renders; a lamps map made from the photo itself can replace this later.
LAMPS = {
    "reception-lounge": [(50, 14, 34), (16, 55, 26), (84, 40, 24)],
    "hallway": [(50, 10, 30), (50, 42, 22), (50, 74, 18)],
    "changing-room": [(30, 14, 28), (70, 14, 28), (50, 60, 30)],
    "dry-sauna": [(50, 82, 36), (20, 30, 20), (80, 30, 20)],
    "wet-sauna": [(50, 80, 36), (22, 40, 20), (78, 40, 20)],
    "cold-plunge": [(50, 20, 34), (20, 70, 24), (80, 70, 24)],
    "showers": [(30, 15, 26), (70, 15, 26), (50, 55, 30)],
    "relaxing-zone": [(30, 14, 28), (70, 14, 28), (50, 62, 30)],
    "massage-room": [(50, 18, 32), (14, 60, 22), (86, 60, 22)],
    "gym": [(25, 14, 26), (75, 14, 26), (50, 50, 28)],
    "kitchenette": [(50, 12, 30), (22, 52, 24), (78, 52, 24)],
}


def lamps_background(slug):
    spots = LAMPS.get(slug, [(50, 20, 34)])
    return ",".join(f"radial-gradient(circle at {x}% {y}%, var(--ctl-warm-3000) 0, transparent {r}%)" for x, y, r in spots)


def clamp(value, low, high):
    return max(low, min(high, value))


def layers(on, bright, warmth):
    """Opacity of each photo layer (section 5). Only opacity ever changes."""
    if not on:
        return {"night": 0.94, "lamps": 0, "pool": 0, "warm": 0, "cool": 0}
    d = 0.88 * (1 - bright / 100) ** 1.2
    return {"night": d, "lamps": d * 0.85, "pool": d * 0.6,
            "warm": clamp((3000 - warmth) / 800, 0, 1) * 0.28, "cool": clamp((warmth - 3000) / 1000, 0, 1) * 0.35}


def layer_style(lights):
    o = layers(lights["on"], lights["bright"], lights["warmth"])
    return ";".join(f"--o-{k}:{v:.3f}" for k, v in o.items())


def light_opacity(lights):
    """The plan light shape, a soft tint and never a strong fill: 0.06 + brightness x 0.22 when on, else 0."""
    return round(0.06 + lights["bright"] / 100 * 0.22, 3) if lights["on"] else 0


def temp_text(value, decimals, unit="°C"):
    return f"{value:.{decimals}f}{unit}"


def people_text(count):
    return "Empty" if not count else ("1 person" if count == 1 else f"{count} people")


def glow_token(warmth):
    return min(demo.WARM_STOPS, key=lambda stop: abs(stop - warmth))


def effective_slide(screen):
    return screen["show"]["k"] if screen["power"] else "off"


def screen_text(screen):
    if not screen["power"]:
        return "Off"
    return f"{SLIDE_LABEL.get(screen['show']['k'], 'Welcome')}, {'looping' if screen['loop'] else 'once'}"


def preset_key(room):
    """The preset whose lights match this room, or "" (changed by hand)."""
    for preset in demo.PRESETS:
        lights = preset["lights"]
        if lights["on"] != room["lights"]["on"]:
            continue
        if lights["on"] and (lights["bright"], lights["warmth"]) != (room["lights"]["bright"], room["lights"]["warmth"]):
            continue
        return preset["key"]
    return ""


def status(room, state, alerts):
    """(badge word, tone). Same rules as the browser."""
    if any(a["room"] == room["slug"] for a in alerts):
        return "Alert", "danger"
    if not state["open"]:
        return "Closed", "muted"
    if state["active_scene"] == "cleaning":
        return "Cleaning", "soft"
    climate = room["caps"]["climate"]
    if climate:
        if not room["heater"]:
            return "Off", "muted"
        gap = room["cur"] - room["target"]
        if abs(gap) <= climate["tol"]:
            return "At target", "ok"
        return ("Heating" if gap < 0 else "Cooling"), "warn"
    return "Open", "ok"


def zone_of(room, zones):
    return next((z for z in zones if room["slug"] in z["rooms"]), None)


def room_view(room, state, screens, alerts):
    caps, lights = room["caps"], room["lights"]
    climate = caps["climate"]
    badge, tone = status(room, state, alerts)
    zone = zone_of(room, state["zones"])
    start = state["zone_start"].get(zone["id"]) if zone else None
    playlist = next((p["name"] for p in state["spotify"] if start and p["id"] == start[0]), None)
    out = {
        "badge": badge, "tone": tone,
        "bright_text": f"{lights['bright']}%" if lights["on"] else "Off", "bright_num": f"{lights['bright']}%",
        "warmth_text": f"{lights['warmth']}K",
        "glow_k": glow_token(lights["warmth"]), "photo": PHOTOS.get(room["slug"]),
        "photo_urls": ({"small": static(f"content/img/{PHOTOS[room['slug']]}-480.webp"), "large": static(f"content/img/{PHOTOS[room['slug']]}-800.webp")}
                       if room["slug"] in PHOTOS else None),
        "photo_style": layer_style(lights), "lamps": lamps_background(room["slug"]),
        "plan_opacity": light_opacity(lights), "off": not lights["on"],
        "people_text": people_text(room["people"]), "preset": preset_key(room),
        "bright_vt": f"{lights['bright']} percent", "warmth_vt": f"{lights['warmth']} kelvin",
        "music_text": f"{zone['name']}, {playlist}" if zone and playlist else (zone["name"] if zone else ""),
        "zone_id": zone["id"] if zone else "", "zone_name": zone["name"] if zone else "",
    }
    if climate:
        out.update({"cur_text": temp_text(room["cur"], climate["decimals"]), "target_text": temp_text(room["target"], 0),
                    "heater_word": "On" if room["heater"] else "Off"})
        if climate.get("humidity"):
            out["hum_text"] = f"{round(room['hum'])}% humidity"
            out["hum_target_text"] = f"{room['hum_target']}%"
    if caps.get("tank"):
        out["tank_text"] = temp_text(room["tank"], 1)
    line = "Alert" if tone == "danger" else (f"{lights['bright']}%  {lights['warmth']}K" if lights["on"] else "Off")
    out["plan_line"] = line
    out["plan_line2"] = out.get("cur_text", "") if climate and room["heater"] else ""
    screen = next((s for s in screens if s["id"] == caps.get("screen")), None)
    if screen:
        out["screen"] = screen
        out["screen_text"] = screen_text(screen)
    return out


def plan_aria(name, room):
    """The accessible name of a room on the plan."""
    v, lights = room["v"], room["lights"]
    parts = [f"{name}.", f"Lights {lights['bright']} percent, {lights['warmth']} kelvin." if lights["on"] else "Lights off."]
    if room["caps"]["climate"] and room["heater"]:
        parts.append(f"{round(room['cur'])} degrees.")
    if room["people"]:
        parts.append(v["people_text"] + ".")
    if v["tone"] == "danger":
        parts.append("Alert.")
    return " ".join(parts)
