"""Plan display data and price helpers. Other apps read plans through here."""
from decimal import ROUND_HALF_UP, Decimal

from .models import Facility, OpeningRule, Plan, SiteSettings

PENNY = Decimal("0.01")


def price_inc_vat(price_ex_vat, vat_rate=None):
    """£299.00 at 20% -> £358.80. `vat_rate` is a percentage; defaults to the site setting."""
    if vat_rate is None:
        vat_rate = SiteSettings.load().vat_rate
    amount = Decimal(price_ex_vat) * (Decimal("100") + Decimal(vat_rate)) / Decimal("100")
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


def visible_plans():
    return Plan.objects.filter(visible=True)


def monthly_plans():
    """Plans the journey can suggest: visible monthly memberships."""
    return Plan.objects.filter(visible=True, kind=Plan.MONTHLY)


def plan_facts(plan):
    """Short plain-English facts about a plan, in a fixed order. They come from the row, so the journey
    reasons and the memberships page change when a plan changes. (Window first: it is the most persuasive.)"""
    facts = []
    days = plan.booking_window_days
    facts.append(f"Book up to {days} day{'s' if days != 1 else ''} ahead")
    if plan.is_unlimited:
        facts.append("Unlimited visits")
    elif plan.visits_per_month is not None:
        visits = plan.visits_per_month
        facts.append(f"{visits} visit{'s' if visits != 1 else ''} a month")
    facts.append("Daytime visits" if plan.is_daytime_only else "Day or evening, any time")
    if plan.guests_per_month:
        guests = plan.guests_per_month
        facts.append(f"Bring {guests} guest{'s' if guests != 1 else ''} a month")
    facts.append(f"Cancel up to {plan.cancel_hours} hours before")
    return facts


def trim_price(amount):
    """'399.00' -> '399', '99.50' stays '99.50'."""
    amount = str(amount)
    return amount[:-3] if amount.endswith(".00") else amount


def _count(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def character_line(plan):
    """'Daytime, 6 visits a month.' / 'Any time, unlimited visits.' (for the journey result)."""
    when = "Daytime" if plan.is_daytime_only else "Any time"
    visits = "unlimited visits" if plan.is_unlimited else f"{_count(plan.visits_per_month, 'visit')} a month"
    return f"{when}, {visits}."


def price_line(plan, price_inc):
    period = "a visit" if plan.kind == plan.ONE_OFF else "a month"
    return f"£{trim_price(plan.price_ex_vat)} {period}, ex VAT (£{price_inc} inc VAT)"


def clock(value):
    """time(18, 0) -> '6pm', time(5, 30) -> '5:30am'."""
    hour = value.hour % 12 or 12
    minutes = f":{value.minute:02d}" if value.minute else ""
    return f"{hour}{minutes}{'am' if value.hour < 12 else 'pm'}"


def _open_periods():
    return [r for r in OpeningRule.objects.filter(active=True, kind=OpeningRule.PERIOD) if r.start_time and r.end_time]


def hours_ranges():
    """{'daytime': '5am to 6pm', 'full': '5am to 3am'} from the open periods ('' when none is set).
    Daytime is the period with key 'daytime'; full runs from the first period's start to the last one's end."""
    periods = _open_periods()
    day = next((r for r in periods if r.key == "daytime"), None) or (periods[0] if periods else None)
    return {
        "daytime": f"{clock(day.start_time)} to {clock(day.end_time)}" if day else "",
        "full": f"{clock(periods[0].start_time)} to {clock(periods[-1].end_time)}" if periods else "",
    }


def plan_pills(plan, ranges=None):
    """The ordered chips for a tier on the memberships page: hours, booking window, bookings at a time, guests,
    then any perk with a `pill` text. All words come from the row and the opening rules."""
    ranges = ranges if ranges is not None else hours_ranges()
    pills = []
    if plan.is_daytime_only:
        pills.append(f"Daytime, {ranges['daytime']}" if ranges["daytime"] else "Daytime")
    else:
        pills.append(f"Day and evening, {ranges['full']}" if ranges["full"] else "Day and evening")
    pills.append(f"Book up to {_count(plan.booking_window_days, 'day')} ahead")
    pills.append(f"{_count(plan.upcoming_limit, 'booking')} at a time")
    if plan.guests_per_month:
        pills.append(f"{_count(plan.guests_per_month, 'guest')} a month")
    pills.extend(perk["pill"] for perk in plan.perks or [] if perk.get("pill"))
    return pills


def plan_image_url(plan):
    """Uploaded picture URL, else '' (the render name is separate: the page resolves it through the image manifest)."""
    try:
        return plan.image.url if plan.image else ""
    except ValueError:
        return ""


def plan_display(plan, vat_rate=None, ranges=None):
    """Everything a template or JSON response needs to show one plan."""
    if vat_rate is None:
        vat_rate = SiteSettings.load().vat_rate
    price_inc = str(price_inc_vat(plan.price_ex_vat, vat_rate))
    return {
        "slug": plan.slug,
        "name": plan.name,
        "kind": plan.kind,
        "price_ex_vat": str(plan.price_ex_vat),
        "price_inc_vat": price_inc,
        "price_whole": trim_price(plan.price_ex_vat),
        "price_line": price_line(plan, price_inc),
        "character_line": character_line(plan),
        "visits_per_month": plan.visits_per_month,
        "hours": plan.hours,
        "booking_window_days": plan.booking_window_days,
        "upcoming_limit": plan.upcoming_limit,
        "cancel_hours": plan.cancel_hours,
        "guests_per_month": plan.guests_per_month,
        "perks": plan.perks,
        "short_description": plan.short_description,
        "highlight": plan.highlight,
        "interest_allowed": plan.interest_allowed,
        "facts": plan_facts(plan),
        "tagline": plan.tagline,
        "pills": plan_pills(plan, ranges),
        "visits_count": plan.visits_per_month,
        "image_url": plan_image_url(plan),
        "render": plan.render,
        "image_alt": plan.image_alt,
    }


def visible_facilities():
    return Facility.objects.filter(visible=True)
