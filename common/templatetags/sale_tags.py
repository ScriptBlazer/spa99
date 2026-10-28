"""Sales on the public site: the bar's server-rendered text and the calm sale lines under prices.
`sale_bar_view` turns the `sale_bar` dict (ISO strings) into what the template prints; `sale_line` gives the line for one plan."""
import math

from django import template
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from plans import sales
from plans.models import Plan

register = template.Library()


def count_parts(seconds):
    """(days, hours, minutes) left, minutes rounded up so a live sale never says 0m."""
    minutes = max(1, math.ceil(seconds / 60))
    return minutes // 1440, (minutes % 1440) // 60, minutes % 60


def count_text(seconds):
    """Same format as sale-bar.js: '3d 04h' + minutes part, '4h 12m', '12m'. Returns (text before minutes, minutes part, has_days)."""
    days, hours, minutes = count_parts(seconds)
    if days:
        return f"{days}d {hours:02d}h", f" {minutes:02d}m", True
    if hours:
        return f"{hours}h", f" {minutes:02d}m", False
    return f"{minutes}m", "", False


def when(value, with_weekday=False):
    local = timezone.localtime(value)
    return local.strftime("%A %-d %B, %H:%M") if with_weekday else local.strftime("%-d %b, %H:%M")


@register.simple_tag
def sale_bar_view(sale_bar):
    now = timezone.now()
    starts, ends = parse_datetime(sale_bar["starts_at"]), parse_datetime(sale_bar["ends_at"])
    upcoming = starts > now
    lead, tail, has_days = count_text((ends - now).total_seconds())
    days, hours, minutes = count_parts((ends - now).total_seconds())
    units = []   # the band's numerals: leading unit unpadded, later ones two digits, a unit that is not needed is left out
    if days:
        units = [(str(days), "day" if days == 1 else "days"), (f"{hours:02d}", "hour" if hours == 1 else "hours"), (f"{minutes:02d}", "minute" if minutes == 1 else "minutes")]
    elif hours:
        units = [(str(hours), "hour" if hours == 1 else "hours"), (f"{minutes:02d}", "minute" if minutes == 1 else "minutes")]
    else:
        units = [(str(minutes), "minute" if minutes == 1 else "minutes")]
    return {"upcoming": upcoming, "starts_label": when(starts), "starts_long": when(starts, True), "ends_sr": when(ends, True), "now": now.isoformat(),
            "lead": lead, "tail": tail, "has_days": has_days, "units": units}


_money = sales._money


@register.simple_tag(takes_context=True)
def sale_line(context, slug, sentence="tier"):
    """The calm line for a plan covered by the sale on this page (live or previewed), or ''. sentence: tier, single or short.
    One Plan query per page: the covered plans are fetched together and kept on the request."""
    bar = context.get("sale_bar")
    if not bar or slug not in bar["plan_slugs"]:
        return ""
    request = context.get("request")
    cache = getattr(request, "_sale_plans", None)
    if cache is None:
        cache = {p.slug: p for p in Plan.objects.filter(slug__in=bar["plan_slugs"])}
        if request is not None:
            request._sale_plans = cache
    plan = cache.get(slug)
    if plan is None:
        return ""
    price = _money(sales.sale_price(plan, bar["percent"]))
    months = bar["months"]
    unit = "month" if months == 1 else "months"
    if sentence == "short":
        return f"{bar['name']}: {price} for {months} {unit}"
    period = "a visit" if plan.kind == plan.ONE_OFF else "a month"
    return f"{bar['name']}: {price} {period} for your first {months} {unit}"


@register.simple_tag
def register_sale_line(register_sale, slug):
    """'Register during the Christmas sale and keep £76 a month for your first 3 months.' for a plan the live sale covers, else ''."""
    return sales.register_line(register_sale, slug)


@register.simple_tag
def kept_line(kept):
    """'You keep £76 a month for your first 3 months, from the Christmas sale.' from the member's kept_price."""
    if not kept:
        return ""
    period = "a visit" if kept.get("plan_kind") == Plan.ONE_OFF else "a month"
    return f"You keep {_money(kept['sale_price_ex_vat'])} {period} {sales.months_phrase(kept['months'])}, from the {kept['name']}."


@register.filter
def ends_in(when_dt):
    """'3d 04h', '4h 12m', '12m': the System list's time left (same format as the bar, server-rendered at load)."""
    lead, tail, has_days = count_text((when_dt - timezone.now()).total_seconds())
    return lead if has_days else lead + tail


@register.simple_tag
def sale_plan_prices():
    """Every plan with its ex-VAT price, for the System form's live 'What people see' panel."""
    return [{"pk": p.pk, "name": p.name, "price": f"{p.price_ex_vat:.2f}", "single": p.kind == p.ONE_OFF} for p in Plan.objects.all()]


@register.simple_tag
def sale_mention_view(sale_bar):
    """The words for common/_sale_mention.html: until, from, upcoming, months_phrase (see plans.sales.mention)."""
    return sales.mention(sale_bar)
