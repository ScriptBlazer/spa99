"""What the Office pages show. The `build_*` functions add up the stored rows (DailyMetric, PeriodMetric, ...) into the
finished payload of a page and range; only `office.snapshots` calls them (the hourly roll-up and the debounced refresh
after events). The public `dashboard`, `analytics` and `pages` just read the one stored OfficeSnapshot row (nothing is
summed on page load; a missing row gives an empty state, never an inline computation). The two short source lists on the
dashboard (waiting applications, latest registrations) are plain `LIMIT 5` reads."""
from datetime import timedelta

from insights import metrics, reader
from insights.metrics import K
from insights import facts
from insights.models import DailyMetric, Insight, MetricCounter, MetricText, OfficeGoal, OfficeSnapshot, PeriodMetric
from insights.rollup import basis_points
from journey.models import Option, Question
from plans.models import Plan

DASHBOARD_RANGES = ("today", "7d", "30d", "all")
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


FUNNEL_NOTE = "A later step can be higher than an earlier one: some people register without the journey, or visited before visitors were counted."


def _share(value, whole):
    """A funnel share in basis points, never above 100%: None when the earlier step is smaller (its counting started later)."""
    if not whole:
        return None
    return basis_points(value, whole) if value <= whole else None


def _goal(goals, key, range_name):
    return goals.get((key, range_name)) or goals.get((key, OfficeGoal.ALL))


def _text(key, scope):
    return MetricText.objects.filter(key=key, scope=scope).values_list("text", flat=True).first() or ""


ANALYTICS_RANK = 6  # Analytics shows up to six options per insight
HIDDEN_INSIGHTS = {"source"}  # still worked out and stored; not shown in the Office (Moishe 2026-10-25: not useful for now)


def insights_for(range_name, max_rank):
    """The stored "what people want" facts for a range, one query: [{key, title, top, runner_up, options, sentence}] in
    the fixed order; an insight with no data has no rows and is simply absent."""
    grouped = {}
    for row in Insight.objects.filter(range=range_name, rank__lte=max_rank).order_by("key", "rank"):
        grouped.setdefault(row.key, []).append(row)
    out = []
    for key in facts.ORDER:
        rows = grouped.get(key)
        if not rows or key in HIDDEN_INSIGHTS:
            continue
        options = [{"rank": r.rank, "label": r.label, "value": r.value, "of_total": r.of_total,
                    "share_bp": basis_points(r.value, r.of_total) or 0} for r in rows]
        out.append({"key": key, "title": rows[0].title, "sentence": rows[0].sentence, "top": options[0],
                    "runner_up": options[1] if len(options) > 1 else None, "options": options})
    return out


def tier_pair(insights):
    """Picked vs suggested tier side by side, from the stored insight rows: [{label, picked, suggested}] (counts)."""
    by_key = {i["key"]: {o["label"]: o["value"] for o in i["options"]} for i in insights if i["key"] in ("tier_picked", "tier_suggested")}
    picked, suggested = by_key.get("tier_picked", {}), by_key.get("tier_suggested", {})
    labels = sorted(set(picked) | set(suggested), key=lambda x: (-(picked.get(x, 0) + suggested.get(x, 0)), x))
    return [{"label": x, "picked": picked.get(x, 0), "suggested": suggested.get(x, 0)} for x in labels]


# ---------- dashboard ----------

def _spark_buckets(range_name, today):
    """The sparkline points as (first day, last day): the last 7 or 30 days, or for All the whole history, daily until it
    passes WEEKLY_AFTER_DAYS and then weekly (like Analytics)."""
    if range_name != "all":
        return [(d, d) for d in _days(today, 30 if range_name == "30d" else 7)]
    first = DailyMetric.objects.order_by("date").values_list("date", flat=True).first() or today
    if (today - first).days <= WEEKLY_AFTER_DAYS:
        return [(d, d) for d in _days(today, max((today - first).days + 1, 7))]
    from insights.rollup import week_start
    out, cursor = [], week_start(first)
    while cursor <= today:
        out.append((cursor, min(cursor + timedelta(days=6), today)))
        cursor += timedelta(days=7)
    return out


def _bucket_sums(by_day, buckets):
    return [sum(v for d, v in by_day.items() if a <= d <= b) for a, b in buckets]


