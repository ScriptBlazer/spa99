"""The floor plan drawn on the Overview (docs/design/CONTROL.md section 4.1). Stylised, not architectural.

It follows the real ground floor lighting drawing (Panorama Interior, "99 Vale Road - Shvitz, Proposed ground floor lighting",
Rev 04, 1:80): one long rectangle, saunas on the far left, then the shower and cold plunge room above the relaxing zone, WCs,
changing room, hallway, kitchenette, the stair and lift core, massage room, gym, and the entrance (lounge and reception) on the
right with its curved feature wall. Rooms are placed in roughly the right places and proportions; unlit rooms (WCs, stairs and
lift, plant rooms, dry riser, electrical) are drawn but have no controls.

`GEOMETRY` is the one list of rooms; the template loops over what `build()` returns, so a new room is a data change here.
Desktop uses viewBox 0 0 1200 440. The phone plan is the same geometry transposed (x and y swapped) so it fills a narrow
screen; the hallway band is stretched there so the hallway stays at least 56 px thick once scaled to the screen.
"""
from django.utils.safestring import mark_safe

DESKTOP_BOX = (1200, 440)
BAND_Y = (247, 305)  # the hallway band
PHONE_EXTRA = 30  # extra units the band gets on the phone plan
PHONE_BOX = (440 + PHONE_EXTRA, 1200)
INSET = 4  # each room is drawn 4 units inside its box: the 8-unit gaps between rooms are the walls

# slug None = a room with no controls (drawn unlit, not a link). "poly" = the drawn outline (already inset), box = its bounds.
GEOMETRY = [
    {"id": "dry-sauna", "slug": "dry-sauna", "name": "Dry sauna", "box": (12, 14, 142, 192),
     "hints": [("rect", 20, 70, 14, 50, 3, "heater"), ("line", 62, 128, 128, 128, "bench"), ("line", 62, 154, 128, 154, "bench")]},
    {"id": "wet-sauna", "slug": "wet-sauna", "name": "Wet sauna", "box": (12, 192, 142, 390),
     "hints": [("line", 40, 300, 128, 300, "bench"), ("line", 40, 326, 128, 326, "bench"), ("line", 40, 352, 128, 352, "bench")]},
    {"id": "showers", "slug": "showers", "name": "Showers", "box": (142, 14, 307, 110),
     "hints": [("circle", 192 + 36 * i, 90, 7) for i in range(4)] + [("rect", 152, 58, 16, 30, 3, "heater")]},
    {"id": "cold-plunge", "slug": "cold-plunge", "name": "Cold plunge", "box": (142, 110, 307, 247),
     "hints": [("circle", 268, 205, 25, "pool"), ("rect", 168, 170, 46, 14, 4), ("rect", 168, 200, 46, 14, 4)]},
    {"id": "relaxing", "slug": "relaxing-zone", "name": "Relaxing zone", "box": (142, 247, 382, 390),
     "hints": [("rect", 156 + 38 * i, 306, 22, 66, 6) for i in range(6)]},
    {"id": "wcs", "slug": None, "name": "WCs", "box": (307, 14, 467, 97), "hints": []},
    {"id": "changing", "slug": "changing-room", "name": "Changing room", "box": (307, 97, 467, 247),
     "hints": [("rect", 316, 140, 12, 92, 3), ("rect", 440, 150, 16, 60, 3)]},
    {"id": "stairs", "slug": None, "name": "Stairs and lift", "box": (467, 14, 757, 164),
     "hints": [("rect", 480, 56, 130, 96, 2, "steps"), ("rect", 656, 40, 84, 104, 4)]},
    {"id": "plant", "slug": None, "name": "Plant room", "box": (467, 164, 597, 247), "hints": []},
    {"id": "riser", "slug": None, "name": "Dry riser", "box": (597, 164, 727, 240), "hints": []},
    {"id": "hallway", "slug": "hallway", "name": "Hallway", "box": (382, 247, 667, 305), "slim": True,
     "hints": [("line", 410, 276, 640, 276, "dot")]},
    {"id": "kitchenette", "slug": "kitchenette", "name": "Kitchenette", "box": (382, 305, 517, 390),
     "hints": [("circle", 452, 366, 14)]},
    {"id": "massage", "slug": "massage-room", "name": "Massage room", "box": (517, 305, 667, 390),
     "hints": [("rect", 548, 346, 90, 30, 6)]},
    {"id": "gym", "slug": "gym", "name": "Gym", "box": (667, 272, 847, 390),
     "hints": [("rect", 690, 340, 26, 40, 5), ("rect", 740, 316, 22, 64, 4), ("rect", 800, 330, 18, 50, 4)]},
    {"id": "wc12", "slug": None, "name": "WC", "box": (757, 14, 837, 127), "hints": []},
    {"id": "plant13", "slug": None, "name": "Plant room", "box": (837, 14, 955, 150), "hints": []},
    {"id": "entrance", "slug": "reception-lounge", "name": "Entrance", "box": (747, 172, 1190, 390),
     "poly": [(751, 176), (1186, 176), (1186, 328), (1086, 328), (1086, 386), (851, 386), (851, 268), (751, 268)],
     "label": (872, 352), "count": (1074, 352), "plabel": (868, 281), "name_dx": 0,
     "hints": [("path", [("M", 756, 214), ("C", 850, 196, 880, 262, 962, 270), ("C", 1030, 276, 1060, 306, 1086, 326)]),
               ("rect", 776, 196, 120, 12, 4, "tank"), ("text", 836, 236, "Fish tank", 0),
               ("rect", 1092, 190, 70, 30, 8), ("rect", 1096, 232, 24, 24, 6), ("rect", 1136, 236, 22, 44, 6),
               ("rect", 1040, 296, 28, 74, 12), ("rect", 960, 330, 56, 22, 5)],
     "door": (947, 1002)},
    {"id": "electrical", "slug": None, "name": "Electrical", "box": (1086, 328, 1190, 390), "hints": []},
    {"id": "survey", "slug": None, "name": "Not surveyed", "box": (955, 14, 1190, 172), "hints": [], "ghost": True},
]


