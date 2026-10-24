"""Display strings for the server-rendered snapshot (the page works without JavaScript). control.js computes the same
strings live; keep the two in step (docs/features/control.md)."""
from . import demo

SCREEN_LABEL = {key: label for key, label in demo.SCREEN_OPTIONS}


def temp_text(value, decimals, unit="°C"):
    return f"{value:.{decimals}f}{unit}"


def people_text(count):
    return "Empty" if not count else ("1 person" if count == 1 else f"{count} people")


def glow_token(warmth):
    return min(demo.WARM_STOPS, key=lambda stop: abs(stop - warmth))


def effective_content(screen):
    return screen["content"] if screen["power"] else "off"


def preset_key(room):
    """The preset whose lights and music match this room, or "" (changed by hand)."""
    for preset in demo.PRESETS:
        lights, music = preset["lights"], preset["music"]
        if lights["on"] != room["lights"]["on"]:
            continue
        if lights["on"] and (lights["bright"], lights["warmth"]) != (room["lights"]["bright"], room["lights"]["warmth"]):
            continue
        if room["caps"]["music"]:
            if music["on"] != room["music"]["on"]:
                continue
            if music["on"] and (music["playlist"], music["vol"]) != (room["music"]["playlist"], room["music"]["vol"]):
                continue
        return preset["key"]
    return ""


def status(room, state, alerts):
    """(badge word, tone). Same rules as control.js."""
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


def room_view(room, state, screens, alerts):
    caps, lights, music = room["caps"], room["lights"], room["music"]
    climate = caps["climate"]
    badge, tone = status(room, state, alerts)
    out = {
        "badge": badge, "tone": tone,
        "bright_text": f"{lights['bright']}%" if lights["on"] else "Off", "bright_num": f"{lights['bright']}%",
        "warmth_text": f"{lights['warmth']}K",
        "glow_k": glow_token(lights["warmth"]),
        "glow_a": round(0.04 + lights["bright"] / 100 * 0.24, 3) if lights["on"] else 0,
        "music_text": music["playlist"] if music["on"] else "Off",
        "people_text": people_text(room["people"]),
        "preset": preset_key(room),
        "lights_word": "On" if lights["on"] else "Off", "music_word": "On" if music["on"] else "Off",
        "bright_vt": f"{lights['bright']} percent", "warmth_vt": f"{lights['warmth']} kelvin", "vol_vt": f"{music['vol']} percent",
    }
    if climate:
        out.update({
            "cur_text": temp_text(room["cur"], climate["decimals"]), "target_text": temp_text(room["target"], 0),
            "heater_word": "On" if room["heater"] else "Off",
        })
        if climate.get("humidity"):
            out["hum_text"] = f"{round(room['hum'])}% humidity"
            out["hum_target_text"] = f"{room['hum_target']}%"
    if caps.get("tank"):
        out["tank_text"] = temp_text(room["tank"], 1)
    screen = next((s for s in screens if s["id"] == caps.get("screen")), None)
    if screen:
        out["screen"] = screen
        out["screen_text"] = SCREEN_LABEL[effective_content(screen)]
    return out
