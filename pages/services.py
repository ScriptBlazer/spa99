"""Glue between the data apps (plans, content, journey) and the page templates. Nothing here is a rule:
every number and word comes from rows edited in Control."""
import re
from functools import lru_cache
from decimal import Decimal

from django.utils import timezone

from content import services as content

from content import images
from plans import services as plan_services
from plans.models import Facility, OpeningRule, Plan, SiteSettings

# Home "What's inside" preview: the photo shown for a room (IMMERSIVE-R2 section 3, R3). Rooms not listed keep the current picture.
# No photo here may appear elsewhere on Home: dry-sauna (Heat, slowly), cold-plunge, relax-loungers (the ritual) and lounge
# (the journey entry) are already used above, so those rooms are not listed.
# Home-specific preview crops; any room not listed uses its own Facility.image_name.
HOME_PREVIEW_IMAGES = {"cold-plunge": "cold-tub", "wet-sauna": "wet-sauna", "showers": "showers", "massage-room": "massage-room", "gym": "gym", "kitchenette": "kitchenette"}


def split_label(label):
    """'Early morning (5 to 9am)' -> ('Early morning', '5 to 9am'); no brackets -> (label, ''). Mirrored in api.js."""
    main, sep, rest = (label or "").partition(" (")
    return (main.strip(), rest.rstrip(")").strip()) if sep else ((label or "").strip(), "")


# ---------- hours ----------

_clock = plan_services.clock


def opening_hours():
    """Opening hours as [(label, text)] from the rules (open periods first, then the closures)."""
    rules = list(OpeningRule.objects.filter(active=True))
    rows = []
    for rule in rules:
        if rule.kind == OpeningRule.PERIOD and rule.start_time and rule.end_time:
            rows.append((rule.label, f"{_clock(rule.start_time)} to {_clock(rule.end_time)}"))
    for rule in rules:
        if rule.kind == OpeningRule.DAILY_CLOSURE and rule.start_time and rule.end_time:
            rows.append(("Closed", f"{_clock(rule.start_time)} to {_clock(rule.end_time)}, every day"))
    shabbos = shabbos_hours_text(rules)
    if shabbos:
        rows.append(shabbos)
    return rows


def _span(minutes):
    """120 -> '2 hours', 60 -> '1 hour', 90 -> '90 minutes'."""
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{minutes} minutes"


def shabbos_hours_text(rules):
    """The detailed Shabbos / Yom Tov row, worked out from the two offsets in System > Hours:
    ('Shabbos and Yom Tov', 'Closes 2 hours before Shabbos and Yom Tov begin. Opens 1 hour after they end.').
    Falls back to a rule's public note when an offset is missing; None when nothing is set."""
    close = next((r for r in rules if r.kind == OpeningRule.CLOSE_BEFORE_CANDLES), None)
    open_ = next((r for r in rules if r.kind == OpeningRule.OPEN_AFTER_NIGHTFALL), None)
    title = next((r.public_title for r in (close, open_) if r and r.public_title), "") or "Shabbos and Yom Tov"
    parts = []
    if close and close.offset_minutes:
        parts.append(f"Closes {_span(close.offset_minutes)} before Shabbos and Yom Tov begin.")
    if open_ and open_.offset_minutes:
        parts.append(f"Opens {_span(open_.offset_minutes)} after {'they' if parts else 'Shabbos and Yom Tov'} end.")
    if parts:
        return (title, " ".join(parts))
    note = next((r for r in (close, open_) if r and r.public_note), None)
    return (note.public_title or note.label, note.public_note) if note else None


def hours_summary():
    """One short line for the footer and menu, e.g. 'Open 5am to 3am'."""
    periods = [
        (_clock(r.start_time), _clock(r.end_time))
        for r in OpeningRule.objects.filter(active=True, kind=OpeningRule.PERIOD) if r.start_time and r.end_time
    ]
    if len(periods) >= 2:
        return f"Open {periods[0][0]} to {periods[-1][1]}"
    return f"Open {periods[0][0]} to {periods[0][1]}" if periods else ""


