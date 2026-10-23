"""System logic: saving with a person recorded, undo, the change list, the dashboard figures and Team. Views stay short."""
import time
from datetime import date, timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, Q, TextField
from django.db.models.functions import Cast
from django.utils import timezone

from . import changes
from .models import SystemChange

ROLES = ("Owner", "Manager", "Viewer", "Approver", "System")
PAGE_SIZE = 50
SNAPSHOT_STALE_SECONDS = 15 * 60


class ChangeRefused(Exception):
    """A change System will not make; the message is shown to the person."""


# ---------- who may use System, and the unlock ----------

def may_use_system(user):
    """Superusers, or members of the System group; always is_staff and active."""
    if not (user.is_authenticated and user.is_staff and user.is_active):
        return False
    return user.is_superuser or user.groups.filter(name="System").exists()


UNLOCK_KEY = "system_unlocked_at"
SIGNED_IN_KEY = "system_signed_in"  # the time of the System sign-in (set only by the System sign-in page: a session made on another host never counts)


def _security_values():
    """(idle minutes, sign-in hours) from the site settings row, or None for a value that is missing (no row yet)."""
    from plans.models import SiteSettings

    row = SiteSettings.objects.filter(singleton_key="site").values("lock_idle_minutes", "max_sign_in_hours").first() or {}
    return row.get("lock_idle_minutes"), row.get("max_sign_in_hours")


def lock_idle_seconds():
    """Seconds without activity before System locks: the Security setting, else the SYSTEM_UNLOCK_SECONDS default."""
    from django.conf import settings

    minutes = _security_values()[0]
    return minutes * 60 if minutes else settings.SYSTEM_UNLOCK_SECONDS


def session_age_seconds():
    """Longest System sign-in in seconds: the Security setting, else the SYSTEM_SESSION_AGE default."""
    from django.conf import settings

    hours = _security_values()[1]
    return hours * 3600 if hours else settings.SYSTEM_SESSION_AGE


def sign_in_valid(session, now=None):
    """True while this System sign-in is younger than the longest sign-in (12 h by default), however active the person is."""
    stamp = session.get(SIGNED_IN_KEY)
    now = time.time() if now is None else now
    return bool(stamp) and now - stamp < session_age_seconds()


def remaining_seconds(session, now=None, idle_seconds=None):
    """Whole seconds left before the lock (0 when locked). The page and the ping both show this; the server decides."""
    stamp = session.get(UNLOCK_KEY)
    now = time.time() if now is None else now
    if not stamp:
        return 0
    return max(0, int((idle_seconds or lock_idle_seconds()) - (now - stamp)))


def is_unlocked(session, now=None, idle_seconds=None):
    return remaining_seconds(session, now, idle_seconds) > 0


def unlock(session):
    session[UNLOCK_KEY] = time.time()


def lock(session):
    session.pop(UNLOCK_KEY, None)


# ---------- saving and undo ----------

@transaction.atomic
def save_logged(obj, user, fields=None):
    """Save a row with the person recorded in its history (the log entries are written from that history row)."""
    obj._history_user = user
    obj.full_clean()
    obj.save(update_fields=None if fields is None else list(fields) + (["updated_at"] if hasattr(obj, "updated_at") else []))
    return obj


def save_form(form, user):
    """Save a valid ModelForm through the change log: a new row is created, an existing one saves only the fields that
    changed. Returns True when something was written."""
    obj = form.instance
    if obj._state.adding:
        save_logged(obj, user)
        return True
    if not form.changed_data:
        return False
    save_logged(obj, user, fields=form.changed_data)
    return True


@transaction.atomic
def delete_logged(obj, user):
    """Delete a row with the person recorded (the change log keeps a 'deleted' entry)."""
    obj._history_user = user
    obj.delete()


