"""Office template helpers. Formatting only (British numbers, London dates) and drawing geometry (ring arcs,
sparkline paths, bar lengths): every figure shown is a stored figure from the selectors, never calculated here."""
from datetime import date, datetime

from django import template
from django.utils import timezone

register = template.Library()

MINUS = "−"


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ---------- numbers ----------

@register.filter
def num(value):
    """1,204"""
    return f"{_int(value):,}"


@register.filter
def compact(value):
    """Counts: 1,204 · 12.4k · 1.2m (compact from 10,000, one decimal)."""
    n = _int(value)
    if n < 10_000:
        return f"{n:,}"
    for size, suffix in ((1_000_000, "m"), (1_000, "k")):
        if n >= size:
            text = f"{n / size:.1f}".rstrip("0").rstrip(".")
            return text + suffix
    return f"{n:,}"


@register.filter
def bp_rate(value):
    """Basis points as a rate: 4.6% under 10%, 38% above. Empty for None."""
    if value in (None, ""):
        return ""
    pct = _int(value) / 100
    return f"{pct:.1f}%" if pct < 10 else f"{round(pct)}%"


@register.filter
def bp_rate_value(value):
    """The rate without its sign, for the count-up: 4.6 or 38."""
    pct = _int(value) / 100
    return f"{pct:.1f}" if pct < 10 else f"{round(pct)}"


@register.filter
def pct(value):
    return f"{_int(value)}%"


@register.filter
def bp_ratio(value):
    """Basis points as 0 to 1 for a bar's scaleX."""
    return f"{max(0, min(_int(value), 10000)) / 10000:.4f}"


@register.simple_tag
def ratio(value, top):
    """A bar's length against the top value of its list (drawing only)."""
    top = _int(top)
    return f"{(max(_int(value), 0) / top if top else 0):.4f}"


# ---------- dates (London) ----------

def _when(value):
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        return value
    else:
        text = str(value or "")
        if not text:
            return None
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        if len(text) <= 10:
            return moment.date()
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return timezone.localtime(moment)


def _dm(d):
    return f"{d.day} {d:%b}"


@register.filter
def dm(value):
    """23 Oct"""
    d = _when(value)
    return _dm(d) if d else ""


@register.filter
def dmy(value):
    """23 Oct 2026"""
    d = _when(value)
    return f"{_dm(d)} {d.year}" if d else ""


@register.filter
def day_label(value):
    """Thu 23 Oct"""
    d = _when(value)
    return f"{d:%a} {_dm(d)}" if d else ""


@register.filter
def week_label(value):
    """w/c 20 Oct"""
    d = _when(value)
    return f"w/c {_dm(d)}" if d else ""


@register.filter
def dt(value):
    """23 Oct 2026, 18:40"""
    d = _when(value)
    return f"{_dm(d)} {d.year}, {d:%H:%M}" if isinstance(d, datetime) else dmy(value)


@register.filter
def relative(value, lower=False):
    """Today, 18:40 · Yesterday · 2 days ago · 14 Oct"""
    d = _when(value)
    if d is None:
        return ""
    today = timezone.localdate()
    day = d.date() if isinstance(d, datetime) else d
    gap = (today - day).days
    if gap == 0:
        text = f"Today, {d:%H:%M}" if isinstance(d, datetime) else "Today"
    elif gap == 1:
        text = "Yesterday"
    elif 1 < gap < 7:
        text = f"{gap} days ago"
    else:
        text = _dm(day) if day.year == today.year else f"{_dm(day)} {day.year}"
    return text[:1].lower() + text[1:] if lower else text


@register.filter
def expires_in(value):
    """Expires in 3 days · Expires today · Expired"""
    d = _when(value)
    if not isinstance(d, datetime):
        return ""
    left = d - timezone.now()
    if left.total_seconds() <= 0:
        return "Expired"
    days = left.days
    return "Expires today" if days < 1 else f"Expires in {days} day{'s' if days != 1 else ''}"


@register.filter
def first_word(value):
    return str(value or "").split(" ")[0]


@register.filter
def status_label(value):
    return {"new": "Waiting", "contacted": "Waiting", "approved": "Approved", "declined": "Declined"}.get(value, str(value).title())


@register.filter
def journey_label(value):
    return {"completed": "Completed", "started": "Started", "not_started": "Not started"}.get(value, "")


# ---------- drawing ----------

@register.simple_tag
def ring_arcs(percent):
    """Offsets for one ring in pathLength units (0 = full lap). Up to two laps; None means no goal (track only)."""
    if percent is None:
        return {"has": False}
    p = max(0, min(_int(percent), 200))
    first, second = min(p, 100), max(p - 100, 0)
    return {"has": True, "first": f"{100 - first:g}", "second": f"{100 - second:g}", "laps": 2 if second else 1, "any": p > 0}


@register.simple_tag
def sparkline(series):
    """A series as SVG geometry in a 100 by 40 box: line path, closed area path, and the last point in percent."""
    values = [_int(v) for v in (series or [])]
    if not values:
        return {"line": "", "area": "", "x": 100, "y": 90}
    lo, hi, n = min(values), max(values), len(values)

    def y(v):
        if hi == lo:
            return 36.0 if hi == 0 else 20.0
        return 36 - (v - lo) / (hi - lo) * 32

    points = [((i / (n - 1) * 100) if n > 1 else 100.0, y(v)) for i, v in enumerate(values)]
    line = "M" + " L".join(f"{x:.2f} {py:.2f}" for x, py in points)
    area = f"{line} L100 40 L{points[0][0]:.2f} 40 Z"
    lx, ly = points[-1]
    return {"line": line, "area": area, "x": f"{lx:.2f}", "y": f"{ly / 40 * 100:.2f}"}


@register.simple_tag
def zip_lists(*lists):
    """Parallel lists as rows, for the 'View as table' tables. Shorter lists are padded with blanks."""
    lists = [list(item or []) for item in lists]
    size = max((len(item) for item in lists), default=0)
    return [[item[i] if i < len(item) else "" for item in lists] for i in range(size)]


@register.filter
def getkey(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag
def index_of(items, value):
    items = list(items or [])
    return items.index(value) if value in items else 0


@register.filter
def range_label(value):
    return {"today": "Today", "7d": "7 days", "30d": "30 days", "90d": "90 days", "all": "All"}.get(value, value)


@register.simple_tag
def has_data(items, key="value"):
    """True when any item has a figure above zero (decides between a chart and its empty line)."""
    return any(_int(item.get(key)) > 0 for item in (items or []))
