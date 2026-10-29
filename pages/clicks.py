"""Counting clicks on the WhatsApp short link. Aggregate only (pages.LinkClickDay): the count per day and source, never an IP,
a browser string or a person. Works the same on SQLite and Postgres: an UPDATE with F() is atomic, and the first click of a
day creates the row (a race on the unique constraint falls back to the UPDATE)."""
import logging
from datetime import timedelta
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.urls import Resolver404, resolve
from django.db.models import F, Sum
from django.utils import timezone

from .links import KEY, SOURCES
from .models import LinkClickDay

logger = logging.getLogger("spa99.pages")
BOT_WORDS = ("bot", "crawler", "spider", "preview", "facebookexternalhit", "whatsapp/", "curl", "python-requests")
BY_SOURCE_MAX = 20
TOP_SOURCES = 3
# A referring page on our own site, by route name, becomes a short key. Anything else (a faked or unknown path) is "other", so the
# table can never grow with made-up sources.
PAGE_KEYS = {"register": "register", "register_sent": "register", "memberships": "membership", "account_membership": "membership", "home": "home",
             "spa": "spa", "tour": "tour", "tour_room": "tour", "gold_card": "gold_card", "visit": "visit"}


def is_bot(user_agent):
    agent = (user_agent or "").strip().lower()
    return not agent or any(word in agent for word in BOT_WORDS)


def source_for(request):
    """A known ?from= key; an unknown one is 'other'. Without ?from=, our own page that sent the person, if its path is a known public
    page (mapped to a short key, PAGE_KEYS); any other path is 'other'; an outside site or no referrer is 'direct'. The Referer can
    be faked, so no free text is ever stored."""
    given = request.GET.get("from")
    if given is not None:
        return given if given in SOURCES else "other"
    referrer = urlparse(request.META.get("HTTP_REFERER", ""))
    if referrer.netloc and referrer.netloc == request.get_host() and referrer.path:
        try:
            name = resolve(referrer.path).url_name
        except Resolver404:
            return "other"
        return PAGE_KEYS.get(name, "other")
    return "direct"


def increment(key, source, day=None):
    day = day or timezone.localdate()
    rows = LinkClickDay.objects.filter(key=key, day=day, source=source)
    if rows.update(count=F("count") + 1):
        return
    try:
        with transaction.atomic():
            LinkClickDay.objects.create(key=key, day=day, source=source, count=1)
    except IntegrityError:  # another request made the row first
        rows.update(count=F("count") + 1)


def record(request, key=KEY):
    """Count one click unless it is a bot. Never raises: a counting problem must not stop the redirect."""
    if request.method != "GET" or is_bot(request.META.get("HTTP_USER_AGENT", "")):
        return False
    try:
        increment(key, source_for(request))
    except Exception:  # noqa: BLE001
        logger.exception("Could not count a click on %s", key)
        return False
    return True


def summary(key=KEY, today=None):
    """Stored figures for System: totals (today, 7 days, 30 days, all time), the last 30 days by day (newest first) and as trend bars (oldest
    first), and by source (all time, top 20; the top 3 as pill labels)."""
    today = today or timezone.localdate()
    rows = LinkClickDay.objects.filter(key=key)

    def total(start=None):
        return (rows.filter(day__gte=start) if start else rows).aggregate(n=Sum("count"))["n"] or 0

    first = today - timedelta(days=29)
    per_day = dict(rows.filter(day__gte=first).values_list("day").annotate(n=Sum("count")))
    by_day = [{"day": today - timedelta(days=i), "count": per_day.get(today - timedelta(days=i), 0)} for i in range(30)]
    by_source = [{"source": s, "count": n} for s, n in rows.values_list("source").annotate(n=Sum("count")).order_by("-n", "source")[:BY_SOURCE_MAX]]
    peak = max((d["count"] for d in by_day), default=0)
    # Oldest first, for the small trend on the Dashboard: pct is each day's height against the busiest day (a day with clicks never shows as empty).
    bars = [{"day": d["day"], "count": d["count"], "pct": max(8, round(d["count"] * 100 / peak)) if d["count"] else 0} for d in reversed(by_day)]
    top_sources = [{"label": r["source"].replace("_", " ").capitalize(), "count": r["count"]} for r in by_source[:TOP_SOURCES]]
    return {"today": total(today), "week": total(today - timedelta(days=6)), "month": total(first), "all": total(),
            "by_day": by_day, "by_source": by_source, "bars": bars, "top_sources": top_sources}