def build_dashboard(range_name="7d", today=None, figures=None):
    """The stored Dashboard payload for range today / 7d / 30d / all (without the two live LIMIT-5 lists). JSON friendly.
    People and registrations come from `figures` (counting rules C1 to C3); visitors and page views from the daily rows."""
    from insights import people

    range_name = range_name if range_name in DASHBOARD_RANGES else "7d"
    today = today or metrics.day()
    figures = figures or people.load()
    size = reader.RANGE_DAYS[range_name]  # None for all: no previous period
    now = (None, today) if size is None else (today - timedelta(days=size - 1), today)
    before = None if size is None else (today - timedelta(days=2 * size - 1), today - timedelta(days=size))
    spark = _spark_buckets(range_name, today)
    daily = {}
    for d, key, v in DailyMetric.objects.filter(key__in=(K.VISITORS, K.PAGE_VIEWS), dimension="").values_list("date", "key", "value"):
        daily.setdefault(key, {})[d] = v
    stored = counters(K.REGISTRATIONS, K.GOLD_APPLICATIONS, K.GOLD_BY_STATUS)
    goals = {(g.key, g.range): g.target for g in OfficeGoal.objects.all()}

    def over(by_day, window):
        return None if window is None else sum(v for d, v in by_day.items() if (window[0] is None or window[0] <= d) and d <= window[1])

    def stat(key, label, link, value, previous, series):
        extra = {"percent": None, "direction": "none"} if previous is None else _direction(value, previous)
        return {"key": key, "label": label, "value": value, "previous": previous,
                "change": None if previous is None else value - previous, **extra, "series": series, "link": link}

    started, done = figures.started(*now), figures.finished(*now)
    registered, visitors = figures.registered(*now), over(daily.get(K.VISITORS, {}), now)
    stats = [stat(K.REGISTRATIONS, "Registrations", "registrations", registered, None if before is None else figures.registered(*before),
                  figures.registered_series(spark)),
             stat(K.VISITORS, "Site visitors", "visitors", visitors, over(daily.get(K.VISITORS, {}), before), _bucket_sums(daily.get(K.VISITORS, {}), spark)),
             stat(K.PAGE_VIEWS, "Page views", "pages", over(daily.get(K.PAGE_VIEWS, {}), now), over(daily.get(K.PAGE_VIEWS, {}), before),
                  _bucket_sums(daily.get(K.PAGE_VIEWS, {}), spark))]

    def ring(key, label, goal_key, value, previous):
        goal = _goal(goals, goal_key, range_name)
        return {"key": key, "label": label, "value": value, "goal": goal,
                "percent": min(200, round(value * 100 / goal)) if goal else None,
                "previous": previous, "change": None if previous is None else value - previous}

    rings = [
        ring("journeys_started", "Started the journey", OfficeGoal.JOURNEYS_STARTED, started, None if before is None else figures.started(*before)),
        ring("journeys_completed", "Finished the journey", OfficeGoal.JOURNEYS_FINISHED, done, None if before is None else figures.finished(*before)),
        ring("registrations", "Registered", OfficeGoal.REGISTRATIONS, registered, None if before is None else figures.registered(*before)),
    ]
    funnel_values = [("visitors", "Visitors", visitors), ("started", "Started the journey", started),
                     ("completed", "Finished the journey", done), ("registered", "Registered", registered)]
    funnel = []
    for i, (key, label, value) in enumerate(funnel_values):
        funnel.append({"key": key, "label": label, "value": value,
                       "previous_value": funnel_values[i - 1][2] if i else None,
                       "share_bp": min(basis_points(value, visitors) or 0, 10000),
                       "step_rate_bp": _share(value, funnel_values[i - 1][2]) if i else None,
                       "partial": bool(i and value > funnel_values[i - 1][2])})
    return {
        "range": range_name, "ranges": list(DASHBOARD_RANGES), "today": today.isoformat(),
        "what_changed": _text("dashboard_changed", range_name),
        "gold_waiting": waiting_count(stored), "rings": rings, "stats": stats, "funnel": funnel, "funnel_note": FUNNEL_NOTE if any(f["partial"] for f in funnel) else "",
        "insights": insights_for(range_name, facts.MAX_RANK),  # every option: the closed card shows each one's top and runner-up, the open card lists them all
        "totals": {"registrations": stored.get((K.REGISTRATIONS, ""), 0), "gold_applications": stored.get((K.GOLD_APPLICATIONS, ""), 0)},
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


SERIES_KEYS = (K.VISITORS, K.EMAIL_VERIFIED, K.GOLD_APPLICATIONS, K.GOLD_APPROVED)  # stored daily rows
PEOPLE_SERIES = ("journeys_started", "journeys_completed", "registrations", "people_registered")  # from the source tables (job only)
BREAKDOWN_KEYS = (K.JOURNEY_GOLD_POTENTIAL, K.GOLD_BY_POTENTIAL, K.JOURNEY_SCREEN)
PAGE_KEYS = (K.PAGE_VIEWS, K.VISITORS, K.REFERRERS)


def _by_dimension(rows, key, labels):
    wanted, out = set(labels), {}
    for d, k, dim, v in rows:
        if k == key and dim and d in wanted:
            out[dim] = out.get(dim, 0) + v
    return out


def _plan_order():
    return list(Plan.objects.order_by("order").values_list("slug", "name"))


def build_analytics(range_name="30d", today=None, figures=None):
    """The stored JSON for the Analytics charts: series per key with the previous period, funnel, breakdowns, journey answers,
    drop-off per screen, Gold, and the stored sentence for each chart."""
    from insights import people as source

    range_name = range_name if range_name in ANALYTICS_RANGES else "30d"
    today = today or metrics.day()
    figures = figures or source.load()
    granularity, labels = _points(range_name, today)
    rows = _fetch(range_name, granularity, labels, SERIES_KEYS + BREAKDOWN_KEYS + (K.PAGE_VIEWS,))
    size = len(labels)
    previous = [] if range_name == "all" else [day - timedelta(days=size) for day in labels]  # same length, just before
    texts = {t.key: t.text for t in MetricText.objects.filter(scope=range_name, key__startswith="chart_")}

    series = {}
    for key in SERIES_KEYS + (K.PAGE_VIEWS,):
        values = _series(rows, key, labels)
        series[key] = {"total": sum(values), "values": values, "previous": _series(rows, key, previous) if previous else [],
                     "previous_total": sum(_series(rows, key, previous)) if previous else None}
    # People and registrations per the counting rules: the total is distinct people (or registrations) in the whole range,
    # the points are per day (per week for a long All).
    def buckets(days):
        return [(d, d) for d in days] if granularity == "day" else [(d, min(d + timedelta(days=6), today)) for d in days]

    start, end = labels[0], today
    here, before = buckets(labels), buckets(previous)
    for key, count, values in (("journeys_started", figures.started, figures.started_series), ("journeys_completed", figures.finished, figures.finished_series),
                               ("registrations", figures.registered, figures.registered_series)):
        series[key] = {"total": count(start, end), "values": values(here), "previous": values(before) if before else [],
                     "previous_total": count(previous[0], previous[-1]) if previous else None}  # distinct people in the previous window
    series["people_registered"] = series["registrations"]  # the hero reads this key
    total = lambda key: series[key]["total"]  # noqa: E731

    funnel_def = [("visitors", "Visitors", total(K.VISITORS)), ("started", "Started the journey", total("journeys_started")),
                  ("completed", "Finished the journey", total("journeys_completed")), ("registered", "Registered", total("registrations"))]
    funnel = [{"key": k, "label": label, "value": v, "share_bp": min(basis_points(v, funnel_def[0][2]) or 0, 10000),
               "step_rate_bp": _share(v, funnel_def[i - 1][2]) if i else None,
               "partial": bool(i and v > funnel_def[i - 1][2])}
              for i, (k, label, v) in enumerate(funnel_def)]

    plans = _plan_order()
    people = insights_for(range_name, ANALYTICS_RANK)

    def by_plan(found):
        out = [{"dimension": slug, "label": name, "value": found.get(slug, 0)} for slug, name in plans]
        if found.get("none"):
            out.append({"dimension": "none", "label": "No plan chosen", "value": found["none"]})
        whole = sum(item["value"] for item in out)
        return [{**item, "share_bp": basis_points(item["value"], whole) or 0} for item in out]

    option_labels = {(q, v): (facts.clean_label(label), order) for q, v, label, order in Option.objects.filter(question__key__in=JOURNEY_QUESTIONS, active=True)
                     .order_by("order").values_list("question__key", "value", "label", "order")}
    voters, answers_found, suggested_found = figures.vote_counts(start, end)  # one vote per person
    answers = {}
    for q in JOURNEY_QUESTIONS:
        items = [{"value": v, "label": label, "count": answers_found.get(f"{q}:{v}", 0)}
                 for (qk, v), (label, _) in option_labels.items() if qk == q]
        whole = sum(item["count"] for item in items)
        answers[q] = [{**item, "share_bp": basis_points(item["count"], whole) or 0} for item in items]

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
        "by_status_now": [{"dimension": s, "label": label, "value": value} for s, label, value in (
            ("approved", "Approved", status.get((K.GOLD_BY_STATUS, "approved"), 0)),
            ("waiting", "Waiting", waiting_count(status)),  # new and contacted: both are waiting for Barry
            ("declined", "Declined", status.get((K.GOLD_BY_STATUS, "declined"), 0)))],
    }
    return {
        "range": range_name, "ranges": list(ANALYTICS_RANGES), "granularity": granularity, "today": today.isoformat(),
        "labels": [d.isoformat() for d in labels], "previous_labels": [d.isoformat() for d in previous],
        "series": series, "funnel": funnel, "funnel_note": FUNNEL_NOTE if any(f["partial"] for f in funnel) else "",
        "registrations_by_plan": by_plan(figures.registered_by(start, end, 1)), "suggested_plan": by_plan(suggested_found),
        "registrations_by_source": [{"dimension": d, "value": v} for d, v in sorted(figures.registered_by(start, end, 2).items())],
        "journey_answers": answers, "drop_off": screens, "gold": gold,
        "insights": people, "tier_pair": tier_pair(people),
        "summaries": {chart: texts.get(f"chart_{chart}", "") for chart in
                      ("visitors", "funnel", "registrations_by_plan", "suggested_plan", "journey_answers", "drop_off", "gold", "top_pages", "referrers")},
    }


