"""Stored daily totals for Office > Activity (docs/features/office-activity.md). The page never counts the source tables: this module does, in the background, and saves
one `ActivityDay` row per (London day, type, staff member) and one `ActivityTimeOfDay` row per (London day, part of the day, type, staff member), by the same paths. It counts with the same per-source filter the list uses (`activity._by_day`), so the figures always match the rows.

`refresh_recent` runs inside the Office refresh path (the hourly roll-up and the debounced job after an event) and recomputes only today and yesterday. `rebuild_activity` (full
history, `--dry-run` to preview) is run once after deploy and any time an old row was added, changed or erased. Plain ORM, the same on SQLite and Postgres."""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.db import transaction
from django.utils import timezone

from . import activity
from .models import ActivityDay, ActivityDirtyDay, ActivityTimeOfDay

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


def wanted_time(first=None, last=None):
    """{(day, part, group, staff_key): (count, label)} counted from the sources for the London days first..last (inclusive; None = open): the same filter as `wanted`, split by part of
    the London day (activity.PARTS). One grouped query per source. The label is only for the rebuild report; it is not stored."""
    start = activity._local(first) if first else None
    end = activity._local(last, 1) if last else None
    counts, labels = defaultdict(int), defaultdict(set)
    for group, label, day, hour, n in activity._by_day_hour(activity.NO_FILTER, start, end):
        ident = (day, activity.part_of_hour(hour), group, activity.staff_key(label))
        counts[ident] += n
        labels[ident].add(label.strip())
    return {ident: (n, max(labels[ident], key=lambda text: (("(" in text), len(text)))) for ident, n in counts.items()}


@dataclass(frozen=True)
class Table:
    """What differs between the two stored tables: the model, the fields that make a row unique, the value a row holds (to compare) and the fields a change writes."""
    model: type
    fields: tuple
    value: Callable      # stored row -> the value it holds
    counted: Callable    # counted (count, label) -> the value to compare with the stored one
    change: Callable     # counted (count, label) -> {field: value} written on create and update


DAY = Table(ActivityDay, ("day", "group", "staff_key"), lambda r: (r.count, r.staff_label), lambda v: v, lambda v: {"count": v[0], "staff_label": v[1]})
TIME = Table(ActivityTimeOfDay, ("day", "part", "group", "staff_key"), lambda r: r.count, lambda v: v[0], lambda v: {"count": v[0]})  # the label is only for the rebuild report


def _differences(table, want, first, last):
    rows = table.model.objects.all()
    if first:
        rows = rows.filter(day__gte=first)
    if last:
        rows = rows.filter(day__lte=last)
    have = {tuple(getattr(r, f) for f in table.fields): r for r in rows}
    create = {i: v for i, v in want.items() if i not in have}
    update = {i: v for i, v in want.items() if i in have and table.value(have[i]) != table.counted(v)}
    delete = [r.pk for i, r in have.items() if i not in want]
    return create, update, delete, have


def differences(first=None, last=None):
    """(create, update, delete, have): what must change so the stored rows for first..last equal the sources. create {ident: (n, label)}, update {ident: (n, label)}, delete [pks]."""
    return _differences(DAY, wanted(first, last), first, last)


def differences_time(first=None, last=None):
    """The same for the time-of-day rows: idents are (day, part, group, staff_key); only the count is stored and compared (the label is for the report)."""
    return _differences(TIME, wanted_time(first, last), first, last)


GUARD_DAYS = 7  # a recount over this many days (or all history) that finds nothing at all while totals are stored is treated as a fault, not as "everything went"


def guarded(plan, first=None, last=None, allow_empty=False):
    """True when the recount found no actions at all while rows are stored, over a long span: it must delete nothing."""
    create, update, delete, have = plan
    span_days = None if first is None or last is None else (last - first).days + 1
    return bool(not allow_empty and delete and not create and not update and len(delete) == len(have) and (span_days is None or span_days >= GUARD_DAYS))


def _write(table, plan):
    create, update, delete, have = plan
    objs = [table.model(**dict(zip(table.fields, ident)), **table.change(v)) for ident, v in create.items()]
    table.model.objects.bulk_create(objs, batch_size=500, ignore_conflicts=True)  # an overlapping job may have inserted it first: both counted the same sources
    for ident, v in update.items():
        table.model.objects.filter(pk=have[ident].pk).update(**table.change(v))
    for i in range(0, len(delete), 500):
        table.model.objects.filter(pk__in=delete[i:i + 500]).delete()


def apply_both(first=None, last=None, allow_empty=False):
    """Make the stored rows for first..last equal the sources, in both tables (ActivityDay and ActivityTimeOfDay); only rows that differ are written. Returns
    ((created, updated, deleted) for the days, the same for the time of day).
    Safeguards (Moishe 2026-11-11, "never delete unless there is a new one"): all the counting runs first and any error stops it before anything is written, the writes are one
    transaction (all or nothing), and a long recount that finds no actions at all while totals are stored deletes nothing and logs a warning instead, in each table
    (`rebuild_activity --allow-empty` overrides this, for the one real case: every staff action really was erased)."""
    plans = [(DAY, differences(first, last)), (TIME, differences_time(first, last))]
    out = []
    for table, plan in plans:
        create, update, delete, have = plan
        if guarded(plan, first, last, allow_empty):
            logging.getLogger("spa99.activity").warning("Activity recount found no actions for %s to %s while %s stored rows exist in %s: nothing deleted", first or "the start", last or "today",
                                                        len(delete), table.model._meta.db_table)
            plan = (create, update, [], have)
        out.append((table, plan))
    with transaction.atomic():
        for table, plan in out:
            _write(table, plan)
    return tuple((len(plan[0]), len(plan[1]), len(plan[2])) for _table, plan in out)


def apply(first=None, last=None, allow_empty=False):
    """apply_both, returning the day totals' (created, updated, deleted) only (what callers have always had)."""
    return apply_both(first, last, allow_empty)[0]


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
    (created, updated, deleted), (t_created, t_updated, t_deleted) = apply_both()
    return f"activity ok: {created} added, {updated} changed, {deleted} removed; by time: {t_created} added, {t_updated} changed, {t_deleted} removed"
