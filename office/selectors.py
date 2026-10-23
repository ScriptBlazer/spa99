"""What the Office pages show, built only from stored rows (MetricCounter, DailyMetric, PeriodMetric, MetricText,
OfficeGoal). Fixed number of queries whatever the data: no counting over source tables. The two short source lists
on the dashboard (waiting applications, latest registrations) are plain `LIMIT 5` reads, not counts."""
from datetime import timedelta

from insights import metrics, reader
from insights.metrics import K
from insights.models import DailyMetric, MetricCounter, MetricText, OfficeGoal, PeriodMetric
from insights.rollup import basis_points
from journey.models import Option, Question
from plans.models import Plan

DASHBOARD_RANGES = ("today", "7d", "30d")
ANALYTICS_RANGES = ("7d", "30d", "90d", "all")
WEEKLY_AFTER_DAYS = 120  # 'all' sends weekly points once history is longer than this
JOURNEY_QUESTIONS = ("time", "frequency", "facilities", "company")


def counters(*keys):
    """{(key, dimension): value} from the stored all-time counters."""
    return {(c.key, c.dimension): c.value for c in MetricCounter.objects.filter(key__in=keys)}


def waiting_count(stored=None):
    stored = stored if stored is not None else counters(K.GOLD_BY_STATUS)
    return stored.get((K.GOLD_BY_STATUS, "new"), 0) + stored.get((K.GOLD_BY_STATUS, "contacted"), 0)


def _days(end, count):
    return [end - timedelta(days=i) for i in range(count - 1, -1, -1)]


def _series(rows, key, days, dimension=""):
    by_day = {d: v for d, k, dim, v in rows if k == key and dim == dimension}
    return [by_day.get(day, 0) for day in days]


def _direction(now, before):
    if not before:
        return {"percent": None, "direction": "none"}
    pct = round((now - before) * 100 / before)
    return {"percent": abs(pct), "direction": "flat" if pct == 0 else ("up" if pct > 0 else "down")}


def _goal(goals, key, range_name):
    return goals.get((key, range_name)) or goals.get((key, OfficeGoal.ALL))


def _text(key, scope):
    return MetricText.objects.filter(key=key, scope=scope).values_list("text", flat=True).first() or ""


# ---------- dashboard ----------

