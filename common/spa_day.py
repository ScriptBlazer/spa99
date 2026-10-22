"""The one place that knows what a "spa day" is (CAL-01..05).

A spa day starts at 5am and ends at 3am the next morning.
    00:00-02:59 belongs to the previous spa day.
    03:00-04:59 (closed) belongs to the spa day about to open.
Everything is worked out in Europe/London local time, so clock changes are handled by the timezone data.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def _local(moment):
    if timezone.is_naive(moment):
        raise ValueError("spa_day_for needs a timezone-aware datetime")
    return moment.astimezone(ZoneInfo(settings.TIME_ZONE))


def spa_day_for(moment, day_end=None):
    """The spa date (a `date`) that `moment` belongs to."""
    day_end = day_end or settings.SPA_DAY_END
    local = _local(moment)
    return local.date() - timedelta(days=1) if local.time() < day_end else local.date()


def current_spa_day():
    return spa_day_for(timezone.now())


def spa_day_bounds(spa_date, day_start=None, day_end=None):
    """(opens, closes) as aware datetimes for a spa date: start that morning, end next morning."""
    day_start = day_start or settings.SPA_DAY_START
    day_end = day_end or settings.SPA_DAY_END
    zone = ZoneInfo(settings.TIME_ZONE)
    opens = datetime.combine(spa_date, day_start, tzinfo=zone)
    closes = datetime.combine(spa_date + timedelta(days=1), day_end, tzinfo=zone)
    return opens, closes