def closure_title():
    """The public name of the weekly closure ('Shabbos and Yom Tov'), or '' when none is set in Control."""
    rule = OpeningRule.objects.filter(active=True, kind=OpeningRule.CLOSE_BEFORE_CANDLES).exclude(public_title="").first()
    return rule.public_title if rule else ""


def hours_facts():
    """The two numbers Home shows, from the open periods: {'range': '5am to 3am', 'hours': 22}. None when no period is set."""
    periods = [r for r in OpeningRule.objects.filter(active=True, kind=OpeningRule.PERIOD) if r.start_time and r.end_time]
    if not periods:
        return None
    minutes = sum(((r.end_time.hour * 60 + r.end_time.minute) - (r.start_time.hour * 60 + r.start_time.minute)) % 1440 or 1440
                  for r in periods)
    return {"range": f"{_clock(periods[0].start_time)} to {_clock(periods[-1].end_time)}", "hours": round(minutes / 60)}


# ---------- greeting ----------

def greeting(user, now=None):
    """'Good evening, Daniel.' (morning before 12, afternoon before 6, evening otherwise, Europe/London)."""
    now = timezone.localtime(now or timezone.now())
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
    name = (user.first_name or "").strip()
    return f"Good {part}, {name}." if name else f"Good {part}."


# ---------- plans ----------

def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def character(plan):
    if plan.kind == Plan.ONE_OFF:
        return "One visit"
    if plan.is_unlimited:
        return "Unlimited"
    return "Daytime" if plan.is_daytime_only else "Any time"


def plan_lines(plan):
    """Short included lines for a plan row, from its data (at most four)."""
    lines = []
    if plan.kind == Plan.ONE_OFF:
        lines.append("One visit, no membership")
    elif plan.is_unlimited:
        lines.append("Unlimited visits")
    else:
        lines.append(f"{_plural(plan.visits_per_month, 'visit')} a month")
    lines.append("Daytime visits" if plan.is_daytime_only else "Evenings and late nights")
    lines.append(f"Book up to {_plural(plan.booking_window_days, 'day')} ahead")
    if plan.guests_per_month:
        lines.append(f"Bring {_plural(plan.guests_per_month, 'guest')} a month")
    else:
        lines.append(f"{_plural(plan.upcoming_limit, 'booking')} at a time")
    return lines


def plan_card(plan, vat_rate=None, ranges=None):
    display = plan_services.plan_display(plan, vat_rate, ranges)
    return {
        **display,
        "tagline": plan.tagline or character(plan),
        "image": plan.image,  # FieldFile: wins over `render`, which is a manifest image name
        "character": character(plan),
        "lines": plan_lines(plan),
        "is_single": plan.kind == Plan.ONE_OFF,
        "price_whole": display["price_whole"],
        "price_inc": display["price_inc_vat"],
        "period": "a visit" if plan.kind == Plan.ONE_OFF else "a month",
    }


def purchasable_plans():
    """Tier 1, 2, 3 and the single visit as cards (Gold is by application, shown elsewhere)."""
    vat, ranges = SiteSettings.load().vat_rate, plan_services.hours_ranges()
    return [plan_card(p, vat, ranges) for p in plan_services.visible_plans() if p.kind in (Plan.MONTHLY, Plan.ONE_OFF)]


def compare_table(cards):
    """Feature rows for the compare table: [{'label', 'cells': [text per card]}]."""

    def row(label, fn):
        return {"label": label, "cells": [{"text": fn(c), "featured": c["highlight"]} for c in cards]}

    def visits(c):
        if c["is_single"]:
            return "1"
        return "Unlimited" if c["visits_per_month"] is None else str(c["visits_per_month"])

    rows = [
        row("Price, ex VAT", lambda c: f"£{c['price_ex_vat']}"),
        row("Price, inc VAT", lambda c: f"£{c['price_inc']}"),
        row("Visits a month", visits),
        row("When", lambda c: "Daytime" if c["hours"] == Plan.DAYTIME_ONLY else "Day and evening"),
        row("Book ahead", lambda c: _plural(c["booking_window_days"], "day")),
        row("Bookings at a time", lambda c: str(c["upcoming_limit"])),
        row("Guests a month", lambda c: str(c["guests_per_month"])),
        row("Cancel up to", lambda c: f"{c['cancel_hours']} hours before"),
    ]
    # One row per perk any shown plan has (Merch, Leil Shishi, ...), in order of first appearance; "No" when a plan lacks it.
    labels = {}
    for c in cards:
        for perk in c["perks"] or []:
            labels.setdefault(perk.get("key"), perk.get("label") or perk.get("key"))

    def perk_value(key):
        return lambda c: next((p.get("value") or "Yes" for p in c["perks"] or [] if p.get("key") == key), "No")

    rows += [row(label, perk_value(key)) for key, label in labels.items()]
    for r in rows:  # `slug` per cell so the page can mark the selected column
        for cell, c in zip(r["cells"], cards):
            cell["slug"] = c["slug"]
    return rows


