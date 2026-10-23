"""Read side helpers over the stored rows: ranges and sums of stored daily rows. Used by the roll-up (to write the
summary sentences) and by the Office views. Never touches the source tables."""
from datetime import timedelta

from django.db.models import Sum

from . import metrics
from .models import DailyMetric

RANGE_DAYS = {"today": 1, "7d": 7, "30d": 30, "90d": 90, "all": None}


def range_dates(name, today=None):
    """(start, end) London days, both inclusive; start is None for 'all'."""
    today = today or metrics.day()
    days = RANGE_DAYS[name]
    return (None if days is None else today - timedelta(days=days - 1)), today


def previous_dates(name, today=None):
    """The window of the same length just before `range_dates`, or None for 'all'."""
    start, _ = range_dates(name, today)
    if start is None:
        return None
    days = RANGE_DAYS[name]
    return start - timedelta(days=days), start - timedelta(days=1)


def totals(start, end, keys=None):
    """{(key, dimension): sum of the stored daily rows} for the days start..end (start None = from the beginning)."""
    rows = DailyMetric.objects.filter(date__lte=end)
    if start is not None:
        rows = rows.filter(date__gte=start)
    if keys is not None:
        rows = rows.filter(key__in=keys)
    return {(r["key"], r["dimension"]): r["total"] for r in rows.values("key", "dimension").annotate(total=Sum("value"))}


def breakdown(sums, key):
    """[(dimension, value)] for a key from `totals`, biggest first (ties by name), zero rows dropped."""
    items = [(dim, value) for (k, dim), value in sums.items() if k == key and dim != "" and value > 0]
    return sorted(items, key=lambda item: (-item[1], item[0]))
