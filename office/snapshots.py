"""The background job behind every Office figure (docs/features/office-counting-rules.md, C5). Nothing is summed while a
page loads: this module works out the people, registrations, answers and insights from the source tables and stored
daily rows and saves one `OfficeSnapshot` per page and range (plus the `Insight` rows and the sentences). It runs in the
hourly roll-up (and `rebuild_metrics`) and, debounced, in the background after each counted event.

(insights.metrics and insights.rollup import this module lazily: the job spans both apps.)"""
import json
import logging
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from insights import facts, metrics, people, summaries
from insights.models import OfficeSnapshot, SnapshotRefresh

from . import selectors

logger = logging.getLogger("spa99.snapshots")

STALE_AFTER = timedelta(minutes=2)  # a queued refresh that never ran (queue off) stops blocking new ones after this
TASK = "office.snapshots.refresh"


def payloads(today, figures):
    """{(page, range): payload} for every page and range."""
    out = {}
    for name in selectors.DASHBOARD_RANGES:
        out[(OfficeSnapshot.DASHBOARD, name)] = selectors.build_dashboard(name, today, figures)
    for name in selectors.ANALYTICS_RANGES:
        out[(OfficeSnapshot.ANALYTICS, name)] = selectors.build_analytics(name, today, figures)
        out[(OfficeSnapshot.PAGES, name)] = selectors.build_pages(name, today)
    return out


def write_snapshots(today, figures, built_at):
    """Save the snapshots whose payload changed, but only over an older one: `built_at` (when this job started loading)
    must be newer than the stored row's, so a slow overlapping job never overwrites a newer snapshot. Each save is one
    conditional UPDATE (or a first INSERT), safe on SQLite and Postgres."""
    wanted = {ident: json.loads(json.dumps(payload)) for ident, payload in payloads(today, figures).items()}
    now = timezone.now()
    existing = {(r.page, r.range): r.payload for r in OfficeSnapshot.objects.all()}
    for (page, name), payload in wanted.items():
        if existing.get((page, name)) == payload:
            continue
        rows = OfficeSnapshot.objects.filter(page=page, range=name)
        if rows.filter(built_at__lt=built_at).update(payload=payload, built_at=built_at, updated_at=now) or rows.exists():
            continue  # updated, or a newer snapshot is already there
        try:
            with transaction.atomic():
                OfficeSnapshot.objects.create(page=page, range=name, payload=payload, built_at=built_at)
        except IntegrityError:  # another job inserted it first
            rows.filter(built_at__lt=built_at).update(payload=payload, built_at=built_at, updated_at=now)
    return len(wanted)


def build_everything(today=None):
    """Sentences, insights, then snapshots (which read both), all from one load of the source tables, so every figure
    on a page agrees. Returns the number of sentences written."""
    built_at = timezone.now()  # before the load: anything saved after this is newer than what the load saw
    today = today or metrics.day()
    figures = people.load()
    sentences = summaries.write_all(today, figures)
    facts.write_all(today, figures)
    write_snapshots(today, figures, built_at)
    return sentences


def refresh():
    """The queued job (django-q2). Clears the debounce flag first, so an event during the run queues another."""
    SnapshotRefresh.objects.filter(key="snapshots").update(queued_at=None)
    build_everything()
    return "snapshots refreshed"


def _already_waiting():
    """True when a refresh job is already sitting in the queue (django-q's OrmQ table)."""
    from django_q.models import OrmQ

    return any(row.task.get("func") == TASK for row in OrmQ.objects.all().iterator())


def _queue():
    """Queue one refresh unless one is already waiting. Never raises."""
    from common.tasks import enqueue

    try:
        if _already_waiting():
            return  # a down worker must not pile up jobs
        row, _ = SnapshotRefresh.objects.get_or_create(key="snapshots")
        cutoff = timezone.now() - STALE_AFTER
        won = SnapshotRefresh.objects.filter(pk=row.pk).filter(Q(queued_at__isnull=True) | Q(queued_at__lt=cutoff)).update(queued_at=timezone.now())
        if won:
            enqueue(TASK)
    except Exception:  # noqa: BLE001
        logger.warning("Could not queue the Office snapshot refresh (the hourly roll-up will catch up)", exc_info=True)


def request_refresh():
    """Ask for a refresh after an event: the job is queued once the surrounding transaction commits (a burst of events
    queues one job). Safe to call anywhere; never raises."""
    try:
        if not any(callback is _queue for _, callback, *_ in connection.run_on_commit):  # once per transaction
            transaction.on_commit(_queue)
    except Exception:  # noqa: BLE001
        logger.warning("Office snapshot refresh not requested", exc_info=True)