def selected_plan_slug(request, cards):
    """Which tier starts selected on the memberships page: a valid ?plan= first, then the signed-in person's
    interest, then the highlighted plan, else ''. Only plans a person can register interest in count."""
    allowed = [c["slug"] for c in cards if c["interest_allowed"]]
    asked = request.GET.get("plan", "")
    if asked in allowed:
        return asked
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from users.models import InterestRegistration  # local: users imports plans

        interest = InterestRegistration.objects.filter(user=user).select_related("plan").first()
        if interest and interest.plan and interest.plan.slug in allowed:
            return interest.plan.slug
    return next((c["slug"] for c in cards if c["interest_allowed"] and c["highlight"]), "")


def booking_lines(cards):
    """'Tier 1 books a day ahead.' lines from the monthly plans' booking windows."""
    words = {1: "a day", 2: "two days", 3: "three days", 4: "four days", 5: "five days", 6: "six days", 7: "a week"}
    return [
        f"{c['name']} books {words.get(c['booking_window_days'], _plural(c['booking_window_days'], 'day'))} ahead."
        for c in cards
        if not c["is_single"]
    ]


# ---------- Gold ----------

def public_perks(plan):
    """A plan's perks that may be shown on the site. A perk with "public": false stays in the data (rules can use it)
    but is shown nowhere. Default is public."""
    return [perk for perk in plan.perks or [] if perk.get("public", True)]


def _gold_plan():
    return Plan.objects.filter(slug="gold", visible=True).first()


def _has_public_perk(plan, key):
    return any(perk.get("key") == key for perk in public_perks(plan))


def gold_groups():
    """The two perk groups on Home's Gold pills, from the Gold plan row. None if the plan is hidden."""
    plan = _gold_plan()
    if plan is None:
        return None
    visits = ["Unlimited visits" if plan.is_unlimited else f"{_plural(plan.visits_per_month, 'visit')} a month"]
    visits.append("Daytime visits" if plan.is_daytime_only else "Any time")
    visits.append(f"Book up to {_plural(plan.booking_window_days, 'day')} ahead")
    if plan.guests_per_month:
        visits.append(f"Bring {_plural(plan.guests_per_month, 'guest')} a month")
    if _has_public_perk(plan, "waitlist_priority"):
        visits.append("First call from the waitlist")
    beyond = [
        perk.get("phrase") or perk.get("label", "")
        for perk in public_perks(plan)
        if perk.get("key") != "waitlist_priority"
    ]
    return [("Your visits", visits), ("Beyond the spa", [b for b in beyond if b])]


def _daytime_range():
    periods = OpeningRule.objects.filter(active=True, kind=OpeningRule.PERIOD)
    rule = periods.filter(key="daytime").first() or periods.first()
    if rule and rule.start_time and rule.end_time:
        return f"{_clock(rule.start_time)} to {_clock(rule.end_time)}"
    return ""


def _figure(value, label, number=None, suffix=""):
    """One engraved figure. `number` (an int or None) is what the page may count up to; `suffix` follows it."""
    return {"value": value, "label": label, "number": number, "suffix": suffix}


