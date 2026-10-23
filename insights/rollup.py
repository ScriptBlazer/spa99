"""The scheduled roll-up (django-q2, hourly; safe to run any number of times).

1. Wipes the visitor dedupe data of finished days (hashes and salts).
2. Writes the derived daily rates (basis points) from the stored daily rows.
3. Writes the weekly (Monday start) and monthly rows by summing the daily rows.
4. Refreshes the all-time visitor and page-view counters.

Everything is recomputed from the daily rows in the window, so a second run changes nothing. The window is the last
`WINDOW_DAYS` days, widened to whole weeks and months; `since=None` recomputes all history (used by rebuild_metrics).
Weekly and monthly "visitors" are sums of daily unique visitors (visitor-days): the daily hashes are wiped, so a person
who returns on two days counts on both."""
import logging
from collections import defaultdict
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum

from . import metrics, summaries, visitors
from .metrics import K, RATE_KEYS
from .models import DailyMetric, MetricCounter, PeriodMetric, VisitorHash, VisitorSalt

logger = logging.getLogger("spa99.metrics")

WINDOW_DAYS = 70


def week_start(d):
    return d - timedelta(days=d.weekday())


def month_start(d):
    return d.replace(day=1)


def basis_points(numerator, denominator):
    """numerator / denominator as integer basis points, rounded half up; None when there is nothing to divide by."""
    if not denominator:
        return None
    return (numerator * 10000 + denominator // 2) // denominator


def rates_for(totals):
    """{rate key: basis points} from one period's totals {(key, dimension): value}."""
    def total(key):
        return totals.get((key, ""), 0)
    rates = {
        K.RATE_JOURNEY_START: basis_points(total(K.JOURNEYS_STARTED), total(K.VISITORS)),
        K.RATE_JOURNEY_FINISH: basis_points(total(K.JOURNEYS_COMPLETED), total(K.JOURNEYS_STARTED)),
        K.RATE_REGISTER: basis_points(total(K.REGISTRATIONS), total(K.VISITORS)),
    }
    return {key: value for key, value in rates.items() if value is not None}


def window_start(today, window_days=WINDOW_DAYS):
    """Whole weeks and whole months: the Monday on or before the first of the month `window_days` ago."""
    return week_start(month_start(today - timedelta(days=window_days)))


def run(today=None, since="window"):
    """Run the roll-up. `since`: "window" (default), a date, or None for all history. Returns a small summary dict."""
    today = today or metrics.day()
    start = window_start(today) if since == "window" else since
    with transaction.atomic():
        wiped = VisitorHash.objects.filter(date__lt=today).delete()[0] + VisitorSalt.objects.filter(date__lt=today).delete()[0]
        daily_rates = _write_daily_rates(start)
        periods = _write_periods(start)
        _refresh_counters()
        sentences = summaries.write_all(today)
    return {"wiped_visitor_rows": wiped, "daily_rates": daily_rates, "period_rows": periods, "sentences": sentences}


def _daily_rows(start, exclude_rates=True):
    rows = DailyMetric.objects.all()
    if start is not None:
        rows = rows.filter(date__gte=start)
    if exclude_rates:
        rows = rows.exclude(key__in=RATE_KEYS)
    return rows.values_list("date", "key", "dimension", "value")


def _write_daily_rates(start):
    per_day = defaultdict(dict)
    for day, key, dimension, value in _daily_rows(start):
        if dimension == "":
            per_day[day][(key, "")] = value
    wanted = {}
    for day, totals in per_day.items():
        for key, bp in rates_for(totals).items():
            wanted[(day, key)] = bp
    existing = DailyMetric.objects.filter(key__in=RATE_KEYS, dimension="")
    if start is not None:
        existing = existing.filter(date__gte=start)
    seen = set()
    for row in existing:
        ident = (row.date, row.key)
        seen.add(ident)
        if ident not in wanted:
            row.delete()
        elif row.value != wanted[ident]:
            row.value = wanted[ident]
            row.save(update_fields=["value"])
    DailyMetric.objects.bulk_create(
        [DailyMetric(date=day, key=key, dimension="", value=bp) for (day, key), bp in wanted.items() if (day, key) not in seen]
    )
    return len(wanted)


def _write_periods(start):
    sums = {PeriodMetric.WEEK: defaultdict(lambda: defaultdict(int)), PeriodMetric.MONTH: defaultdict(lambda: defaultdict(int))}
    for day, key, dimension, value in _daily_rows(start):
        sums[PeriodMetric.WEEK][week_start(day)][(key, dimension)] += value
        sums[PeriodMetric.MONTH][month_start(day)][(key, dimension)] += value
    rows = []
    for period, buckets in sums.items():
        for first, totals in buckets.items():
            if start is not None and first < start:
                continue  # a partial period at the edge of the window: its row is left as it was
            totals = dict(totals)
            totals.update({(key, ""): bp for key, bp in rates_for(totals).items()})
            rows += [PeriodMetric(period=period, start=first, key=key, dimension=dim, value=value) for (key, dim), value in totals.items()]
    old = PeriodMetric.objects.all() if start is None else PeriodMetric.objects.filter(start__gte=start)
    old.delete()
    PeriodMetric.objects.bulk_create(rows)
    return len(rows)


def _refresh_counters():
    """All-time visitor-days and page views: sums of the daily rows, stored so pages never add them up."""
    for key in (K.VISITORS, K.PAGE_VIEWS):
        total = DailyMetric.objects.filter(key=key, dimension="").aggregate(total=Sum("value"))["total"] or 0
        MetricCounter.objects.update_or_create(key=key, dimension="", defaults={"value": total})


def scheduled():
    """The django-q2 entry point (common.management.commands.register_schedules). Returns a plain status string."""
    summary = run()
    visitors.forget_salts()  # yesterday's salt is gone from the database; drop it from this process too
    return f"rollup ok: {summary['daily_rates']} daily rates, {summary['period_rows']} period rows, wiped {summary['wiped_visitor_rows']}"