def _fix(value):
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text or "0"


def _map_y(y, phone):
    """Phone only: the hallway band is stretched and everything below it moves down."""
    if not phone:
        return y
    top, bottom = BAND_Y
    if y <= top:
        return y
    if y <= bottom:
        return top + (y - top) * (1 + PHONE_EXTRA / (bottom - top))
    return y + PHONE_EXTRA


def _pt(x, y, phone):
    """Plan point to drawing point."""
    return (_map_y(y, phone), x) if phone else (x, y)


def _hint(hint, phone):
    kind = hint[0]
    if kind == "rect":
        x, y, w, h, rx = hint[1:6]
        style = hint[6] if len(hint) > 6 else ""
        (ax, ay), (bx, by) = _pt(x, y, phone), _pt(x + w, y + h, phone)
        x0, y0, x1, y1 = min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)
        return f'<rect class="pr-hint {style}" x="{_fix(x0)}" y="{_fix(y0)}" width="{_fix(x1 - x0)}" height="{_fix(y1 - y0)}" rx="{rx}"/>'
    if kind == "line":
        x1, y1, x2, y2 = hint[1:5]
        style = hint[5] if len(hint) > 5 else ""
        (ax, ay), (bx, by) = _pt(x1, y1, phone), _pt(x2, y2, phone)
        return f'<line class="pr-hint {style}" x1="{_fix(ax)}" y1="{_fix(ay)}" x2="{_fix(bx)}" y2="{_fix(by)}"/>'
    if kind == "circle":
        cx, cy, r = hint[1:4]
        style = hint[4] if len(hint) > 4 else ""
        px, py = _pt(cx, cy, phone)
        return f'<circle class="pr-hint {style}" cx="{_fix(px)}" cy="{_fix(py)}" r="{r}"/>'
    if kind == "path":
        parts = []
        for command, *numbers in hint[1]:
            pairs = [_pt(numbers[i], numbers[i + 1], phone) for i in range(0, len(numbers), 2)]
            parts.append(command + " " + " ".join(f"{_fix(x)} {_fix(y)}" for x, y in pairs))
        return f'<path class="pr-hint" d="{" ".join(parts)}"/>'
    if kind == "text":
        x, y, text, rotate = hint[1:5]
        px, py = _pt(x, y, phone)
        if phone:  # labels stay upright on the phone plan
            return f'<text class="pr-note" x="{_fix(px)}" y="{_fix(py)}" text-anchor="middle">{text}</text>'
        return f'<text class="pr-note" x="{_fix(px)}" y="{_fix(py)}" text-anchor="middle">{text}</text>'
    return ""