def gold_facts():
    """Everything the Gold Card page shows below the card, from the visible Gold plan (GOLD-PAGE-R3 section 5):
    {"figures": [{value, label, number, suffix}], "pills": [str], "perks": [{name, note}]}. None when the plan is hidden.
    Figures: visits, hours, booking window, guests (no figure when the plan has no guests). Perks leave out the waitlist
    (it is a pill) and anything marked "public": false."""
    plan = _gold_plan()
    if plan is None:
        return None
    figures = [_figure("Unlimited", "visits") if plan.is_unlimited
               else _figure(str(plan.visits_per_month), "visits a month", plan.visits_per_month)]
    if plan.is_daytime_only:
        daytime = _daytime_range()
        if daytime:
            figures.append(_figure("Daytime", daytime))
    else:
        facts = hours_facts()
        if facts:
            figures.append(_figure("Any time", facts["range"]))
    days = plan.booking_window_days
    figures.append(_figure(f"{days} {'day' if days == 1 else 'days'}", "to book ahead", days, " day" if days == 1 else " days"))
    if plan.guests_per_month:
        figures.append(_figure(str(plan.guests_per_month), "guests a month", plan.guests_per_month))
    pills = [f"{_plural(plan.upcoming_limit, 'booking')} at a time", f"Cancel up to {plan.cancel_hours} hours before"]
    if _has_public_perk(plan, "waitlist_priority"):
        pills.append("First call from the waitlist")
    perks = [{"name": perk.get("phrase") or perk.get("label", ""), "note": perk.get("note", "")}
             for perk in public_perks(plan) if perk.get("key") != "waitlist_priority"]
    return {"figures": figures, "pills": pills, "perks": [p for p in perks if p["name"]]}


# ---------- facilities ----------

def facility_cards():
    """Visible facilities in order, as plain dicts. Picture order: uploaded `image`, then `image_name` (a built render,
    only given when it exists), then the brand tile. The same for the small `detail_image`."""
    return [
        {
            "slug": f.slug,
            "name": f.name,
            "line": f.short_line,
            "tour_url": tour_url(f.slug) if f.slug in tour_slugs() and f.slug != TOUR_LOUNGE else "",
            "description": f.description,
            "display": f.display,
            "facts": [x for x in (f.facts or []) if isinstance(x, str) and x.strip()][: Facility.FACTS_MAX],
            "image": f.image,
            "image_name": f.image_name if images.has_image(f.image_name) else "",
            "focus": f.image_focus or "50% 50%",
            "alt": f.image_alt or f.name,
            "detail_image": f.detail_image,
            "detail_image_name": f.detail_image_name if images.has_image(f.detail_image_name) else "",
            "detail_alt": f.detail_alt,
        }
        for f in plan_services.visible_facilities()
    ]


