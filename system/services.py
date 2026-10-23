"""System logic: saving with a person recorded, undo, the change list, the dashboard figures and Team. Views stay short."""
import time
from datetime import date

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.utils import timezone

from . import changes
from .models import SystemChange

ROLES = ("Owner", "Manager", "Viewer", "Approver", "System")
PAGE_SIZE = 50


class ChangeRefused(Exception):
    """A change System will not make; the message is shown to the person."""


# ---------- who may use System, and the unlock ----------

def may_use_system(user):
    """Superusers, or members of the System group; always is_staff and active."""
    if not (user.is_authenticated and user.is_staff and user.is_active):
        return False
    return user.is_superuser or user.groups.filter(name="System").exists()


UNLOCK_KEY = "system_unlocked_at"
SIGNED_IN_KEY = "system_signed_in"  # set only by the System sign-in page: a session made on another host never counts


def is_unlocked(session, now=None, idle_seconds=None):
    from django.conf import settings

    stamp = session.get(UNLOCK_KEY)
    now = time.time() if now is None else now
    return bool(stamp) and now - stamp < (idle_seconds or settings.SYSTEM_UNLOCK_SECONDS)


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


def record_direct(user, section, model_label, obj, field, old, new):
    """A change to something without history (Team). Not undoable."""
    return SystemChange.objects.create(
        section=section, model_label=model_label, object_pk=str(obj.pk), object_repr=str(obj)[:200], field=field,
        old_value=changes.to_json(old), new_value=changes.to_json(new), kind=SystemChange.DIRECT,
        user=user, user_label=changes.current_user_label(user))


# ---------- the change list ----------

def change_list(params, page=1):
    """Filtered, paginated entries. params: section, user (email contains), date_from, date_to (YYYY-MM-DD)."""
    queryset = SystemChange.objects.select_related("user")
    if params.get("section"):
        queryset = queryset.filter(section=params["section"])
    if params.get("user"):
        queryset = queryset.filter(user_label__icontains=params["user"].strip())
    for key, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
        value = params.get(key)
        if value:
            try:
                queryset = queryset.filter(**{lookup: date.fromisoformat(value)})
            except ValueError:
                pass
    return Paginator(queryset, PAGE_SIZE).get_page(page)


def recent_changes(count=10):
    return list(SystemChange.objects.select_related("user")[:count])


# ---------- the dashboard (stored figures only) ----------

def health_report():
    """DB ok, queue size, last roll-up, snapshot age, and the key counts from the stored dashboard snapshot."""
    from django_q.models import OrmQ, Success

    from insights.models import OfficeSnapshot

    report = {"database_ok": True, "queue_size": None, "last_rollup": None, "snapshot_age_seconds": None, "counts": {}}
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
    snapshot = OfficeSnapshot.objects.filter(page=OfficeSnapshot.DASHBOARD, range="7d").first()
    if snapshot is not None:
        report["snapshot_age_seconds"] = max(0, int((timezone.now() - snapshot.updated_at).total_seconds()))
        report["counts"] = (snapshot.payload or {}).get("totals", {})
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