def build_pages(range_name="30d", today=None, limit=10):
    """The stored JSON for page views: series, top pages by path group and referring sites (site names only; 'direct' = no referrer)."""
    range_name = range_name if range_name in ANALYTICS_RANGES else "30d"
    today = today or metrics.day()
    granularity, labels = _points(range_name, today)
    rows = _fetch(range_name, granularity, labels, PAGE_KEYS)
    top = sorted(_by_dimension(rows, K.PAGE_VIEWS, labels).items(), key=lambda i: (-i[1], i[0]))[:limit]
    refs = sorted(_by_dimension(rows, K.REFERRERS, labels).items(), key=lambda i: (-i[1], i[0]))[:limit]
    texts = {t.key: t.text for t in MetricText.objects.filter(scope=range_name, key__in=("chart_top_pages", "chart_referrers"))}
    return {
        "range": range_name, "granularity": granularity, "today": today.isoformat(), "labels": [d.isoformat() for d in labels],
        "page_views": _series(rows, K.PAGE_VIEWS, labels), "visitors": _series(rows, K.VISITORS, labels),
        "top_pages": [{"page": p, "views": v} for p, v in top], "referrers": [{"site": s, "visits": v} for s, v in refs],
        "summaries": {"top_pages": texts.get("chart_top_pages", ""), "referrers": texts.get("chart_referrers", "")},
    }