def _tile_rows(tiles):
    """Split tiles into balanced rows of at most 4 (5 gives 3 + 2, 6 gives 3 + 3)."""
    rows = -(-len(tiles) // 4)
    size, extra = divmod(len(tiles), rows)
    out, start = [], 0
    for n in range(rows):
        end = start + size + (1 if n < extra else 0)
        out.append(tiles[start:end])
        start = end
    return out


def spa_sections(cards):
    """Group facility cards into the layouts of The spa page (docs/design/SPA-PAGE.md 3.1).
    Returns a list of {"kind": "feature", "side": "left"|"right", "feature": card, "companion": card|None}
    and {"kind": "tiles", "tiles": [cards]}. A feature takes the companion straight after it; any other companion
    is shown as a tile. Runs of tiles become rows of 2 to 4 (a single tile stays alone). The first feature is on
    the left (the opening frame is on the right) and sides alternate. Hiding or moving rooms never breaks this."""
    sections, tiles, features = [], [], 0

    def flush():
        if tiles:
            sections.extend({"kind": "tiles", "tiles": row} for row in _tile_rows(list(tiles)))
            tiles.clear()

    index = 0
    while index < len(cards):
        card = cards[index]
        index += 1
        if card["display"] != Facility.FEATURE:
            tiles.append(card)  # tiles, and companions with no feature before them
            continue
        flush()
        companion = None
        if index < len(cards) and cards[index]["display"] == Facility.COMPANION:
            companion, index = cards[index], index + 1
        sections.append({"kind": "feature", "side": "left" if features % 2 == 0 else "right",
                         "feature": card, "companion": companion})
        features += 1
    flush()
    return sections


def visit_pills(copy=None):
    """Pills for the three steps of 'How a visit works': {"book": [...], "arrive": [...], "stay": [...]}.
    Numbers come from the visible monthly plans and the opening rules; words come from the `spa` content rows
    (step_N_pills, one pill per line; booking_pending while booking is not open)."""
    copy = copy if copy is not None else content.page_content("spa")

    def lines(key):
        return [line.strip() for line in copy[key].body.splitlines() if line.strip()]

    plans = [p for p in plan_services.visible_plans() if p.kind == Plan.MONTHLY]
    book = []
    windows = sorted({p.booking_window_days for p in plans})
    if windows:
        low, high = windows[0], windows[-1]
        book.append(f"Book {low} to {high} days ahead" if low != high else
                    "Book a day ahead" if low == 1 else f"Book up to {low} days ahead")
    cancels = {p.cancel_hours for p in plans}
    if len(cancels) == 1:
        book.append(f"Cancel up to {cancels.pop()} hours before")
    if not SiteSettings.load().booking_open and copy["booking_pending"].body:
        book.append(copy["booking_pending"].body)
    stay = []
    facts = hours_facts()
    if facts:
        stay.append(f"Open {facts['range']}")
    if closure_title():
        stay.append(f"Closed for {closure_title()}")
    return {"book": book + lines("step_1_pills"), "arrive": lines("step_2_pills"), "stay": stay + lines("step_3_pills")}


def next_from_line(copy=None):
    """'Memberships from £X a month, £Y inc VAT.' from the next_from row and the lowest visible monthly plan.
    Empty when there is no row or no plan."""
    copy = copy if copy is not None else content.page_content("spa")
    cards = [c for c in purchasable_plans() if c["kind"] == Plan.MONTHLY]
    if not copy["next_from"].body or not cards:
        return ""
    cheapest = min(cards, key=lambda c: Decimal(c["price_ex_vat"]))
    return copy["next_from"].body.replace("{price}", f"£{cheapest['price_whole']}").replace("{price_inc}", f"£{cheapest['price_inc']}")


def _home_preview(facility):
    """The hover picture on Home: a Home-specific crop when there is one, else the room's own image (Facility.image_name),
    so every visible room has a preview (Moishe 2026-10-23: dry sauna, cold plunge and relaxing zone had none)."""
    for name in (HOME_PREVIEW_IMAGES.get(facility.slug, ""), facility.image_name or ""):
        if name and images.has_image(name):
            return name
    return ""


def room_index():
    """All visible rooms for Home: name, one line, anchor slug, and the render to preview (an uploaded image wins)."""
    return [
        {"slug": f.slug, "name": f.name, "line": f.short_line, "image": f.image if f.image else None,
         "preview": _home_preview(f)}
        for f in plan_services.visible_facilities()
    ]


def journey_facility_images():
    """Option value (wet_sauna) -> {src, alt} for the journey tiles. src '' means the calm placeholder."""
    mapping = {}
    for card in facility_cards():
        url = ""
        try:
            url = card["image"].url if card["image"] else ""
        except ValueError:
            url = ""
        if not url and card["image_name"] and images.has_image(card["image_name"]):
            url = images.src(card["image_name"], 480)
        mapping[card["slug"].replace("-", "_")] = {"src": url, "alt": card["alt"]}
    return mapping


# ---------- the spa opener (SPA-OPENER.md section 2) ----------

OPENER_MAX_LINES = 5
OPENER_HERO_LINES = 1  # Moishe 2026-10-23: only "Open 5am to 3am." in the hero; rows 2 to 5 stay in the database, unrendered
OPENER_PICTURES = ["robe", "door-gold"]  # the design picture, then the picture that exists today (until the robe is built)


def _opener_values():
    facts = hours_facts()
    count = Facility.objects.filter(visible=True).count()
    rooms = content.NUMBER_WORDS[count] if 0 < count < len(content.NUMBER_WORDS) else (str(count) if count else "")
    return {"hours": facts["range"] if facts else "", "closure": closure_title(), "rooms": rooms,
            "Rooms": rooms[:1].upper() + rooms[1:]}


_PLACEHOLDER = re.compile(r"\{(hours|closure|rooms|Rooms)\}")


def _fill_statement(text, values):
    """None when a value the text needs is missing (the line is then skipped: never 'Open .')."""
    if any(not values[name] for name in _PLACEHOLDER.findall(text)):
        return None
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def _fill_note(text, values):
    """Sentences that need a missing value are dropped ('Every day. Closed for {closure}.' -> 'Every day.')."""
    sentences = re.findall(r"[^.!?]+[.!?]?\s*", text)
    kept = [s for s in sentences if all(values[name] for name in _PLACEHOLDER.findall(s))]
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], "".join(kept)).strip()


