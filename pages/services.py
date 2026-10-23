"""Glue between the data apps (plans, content, journey) and the page templates. Nothing here is a rule:
every number and word comes from rows edited in Control."""
from decimal import Decimal

from django.utils import timezone

from content import services as content

from content import images
from plans import services as plan_services
from plans.models import Facility, OpeningRule, Plan, SiteSettings

# Home "What's inside" preview: the photo shown for a room (IMMERSIVE-R2 section 3, R3). Rooms not listed keep the current picture.
# No photo here may appear elsewhere on Home: dry-sauna (Heat, slowly), cold-plunge, relax-loungers (the ritual) and lounge
# (the journey entry) are already used above, so those rooms are not listed.
HOME_PREVIEW_IMAGES = {"wet-sauna": "wet-sauna", "showers": "showers", "massage-room": "massage-room", "gym": "gym", "kitchenette": "kitchenette"}


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
    for rule in rules:  # Shabbos / Yom Tov rules that carry a public note (written in Control)
        if rule.kind in (OpeningRule.CLOSE_BEFORE_CANDLES, OpeningRule.OPEN_AFTER_NIGHTFALL) and rule.public_note:
            rows.append((rule.public_title or rule.label, rule.public_note))
    return rows


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

def gold_groups():
    """The two perk groups on the Gold Card page, from the Gold plan row. None if the plan is hidden."""
    plan = Plan.objects.filter(slug="gold", visible=True).first()
    if plan is None:
        return None
    visits = ["Unlimited visits" if plan.is_unlimited else f"{_plural(plan.visits_per_month, 'visit')} a month"]
    visits.append("Daytime visits" if plan.is_daytime_only else "Any time")
    visits.append(f"Book up to {_plural(plan.booking_window_days, 'day')} ahead")
    if plan.guests_per_month:
        visits.append(f"Bring {_plural(plan.guests_per_month, 'guest')} a month")
    if plan.perk("waitlist_priority"):
        visits.append("First call from the waitlist")
    beyond = [
        perk.get("phrase") or perk.get("label", "")
        for perk in plan.perks or []
        if perk.get("key") != "waitlist_priority"
    ]
    return [("Your visits", visits), ("Beyond the spa", [b for b in beyond if b])]


# ---------- facilities ----------

def facility_cards():
    """Visible facilities in order, as plain dicts. Picture order: uploaded `image`, then `image_name` (a built render,
    only given when it exists), then the brand tile. The same for the small `detail_image`."""
    return [
        {
            "slug": f.slug,
            "name": f.name,
            "line": f.short_line,
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


def room_index():
    """All visible rooms for Home: name, one line, anchor slug, and the render to preview (an uploaded image wins)."""
    return [
        {"slug": f.slug, "name": f.name, "line": f.short_line, "image": f.image if f.image else None,
         "preview": HOME_PREVIEW_IMAGES.get(f.slug, "") if images.has_image(HOME_PREVIEW_IMAGES.get(f.slug, "")) else ""}
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
