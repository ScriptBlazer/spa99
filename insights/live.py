"""Live now (docs/features/analytics.md A8): who is on the public site in the last 5 minutes. The one Office figure that reads
today's visit rows (a single indexed query, no personal data returned: counts only, never a list of people)."""
from datetime import timedelta

from django.utils import timezone

from . import metrics
from .models import VisitorHash

WINDOW = timedelta(minutes=5)
TOP = 5


def _ranked(values):
    counts = {}
    for value in values:
        counts[value or "unknown"] = counts.get(value or "unknown", 0) + 1
    return [{"label": label, "value": n} for label, n in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:TOP]]


def live_now(now=None):
    """{count, window_minutes, as_of, by_page, by_country, by_device, by_channel}; each list is [{label, value}], biggest first."""
    now = now or timezone.now()
    rows = list(VisitorHash.objects.filter(date=metrics.day(now), last_seen__gte=now - WINDOW).values_list("current_group", "country", "device", "channel"))
    return {
        "count": len(rows), "window_minutes": int(WINDOW.total_seconds() // 60), "as_of": now.isoformat(),
        "by_page": _ranked(r[0] for r in rows), "by_country": _ranked(r[1] for r in rows),
        "by_device": _ranked(r[2] for r in rows), "by_channel": _ranked(r[3] for r in rows),
    }