def opener_lines(copy=None, count=OPENER_HERO_LINES):
    """The opener words: [{statement, note}] from the first `count` `opener_n` rows of the `spa` page (the hero shows
    row 1 only; `count` up to 5 for the full set), placeholders {hours} {closure} {rooms} {Rooms} filled from the
    opening rules and the visible rooms. Rows with an empty heading (or a statement that needs a value we do not have)
    are skipped, never replaced by a later row."""
    copy = copy if copy is not None else content.page_content("spa")
    values, lines = _opener_values(), []
    for n in range(1, min(count, OPENER_MAX_LINES) + 1):
        row = copy[f"opener_{n}"]
        statement = _fill_statement(row.heading, values) if row.heading else None
        if statement:
            lines.append({"statement": statement, "note": _fill_note(row.body, values)})
    return lines


OPENER_ALTS = {
    "robe": "A white robe with the gold swan hanging on a bronze hook",
    "door-gold": "A frosted glass door etched with a gold swan, between stone jambs",
    "door-wide": "The entrance to the spa: a frosted glass door etched with a gold swan, a little open, warm light beyond",
}
OPENER_ALT_FALLBACK = "A quiet corner of Spa 99"
SIGNIN_ALT = "Wooden lockers, each with the swan carved in its door"


def opener_picture(copy=None):
    """Which picture opens The spa. Order: an upload on `intro`, the `opener_image` row's name, `robe`, then the old door.
    Returns {"upload", "name", "portrait", "is_door", "alt", "video"}; `video` is the opener video's file prefix ('spa-hero'
    for the robe without an upload, 'spa-door' for the wide door, else ''); `alt` is the upload's own alt, else one per name, else a
    generic one. `name` is '' when none of them is built (the template then
    shows the brand tile, never a broken image). `portrait` is `<name>-portrait` when that is built."""
    copy = copy if copy is not None else content.page_content("spa")
    chosen = copy["opener_image"].body.strip()
    name = next((n for n in [chosen, *OPENER_PICTURES] if n and images.has_image(n)), "")
    portrait = f"{name}-portrait" if name and images.has_image(f"{name}-portrait") else ""
    upload = copy["intro"].image
    alt = (copy["intro"].image_alt if upload else "") or OPENER_ALTS.get(name, OPENER_ALT_FALLBACK)
    is_door = name.startswith("door")
    # the opener video's file prefix (pages_media.opener_video): the steam loop over the robe (2026-10-23), the door's later
    video = "spa-hero" if name == "robe" and not upload else ("spa-door" if is_door and name != "door-gold" else "")
    return {"upload": upload, "name": name, "portrait": portrait, "is_door": is_door, "alt": alt, "video": video}


# ---------- the amenity moments (AMENITIES.md sections 3 and 4) ----------

# moment key -> its content row and the pictures it shows: (default name, focus, alt). A row's upload replaces the first picture.
MOMENTS = {
    "shower": ("moment_shower", [("toiletries", "50% 55%", "Three frosted bottles with the gold swan in a stone niche"),
                                 ("towel-rail", "50% 50%", "A swan towel on a bronze rail by the shower")]),
    "slippers": ("moment_slippers", [("slippers", "62% 60%", "A pair of white swan slippers by a wooden lounger")]),
    "tote": ("moment_tote", [("tote", "50% 50%", "An espresso canvas bag with the gold swan on a stone bench")]),
}


def _moment_pictures(row, pictures):
    out = []
    for index, (name, focus, alt) in enumerate(pictures):
        upload = row.image if index == 0 else None
        out.append({
            "name": name, "focus": focus, "alt": (row.image_alt if index == 0 and row.image_alt else alt), "upload": upload,
            "has_image": bool(upload) or images.has_image(name),
            "portrait": f"{name}-portrait" if images.has_image(f"{name}-portrait") else "",
        })
    return out


