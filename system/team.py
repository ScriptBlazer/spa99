"""System > Team: who is on the team, at what level, and the changes to it (user rule book U4). Every change is guarded by
common.levels.can_manage (never yourself, strictly below you; a superuser may manage another superuser), is recorded
in the change list (record_direct) and the audit log. Views stay short; the guards live here, not in the template."""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from common import levels
from common.tasks import enqueue
from common.validators import normalise_email
from users import merge as user_merge

from . import audit
from .models import SystemEvent
from .services import ChangeRefused, record_direct

logger = logging.getLogger("spa99.system")
User = get_user_model()
ASSIGNABLE = (levels.OFFICE, levels.ADMIN, levels.DEVELOPER, levels.SUPERUSER)


def describe(level, approver):
    return levels.LABELS[level] + (" and Approver" if approver and level != levels.NONE else "")


def members():
    """Everyone with a team level, a staff flag or an Approver group, lowest email first."""
    users = (User.objects.filter(Q(is_staff=True) | Q(is_superuser=True) | Q(groups__name__in=levels.TEAM_GROUPS))
             .distinct().prefetch_related("groups").order_by("email"))
    return list(users)


def rows(actor):
    """The Team table: each person with their level, Approver flag and whether `actor` may change them."""
    result = []
    for user in members():
        level, approver = levels.held(user)
        result.append({"user": user, "level": level, "level_label": levels.LABELS[level], "approver": approver,
                       "can_manage": levels.can_manage(actor, user), "invite_pending": not user.has_usable_password()})
    return result


def level_choices(actor):
    return [(level, levels.LABELS[level]) for level in ASSIGNABLE if levels.can_assign(actor, level)]


def _guard(actor, target):
    if actor.pk == target.pk:
        raise ChangeRefused("You cannot change your own access.")
    if not levels.can_manage(actor, target):
        raise ChangeRefused("Only a superuser can change another superuser." if target.is_superuser
                            else "You can only change people below your own level.")


def _log(actor, target, field, old, new, sentence, kind=SystemEvent.ROLE_CHANGED, detail=None):
    record_direct(actor, "team", "users.user", target, field, old, new, sentence=sentence)
    audit.log_event(kind, user=actor, detail={"person": target.email, "old": old, "new": new, **(detail or {})}, sentence=sentence)


def apply_level(target, level, approver, actor=None):
    """Make the groups and flags say `level` (+ Approver, only valid on a level). Never touches membership or password."""
    names = ([levels.GROUP_FOR[level]] if level in levels.GROUP_FOR else []) + ([levels.APPROVER_GROUP] if approver and level != levels.NONE else [])
    groups = {g.name: g for g in Group.objects.filter(name__in=levels.TEAM_GROUPS)}
    if any(name not in groups for name in names):
        raise ChangeRefused("The levels do not exist yet. Run: manage.py setup_roles")
    target.groups.set(list(target.groups.exclude(name__in=levels.TEAM_GROUPS)) + [groups[n] for n in names])
    target.is_staff, target.is_superuser = level != levels.NONE, level == levels.SUPERUSER
    target._history_user = actor
    target.save(update_fields=["is_staff", "is_superuser", "updated_at"])


@transaction.atomic
def set_access(actor, target, level, approver=False, added=False):
    """Change someone's level and Approver permission. Approver needs a level. `added`: worded as joining the team."""
    _guard(actor, target)
    if level not in ASSIGNABLE or not levels.can_assign(actor, level):
        raise ChangeRefused("You can only give a level below your own.")
    old_level, old_approver = levels.held(target)
    approver = bool(approver)
    if (old_level, old_approver) == (level, approver):
        return False
    apply_level(target, level, approver, actor)
    old, new = describe(old_level, old_approver), describe(level, approver)
    _log(actor, target, "level", old, new, f"Added {target.email} to the team as {new}" if added else f"Changed access for {target.email} from {old} to {new}")
    return True


