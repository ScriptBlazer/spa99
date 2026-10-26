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
    facts.append("Off-peak visits" if plan.is_daytime_only else "Off-peak or peak, any time")
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
    """'Off-peak, 6 visits a month.' / 'Any time, unlimited visits.' (for the journey result)."""
    when = "Off-peak" if plan.is_daytime_only else "Any time"
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


def _minutes(rule):
    return ((rule.end_time.hour * 60 + rule.end_time.minute) - (rule.start_time.hour * 60 + rule.start_time.minute)) % 1440 or 1440


def cleaning_rules():
    return [r for r in OpeningRule.objects.filter(active=True, kind=OpeningRule.DAILY_CLOSURE) if r.start_time and r.end_time]


def open_all_day():
    """True when the open periods plus the daily cleaning window fill the whole day (Moishe, 2026-10-26: open 24 hours a day;
    the short window is Cleaning hours, not Closed). Worked out from the rules, so editing them in System > Hours changes the words."""
    periods = _open_periods()
    return bool(periods) and sum(_minutes(r) for r in periods) + sum(_minutes(r) for r in cleaning_rules()) >= 1440


def hours_ranges():
    """{'daytime': '5am to 6pm', 'full': '5am to 3am', 'all_day': bool} from the open periods ('' when none is set).
    Daytime (shown as Off-peak) is the period with key 'daytime'; full runs from the first period's start to the last one's end."""
    periods = _open_periods()
    day = next((r for r in periods if r.key == "daytime"), None) or (periods[0] if periods else None)
    return {
        "daytime": f"{clock(day.start_time)} to {clock(day.end_time)}" if day else "",
        "full": f"{clock(periods[0].start_time)} to {clock(periods[-1].end_time)}" if periods else "",
        "all_day": open_all_day(),
    }


def leil_shishi_shown():
    return SiteSettings.load().show_leil_shishi


def shown_perks(plan, show_leil=None):
    """A plan's perks without the ones switched off. Leil Shishi is hidden everywhere while Site settings 'show Leil Shishi'
    is off (default); the data stays on the plan."""
    show = leil_shishi_shown() if show_leil is None else show_leil
    return [p for p in plan.perks or [] if show or p.get("key") != "leil_shishi"]


def annual_fee_text(plan, vat_rate=None, inc=False):
    """Gold Card fee: 'By application' while empty, else '£150 a year' (ex VAT; `inc` = with VAT)."""
    if plan.annual_fee is None:
        return "By application"
    amount = price_inc_vat(plan.annual_fee, vat_rate) if inc else plan.annual_fee
    return f"£{trim_price(amount)} a year"


GOLD_STAR = "{gold_star}"


def gold_annual_fee():
    """The Gold plan's annual admin fee (ex VAT), or None while empty."""
    return Plan.objects.filter(slug="gold").values_list("annual_fee", flat=True).first()


def gold_star(fee=None):
    """'*' after the word free in Gold copy while a fee is set (Moishe, 2026-10-26), else ''. Copy writes {gold_star}."""
    return "*" if (fee if fee is not None else gold_annual_fee()) is not None else ""


def gold_fee_note(fee=None):
    """'*An annual admin fee of £299 + VAT applies.' from the Gold plan's annual fee (ex VAT); '' while it is empty."""
    fee = fee if fee is not None else gold_annual_fee()
    return "" if fee is None else f"*An annual admin fee of £{trim_price(fee)} + VAT applies."


def plan_pills(plan, ranges=None):
    """The ordered chips for a tier on the memberships page: hours, booking window, bookings at a time, guests,
    then any perk with a `pill` text. All words come from the row and the opening rules."""
    ranges = ranges if ranges is not None else hours_ranges()
    pills = []
    if plan.is_daytime_only:
        pills.append(f"Off-peak, {ranges['daytime']}" if ranges["daytime"] else "Off-peak")
    elif ranges.get("all_day"):
        pills.append("Off-peak and peak, 24 hours a day")
    else:
        pills.append(f"Off-peak and peak, {ranges['full']}" if ranges["full"] else "Off-peak and peak")
    pills.append(f"Book up to {_count(plan.booking_window_days, 'day')} ahead")
    pills.append(f"{_count(plan.upcoming_limit, 'booking')} at a time")
    if plan.guests_per_month:
        pills.append(f"{_count(plan.guests_per_month, 'guest')} a month")
    pills.extend(perk["pill"] for perk in shown_perks(plan) if perk.get("pill"))
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
        "perks": shown_perks(plan),
        "annual_fee": plan.annual_fee,
        "annual_fee_text": annual_fee_text(plan, vat_rate),
        "annual_fee_inc_text": annual_fee_text(plan, vat_rate, inc=True),
        "short_description": plan.short_description.replace(GOLD_STAR, gold_star(plan.annual_fee) if plan.slug == "gold" else ""),
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