def spa_moments(copy=None):
    """Moments that can be shown: {key: {key, heading, body, pictures}} for shower, slippers and tote.
    A moment is left out when its row has no heading (how Moishe turns one off) or none of its pictures exist
    (an upload, or a built render), so the page never shows an empty frame. Each picture has `has_image`."""
    copy = copy if copy is not None else content.page_content("spa")
    moments = {}
    for key, (row_key, pictures) in MOMENTS.items():
        row = copy[row_key]
        built = _moment_pictures(row, pictures)
        if row.heading and any(p["has_image"] for p in built):
            moments[key] = {"key": key, "heading": row.heading, "body": row.body, "pictures": built}
    return moments


def place_moments(sections, moments):
    """Insert moment items ({"kind": "moment", "moment": {...}}) into the room sections by rule, so hiding or moving
    rooms never breaks the page: shower after the first tiles row (else after the first feature, else
    last); slippers after the first feature that follows the shower (else last, before 'How a visit works')."""
    sections = list(sections)

    def item(key):
        return {"kind": "moment", "moment": moments[key]}

    def first(kind, start=0):
        return next((i for i in range(start, len(sections)) if sections[i]["kind"] == kind), None)

    anchor = first("tiles")
    anchor = first("feature") if anchor is None else anchor
    at = len(sections) if anchor is None else anchor + 1  # where the shower moment goes (or would go)
    if "shower" in moments:
        sections.insert(at, item("shower"))
        at += 1
    if "slippers" in moments:
        anchor = first("feature", at)
        sections.insert(len(sections) if anchor is None else anchor + 1, item("slippers"))
    return sections


KIT_MAX = 5


def arrive_kit(copy=None):
    """'Every visit includes': {"heading", "items": [{label, name, focus, has_image}]} from the `arrive_kit` row, one item per
    line as `Label | image-name | focus` (max 5). An unknown image name gives `has_image` False (the swan tile)."""
    copy = copy if copy is not None else content.page_content("spa")
    row, items = copy["arrive_kit"], []
    for line in row.body.splitlines():
        label, _, rest = (part.strip() for part in line.partition("|"))
        name, _, focus = (part.strip() for part in rest.partition("|"))
        if label:
            has = bool(name) and images.has_image(name)
            info = images.manifest().get(name, {}) if has else {}
            wide = bool(info.get("width") and info.get("height") and info["width"] / info["height"] >= 1.8)  # a wide picture gets a wide frame
            items.append({"label": label, "name": name, "focus": focus or "50% 50%", "has_image": has, "wide": wide})
    return {"heading": row.heading, "items": items[:KIT_MAX]}


def _words(labels):
    labels = [label[:1].lower() + label[1:] for label in labels]
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1] if labels else ""


def every_visit():
    """The Memberships 'Every visit' row, from the kit on The spa page so it changes in one place:
    {"text", "items", "pictured", "cta_label", "cta_url"}; None when the `every_visit` row is hidden or there is no kit.
    {kit} in the row's text becomes 'towels, robe, slippers and toiletries'. `pictured` = items whose picture is built."""
    row = content.page_content("memberships")["every_visit"]
    kit = arrive_kit()["items"]
    if not row.body or not kit:
        return None
    return {"text": row.body.replace("{kit}", _words([i["label"] for i in kit])), "items": kit,
            "pictured": [i for i in kit if i["has_image"]], "cta_label": row.cta_label, "cta_url": row.cta_url}


# ---------- sign in (SIGN-IN.md section 6) ----------

def signin_shell():
    """Words and picture for the public sign-in and the pages that share its shell:
    {"heading", "lead", "caption", "upload", "name", "alt", "has_image", "address_line": [str]}. Falls back to the words in the
    brief when the rows are missing. `name` is the default picture; an upload overrides it."""
    copy = content.page_content("signin")
    site = SiteSettings.load()
    return {
        "heading": copy["intro"].heading or "Welcome back.",
        "lead": copy["intro"].body or "Sign in to your Spa 99 account.",
        "caption": copy["caption"].body or "Your own locker, every visit.",
        "upload": copy["intro"].image, "name": "lockers",
        "alt": (copy["intro"].image_alt if copy["intro"].image else "") or SIGNIN_ALT,
        "has_image": bool(copy["intro"].image) or images.has_image("lockers"),
        "address_line": [part for part in (site.address_one_line, site.opening_text) if part],
    }