@transaction.atomic
def remove_from_team(actor, target):
    """Takes away every level and the Approver permission. The account, its password and any membership stay."""
    _guard(actor, target)
    old_level, old_approver = levels.held(target)
    if old_level == levels.NONE and not old_approver and not target.is_staff:
        return False
    apply_level(target, levels.NONE, False, actor)
    old = describe(old_level, old_approver)
    _log(actor, target, "level", old, "No team access", f"Removed {target.email} from the team (was {old})")
    return True


@transaction.atomic
def set_active(actor, target, active):
    _guard(actor, target)
    if target.is_active == active:
        return False
    target.is_active = active
    target._history_user = actor
    target.save(update_fields=["is_active", "updated_at"])
    sentence = f"{'Reactivated' if active else 'Deactivated'} {target.email}"
    _log(actor, target, "is_active", not active, active, sentence, kind=SystemEvent.USER_REACTIVATED if active else SystemEvent.USER_DEACTIVATED)
    return True


def _send_invite(user):
    try:
        enqueue("users.tasks.send_team_invite_email", str(user.pk))
    except Exception:  # noqa: BLE001 - the account is made; "Send a new invite" retries
        logger.exception("Could not queue the team invite for %s", user.pk)


def add_member(actor, email, level, approver=False):
    """Give someone a team level. No account yet: one is made with no password and they are emailed a link to choose their own.
    An existing account just gains the level and keeps its password. Returns (user, created)."""
    try:
        email = normalise_email(email)
    except ValidationError as error:
        raise ChangeRefused(" ".join(error.messages)) from error
    if level not in ASSIGNABLE or not levels.can_assign(actor, level):
        raise ChangeRefused("You can only give a level below your own.")
    with transaction.atomic():
        user = User.objects.filter(email__iexact=email).first()
        created = user is None
        if created:
            user = User.objects.create_user(email, None)  # no password: they choose it from the email
        elif not user.is_active:
            raise ChangeRefused("That account is deactivated. Reactivate it first.")
        set_access(actor, user, level, approver, added=not user.is_staff)
    if created:
        _send_invite(user)
    return user, created


def resend_invite(actor, target):
    _guard(actor, target)
    if target.has_usable_password() or not target.is_active:
        raise ChangeRefused("Only someone who has not chosen a password yet can be sent a new invite.")
    _send_invite(target)
    audit.log_event(SystemEvent.ROLE_CHANGED, user=actor, detail={"person": target.email}, sentence=f"Sent a new team invite to {target.email}")


def find_user(email):
    try:
        email = normalise_email(email)
    except ValidationError as error:
        raise ChangeRefused(" ".join(error.messages)) from error
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        raise ChangeRefused(f"No account with the email {email}.")
    return user


def merge_preview(actor, keep_email, remove_email):
    """(keep, remove, what would move) for the confirm screen."""
    keep, remove = find_user(keep_email), find_user(remove_email)
    try:
        return keep, remove, user_merge.preview(actor, keep, remove)
    except user_merge.MergeRefused as error:
        raise ChangeRefused(str(error)) from error


def merge_accounts(actor, keep_email, remove_email):
    keep, remove = find_user(keep_email), find_user(remove_email)
    try:
        moved = user_merge.merge(actor, keep, remove)
    except user_merge.MergeRefused as error:
        raise ChangeRefused(str(error)) from error
    sentence = (f"Merged the account {moved['removed_email']} into {keep.email} "
                f"({moved['sessions']} journey sessions, {moved['gold']} Gold applications, membership: {moved['membership'].lower()})")
    record_direct(actor, "team", "users.user", keep, "merged", moved["removed_email"], keep.email, sentence=sentence)
    audit.log_event(SystemEvent.ROLE_CHANGED, user=actor, detail={"kept": keep.email, "removed": moved["removed_email"], "moved": {k: v for k, v in moved.items() if k != "removed_email"}}, sentence=sentence)
    return keep, moved