def dashboard(range_name="7d", today=None):
    """Everything the Dashboard needs, for range today / 7d / 30d. JSON friendly."""
    range_name = range_name if range_name in DASHBOARD_RANGES else "7d"
    today = today or metrics.day()
    size = reader.RANGE_DAYS[range_name]
    spark_days = _days(today, 30 if range_name == "30d" else 7)
    first = today - timedelta(days=2 * size - 1)  # this window and the one before it
    first = min(first, spark_days[0])
    rows = list(DailyMetric.objects.filter(date__gte=first, date__lte=today).values_list("date", "key", "dimension", "value"))
    stored = counters(K.REGISTRATIONS, K.GOLD_APPLICATIONS, K.GOLD_BY_STATUS, K.JOURNEYS_STARTED, K.JOURNEYS_COMPLETED)
    goals = {(g.key, g.range): g.target for g in OfficeGoal.objects.all()}

    now_days, before_days = _days(today, size), _days(today - timedelta(days=size), size)

    def total(key, days):
        return sum(_series(rows, key, days))

    def stat(key, label, link):
        value, previous = total(key, now_days), total(key, before_days)
        return {"key": key, "label": label, "value": value, "previous": previous, **_direction(value, previous),
                "series": _series(rows, key, spark_days), "link": link}

    started, done = total(K.JOURNEYS_STARTED, now_days), total(K.JOURNEYS_COMPLETED, now_days)
    visitors, registered = total(K.VISITORS, now_days), total(K.REGISTRATIONS, now_days)
    conversion = basis_points(registered, visitors)
    before_conversion = basis_points(total(K.REGISTRATIONS, before_days), total(K.VISITORS, before_days))
    conv_stat = {
        "key": "conversion", "label": "Conversion", "value": conversion or 0, "unit": "basis_points",
        "previous": before_conversion or 0, **_direction(conversion or 0, before_conversion or 0),
        "series": _series(rows, K.RATE_REGISTER, spark_days), "link": "registrations",
    }
    stats = [stat(K.REGISTRATIONS, "Registrations", "registrations"), stat(K.JOURNEYS_COMPLETED, "Journeys completed", "journeys"),
             stat(K.VISITORS, "Site visitors", "visitors"), conv_stat]

    received = stored.get((K.GOLD_APPLICATIONS, ""), 0)
    handled = stored.get((K.GOLD_BY_STATUS, "approved"), 0) + stored.get((K.GOLD_BY_STATUS, "declined"), 0)
    finish_bp = basis_points(done, started) or 0
    reg_goal, fin_goal = _goal(goals, OfficeGoal.REGISTRATIONS, range_name), _goal(goals, OfficeGoal.JOURNEY_COMPLETION, range_name)
    gold_goal = _goal(goals, OfficeGoal.GOLD_HANDLED, range_name)
    handled_pct = round(handled * 100 / received) if received else 0
    rings = [
        {"key": "registrations", "label": "Registrations", "value": registered, "of": reg_goal, "goal": reg_goal, "unit": "count",
         "percent": min(200, round(registered * 100 / reg_goal)) if reg_goal else None},
        {"key": "journeys_completed", "label": "Journeys completed", "value": round(finish_bp / 100), "of": fin_goal, "goal": fin_goal,
         "unit": "percent", "completed": done, "started": started,
         "percent": min(200, round(finish_bp / 100 * 100 / fin_goal)) if fin_goal else None},
        {"key": "gold_handled", "label": "Gold handled", "value": handled, "of": received, "goal": gold_goal, "unit": "count",
         "handled_percent": handled_pct,
         "percent": min(200, round(handled_pct * 100 / gold_goal)) if gold_goal else None},
    ]
    funnel_values = [("visitors", "Visitors", visitors), ("started", "Started the journey", started),
                     ("completed", "Completed it", done), ("registered", "Registered", registered)]
    funnel = []
    for i, (key, label, value) in enumerate(funnel_values):
        funnel.append({"key": key, "label": label, "value": value,
                       "share_bp": basis_points(value, visitors) or 0,
                       "step_rate_bp": basis_points(value, funnel_values[i - 1][2]) if i else None})
    from gold.models import GoldApplication
    from users.models import InterestRegistration

    waiting_rows = GoldApplication.objects.filter(status__in=[GoldApplication.NEW, GoldApplication.CONTACTED]).order_by("-created_at")[:5]
    latest = InterestRegistration.objects.select_related("user", "plan").order_by("-created_at")[:5]
    return {
        "range": range_name, "ranges": list(DASHBOARD_RANGES), "today": today.isoformat(),
        "what_changed": _text("dashboard_changed", range_name),
        "rings": rings, "stats": stats, "funnel": funnel,
        "waiting": {
            "count": waiting_count(stored),
            "items": [{"id": str(a.pk), "name": a.full_name, "potential": a.potential_level, "applied": a.created_at.isoformat()} for a in waiting_rows],
        },
        "latest": [{"id": str(i.user_id), "name": i.user.get_full_name() or i.user.email, "plan": i.plan.name if i.plan_id else "",
                    "registered": i.created_at.isoformat()} for i in latest],
        "totals": {"registrations": stored.get((K.REGISTRATIONS, ""), 0), "gold_applications": received},
    }


# ---------- analytics ----------

def _points(range_name, today):
    """(granularity, labels as dates, start of the previous window or None, rows)."""
    start, _ = reader.range_dates(range_name, today)
    if start is not None:
        return "day", _days(today, reader.RANGE_DAYS[range_name])
    first = DailyMetric.objects.order_by("date").values_list("date", flat=True).first()
    if first is None or (today - first).days <= WEEKLY_AFTER_DAYS:
        span = 0 if first is None else (today - first).days
        return "day", _days(today, max(span + 1, 1))
    from insights.rollup import week_start
    weeks, cursor = [], week_start(first)
    while cursor <= today:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return "week", weeks