def _shape(room, phone):
    x1, y1, x2, y2 = room["box"]
    (ax, ay), (bx, by) = _pt(x1, y1, phone), _pt(x2, y2, phone)
    left, top, right, bottom = min(ax, bx) + INSET, min(ay, by) + INSET, max(ax, bx) - INSET, max(ay, by) - INSET  # the 8-unit gaps are drawn, not scaled
    width, height = right - left, bottom - top
    slim = bool(room.get("slim"))
    small = (min(width, height) < (110 if phone else 140)) or slim
    if phone:
        # centred and upright, near the top of the shape (a slim room: the middle); the entrance has its own spot
        if room.get("plabel"):
            centre_x, name_y = _pt(*room["plabel"], phone=True)
        else:
            centre_x, name_y = left + width / 2, top + (height / 2 - 4 if slim else 24)
        out = {"anchor": "middle", "name_x": centre_x, "name_y": name_y, "val_x": centre_x, "val_y": name_y + 19,
               "val2_y": name_y + 37, "count_x": right - 8, "count_y": top + 18}
    else:
        if room.get("label"):
            lx, ly = room["label"]
            out = {"anchor": "start", "name_x": lx, "name_y": ly, "val_x": lx, "val_y": ly + 22, "val2_y": ly + 42,
                   "count_x": room["count"][0], "count_y": room["count"][1]}
        else:
            out = {"anchor": "start", "name_x": left + 10, "name_y": top + 22, "val_x": left + 10, "val_y": top + 40,
                   "val2_y": top + 58, "count_x": right - 8, "count_y": top + 20}
    shape = {"id": room["id"], "slug": room["slug"], "name": room["name"], "x": _fix(left), "y": _fix(top), "w": _fix(width),
             "h": _fix(height), "small": small, "slim": slim, "ghost": bool(room.get("ghost")),
             "hints": mark_safe("".join(_hint(h, phone) for h in room["hints"])),
             "lines": room["name"].split(" ") if (phone and small and " " in room["name"] and not slim) else None}
    if room.get("poly"):
        points = [_pt(x, y, phone) for x, y in room["poly"]]
        shape["poly"] = "M " + " L ".join(f"{_fix(x)} {_fix(y)}" for x, y in points) + " Z"
    shape.update({k: _fix(v) if isinstance(v, (int, float)) else v for k, v in out.items()})
    if room.get("door"):
        a, b = room["door"]
        p1, p2 = _pt(a, 388, phone), _pt(b, 388, phone)
        shape["door"] = {"x1": _fix(p1[0]), "y1": _fix(p1[1]), "x2": _fix(p2[0]), "y2": _fix(p2[1])}
        mid = _pt((a + b) / 2, 388, phone)
        shape["entrance"] = ({"x": _fix(mid[0]), "y": "424", "anchor": "middle"} if not phone
                             else {"x": _fix(mid[0] - 6), "y": _fix(mid[1] - 10), "anchor": "end"})
    return shape


def build(phone=False):
    """The shapes for one drawing, in paint order."""
    return {"viewbox": "0 0 %d %d" % (PHONE_BOX if phone else DESKTOP_BOX), "shapes": [_shape(r, phone) for r in GEOMETRY],
            "planters": planters(phone)}


def planters(phone):
    """Decoration: the planters along the pavement outside the Vale Road wall."""
    out = []
    for i in range(10):
        x = 40 + i * 118
        (ax, ay), (bx, by) = _pt(x, 402, phone), _pt(x + 70, 410, phone)
        out.append({"x": _fix(min(ax, bx)), "y": _fix(min(ay, by)), "w": _fix(abs(bx - ax)), "h": _fix(abs(by - ay))})
    return out


def model():
    """The same plan as outlines for the 3D Overview, in plan units (y down). Each room is already inset by INSET, so the gaps
    between rooms are the walls; the script grows each outline by half a gap to draw its own half of every shared wall.
    `slug` None = a space with no controls (drawn darker, no label). The "not surveyed" ghost is not drawn."""
    rooms = []
    for room in GEOMETRY:
        if room.get("ghost"):
            continue
        x1, y1, x2, y2 = room["box"]
        points = room.get("poly") or [(x1 + INSET, y1 + INSET), (x2 - INSET, y1 + INSET), (x2 - INSET, y2 - INSET), (x1 + INSET, y2 - INSET)]
        rooms.append({"id": room["id"], "slug": room["slug"], "name": room["name"], "points": [list(point) for point in points]})
    door = next(r["door"] for r in GEOMETRY if r.get("door"))
    return {"rooms": rooms, "notes": [{"text": "Entrance, Vale Road", "x": (door[0] + door[1]) / 2, "y": 408}]}