# ---------- the virtual tour (docs/design/VIRTUAL-TOUR.md 6) ----------

# The toured rooms, in tour order. Adding a room later is one line: (slug, fallback name, photo alt, photo focus).
# The slug is the Facility slug (and the photo name in the image manifest); the lounge has no Facility row.
TOUR_ROOMS = [
    ("lounge", "Lounge", "The lounge, with the wide reef tank beside a long bench", "28% 55%"),
    ("gym", "Gym", "The gym, free weights and machines in low warm light", "40% 55%"),
    ("massage-room", "Massage room", "The massage room, leather chairs beside an oak slatted wall and the swan", "60% 60%"),
    ("kitchenette", "Kitchenette", "The kitchenette, a walnut counter and two caramel armchairs", "35% 55%"),
    ("relaxing-zone", "Relaxing zone", "The relaxing zone, with loungers and the swan on the wall", "55% 60%"),
    ("wet-sauna", "Wet sauna", "The wet sauna, travertine walls and a curved bench", "50% 40%"),
    ("dry-sauna", "Dry sauna", "The dry sauna, with pale wood benches in low light", "50% 55%"),
]
TOUR_LOUNGE = TOUR_ROOMS[0][0]
TOUR_CANVAS_KEYS = ("intro", "hint", "hint_tilt", "tilt")


def tour_slugs():
    return [room[0] for room in TOUR_ROOMS]


def tour_url(slug):
    from django.urls import reverse

    return reverse("tour") if slug == TOUR_LOUNGE else reverse("tour_room", args=[slug])


def spa_room_url(slug):
    from django.urls import reverse

    return reverse("spa") + ("" if slug == TOUR_LOUNGE else f"#{slug}")


def _tour_photo(slug, image):
    """URL of the room photo: the `room_<slug>` section image wins, then the manifest render, else ''."""
    if image:
        try:
            return image.url
        except ValueError:
            pass
    return images.src(slug, 1600) if images.has_image(slug) else ""


def tour_rooms(copy=None):
    """The visible toured rooms in order, as plain dicts (also the JSON the 3D script reads).
    A room whose Facility is hidden in Control leaves the tour; the lounge (no Facility) is always in."""
    copy = copy if copy is not None else content.page_content("tour")
    facilities = {f.slug: f for f in Facility.objects.filter(slug__in=tour_slugs())}
    rooms = []
    for slug, fallback_name, alt, focus in TOUR_ROOMS:
        facility = facilities.get(slug)
        if facility is not None and not facility.visible:
            continue
        row = copy[f"room_{slug.replace('-', '_')}"]
        rooms.append({
            "slug": slug,
            "name": row.heading or (facility.name if facility else fallback_name),
            "line": row.body or (facility.short_line if facility else ""),
            "photo": _tour_photo(slug, row.image),
            "alt": row.image_alt or alt,
            "focus": focus,
            "spa_url": row.cta_url or spa_room_url(slug),
            "spa_label": row.cta_label or "See it on The spa",
            "tour_url": tour_url(slug),
            "order": len(rooms) + 1,
        })
    return rooms


def tour_config(rooms, current, copy):
    """Everything the 3D script needs, for json_script."""
    return {
        "current": current,
        "rooms": rooms,
        "copy": {key: {"heading": copy[key].heading, "body": copy[key].body, "cta_label": copy[key].cta_label}
                 for key in TOUR_CANVAS_KEYS},
    }


_STACKED_LOGO = "common/img/logo-stacked-gold.svg"


@lru_cache(maxsize=1)
def stacked_logo_svg():
    """The stacked gold lockup, inline, for the hidden logo holder the 3D script reads its paths from. Read once per process (restart to pick up an edit)."""
    from django.contrib.staticfiles import finders
    from django.utils.safestring import mark_safe

    path = finders.find(_STACKED_LOGO)
    if not path:
        return ""
    with open(path, encoding="utf-8") as handle:
        return mark_safe(handle.read())  # our own file in the repo, never user input