def _fetch(range_name, granularity, labels, key_list):
    """Rows as (date, key, dimension, value), daily or weekly, for the labels' window plus the previous window."""
    if granularity == "week":
        rows = PeriodMetric.objects.filter(period=PeriodMetric.WEEK, key__in=key_list, start__gte=labels[0])
        return [(r.start, r.key, r.dimension, r.value) for r in rows]
    size = len(labels)
    first = labels[0] - timedelta(days=size) if range_name != "all" else labels[0]
    rows = DailyMetric.objects.filter(date__gte=first, date__lte=labels[-1], key__in=key_list)
    return list(rows.values_list("date", "key", "dimension", "value"))


SERIES_KEYS = (K.VISITORS, K.JOURNEYS_STARTED, K.JOURNEYS_COMPLETED, K.REGISTRATIONS, K.EMAIL_VERIFIED, K.GOLD_APPLICATIONS, K.GOLD_APPROVED)
BREAKDOWN_KEYS = (K.REGISTRATIONS_BY_PLAN, K.REGISTRATIONS_BY_SOURCE, K.SUGGESTED_PLAN, K.JOURNEY_GOLD_POTENTIAL,
                  K.GOLD_BY_POTENTIAL, K.JOURNEY_ANSWER, K.JOURNEY_SCREEN)
PAGE_KEYS = (K.PAGE_VIEWS, K.VISITORS, K.REFERRERS)


def _by_dimension(rows, key, labels):
    wanted, out = set(labels), {}
    for d, k, dim, v in rows:
        if k == key and dim and d in wanted:
            out[dim] = out.get(dim, 0) + v
    return out


def _plan_order():
    return list(Plan.objects.order_by("order").values_list("slug", "name"))