# ---------- reading the stored snapshots ----------

def _snapshot(page, range_name):
    """The stored payload, or None when there is none yet or it is from before London midnight (then a refresh is asked
    for in the background and the caller shows an "Updating" state; nothing is computed here)."""
    from office import snapshots

    payload = OfficeSnapshot.objects.filter(page=page, range=range_name).values_list("payload", flat=True).first()
    if payload is None or payload.get("today") != metrics.day().isoformat():
        snapshots.request_refresh()
        return None
    return payload


UPDATING = "Updating\u2026"


def _empty_funnel():
    steps = (("visitors", "Visitors"), ("started", "Started the journey"), ("completed", "Finished the journey"), ("registered", "Registered"))
    return [{"key": k, "label": label, "value": 0, "previous_value": None if i == 0 else 0, "share_bp": 0, "step_rate_bp": None, "partial": False}
            for i, (k, label) in enumerate(steps)]


def empty_dashboard(range_name):
    """What the Dashboard shows before its first snapshot exists (a fresh database): zeros, no text. Never computed from data."""
    today = metrics.day()
    zeros = [0] * (30 if range_name == "30d" else 7)
    stat = lambda key, label, link: {"key": key, "label": label, "value": 0, "previous": 0, "change": 0, "percent": None,  # noqa: E731
                                     "direction": "none", "series": zeros, "link": link}
    ring = lambda key, label: {"key": key, "label": label, "value": 0, "goal": None, "percent": None, "previous": 0, "change": 0}  # noqa: E731
    return {"range": range_name, "ranges": list(DASHBOARD_RANGES), "today": today.isoformat(), "what_changed": "", "gold_waiting": 0,
            "rings": [ring("journeys_started", "Started the journey"), ring("journeys_completed", "Finished the journey"),
                      ring("registrations", "Registered")],
            "stats": [stat(K.REGISTRATIONS, "Registrations", "registrations"), stat(K.VISITORS, "Site visitors", "visitors"),
                      stat(K.PAGE_VIEWS, "Page views", "pages")],
            "funnel": _empty_funnel(), "funnel_note": "", "insights": [], "totals": {"registrations": 0, "gold_applications": 0}}


