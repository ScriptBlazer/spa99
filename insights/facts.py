"""The "what people want" insights: top answers per range, written into `Insight` by the roll-up from the stored daily
rows (journey answers, registrations by plan, suggested plan, referrers). Pages only read the table. Refreshed hourly by
the roll-up (and by rebuild_metrics, which runs the roll-up): recomputing five ranges is too much for a request, so no
event refreshes it. Referrers come from visitors, so they are only as rebuildable as visitors are (not at all)."""
import logging
import re

from django.db import transaction
from django.utils import timezone

from . import metrics, people, reader
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
    ("tier_suggested", "Most suggested tier", ("plan", K.SUGGESTED_PLAN), "people"),
    ("source", "Where people come from", ("referrer",), "visits"),
)
TITLES = {key: title for key, title, _, _ in INSIGHTS}
ORDER = [key for key, _, _, _ in INSIGHTS]


_HINT = re.compile(r"\s*\([^()]*\.\)\s*$")


def clean_label(label):
    """An option's name without its hint: 'Often with someone (Most visits.)' is 'Often with someone'. A parenthesis that is part of the
    name ('Early morning (5 to 9am)') has no full stop inside, so it stays."""
    return _HINT.sub("", label or "").strip()


def _lookups():
    from journey.models import Option, Question
    from plans.models import Plan

    options = {f"{q}:{v}": clean_label(label) for q, v, label in Option.objects.values_list("question__key", "value", "label")}
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


def wanted(today=None, figures=None):
    """{(range, key, rank): fields} per the counting rules (office-counting-rules.md): answers and the suggested tier are one
    vote per person (latest finished journey in the range), the picked tier is registrations in the range. Insights with no
    data are left out."""
    today = today or metrics.day()
    figures = figures or people.load()
    plans, options, _ = _lookups()
    out = {}
    for name in RANGES:
        start, end = reader.range_dates(name, today)
        sums = figures.overlay(reader.totals(start, end, (K.REFERRERS,)), start, end)
        voters = sums[(people.VOTERS, "")]
        for key, title, source, noun in INSIGHTS:
            items = _items(source, sums, plans, options)
            if not items:
                continue
            if source[0] == "answer":
                total = max(voters, items[0][1])  # of the people who finished a journey in the range
            elif key == "tier_picked":  # of all registrations in the range, including the few without a tier
                total = max(sums[(K.REGISTRATIONS, "")], sum(v for _, v in items))
            else:
                total = sum(v for _, v in items)
            for rank, (label, value) in enumerate(items[:MAX_RANK], start=1):
                out[(name, key, rank)] = {
                    "title": title, "label": label[:120], "value": value, "of_total": total,
                    "sentence": _sentence(title, items, total, noun)[:300] if rank == 1 else "",
                }
    return out


def write_all(today=None, figures=None):
    """Make the table equal to `wanted` (idempotent: a second run changes nothing, and only changed rows are written).
    Overlapping runs are safe on SQLite and Postgres: rows are upserted on the unique key, never delete-then-insert.
    Returns the number of rows."""
    want = wanted(today, figures)
    now = timezone.now()
    with transaction.atomic():
        existing = {(r.range, r.key, r.rank): r for r in Insight.objects.all()}
        stale = [existing[i].pk for i in set(existing) - set(want)]
        if stale:
            Insight.objects.filter(pk__in=stale).delete()
        changed = []
        for (name, key, rank), fields in want.items():
            row = existing.get((name, key, rank))
            if row is None or any(getattr(row, f) != v for f, v in fields.items()):
                changed.append(Insight(range=name, key=key, rank=rank, updated_at=now, **fields))
        Insight.objects.bulk_create(
            changed, update_conflicts=True, unique_fields=["range", "key", "rank"],
            update_fields=["title", "label", "value", "of_total", "sentence", "updated_at"],
        )
    return len(want)
