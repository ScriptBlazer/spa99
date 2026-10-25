"""The sentences the Office shows: the dashboard's "what changed" line and one summary per Analytics chart. Written by
the roll-up into MetricText from the stored daily rows and counters; pages only read them (up to an hour old)."""
from django.db import transaction

from . import metrics, people, reader
from .metrics import K
from .models import MetricCounter, MetricText

DASHBOARD_RANGES = ("today", "7d", "30d", "all")
CHART_RANGES = ("7d", "30d", "90d", "all")
CHARTS = ("visitors", "funnel", "registrations_by_plan", "suggested_plan", "journey_answers", "drop_off", "gold", "top_pages", "referrers")
THAN = {"today": "yesterday", "7d": "last week", "30d": "the previous 30 days", "90d": "the previous 90 days"}
PERIOD = {"today": "today", "7d": "in the last 7 days", "30d": "in the last 30 days", "90d": "in the last 90 days", "all": "so far"}
NOTHING = {
    "visitors": "No visitors in this range yet.", "funnel": "No visitors in this range yet.",
    "registrations_by_plan": "No registrations in this range yet.", "suggested_plan": "No journeys completed in this range yet.",
    "journey_answers": "No journeys completed in this range yet.", "drop_off": "No journeys started in this range yet.",
    "gold": "No Gold applications in this range yet.", "top_pages": "No page views in this range yet.",
    "referrers": "No visits in this range yet.",
}


def plural(n, one, many=None):
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def change(now, before):
    """'3 more than', '2 fewer than' or 'the same as' the previous window, as a plain count; None with nothing to compare."""
    if not before:
        return None
    diff = now - before
    return "the same as" if diff == 0 else (f"{diff:,} more than" if diff > 0 else f"{-diff:,} fewer than")


def _names():
    """{plan slug: name} and {"question:option": label}, for readable sentences."""
    from journey.models import Option
    from plans.models import Plan

    plans = dict(Plan.objects.values_list("slug", "name"))
    options = {f"{q}:{v}": label for q, v, label in Option.objects.values_list("question__key", "value", "label")}
    return plans, options


def _top(sums, key, labels):
    items = reader.breakdown(sums, key)
    return (labels.get(items[0][0], items[0][0]), items[0][1], sum(v for _, v in items)) if items else None


def chart_sentences(name, today, plans, options, waiting, figures):
    start, end = reader.range_dates(name, today)
    sums = figures.overlay(reader.totals(start, end), start, end)  # people and answers per the counting rules, not per session
    prev = reader.previous_dates(name, today)
    before = reader.totals(*prev) if prev else {}
    total = lambda k, s=sums: s.get((k, ""), 0)  # noqa: E731
    visitors, started, done, registered = total(K.VISITORS), total(people.STARTED), total(people.FINISHED), total(people.REGISTERED)
    out = {}
    if visitors:
        trend = change(visitors, total(K.VISITORS, before))
        out["visitors"] = f"{plural(visitors, 'visitor')} {PERIOD[name]}" + (f", {trend} {THAN[name]}." if trend else ".")
        out["funnel"] = (f"Of {visitors:,} visitors, {started:,} started the journey, {done:,} finished the journey and {registered:,} registered.")
    top = _top(sums, K.REGISTRATIONS_BY_PLAN, plans)
    if top:
        out["registrations_by_plan"] = f"{top[0]} leads with {top[1]:,} of {plural(top[2], 'registration')}."
    top = _top(sums, K.SUGGESTED_PLAN, plans)
    if top:
        out["suggested_plan"] = f"{top[0]} is suggested most often: {top[1]:,} of {plural(top[2], 'journey')}."
    answers = [(d, v) for d, v in reader.breakdown(sums, K.JOURNEY_ANSWER) if d.startswith("time:")]
    if answers:
        out["journey_answers"] = f"{options.get(answers[0][0], answers[0][0])} is the most popular time to visit."
    reach = {int(d): v for d, v in reader.breakdown(sums, K.JOURNEY_SCREEN)}
    steps = sorted(reach)
    drops = [(reach[a] - reach[b], a) for a, b in zip(steps, steps[1:]) if reach[a] > reach[b]]
    if drops:
        lost, screen = max(drops)
        out["drop_off"] = f"Most people stop at screen {screen}: {round(lost * 100 / reach[screen])}% of those who got there."
    elif reach:
        out["drop_off"] = "Everyone who started reached the end."
    applications = total(K.GOLD_APPLICATIONS)
    if applications:
        out["gold"] = f"{plural(applications, 'Gold application')} {PERIOD[name]}, {waiting:,} waiting now."
    page = [(d, v) for d, v in reader.breakdown(sums, K.PAGE_VIEWS)]
    if page:
        out["top_pages"] = f"{page[0][0].title()} is the most viewed page, with {plural(page[0][1], 'view')}."
    refs = reader.breakdown(sums, K.REFERRERS)
    if refs:
        out["referrers"] = ("Most visits come straight to the site." if refs[0][0] == "direct"
                            else f"Most visits come from {refs[0][0]}.") 
    return {chart: out.get(chart, NOTHING[chart]) for chart in CHARTS}