def empty_analytics(range_name):
    series = {key: {"total": 0, "values": [], "previous": [], "previous_total": None} for key in SERIES_KEYS + PEOPLE_SERIES + (K.PAGE_VIEWS,)}
    return {"range": range_name, "ranges": list(ANALYTICS_RANGES), "granularity": "day", "labels": [], "previous_labels": [],
            "series": series, "funnel": _empty_funnel(), "funnel_note": "", "registrations_by_plan": [], "suggested_plan": [],
            "registrations_by_source": [], "journey_answers": {q: [] for q in JOURNEY_QUESTIONS}, "drop_off": [],
            "gold": {"by_potential": [], "by_status_now": []}, "insights": [], "tier_pair": [],
            "summaries": {chart: "" for chart in ("visitors", "funnel", "registrations_by_plan", "suggested_plan", "journey_answers",
                                                  "drop_off", "gold", "top_pages", "referrers")}}


def empty_pages(range_name):
    return {"range": range_name, "granularity": "day", "labels": [], "page_views": [], "visitors": [], "top_pages": [], "referrers": [],
            "summaries": {"top_pages": "", "referrers": ""}}


def dashboard(range_name="7d"):
    """The Dashboard payload: one stored snapshot row, plus the two short live lists (LIMIT 5 reads, not counts)."""
    from gold.models import GoldApplication
    from users.models import InterestRegistration

    range_name = range_name if range_name in DASHBOARD_RANGES else "7d"
    data = _snapshot(OfficeSnapshot.DASHBOARD, range_name) or {**empty_dashboard(range_name), "what_changed": UPDATING, "updating": True}
    waiting_rows = GoldApplication.objects.filter(status__in=[GoldApplication.NEW, GoldApplication.CONTACTED]).order_by("-created_at")[:5]
    latest = InterestRegistration.objects.select_related("user", "plan").order_by("-created_at")[:5]
    return {**data,
            "waiting": {"count": data["gold_waiting"],
                        "items": [{"id": str(a.pk), "name": a.full_name, "potential": a.potential_level, "applied": a.created_at.isoformat()} for a in waiting_rows]},
            "latest": [{"id": str(i.user_id), "name": i.user.get_full_name() or i.user.email, "plan": i.plan.name if i.plan_id else "",
                        "registered": i.created_at.isoformat()} for i in latest]}


def analytics(range_name="30d"):
    range_name = range_name if range_name in ANALYTICS_RANGES else "30d"
    return _snapshot(OfficeSnapshot.ANALYTICS, range_name) or {**empty_analytics(range_name), "updating": True}


def pages(range_name="30d"):
    range_name = range_name if range_name in ANALYTICS_RANGES else "30d"
    return _snapshot(OfficeSnapshot.PAGES, range_name) or {**empty_pages(range_name), "updating": True}