def undo_change(change, user):
    """Put the old value back as a new logged change. Refused unless the field still holds the value this change set
    (otherwise undo the newer change first), and for created, deleted or file entries."""
    if not change.undoable:
        raise ChangeRefused("This entry cannot be undone.")
    model = apps.get_model(change.model_label)
    field = model._meta.get_field(change.field)
    if not changes.is_undoable_field(field):
        raise ChangeRefused("This entry cannot be undone.")
    with transaction.atomic():
        change = SystemChange.objects.select_for_update().get(pk=change.pk)  # no select_related: Postgres cannot lock nullable joins
        if change.undone_by.exists():
            raise ChangeRefused("This change has already been undone.")
        obj = model.objects.filter(pk=change.object_pk).first()
        if obj is None:
            raise ChangeRefused("That row no longer exists.")
        if changes.to_json(getattr(obj, field.attname)) != change.new_value:
            raise ChangeRefused("It has been changed again since. Undo the newer change first.")
        setattr(obj, field.attname, changes.from_json(field, change.old_value))
        try:
            with changes.undoing(change.pk):
                save_logged(obj, user, fields=[field.name])
        except ValidationError as error:
            raise ChangeRefused(" ".join(error.messages)) from error
    return obj


@transaction.atomic
def undo_batch(batch_id, user):
    """Undo every undoable, not yet undone entry saved together. Returns (undone count, refused messages).
    One transaction for the whole batch; each entry runs in its own savepoint (undo_change). A ChangeRefused rolls back
    only that entry's savepoint and is reported (the others still go through); any other error escapes and rolls the
    whole batch back."""
    entries = SystemChange.objects.filter(batch_id=batch_id, kind=SystemChange.UPDATED, undo_of__isnull=True, undone_by__isnull=True)
    done, refused = 0, []
    for change in list(entries.order_by("-created_at")):
        try:
            undo_change(change, user)
            done += 1
        except ChangeRefused as error:
            refused.append(str(error))
    return done, refused


def undo_url_for_batch(batch_id):
    """The URL that undoes what this request saved: one entry -> its undo, several -> undo all, none -> ''."""
    from django.urls import reverse

    if not batch_id:
        return ""
    rows = [c for c in SystemChange.objects.filter(batch_id=batch_id, undo_of__isnull=True) if c.undoable]
    if len(rows) == 1:
        return reverse("system_undo", args=[rows[0].pk])
    return reverse("system_undo_batch", args=[batch_id]) if rows else ""


def annotate_batches(entries):
    """Mark entries saved together (one query for the whole list): `batch_size`, `batch_open` (entries still undoable)
    and `batch_first` (the first row of that group in this list, where the page shows 'Saved together' and Undo all)."""
    entries = list(entries)
    ids = {c.batch_id for c in entries if c.batch_id}
    stats = {}
    if ids:
        rows = SystemChange.objects.filter(batch_id__in=ids).values("batch_id").annotate(
            size=Count("id", distinct=True),
            open=Count("id", distinct=True, filter=Q(kind=SystemChange.UPDATED, undo_of__isnull=True, undone_by__isnull=True, history_id__isnull=False)))
        stats = {r["batch_id"]: r for r in rows}
    seen = set()
    for c in entries:
        info = stats.get(c.batch_id)
        c.batch_size = info["size"] if info else 1
        c.batch_open = info["open"] if info else 0
        c.batch_first = bool(info) and c.batch_id not in seen
        seen.add(c.batch_id)
    return entries


def record_direct(user, section, model_label, obj, field, old, new):
    """A change to something without history (Team). Not undoable."""
    return SystemChange.objects.create(
        section=section, model_label=model_label, object_pk=str(obj.pk), object_repr=str(obj)[:200], field=field,
        old_value=changes.to_json(old), new_value=changes.to_json(new), kind=SystemChange.DIRECT,
        user=user, user_label=changes.current_user_label(user))


# ---------- the change list ----------

def change_list(params, page=1):
    """Filtered, paginated entries (a fixed number of queries). params: section, user (a person's email), q (text in the
    field, row, person or values), range (1, 7 or 30 days, wins over the dates), date_from, date_to (YYYY-MM-DD)."""
    queryset = SystemChange.objects.select_related("user").prefetch_related("undone_by")
    if params.get("section"):
        queryset = queryset.filter(section=params["section"])
    if params.get("user"):
        queryset = queryset.filter(user_label__icontains=params["user"].strip())
    if params.get("q"):
        text = params["q"].strip()
        queryset = queryset.annotate(old_text=Cast("old_value", TextField()), new_text=Cast("new_value", TextField())).filter(
            Q(field__icontains=text) | Q(object_repr__icontains=text) | Q(user_label__icontains=text) | Q(old_text__icontains=text) | Q(new_text__icontains=text))
    start, end = params.get("date_from"), params.get("date_to")
    if params.get("range") in ("1", "7", "30"):
        start, end = (timezone.localdate() - timedelta(days=int(params["range"]) - 1)).isoformat(), ""
    for value, lookup in ((start, "created_at__date__gte"), (end, "created_at__date__lte")):
        if value:
            try:
                queryset = queryset.filter(**{lookup: date.fromisoformat(value)})
            except ValueError:
                pass
    result = Paginator(queryset, PAGE_SIZE).get_page(page)
    result.object_list = annotate_batches(result.object_list)
    return result


