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
def bp_ratio(value):
    """Basis points as 0 to 1 for a bar's scaleX."""
    return f"{max(0, min(_int(value), 10000)) / 10000:.4f}"


@register.simple_tag
def bar_share(value, share_bp):
    """A funnel bar's length as 0 to 1. A step with people in it never draws shorter than a sliver (3%), so it still shows."""
    if not _int(value):
        return "0.0000"
    return f"{max(max(0, min(_int(share_bp), 10000)) / 10000, 0.03):.4f}"


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
    """Offsets for one ring in pathLength units (0 = full lap), up to two laps. `goal` is 0 when no goal is set (the ring is then
    a calm closed circle); `on` and `on2` are 0 for an arc that has nothing to draw (a round cap would still leave a dot)."""
    if percent is None:
        return {"goal": 0, "first": "100", "second": "100", "on": 0, "on2": 0}
    p = max(0, min(_int(percent), 200))
    first, second = min(p, 100), max(p - 100, 0)
    return {"goal": 1, "first": f"{100 - first:g}", "second": f"{100 - second:g}", "on": 1 if first else 0, "on2": 1 if second else 0}


PERIODS = {   # how a change line names the period before: (reference, the word for "new")
    "today": ("yesterday", "today"), "7d": ("last week", "this week"), "30d": ("the 30 days before", "this month"),
}
ANALYTICS_PERIODS = {"7d": "the previous 7 days", "30d": "the previous 30 days", "90d": "the previous 90 days"}


@register.simple_tag
def change_line(value, previous, range_name):
    """A change as a count, in words (OFFICE section 10): +12 on last week · 6 fewer than last week · Same as last week · New this week."""
    if range_name == "all" or previous is None:
        return ""  # All time has no period before it
    value, previous = _int(value), _int(previous)
    ref, fresh = PERIODS.get(range_name, PERIODS["7d"])
    diff = value - previous
    if diff == 0:
        return f"Same as {ref}"
    if diff > 0:
        return f"New {fresh}" if previous == 0 else f"+{diff:,} on {ref}"
    return f"{-diff:,} fewer than {ref}"


def _prev(previous):
    """The previous period's total: the stored `previous_total` (distinct people for people series), or a list to sum."""
    return sum(_int(v) for v in previous) if isinstance(previous, (list, tuple)) else _int(previous)


@register.simple_tag
def change_ana(value, previous_values, range_name):
    """Analytics: '+1,204 on the previous 30 days' (empty for All, which has no previous period)."""
    ref = ANALYTICS_PERIODS.get(range_name)
    if not ref or previous_values is None:
        return ""
    value, previous = _int(value), _prev(previous_values)
    diff = value - previous
    if diff == 0:
        return f"Same as {ref}"
    if diff > 0:
        return f"New in the last {ref.split()[-2]} days" if previous == 0 else f"+{diff:,} on {ref}"
    return f"{-diff:,} fewer than {ref}"


@register.simple_tag
def change_rate(value, previous_values):
    """Analytics only: the change as a rate after the count ('▲ 18%'), empty when there is no earlier figure."""
    previous = _prev(previous_values)
    if not previous:
        return ""
    pct = round((_int(value) - previous) * 100 / previous)
    return "" if pct == 0 else (f"▲ {pct}%" if pct > 0 else f"▼ {-pct}%")


@register.filter
def sum_of(values):
    """The sum of a stored series (the previous period's total for a change line)."""
    return sum(_int(v) for v in (values or []))


GOAL_WORDS = {"journeys_started": ("started the journey", "started the journey"), "journeys_completed": ("finished the journey", "finished the journey"),
              "registrations": ("registered", "registered")}


@register.simple_tag
def ring_sentence(rings):
    """One sentence for the three rings: '42 started the journey, goal 60. 31 finished the journey, goal 40. 18 registered, goal 25.'"""
    parts = []
    for ring in rings or []:
        words = GOAL_WORDS.get(ring.get("key"), (ring.get("label", ""), ring.get("label", "")))[0]
        goal = f", goal {_int(ring.get('goal')):,}" if ring.get("goal") else ""
        parts.append(f"{_int(ring.get('value')):,} {words}{goal}.")
    return " ".join(parts)


@register.filter
def ring_name(key):
    """The words under a ring."""
    return GOAL_WORDS.get(key, ("", str(key)))[1]


@register.filter
def step_label(step):
    """Funnel step names: the label the selector stored."""
    return step.get("label", "")


FUNNEL_FROM = {"visitors": "visitors", "started": "who started", "completed": "who finished"}


@register.simple_tag
def funnel_of(funnel, index):
    """'31 of 42 who started': the count of the step before, never a rate. Empty for the first step."""
    if not index:
        return ""
    step, before = funnel[index], funnel[index - 1]
    if step.get("partial") or not _int(step.get("previous_value", before.get("value"))):
        return ""
    return f"{_int(step.get('value')):,} of {_int(before.get('value')):,} {FUNNEL_FROM.get(before.get('key'), 'before')}"


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
    return {"today": "Today", "7d": "7 days", "30d": "30 days", "90d": "90 days", "all": "All time"}.get(value, value)


@register.simple_tag
def sum_key(items, key="value"):
    """The total of one field across a list (the number in the middle of a donut)."""
    return sum(_int(item.get(key)) for item in (items or []))


@register.simple_tag
def top_of(items, key="value"):
    """The biggest value in a list, for bar lengths."""
    return max((_int(item.get(key)) for item in (items or [])), default=0)


RAMP = {"clay": ("clay", "clay-2", "clay-3", "clay-4"), "teal": ("teal", "teal-2", "teal-3", "teal-4")}


@register.simple_tag
def ramp_rows(items, hue, key="value"):
    """Ordered categories as legend rows in a ramp of the metric's own hue (full, 72%, 48%, 28%). 'No plan chosen' is taupe and last;
    a fifth or later category folds into 'Other' (taupe). The chart script folds the same way, so swatch and arc always match."""
    steps, rows, other, none = RAMP.get(hue, RAMP["clay"]), [], None, None
    for item in items or []:
        row = {"label": item.get("label", ""), "value": _int(item.get(key)), "share_bp": _int(item.get("share_bp"))}
        if item.get("dimension") == "none":
            none = row
        elif len(rows) < len(steps):
            row["swatch"] = f"var(--office-{steps[len(rows)]})"
            rows.append(row)
        else:
            other = other or {"label": "Other", "value": 0, "share_bp": 0}
            other["value"] += row["value"]
            other["share_bp"] += row["share_bp"]
    for extra in (other, none):
        if extra:
            extra["swatch"] = "var(--office-taupe)"
            rows.append(extra)
    return rows


INSIGHT_NAMES = {"facility": "Facilities", "time": "Time of day", "frequency": "How often", "company": "Who with",
                 "tier_picked": "Tier picked", "tier_suggested": "Tier suggested", "source": "Where people come from"}


@register.filter
def insight_name(key):
    """The section name of an insight in the open "What people want" card."""
    return INSIGHT_NAMES.get(key, key)


@register.simple_tag
def insight_of(insights, key):
    """One stored insight by key (or None): {key, title, sentence, top, runner_up, options}. Display only; nothing is computed."""
    return next((i for i in (insights or []) if i.get("key") == key), None)


@register.simple_tag
def has_data(items, key="value"):
    """True when any item has a figure above zero (decides between a chart and its empty line)."""
    return any(_int(item.get(key)) > 0 for item in (items or []))
