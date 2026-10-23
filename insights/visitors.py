"""Cookieless visitor counter (docs/features/office.md, "Visitors"). No cookie, no stored IP or user agent, no full
referrer: a page view adds to the day's page-view rows, and a visitor counts once a day through an anonymous hash of
(the day's random salt, IP, user agent). The salt row and the day's hashes are deleted by the roll-up, so yesterday's
hashes cannot be recomputed or linked to anyone."""
import hashlib
import logging
import re
import secrets
from urllib.parse import urlparse

from django.db import IntegrityError, transaction

from common.audit import client_ip
from common.useragent import device_type

from . import metrics
from .metrics import K
from .models import VisitorHash, VisitorSalt

logger = logging.getLogger("spa99.visitors")

_salts = {}  # {date: salt}, this process only (a miss reads the database; a race resolves to one row)
_GROUP = re.compile(r"[^a-z0-9_-]")


def todays_salt(today):
    salt = _salts.get(today)
    if salt is not None:
        return salt
    row = VisitorSalt.objects.filter(date=today).first()
    if row is None:
        try:
            with transaction.atomic():
                row = VisitorSalt.objects.create(date=today, salt=secrets.token_hex(32))
        except IntegrityError:  # another worker made it first
            row = VisitorSalt.objects.get(date=today)
    _salts.clear()  # only today's salt is ever held in memory
    _salts[today] = row.salt
    return row.salt


def forget_salts():
    _salts.clear()


def visitor_hash(salt, ip, user_agent):
    return hashlib.sha256(f"{salt}|{ip}|{user_agent}".encode()).hexdigest()


def path_group(path):
    """First path segment, e.g. /plans/tier-2/ -> 'plans'; the home page is 'home'. Letters, digits, - and _ only."""
    first = path.strip("/").split("/", 1)[0].lower()
    return _GROUP.sub("", first)[:40] or "home"


def referrer_source(request):
    """Where the visit came from, as a site name only ('l.instagram.com'), never the path or query: 'direct' when
    there is no referrer, None when it is our own site (moving between our pages is not a source)."""
    raw = request.META.get("HTTP_REFERER", "")
    host = (urlparse(raw).hostname or "").lower() if raw else ""
    if not host:
        return "direct"
    host = host[4:] if host.startswith("www.") else host
    own = request.get_host().split(":")[0].lower()
    own = own[4:] if own.startswith("www.") else own
    return None if host == own else host[:100]


def should_count(request, response):
    """A real person's page view of the public site: GET, a 200 HTML page, not a bot, not a staff host (the staff hosts
    have their own urlconf), not static/media."""
    if request.method != "GET" or response.status_code != 200:
        return False
    if not response.get("Content-Type", "").startswith("text/html"):
        return False
    if getattr(request, "urlconf", "config.urls") != "config.urls":
        return False
    if request.path.startswith(("/static/", "/media/", "/health/")):
        return False
    if request.META.get("HTTP_SEC_PURPOSE", "").startswith("prefetch") or request.META.get("HTTP_PURPOSE") == "prefetch":
        return False
    agent = request.META.get("HTTP_USER_AGENT", "")
    return device_type(agent) not in ("bot", "unknown")


def _refresh_sentences(today):
    """Keep the stored visitor sentences close behind the figures: for each of the day's first visitors, then every 25th."""
    from common.tasks import enqueue

    from .models import DailyMetric

    count = DailyMetric.objects.filter(date=today, key=K.VISITORS, dimension="").values_list("value", flat=True).first() or 0
    if count <= 5 or count % 25 == 0:
        enqueue("insights.summaries.write_visitor_sentences")  # a background job: never in the page request


def record_page_view(request):
    """Count one page view (and the visitor, once a day). Never raises."""
    today = metrics.day()
    group = path_group(request.path)
    salt = todays_salt(today)
    digest = visitor_hash(salt, client_ip(request) or "", request.META.get("HTTP_USER_AGENT", ""))
    new_visitor = True
    try:
        with transaction.atomic():
            VisitorHash.objects.create(date=today, hash=digest)
    except IntegrityError:
        new_visitor = False
    metrics.count(K.PAGE_VIEWS, "", 1, today, counter=False)
    metrics.count(K.PAGE_VIEWS, group, 1, today, counter=False)
    if new_visitor:
        metrics.count(K.VISITORS, "", 1, today, counter=False)
        _refresh_sentences(today)
    source = referrer_source(request)
    if source:
        metrics.count(K.REFERRERS, source, 1, today, counter=False)
