"""Cookieless visitor counter (docs/features/office.md, "Visitors"). No cookie, no stored IP or user agent, no full
referrer: a page view adds to the day's page-view rows, and a visitor counts once a day through an anonymous hash of
(the day's random salt, IP, user agent). The salt row and the day's hashes are deleted by the roll-up, so yesterday's
hashes cannot be recomputed or linked to anyone."""
import hashlib
import logging
import re
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from common import geoip
from common.audit import client_ip
from common.useragent import browser_family, device_type, os_family

from . import campaigns, metrics
from .metrics import K
from .models import VisitorHash, VisitorSalt

logger = logging.getLogger("spa99.visitors")

_salts = {}  # {date: salt}, this process only (a miss reads the database; a race resolves to one row)
_GROUP = re.compile(r"[^a-z0-9_-]")

VISIT_GAP = timedelta(minutes=30)  # a visit ends after this long without a page view (A3)
LENGTH_BUCKETS = (("0-10s", 10), ("10-30s", 30), ("30s-1m", 60), ("1-3m", 180), ("3-10m", 600), ("10m+", None))
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
REAL = "real:"  # the real-visitors twin of a daily key: "real:visitors" (A12). Same dimensions, written only for human visitors.
STEPS = ("started", "finished", "registered", "gold", "contact")  # what a visit's campaign and channel are credited with (A5)


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


def length_bucket(seconds):
    for name, upper in LENGTH_BUCKETS:
        if upper is None or seconds < upper:
            return name


def _add(human, key, dimension, amount, day):
    """One figure for the day: always under `key` (all visitors) and, for a human visitor, under REAL + key too (A12)."""
    for name in ((key, REAL + key) if human else (key,)):
        if dimension == "":
            metrics.count(name, "", amount, day, counter=False)
        else:
            metrics.count_capped(name, dimension, amount, day)


def _refresh_sentences(today):
    """Keep the stored snapshots close behind the figures: for each of the day's first visitors, then every 25th."""
    from office import snapshots

    from .models import DailyMetric

    count = DailyMetric.objects.filter(date=today, key=K.VISITORS, dimension="").values_list("value", flat=True).first() or 0
    if count <= 5 or count % 25 == 0:
        snapshots.request_refresh()  # a debounced background job: never in the page request


def _digest(request, today):
    return visitor_hash(todays_salt(today), client_ip(request) or "", request.META.get("HTTP_USER_AGENT", ""))


def today_row(request, today=None):
    """Today's VisitorHash row for this request's visitor, or None."""
    today = today or metrics.day()
    return VisitorHash.objects.filter(date=today, hash=_digest(request, today)).first()


def _visit_fields(request, group, now):
    """What a new visit starts with: channel, source and campaign from the first page's address and referrer (A5)."""
    utm = campaigns.utm_from_query(request.GET)
    referrer = referrer_source(request) or "direct"
    channel, source = campaigns.channel_for(utm, referrer, browser_family(request.META.get("HTTP_USER_AGENT", "")))
    return {"visit_started": now, "last_seen": now, "visit_pages": 1, "visit_seconds": 0, "entry_group": group, "current_group": group,
            "channel": channel, "source": source[:100], "campaign": campaigns.campaign_key(utm), "steps": ""}


def _count_new_visit(fields, now, today, human=False):
    local = timezone.localtime(now)
    _add(human, K.VISITS, "", 1, today)
    _add(human, K.BOUNCES, "", 1, today)  # taken back by the visit's second page view
    _add(human, K.VISIT_PAGES, "", 1, today)
    _add(human, K.ENTRY_PAGES, fields["entry_group"], 1, today)
    _add(human, K.VISITS_BY_CHANNEL, fields["channel"], 1, today)
    _add(human, K.VISIT_SOURCES, fields["source"], 1, today)
    if fields["campaign"]:
        _add(human, K.CAMPAIGN_VISITS, fields["campaign"], 1, today)
    _add(human, K.VISIT_HOUR, f"{WEEKDAYS[local.weekday()]}:{local.hour:02d}", 1, today)


