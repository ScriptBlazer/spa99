"""The page beacon (docs/features/analytics.md A4 and A6): POST /a/e/ from common/static/common/js/beacon.js.
Time on the page, how far it was scrolled, and taps on contact links. No CSRF token (the beacon has none), a tiny JSON body, the
visitor counter's own rules, a rate limit per visitor, and it always answers 204: odd input is ignored, never stored, never an error.
Body: {"p": "/plans/", "t": 12, "s": 50, "n": 0}  or  {"p": "/", "c": "whatsapp"}
  p  path of the page (must be a real page of the public site; only its first segment is kept)
  t  seconds the page was visible since the last beacon (0 to 1800)
  s  furthest scroll so far: 0, 25, 50, 75 or 100 (first beacon of a page view only)
  n  0 for the first beacon of this page view (counts the view and the scroll), 1 for any later one (adds seconds only)
  h  1 for the "hello" beacon: sent once, about 1.5 seconds after the page is on screen. It carries no figures; it only tells us the
     page script ran, so the visitor counts as a real browser at once (A12)
  c  a contact tap: one of metrics.CONTACT_KINDS (whatsapp, phone, email, instagram, map); anything else is ignored"""
import json
import logging
import math

from django.contrib.auth.decorators import login_not_required
from django.db.models import F
from django.http import HttpResponse
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from common.ratelimit import hit

from . import metrics, visitors
from .metrics import K
from .models import VisitorHash

logger = logging.getLogger("spa99.visitors")

MAX_BODY = 2048
MAX_SECONDS = 30 * 60
SCROLL_BUCKETS = (0, 25, 50, 75, 100)
RATE_LIMIT, RATE_WINDOW = 40, 60  # beacons per visitor per minute
# not pages: webhooks, APIs, files
_SKIP = ("/static/", "/media/", "/health/", "/a/", "/ses/", "/postmark/", "/phone/")


def parse(raw):
    """The cleaned beacon as a dict, or None when it is not one. Strict: anything odd means the whole beacon is ignored."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    path = data.get("p")
    if not isinstance(path, str) or not path.startswith("/") or len(path) > 300 or path.startswith(_SKIP):
        return None
    out = {"group": visitors.path_group(path.split("?", 1)[0])}
    try:
        resolve(path.split("?", 1)[0].split("#", 1)[0], urlconf="config.urls")  # a real page of ours, so junk cannot invent page names
    except Resolver404:
        return None
    if "t" in data:
        seconds = data["t"]
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            return None
        out["seconds"] = min(int(seconds), MAX_SECONDS)
        scroll = data.get("s", 0)
        if isinstance(scroll, bool) or scroll not in SCROLL_BUCKETS:
            return None
        out["scroll"] = int(scroll)
        out["first"] = data.get("n", 0) == 0
    if data.get("h") == 1:
        out["hello"] = True
    if "c" in data:
        kind = data["c"]
        if not isinstance(kind, str) or kind.lower() not in metrics.CONTACT_KINDS:
            return None
        out["contact"] = kind.lower()
    return out if ("seconds" in out or "contact" in out or "hello" in out) else None


def record(request, beacon):
    """Count a parsed beacon against today's row of this visitor. No row today (a bot, a staff host, an earlier day) = ignored."""
    now = timezone.now()
    today = metrics.day(now)
    row = visitors.today_row(request, today)
    if row is None or not hit("beacon", row.hash, RATE_LIMIT, RATE_WINDOW):
        return
    group = beacon["group"]

    def both(key, dimension, amount):  # a beacon only comes from a real browser, so it counts in both
        metrics.count_capped(key, dimension, amount, today)
        metrics.count_capped(visitors.REAL + key, dimension, amount, today)

    visitors.make_human(request, row, group)  # any accepted beacon shows the page script ran (A12); only the first one acts
    if "seconds" in beacon:
        both(K.ENGAGED_SECONDS, group, beacon["seconds"])
        if beacon["first"]:
            both(K.ENGAGED_VIEWS, group, 1)
            both(K.SCROLL, f"{group}:{beacon['scroll']}", 1)
        # the visit goes on while the page is read; a visit already closed stays closed
        VisitorHash.objects.filter(pk=row.pk, visit_started__isnull=False).update(
            last_seen=now, visit_seconds=F("visit_seconds") + beacon["seconds"])
    if "contact" in beacon:
        both(K.CONTACT_TAPS, beacon["contact"], 1)
        both(K.CONTACT_TAPS_PAGE, f"{beacon['contact']}:{group}", 1)
        visitors.credit_step(row, "contact", once=False)


@csrf_exempt
@login_not_required  # PUBLIC: the page script has no session to show
@require_POST
@never_cache
def beacon(request):
    try:
        if visitors.counts_here(request) and int(request.META.get("CONTENT_LENGTH") or 0) <= MAX_BODY:
            parsed = parse(request.read(MAX_BODY + 1)[:MAX_BODY])
            if parsed:
                record(request, parsed)
    except Exception:  # noqa: BLE001 - counting must never show as an error
        logger.warning("Visitor counter skipped a beacon", exc_info=True)
    return HttpResponse(status=204)
