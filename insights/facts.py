"""The "what people want" insights: top answers per range, written into `Insight` by the roll-up from the stored daily
rows (journey answers, registrations by plan, suggested plan, referrers). Pages only read the table. Refreshed hourly by
the roll-up (and by rebuild_metrics, which runs the roll-up): recomputing five ranges is too much for a request, so no
event refreshes it. Referrers come from visitors, so they are only as rebuildable as visitors are (not at all)."""
import logging

from django.db import transaction

from . import metrics, reader
from .metrics import K
from .models import Insight

logger = logging.getLogger("spa99.insights")

RANGES = ("today", "7d", "30d", "90d", "all")
MAX_RANK = 6
# (key, title, source, noun for the sentence); source is ("answer", question key), ("plan", metric key) or ("referrer",)
INSIGHTS = (
    ("facility", "Most wanted facility", ("answer", "facilities"), "people"),
    ("time", "Most popular time to visit", ("answer", "time"), "people"),
    ("frequency", "How often they would come", ("answer", "frequency"), "people"),
    ("company", "Who they come with", ("answer", "company"), "people"),
    ("tier_picked", "Most picked tier", ("plan", K.REGISTRATIONS_BY_PLAN), "registrations"),
    ("tier_suggested", "Most suggested tier", ("plan", K.SUGGESTED_PLAN), "journeys"),
    ("source", "Where people come from", ("referrer",), "visits"),
)
TITLES = {key: title for key, title, _, _ in INSIGHTS}
ORDER = [key for key, _, _, _ in INSIGHTS]


def _lookups():
    from journey.models import Option, Question
    from plans.models import Plan

    options = {f"{q}:{v}": label for q, v, label in Option.objects.values_list("question__key", "value", "label")}
    multi = set(Question.objects.filter(type=Question.MULTI).values_list("key", flat=True))
    return dict(Plan.objects.values_list("slug", "name")), options, multi


def _items(source, sums, plans, options):
    """[(label, count)] biggest first for one insight, with real names instead of slugs."""
    kind = source[0]
    if kind == "answer":
        prefix = source[1] + ":"
        return [(options.get(d, d[len(prefix):]), v) for d, v in reader.breakdown(sums, K.JOURNEY_ANSWER) if d.startswith(prefix)]
    if kind == "plan":
        return [(plans.get(d, d), v) for d, v in reader.breakdown(sums, source[1]) if d != "none"]
    return [("Straight to the site" if d == "direct" else d, v) for d, v in reader.breakdown(sums, K.REFERRERS)]


def _sentence(title, items, total, noun):
    (label, value), rest = items[0], items[1:]
    text = f"{label}: {value:,} of {total:,} {noun}."
    return (text + f" Next is {rest[0][0]} with {rest[0][1]:,}.") if rest else text


def wanted(today=None):
    """{(range, key, rank): fields} the stored daily rows imply. Insights with no data are left out."""
    today = today or metrics.day()
    plans, options, multi = _lookups()
    out = {}
    for name in RANGES:
        start, end = reader.range_dates(name, today)
        sums = reader.totals(start, end, (K.JOURNEY_ANSWER, K.REGISTRATIONS_BY_PLAN, K.SUGGESTED_PLAN, K.REFERRERS, K.JOURNEYS_COMPLETED))
        finished = sums.get((K.JOURNEYS_COMPLETED, ""), 0)
        for key, title, source, noun in INSIGHTS:
            items = _items(source, sums, plans, options)
            if not items:
                continue
            # a multiple-choice question is shared out as people (journeys finished), not as answers
            total = max(finished, items[0][1]) if source[0] == "answer" and source[1] in multi else sum(v for _, v in items)
            for rank, (label, value) in enumerate(items[:MAX_RANK], start=1):
                out[(name, key, rank)] = {
                    "title": title, "label": label[:120], "value": value, "of_total": total,
                    "sentence": _sentence(title, items, total, noun)[:300] if rank == 1 else "",
                }
    return out


def write_all(today=None):
    """Make the table equal to `wanted` (idempotent: a second run changes nothing). Returns the number of rows."""
    want = wanted(today)
    with transaction.atomic():
        existing = {(r.range, r.key, r.rank): r for r in Insight.objects.all()}
        for ident in set(existing) - set(want):
            existing[ident].delete()
        fresh = []
        for (name, key, rank), fields in want.items():
            row = existing.get((name, key, rank))
            if row is None:
                fresh.append(Insight(range=name, key=key, rank=rank, **fields))
            elif any(getattr(row, f) != v for f, v in fields.items()):
                for f, v in fields.items():
                    setattr(row, f, v)
                row.save()
        Insight.objects.bulk_create(fresh)
    return len(want)