def _create_row(request, today, digest, now, visit):
    """Make today's row for a new visitor and count him (once a day): visitor, device, browser, system, country.
    Returns the row, or None when another request made it first."""
    agent = request.META.get("HTTP_USER_AGENT", "")
    device = device_type(agent)
    country = geoip.country_code(client_ip(request))
    try:
        with transaction.atomic():
            row = VisitorHash.objects.create(date=today, hash=digest, country=country, device=device, **visit)
    except IntegrityError:
        return None
    metrics.count(K.VISITORS, "", 1, today, counter=False)
    metrics.count_capped(K.DEVICES, device, 1, today)
    metrics.count_capped(K.BROWSERS, browser_family(agent), 1, today)
    metrics.count_capped(K.SYSTEMS, os_family(agent), 1, today)
    metrics.count_capped(K.COUNTRIES, country, 1, today)
    if visit:
        _count_new_visit(visit, now, today)
    _refresh_sentences(today)
    return row


def close_visit(row):
    """End the visit `row` holds: the exit page, the length bucket and the seconds are written once. Many callers may race
    (the next hit, the roll-up); the one that clears `visit_started` wins and the rest do nothing. Returns True for the winner."""
    if row.visit_started is None:
        return False
    if not VisitorHash.objects.filter(pk=row.pk, visit_started=row.visit_started).update(visit_started=None):
        return False
    span = max(int((row.last_seen - row.visit_started).total_seconds()), 0) if row.last_seen else 0
    length = max(span, row.visit_seconds)  # the beacon's visible seconds can exceed the span of a one-page visit
    _add(row.human, K.EXIT_PAGES, row.current_group, 1, row.date)
    _add(row.human, K.VISIT_LENGTH, length_bucket(length), 1, row.date)
    _add(row.human, K.VISIT_SECONDS, "", length, row.date)
    return True


def close_idle(today=None, now=None):
    """The roll-up's part: close visits idle for 30 minutes and every visit of an earlier day (midnight closes them all, booked to
    their own day). Run before the finished days' rows are wiped. Returns how many it closed."""
    now = now or timezone.now()
    today = today or metrics.day(now)
    rows = VisitorHash.objects.filter(visit_started__isnull=False).filter(Q(date__lt=today) | Q(last_seen__lt=now - VISIT_GAP))
    return sum(1 for row in list(rows) if close_visit(row))


def record_page_view(request):
    """Count one page view, the visitor (once a day) and the visit (A3). Never raises."""
    now = timezone.now()
    today = metrics.day(now)
    group = path_group(request.path)
    agent = request.META.get("HTTP_USER_AGENT", "")
    digest = _digest(request, today)
    row = VisitorHash.objects.filter(date=today, hash=digest).first()
    if row is None and _create_row(request, today, digest, now, _visit_fields(request, group, now)) is None:
        row = VisitorHash.objects.filter(date=today, hash=digest).first()  # lost a race: he is already here
    human = False
    if row is not None:
        human = row.human
        _continue_visit(row, request, group, now, today)
    _add(human, K.PAGE_VIEWS, "", 1, today)
    _add(human, K.PAGE_VIEWS, group, 1, today)
    _add(human, K.VIEWS_BY_DEVICE, device_type(agent), 1, today)
    _add(human, K.VIEWS_BY_BROWSER, browser_family(agent), 1, today)
    _add(human, K.VIEWS_BY_SYSTEM, os_family(agent), 1, today)
    source = referrer_source(request)
    if source:
        _add(human, K.REFERRERS, source, 1, today)


def _continue_visit(row, request, group, now, today):
    """A returning visitor's page view: the visit goes on (a second page takes the bounce back), or, after a gap of 30 minutes or
    with no visit open, a new one starts. Every claim is one conditional UPDATE, so racing requests count each thing once."""
    open_visit = row.visit_started is not None and row.last_seen is not None and now - row.last_seen < VISIT_GAP
    if not open_visit:
        close_visit(row)
        fields = _visit_fields(request, group, now)
        if VisitorHash.objects.filter(pk=row.pk, visit_started__isnull=True).update(**fields):
            _count_new_visit(fields, now, today, row.human)
            return
    _add(row.human, K.VISIT_PAGES, "", 1, today)
    rows = VisitorHash.objects.filter(pk=row.pk)
    if rows.filter(visit_pages=1, visit_started__isnull=False).update(visit_pages=2, last_seen=now, current_group=group):
        _add(row.human, K.BOUNCES, "", -1, today)
    else:
        rows.update(visit_pages=F("visit_pages") + 1, last_seen=now, current_group=group)


def credit_step(row, step, once=True):
    """Add one step (A5) to the visit's channel and campaign. `once`: a step counts once per visit (a contact tap counts every time)."""
    if row is None or not row.channel:
        return
    if once:
        if f",{step}," in row.steps:
            return
        if not VisitorHash.objects.filter(pk=row.pk, steps=row.steps).update(steps=(row.steps or ",") + step + ","):
            return  # another request is crediting it right now
    _add(row.human, K.CHANNEL_STEPS, f"{row.channel}:{step}", 1, row.date)
    if row.campaign:
        _add(row.human, K.CAMPAIGN_STEPS, f"{row.campaign}:{step}", 1, row.date)


