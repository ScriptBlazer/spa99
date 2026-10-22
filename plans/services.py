"""Plan display data and price helpers. Other apps read plans through here."""
from decimal import ROUND_HALF_UP, Decimal

from .models import Facility, Plan, SiteSettings

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


def plan_display(plan, vat_rate=None):
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
    }


def visible_facilities():
    return Facility.objects.filter(visible=True)
