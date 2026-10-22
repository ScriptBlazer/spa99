"""Glue between the data apps (plans, content, journey) and the page templates. Nothing here is a rule:
every number and word comes from rows edited in Control."""
from django.utils import timezone

from content import images
from plans import services as plan_services
from plans.models import OpeningRule, Plan, SiteSettings

# Facility slug -> optimised render name (content/static/content/img). The new renders are not here yet:
# those facilities show a placeholder until a file is uploaded on the Facility in Control.
FACILITY_IMAGES = {"dry-sauna": "dry-sauna", "relaxing-zone": "relaxing-zone", "gym": "gym"}
# Home "What's inside" preview: the render shown for a room (IMMERSIVE-R2 section 3, R3). Rooms not listed keep the current picture.
HOME_PREVIEW_IMAGES = {"dry-sauna": "dry-sauna", "showers": "showers", "relaxing-zone": "relax-loungers", "gym": "gym", "kitchenette": "lounge"}


def split_label(label):
    """'Early morning (5 to 9am)' -> ('Early morning', '5 to 9am'); no brackets -> (label, ''). Mirrored in api.js."""
    main, sep, rest = (label or "").partition(" (")
    return (main.strip(), rest.rstrip(")").strip()) if sep else ((label or "").strip(), "")


# ---------- hours ----------

def _clock(value):
    """time(18, 0) -> '6pm', time(5, 30) -> '5:30am'."""
    hour = value.hour % 12 or 12
    minutes = f":{value.minute:02d}" if value.minute else ""
    return f"{hour}{minutes}{'am' if value.hour < 12 else 'pm'}"


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


def plan_card(plan, vat_rate=None):
    display = plan_services.plan_display(plan, vat_rate)
    return {
        **display,
        "character": character(plan),
        "lines": plan_lines(plan),
        "is_single": plan.kind == Plan.ONE_OFF,
        "price_whole": display["price_whole"],
        "price_inc": display["price_inc_vat"],
        "period": "a visit" if plan.kind == Plan.ONE_OFF else "a month",
    }


def purchasable_plans():
    """Tier 1, 2, 3 and the single visit as cards (Gold is by application, shown elsewhere)."""
    vat = SiteSettings.load().vat_rate
    return [plan_card(p, vat) for p in plan_services.visible_plans() if p.kind in (Plan.MONTHLY, Plan.ONE_OFF)]


def compare_table(cards):
    """Feature rows for the compare table: [{'label', 'cells': [text per card]}]."""

    def row(label, fn):
        return {"label": label, "cells": [{"text": fn(c), "featured": c["highlight"]} for c in cards]}

    def visits(c):
        if c["is_single"]:
            return "1"
        return "Unlimited" if c["visits_per_month"] is None else str(c["visits_per_month"])

    return [
        row("Price, ex VAT", lambda c: f"£{c['price_ex_vat']}"),
        row("Price, inc VAT", lambda c: f"£{c['price_inc']}"),
        row("Visits a month", visits),
        row("When", lambda c: "Daytime" if c["hours"] == Plan.DAYTIME_ONLY else "Day and evening"),
        row("Book ahead", lambda c: _plural(c["booking_window_days"], "day")),
        row("Bookings at a time", lambda c: str(c["upcoming_limit"])),
        row("Guests a month", lambda c: str(c["guests_per_month"])),
        row("Cancel up to", lambda c: f"{c['cancel_hours']} hours before"),
    ]


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
    """Facilities in visiting order with the render to show (an uploaded image wins, then the optimised render)."""
    return [
        {
            "slug": f.slug,
            "name": f.name,
            "line": f.short_line,
            "image": f.image,
            "image_name": FACILITY_IMAGES.get(f.slug, ""),
            "alt": f.image_alt or f.name,
        }
        for f in plan_services.visible_facilities()
    ]


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