def make_human(request, row, group):
    """The first accepted beacon of the day for this visitor (A12): our page script ran, so he is a real browser. One conditional
    UPDATE claims it, so racing beacons count it once. What he already contributed today is added to the real figures once, from
    what the row holds: the visitor and his device, browser, system and country; the visit now open (its entry page, channel,
    source, campaign, hour, pages so far, and the steps already credited); and the page view of the beacon's page. Earlier closed
    visits of the day and earlier page views are not added (an approximation). Returns True when this call made him human."""
    if not VisitorHash.objects.filter(pk=row.pk, human=False).update(human=True):
        row.human = True  # already human (or another beacon just made him): the caller's row object must say so
        return False
    row.refresh_from_db()  # what the visit holds right now
    day = row.date
    agent = request.META.get("HTTP_USER_AGENT", "")

    def real(key, dimension, amount=1):
        _add_real(key, dimension, amount, day)

    real(K.VISITORS, "")
    real(K.DEVICES, row.device)
    real(K.BROWSERS, browser_family(agent))
    real(K.SYSTEMS, os_family(agent))
    real(K.COUNTRIES, row.country)
    if row.visit_started is not None:
        local = timezone.localtime(row.visit_started)
        real(K.VISITS, "")
        if row.visit_pages <= 1:
            real(K.BOUNCES, "")
        real(K.VISIT_PAGES, "", max(row.visit_pages, 1))
        real(K.ENTRY_PAGES, row.entry_group)
        real(K.VISITS_BY_CHANNEL, row.channel)
        real(K.VISIT_SOURCES, row.source)
        if row.campaign:
            real(K.CAMPAIGN_VISITS, row.campaign)
        real(K.VISIT_HOUR, f"{WEEKDAYS[local.weekday()]}:{local.hour:02d}")
        for step in (part for part in row.steps.split(",") if part):
            real(K.CHANNEL_STEPS, f"{row.channel}:{step}")
            if row.campaign:
                real(K.CAMPAIGN_STEPS, f"{row.campaign}:{step}")
    real(K.PAGE_VIEWS, "")
    real(K.PAGE_VIEWS, group)
    real(K.VIEWS_BY_DEVICE, device_type(agent))
    real(K.VIEWS_BY_BROWSER, browser_family(agent))
    real(K.VIEWS_BY_SYSTEM, os_family(agent))
    return True


def _add_real(key, dimension, amount, day):
    if dimension == "":
        metrics.count(REAL + key, "", amount, day, counter=False)
    else:
        metrics.count_capped(REAL + key, dimension, amount, day)


def record_step(request, step):
    """The visitor started or finished the journey, registered, or applied for Gold: credited to today's visit, same day only.
    Never raises: counting must not break the step."""
    try:
        if counts_here(request):
            credit_step(today_row(request), step)
    except Exception:  # noqa: BLE001
        logger.warning("Visitor counter skipped the step %s", step, exc_info=True)


def counts_here(request):
    """The step counters follow the visitor counter's rules: counter on, public host, not a bot, not a prefetch."""
    from django.conf import settings

    if not getattr(settings, "VISITOR_COUNTER", True):
        return False
    if getattr(request, "urlconf", "config.urls") != "config.urls":
        return False
    if request.META.get("HTTP_SEC_PURPOSE", "").startswith("prefetch") or request.META.get("HTTP_PURPOSE") == "prefetch":
        return False
    return device_type(request.META.get("HTTP_USER_AGENT", "")) not in ("bot", "unknown")


def record_journey_start(request):
    """A journey start also counts as a visitor that day (the same anonymous daily hash, nothing else stored), so the
    funnel's first step is never below its second, and the visit's campaign gets its 'started' step. The people figures themselves
    come from the journey tables in the background job. Never raises: counting must not break the journey."""
    try:
        if not counts_here(request):
            return
        now = timezone.now()
        today = metrics.day(now)
        digest = _digest(request, today)
        row = VisitorHash.objects.filter(date=today, hash=digest).first()
        if row is None:
            _create_row(request, today, digest, now, {})  # a visitor with no page view yet: no visit, so no channel to credit
        else:
            credit_step(row, "started")
    except Exception:  # noqa: BLE001
        logger.warning("Visitor counter skipped a journey start", exc_info=True)
