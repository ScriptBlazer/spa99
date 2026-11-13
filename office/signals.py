"""Every row added, changed or deleted in an Activity source asks for the Office refresh (office.snapshots.request_refresh: debounced, queued after the transaction commits, never raises),
so the Activity dashboard is at most moments behind. One place instead of a call in every service: notes, edits, archive and genuine marks, approach list adds and done, emails, membership
decisions, Gold staff actions and manual membership events all come through here, whichever code wrote them. Automatic actions (no staff label) do not ask.

The refresh recounts today and yesterday. A change to an older day (a delete or cascade, an erased person, a backdated save, a time moved) also marks that London day: the days of a
transaction are collected in memory and written once when it commits (`ActivityDirtyDay`, one row per day), and the next refresh recounts them. Nothing is counted in the request."""
import logging
import threading

from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone

from gold.models import ApplicationEvent
from outreach.models import LeadArchiveEvent, NoteEvent, OutreachEntry, PersonEdit, PersonMessage, StickyNote
from system.models import SystemEvent

from .models import MembershipReviewEvent

# model -> [(time field, staff label field)]: what each source counts (office.activity.SOURCES)
FIELDS = {StickyNote: [("created_at", "author_label")], NoteEvent: [("at", "by_label")], PersonEdit: [("at", "by_label")], LeadArchiveEvent: [("at", "by_label")],
          OutreachEntry: [("added_at", "added_by_label"), ("done_at", "done_by_label")], PersonMessage: [("sent_at", "author_label")], MembershipReviewEvent: [("at", "by_label")],
          ApplicationEvent: [("at", "actor_label")], SystemEvent: [("created_at", "user_label")]}
_local = threading.local()


def _counted(instance):
    """False for the rows the page leaves out (not staff, not these Gold or System kinds)."""
    from . import activity

    if isinstance(instance, ApplicationEvent) and instance.action in activity.GOLD_NOT_STAFF:
        return False
    return not (isinstance(instance, SystemEvent) and instance.kind not in activity.SYSTEM_KINDS)


def _days(instance, values=None):
    """The London days this row counts on: {date} (several for an approach list row that was added and done)."""
    from . import activity

    out = set()
    for when, label in FIELDS[type(instance)]:
        at, who = (values or {}).get(when, getattr(instance, when, None)), getattr(instance, label, "") if values is None else values.get(label, "")
        if at and (who or "").strip() and who not in activity.AUTOMATIC:
            out.add(timezone.localtime(at).date())
    return out


def _flush():
    """Never raises: a failure here only means a day waits for the nightly recount, it must never turn a staff action's save into an error."""
    from .models import ActivityDirtyDay

    days, _local.days = getattr(_local, "days", set()), set()
    try:
        for day in days:
            if not ActivityDirtyDay.objects.filter(day=day).update(marked_at=timezone.now()):
                ActivityDirtyDay.objects.get_or_create(day=day)
    except Exception:  # noqa: BLE001
        logging.getLogger("spa99.activity").exception("Could not mark Activity days for a recount; the nightly recount will catch them")


def _mark(days):
    from . import activity_store

    days = days - set(activity_store.recent_days())  # today and yesterday are recounted by every refresh anyway
    if not days:
        return
    _local.days = getattr(_local, "days", set()) | days
    if not any(callback is _flush for _, callback, *_ in connection.run_on_commit):
        transaction.on_commit(_flush)


def remember_old_days(sender, instance, raw=False, **kwargs):
    """Before a save of an existing row: the days it counted on, so a moved time also recounts its old day (one small read, only for rows already stored)."""
    instance._activity_old_days = set()
    try:
        if raw or instance._state.adding or not _counted(instance):
            return
        fields = [f for pair in FIELDS[sender] for f in pair]
        old = sender.objects.filter(pk=instance.pk).values(*fields).first()
        if old:
            instance._activity_old_days = _days(instance, old)
    except Exception:  # noqa: BLE001  never let the bookkeeping break the save itself
        logging.getLogger("spa99.activity").exception("Could not read the old Activity days")


def activity_row_changed(sender, instance, **kwargs):
    """Never raises: the staff action has been saved; at worst a day waits for the nightly recount."""
    try:
        if kwargs.get("raw") or not _counted(instance):
            return
        days = _days(instance) | getattr(instance, "_activity_old_days", set())
        if not days:
            return
        from . import snapshots

        _mark(days)  # first: the days are stored before the refresh job is queued
        snapshots.request_refresh()
    except Exception:  # noqa: BLE001
        logging.getLogger("spa99.activity").exception("Could not note an Activity change; the nightly recount will catch it")


for _model in FIELDS:
    pre_save.connect(remember_old_days, sender=_model, dispatch_uid=f"office_activity_pre_{_model.__name__}")
    post_save.connect(activity_row_changed, sender=_model, dispatch_uid=f"office_activity_save_{_model.__name__}")
    post_delete.connect(activity_row_changed, sender=_model, dispatch_uid=f"office_activity_delete_{_model.__name__}")