WORDS = ((people.REGISTERED, "person registered", "people registered"),
         (people.STARTED, "person started the journey", "people started the journey"),
         (people.FINISHED, "person finished the journey", "people finished the journey"))


def dashboard_sentence(name, today, waiting, figures):
    """Plain counts only: '5 people registered in the last 7 days, 2 more than last week. 9 people started the journey, ...'"""
    start, end = reader.range_dates(name, today)
    now = figures.overlay({}, start, end)
    prev = reader.previous_dates(name, today)
    before = figures.overlay({}, *prev) if prev else {}
    sentences = []
    for key, one, many in WORDS:
        value, was = now.get((key, ""), 0), before.get((key, ""), 0)
        if not value and not was:
            continue
        trend = change(value, was)
        text = f"{value:,} {one if value == 1 else many}" + (f" {PERIOD[name]}" if not sentences else "")
        sentences.append(text + (f", {trend} {THAN[name]}." if trend else "."))
    if waiting:
        sentences.append(f"{plural(waiting, 'Gold application')} {'is' if waiting == 1 else 'are'} waiting.")
    return " ".join(sentences) or ("A quiet day so far." if name == "today" else "A quiet spell so far.")


def _store(wanted):
    with transaction.atomic():
        existing = {(t.key, t.scope): t for t in MetricText.objects.filter(key__in={k for k, _ in wanted})}
        for (key, scope), text in wanted.items():
            row = existing.get((key, scope))
            if row is None:
                MetricText.objects.create(key=key, scope=scope, text=text[:300])
            elif row.text != text[:300]:
                row.text = text[:300]
                row.save(update_fields=["text", "updated_at"])


def _waiting():
    counters = {(c.key, c.dimension): c.value for c in MetricCounter.objects.filter(key=K.GOLD_BY_STATUS)}
    return sum(counters.get((K.GOLD_BY_STATUS, s), 0) for s in ("new", "contacted", "awaiting_final"))  # the Waiting list shows these too


def write_all(today=None, figures=None):
    """Rewrite every sentence (idempotent: same stored rows, same text). Job only. Returns the number of rows written."""
    today = today or metrics.day()
    figures = figures or people.load()
    waiting = _waiting()
    plans, options = _names()
    wanted = {("dashboard_changed", name): dashboard_sentence(name, today, waiting, figures) for name in DASHBOARD_RANGES}
    for name in CHART_RANGES:
        for chart, text in chart_sentences(name, today, plans, options, waiting, figures).items():
            wanted[(f"chart_{chart}", name)] = text
    _store(wanted)
    return len(wanted)