def analytics(range_name="30d", today=None):
    """JSON for the Analytics charts: series per key with the previous period, funnel, breakdowns, journey answers,
    drop-off per screen, Gold, and the stored sentence for each chart."""
    range_name = range_name if range_name in ANALYTICS_RANGES else "30d"
    today = today or metrics.day()
    granularity, labels = _points(range_name, today)
    rows = _fetch(range_name, granularity, labels, SERIES_KEYS + BREAKDOWN_KEYS + (K.PAGE_VIEWS,))
    size = len(labels)
    previous = [] if range_name == "all" else [day - timedelta(days=size) for day in labels]  # same length, just before
    texts = {t.key: t.text for t in MetricText.objects.filter(scope=range_name, key__startswith="chart_")}

    series = {}
    for key in SERIES_KEYS + (K.PAGE_VIEWS,):
        values = _series(rows, key, labels)
        series[key] = {"total": sum(values), "values": values, "previous": _series(rows, key, previous) if previous else []}
    total = lambda key: series[key]["total"]  # noqa: E731

    funnel_def = [("visitors", "Visitors", total(K.VISITORS)), ("started", "Started the journey", total(K.JOURNEYS_STARTED)),
                  ("completed", "Completed it", total(K.JOURNEYS_COMPLETED)), ("registered", "Registered", total(K.REGISTRATIONS))]
    funnel = [{"key": k, "label": label, "value": v, "step_rate_bp": basis_points(v, funnel_def[i - 1][2]) if i else None}
              for i, (k, label, v) in enumerate(funnel_def)]

    plans = _plan_order()

    def by_plan(key):
        found = _by_dimension(rows, key, labels)
        out = [{"dimension": slug, "label": name, "value": found.get(slug, 0)} for slug, name in plans]
        if found.get("none"):
            out.append({"dimension": "none", "label": "No plan chosen", "value": found["none"]})
        return out

    option_labels = {(q, v): (label, order) for q, v, label, order in Option.objects.filter(question__key__in=JOURNEY_QUESTIONS, active=True)
                     .order_by("order").values_list("question__key", "value", "label", "order")}
    answers_found = _by_dimension(rows, K.JOURNEY_ANSWER, labels)
    answers = {q: [{"value": v, "label": label, "count": answers_found.get(f"{q}:{v}", 0)}
                   for (qk, v), (label, _) in option_labels.items() if qk == q] for q in JOURNEY_QUESTIONS}

    reach = _by_dimension(rows, K.JOURNEY_SCREEN, labels)
    screen_text = {}
    for number, text in Question.objects.filter(active=True).order_by("screen", "order").values_list("screen", "text"):
        screen_text.setdefault(number, text)
    ordered = sorted(int(n) for n in reach)
    screens = []
    for i, n in enumerate(ordered):
        reached = reach[str(n)]
        later = reach[str(ordered[i + 1])] if i + 1 < len(ordered) else None
        left = max(reached - later, 0) if later is not None else 0
        screens.append({"screen": n, "label": screen_text.get(n, f"Screen {n}"), "reached": reached, "left": left,
                        "left_percent": round(left * 100 / reached) if reached else 0})

    status = counters(K.GOLD_BY_STATUS)
    potential = _by_dimension(rows, K.GOLD_BY_POTENTIAL, labels)
    gold = {
        "by_potential": [{"dimension": p, "label": p.title(), "value": potential.get(p, 0)} for p in ("high", "medium", "low")],
        "by_status_now": [{"dimension": s, "label": label, "value": status.get((K.GOLD_BY_STATUS, s), 0)}
                          for s, label in (("approved", "Approved"), ("new", "Waiting"), ("contacted", "Contacted"), ("declined", "Declined"))],
    }
    return {
        "range": range_name, "ranges": list(ANALYTICS_RANGES), "granularity": granularity,
        "labels": [d.isoformat() for d in labels], "previous_labels": [d.isoformat() for d in previous],
        "series": series, "funnel": funnel,
        "registrations_by_plan": by_plan(K.REGISTRATIONS_BY_PLAN), "suggested_plan": by_plan(K.SUGGESTED_PLAN),
        "registrations_by_source": [{"dimension": d, "value": v} for d, v in sorted(_by_dimension(rows, K.REGISTRATIONS_BY_SOURCE, labels).items())],
        "journey_answers": answers, "drop_off": screens, "gold": gold,
        "summaries": {chart: texts.get(f"chart_{chart}", "") for chart in
                      ("visitors", "funnel", "registrations_by_plan", "suggested_plan", "journey_answers", "drop_off", "gold", "top_pages", "referrers")},
    }


def pages(range_name="30d", today=None, limit=10):
    """JSON for page views: series, top pages by path group and referring sites (site names only; 'direct' = no referrer)."""
    range_name = range_name if range_name in ANALYTICS_RANGES else "30d"
    today = today or metrics.day()
    granularity, labels = _points(range_name, today)
    rows = _fetch(range_name, granularity, labels, PAGE_KEYS)
    top = sorted(_by_dimension(rows, K.PAGE_VIEWS, labels).items(), key=lambda i: (-i[1], i[0]))[:limit]
    refs = sorted(_by_dimension(rows, K.REFERRERS, labels).items(), key=lambda i: (-i[1], i[0]))[:limit]
    texts = {t.key: t.text for t in MetricText.objects.filter(scope=range_name, key__in=("chart_top_pages", "chart_referrers"))}
    return {
        "range": range_name, "granularity": granularity, "labels": [d.isoformat() for d in labels],
        "page_views": _series(rows, K.PAGE_VIEWS, labels), "visitors": _series(rows, K.VISITORS, labels),
        "top_pages": [{"page": p, "views": v} for p, v in top], "referrers": [{"site": s, "visits": v} for s, v in refs],
        "summaries": {"top_pages": texts.get("chart_top_pages", ""), "referrers": texts.get("chart_referrers", "")},
    }