def change_people():
    """Who has made changes (for the person filter)."""
    return list(SystemChange.objects.exclude(user_label="").order_by("user_label").values_list("user_label", flat=True).distinct())


def recent_changes(count=10):
    return annotate_batches(SystemChange.objects.select_related("user").prefetch_related("undone_by")[:count])


# ---------- the dashboard (stored figures only) ----------

def health_report():
    """DB ok, queue size, last roll-up, snapshot age, and the key counts from the stored dashboard snapshot."""
    from django_q.models import Failure, OrmQ, Success

    from insights.metrics import K
    from insights.models import OfficeSnapshot
    from office import selectors

    report = {"database_ok": True, "queue_size": None, "last_rollup": None, "snapshot_age_seconds": None, "snapshot_stale": True,
              "counts": {}, "failed_tasks_24h": None, "gold_waiting": 0, "people_total": 0}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        report["database_ok"] = False
        return report
    report["queue_size"] = OrmQ.objects.count()
    last = Success.objects.filter(func="insights.rollup.scheduled").order_by("-stopped").values_list("stopped", flat=True).first()
    report["last_rollup"] = last
    report["failed_tasks_24h"] = Failure.objects.filter(stopped__gte=timezone.now() - timedelta(hours=24)).count()
    snapshot = OfficeSnapshot.objects.filter(page=OfficeSnapshot.DASHBOARD, range="7d").first()
    if snapshot is not None:
        age = max(0, int((timezone.now() - snapshot.updated_at).total_seconds()))
        report["snapshot_age_seconds"], report["snapshot_stale"] = age, age > SNAPSHOT_STALE_SECONDS  # no snapshot at all counts as stale
        report["counts"] = (snapshot.payload or {}).get("totals", {})
    stored = selectors.counters(K.GOLD_BY_STATUS, K.REGISTRATIONS)  # stored counters, nothing summed here
    report["gold_waiting"] = selectors.waiting_count(stored)
    report["people_total"] = stored.get((K.REGISTRATIONS, ""), report["counts"].get("registrations", 0))
    return report


# ---------- Team ----------

def staff_users():
    User = get_user_model()
    users = list(User.objects.filter(is_staff=True).prefetch_related("groups").order_by("email"))
    return [{"user": u, "roles": sorted(g.name for g in u.groups.all() if g.name in ROLES)} for u in users]


def _guard_target(actor, target):
    if target.is_superuser and not actor.is_superuser:
        raise ChangeRefused("Only a superuser can change another superuser.")


@transaction.atomic
def set_roles(actor, target, roles):
    """Make `roles` the person's exact set of System/Office roles. Never touches superuser flags; you cannot take the
    System role off yourself (you would lock yourself out)."""
    _guard_target(actor, target)
    roles = [r for r in ROLES if r in set(roles)]
    if target.pk == actor.pk and not actor.is_superuser and "System" not in roles:
        raise ChangeRefused("You cannot remove your own System role.")
    old = sorted(g.name for g in target.groups.filter(name__in=ROLES))
    groups = {g.name: g for g in Group.objects.filter(name__in=ROLES)}
    missing = [r for r in roles if r not in groups]
    if missing:
        raise ChangeRefused("The roles do not exist yet. Run: manage.py setup_roles")
    keep = [g for g in target.groups.exclude(name__in=ROLES)]
    target.groups.set(keep + [groups[r] for r in roles])
    if old != roles:
        record_direct(actor, "team", "users.user", target, "roles", old, roles)
    return roles


@transaction.atomic
def set_active(actor, target, active):
    _guard_target(actor, target)
    if target.pk == actor.pk and not active:
        raise ChangeRefused("You cannot deactivate yourself.")
    if target.is_active != active:
        old, target.is_active = target.is_active, active
        target._history_user = actor
        target.save(update_fields=["is_active", "updated_at"])
        record_direct(actor, "team", "users.user", target, "is_active", old, active)
