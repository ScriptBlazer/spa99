"""Stored daily totals for Office > Activity (docs/features/office-activity.md). The page never counts the source tables: this module does, in the background, and saves
one `ActivityDay` row per (London day, type, staff member). It counts with the same per-source filter the list uses (`activity._by_day`), so the figures always match the rows.

`refresh_recent` runs inside the Office refresh path (the hourly roll-up and the debounced job after an event) and recomputes only today and yesterday. `rebuild_activity` (full
history, `--dry-run` to preview) is run once after deploy and any time an old row was added, changed or erased. Plain ORM, the same on SQLite and Postgres."""
import logging
from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from . import activity
from .models import ActivityDay, ActivityDirtyDay

RECENT_DAYS = 2  # today and the day before


def wanted(first=None, last=None):
    """{(day, group, staff_key): (count, label)} counted from the sources for the London days first..last (inclusive; None = open). One grouped query per source."""
    start = activity._local(first) if first else None
    end = activity._local(last, 1) if last else None
    counts, labels = defaultdict(int), defaultdict(set)
    for group, label, day, n in activity._by_day(activity.NO_FILTER, start, end):
        ident = (day, group, activity.staff_key(label))
        counts[ident] += n
        labels[ident].add(label.strip())
    return {ident: (n, max(labels[ident], key=lambda text: (("(" in text), len(text)))) for ident, n in counts.items()}


def differences(first=None, last=None):
    """(create, update, delete): what must change so the stored rows for first..last equal the sources. create {ident: (n, label)}, update {ident: (n, label)}, delete [pks]."""
    want = wanted(first, last)
    rows = ActivityDay.objects.all()
    if first:
        rows = rows.filter(day__gte=first)
    if last:
        rows = rows.filter(day__lte=last)
    have = {(r.day, r.group, r.staff_key): r for r in rows}
    create = {i: v for i, v in want.items() if i not in have}
    update = {i: v for i, v in want.items() if i in have and (have[i].count, have[i].staff_label) != v}
    delete = [r.pk for i, r in have.items() if i not in want]
    return create, update, delete, have


GUARD_DAYS = 7  # a recount over this many days (or all history) that finds nothing at all while totals are stored is treated as a fault, not as "everything went"


def apply(first=None, last=None, allow_empty=False):
    """Make the stored rows for first..last equal the sources; only rows that differ are written. Returns (created, updated, deleted).
    Safeguards (Moishe 2026-11-11, "never delete unless there is a new one"): the counting runs first and any error stops it before anything is written, the writes are one
    transaction (all or nothing), and a long recount that finds no actions at all while totals are stored deletes nothing and logs a warning instead
    (`rebuild_activity --allow-empty` overrides this, for the one real case: every staff action really was erased)."""
    create, update, delete, have = differences(first, last)
    span_days = None if first is None or last is None else (last - first).days + 1
    if not allow_empty and delete and not create and not update and len(delete) == len(have) and (span_days is None or span_days >= GUARD_DAYS):
        logging.getLogger("spa99.activity").warning("Activity recount found no actions for %s to %s while %s stored rows exist: nothing deleted", first or "the start", last or "today", len(delete))
        delete = []
    with transaction.atomic():
        ActivityDay.objects.bulk_create([ActivityDay(day=d, group=g, staff_key=k, staff_label=label, count=n) for (d, g, k), (n, label) in create.items()], batch_size=500,
                                        ignore_conflicts=True)  # an overlapping job may have inserted it first: both counted the same sources
        for ident, (n, label) in update.items():
            ActivityDay.objects.filter(pk=have[ident].pk).update(count=n, staff_label=label)
        for i in range(0, len(delete), 500):
            ActivityDay.objects.filter(pk__in=delete[i:i + 500]).delete()
    return len(create), len(update), len(delete)


def recent_days(today=None):
    today = today or timezone.localdate()
    return [today - timedelta(days=i) for i in range(RECENT_DAYS)]


SPAN_LIMIT = 31  # more marked days than this are recounted as one span from the first to the last


def refresh_recent(today=None):
    """Recompute today and yesterday (London), then the older days marked by office.signals (a delete, an erased person, a backdated save), each once. Called by the Office refresh;
    cheap whatever the history. Marks made while it ran are kept for the next run."""
    started = timezone.now()
    today = today or timezone.localdate()
    totals = list(apply(today - timedelta(days=RECENT_DAYS - 1), today))
    marked = sorted(ActivityDirtyDay.objects.filter(marked_at__lte=started).values_list("day", flat=True))
    older = [d for d in marked if d not in recent_days(today)]
    spans = [(d, d) for d in older] if len(older) <= SPAN_LIMIT else [(older[0], older[-1])]
    for first, last in spans:
        totals = [a + b for a, b in zip(totals, apply(first, last))]
    if marked:
        ActivityDirtyDay.objects.filter(day__in=marked, marked_at__lte=started).delete()
    return tuple(totals)


def scheduled():
    """Nightly (common.management.commands.register_schedules): a full recount, so a backdated row or an erased person also fixes older days
    (the refresh after each action only recounts today and yesterday). Returns a plain status string."""
    created, updated, deleted = apply()
    return f"activity ok: {created} added, {updated} changed, {deleted} removed"
