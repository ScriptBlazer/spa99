"""System > Approval: who approves Gold applications (Approver, Office level or higher) and who gives the final approval to
Low potential ones (Final approver, Admin level or higher), and where each person's approval emails go.

The roles are the Approver and Final approver groups (common.levels); Team only shows them. Every change is guarded here,
recorded in the change list (record_direct, section "approval") and in the audit log (role_changed) with a plain sentence.

Who may change whom (user rule book U4, same `can_manage` as Team): nobody changes themselves, nobody changes someone at their
own level or higher, a superuser may change another superuser. One choice beyond U4, flagged: a superuser may set their own
approval roles, because they already hold every power (U3) and these roles only decide who is emailed."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from common import levels
from common.validators import normalise_email
from gold import approval
from gold.models import ApproverDelivery
from plans.models import SiteSettings

from . import audit
from . import team as team_service
from .models import SystemEvent
from .services import ChangeRefused, record_direct

User = get_user_model()
SECTION = "approval"
APPROVER, FINAL = "approver", "final"
ROLES = {
    APPROVER: {"group": levels.APPROVER_GROUP, "noun": "an approver", "noun_plain": "approver", "can_hold": levels.can_hold_approver,
               "eligible": "Only people at Office level or higher can be approvers."},
    FINAL: {"group": levels.FINAL_APPROVER_GROUP, "noun": "a final approver", "noun_plain": "final approver", "can_hold": levels.can_hold_final_approver,
            "eligible": "Only people at Admin level or higher can be final approvers."},
}


def _name(user):
    return user.get_full_name() or user.email


def _holds(user, role):
    return levels.held_roles(user)[0 if role == APPROVER else 1]


def _may_change(actor, target):
    """U4 through can_manage; plus a superuser's own approval roles (see the module note)."""
    return levels.can_manage(actor, target) or (actor.pk == target.pk and levels.level_of(actor) == levels.SUPERUSER)


def _delivery(user):
    return getattr(user, "approver_delivery", None)


def row(actor, user):
    """One person for the page: {user, id, name, email, level, level_label, use_account_email, other_email, address, can_change}."""
    delivery = _delivery(user)
    level = levels.held_level(user)
    return {"user": user, "id": str(user.pk), "name": _name(user), "email": user.email, "level": level, "level_label": levels.LABELS[level],
            "use_account_email": delivery.use_account_email if delivery else True, "other_email": delivery.other_email if delivery else "",
            "address": approval.address_for(user), "can_change": _may_change(actor, user), "active": user.is_active}


def _holders(role):
    users = (User.objects.filter(groups__name=ROLES[role]["group"]).distinct().select_related("approver_delivery")
             .prefetch_related("groups").order_by("email"))
    return [u for u in users if ROLES[role]["can_hold"](u)]


def candidates(actor, role):
    """Active team members who may hold the role, are not chosen yet, and whom `actor` may change: [{id, name, email, level}]."""
    chosen = {u.pk for u in _holders(role)}
    result = []
    for user in team_service.members():
        if user.pk in chosen or not user.is_active or not ROLES[role]["can_hold"](user) or not _may_change(actor, user):
            continue
        level = levels.held_level(user)
        result.append({"id": str(user.pk), "name": _name(user), "email": user.email, "level": level, "level_label": levels.LABELS[level]})
    return result


def context(actor):
    """Everything the Approval page shows. `cc` is the Gold approver CC list (edited in System > Emails)."""
    site = SiteSettings.load()
    final_rows = [row(actor, u) for u in _holders(FINAL)]
    return {
        "approvers": [row(actor, u) for u in _holders(APPROVER)], "final_approvers": final_rows,
        "approver_candidates": candidates(actor, APPROVER), "final_candidates": candidates(actor, FINAL),
        "cc": site.approver_cc_list, "cc_text": site.gold_approver_cc,
        "final_approver_missing": approval.final_approver_missing(),
        "final_on": site.final_approval_on, "final_nothing_ticked": site.final_approval_on and not site.final_potential_list,
        "awaiting_final_count": approval.awaiting_final_count(),
    }


# ---------- changes ----------

def _group(role):
    return Group.objects.get_or_create(name=ROLES[role]["group"])[0]


def _log(actor, target, field, old, new, sentence):
    record_direct(actor, SECTION, "users.user", target, field, old, new, sentence=sentence)
    audit.log_event(SystemEvent.ROLE_CHANGED, user=actor, detail={"person": target.email, "role": field, "old": old, "new": new}, sentence=sentence)


def _check(actor, target, role, adding):
    if not team_service.team_queryset().filter(pk=target.pk).exists():
        raise ChangeRefused("That person is not on the team. Add them in Team first.")
    if adding:
        if not target.is_active:
            raise ChangeRefused(f"{target.email} is deactivated. Reactivate them in Team first.")
        if not ROLES[role]["can_hold"](target):
            raise ChangeRefused(f"{target.email}: {ROLES[role]['eligible']}")
    if not _may_change(actor, target):
        raise ChangeRefused("You cannot change your own approval roles." if actor.pk == target.pk
                            else "You can only change people below your own level." if not target.is_superuser
                            else "Only a superuser can change another superuser.")


_drop_delivery_if_unused = team_service._drop_delivery_if_unused


@transaction.atomic
def add(actor, role, user_ids):
    """Give the role to each person. All or nothing: one refusal refuses the lot (including an id that no longer exists).
    Returns how many people gained it, or False when nobody was new. A new final approver is emailed every application
    already waiting for final approval."""
    ids = set(_clean_ids(user_ids))
    if not ids and not user_ids:
        raise ChangeRefused("Pick at least one person.")
    targets = list(User.objects.filter(pk__in=ids).order_by("email"))
    if len(targets) != len(set(map(str, user_ids))) or len(targets) != len(ids):
        raise ChangeRefused("Someone you picked is no longer available. Reload and try again.")
    for target in targets:
        _check(actor, target, role, adding=True)
    group, gained = _group(role), 0
    for target in targets:
        if _holds(target, role):
            continue
        target.groups.add(group)
        _log(actor, target, ROLES[role]["group"], False, True, f"Made {target.email} {ROLES[role]['noun']}")
        gained += 1
        if role == FINAL:
            transaction.on_commit(lambda target=target: approval.send_pending_to(target))
    return gained or False


@transaction.atomic
def remove(actor, role, user_id):
    target = User.objects.filter(pk=_clean_ids([user_id])[0] if _clean_ids([user_id]) else None).first()
    if target is None:
        raise ChangeRefused("That person was not found.")
    _check(actor, target, role, adding=False)
    if not _holds(target, role):
        return False
    if role == FINAL and len(_holders(FINAL)) <= 1:
        waiting = approval.awaiting_final_count()
        if waiting:
            raise ChangeRefused(f"Can't remove the last final approver while {waiting} application{'s' if waiting != 1 else ''} wait{'' if waiting != 1 else 's'} for final approval.")
    target.groups.remove(_group(role))
    _drop_delivery_if_unused(target)
    _log(actor, target, ROLES[role]["group"], True, False, f"Removed {target.email} as {ROLES[role]['noun_plain']}")
    return True


@transaction.atomic
def set_delivery(actor, user_id, use_account_email, other_email=""):
    """Where this person's approval emails go (one setting for both roles). Returns True when something changed."""
    target = User.objects.filter(pk=_clean_ids([user_id])[0] if _clean_ids([user_id]) else None).first()
    if target is None or not any(levels.held_roles(target)):
        raise ChangeRefused("Only approvers and final approvers have an email setting.")
    if not _may_change(actor, target):
        raise ChangeRefused("You cannot change your own approval roles." if actor.pk == target.pk else "You can only change people below your own level.")
    other = (other_email or "").strip()
    if other:
        try:
            validate_email(other)
            other = normalise_email(other)
        except ValidationError:
            raise ChangeRefused("Enter a valid email address.") from None
    if not use_account_email and not other:
        raise ChangeRefused("Enter the other address, or send to the account email.")
    old_address = approval.address_for(target)
    delivery = _delivery(target)
    use = bool(use_account_email)
    keep = other or (delivery.other_email if delivery else "")  # unticked and blank is refused above; ticked keeps what was typed before
    if delivery is None and use and not other:
        return False  # the default: nothing to store
    if delivery is not None and (delivery.use_account_email, delivery.other_email) == (use, keep):
        return False
    delivery = delivery or ApproverDelivery(user=target)
    delivery.use_account_email, delivery.other_email = use, keep
    delivery.full_clean(exclude=["user"])
    delivery.save()
    where = "their account email" if use else keep
    _log(actor, target, "approval_email", old_address, delivery.address, f"{target.email}'s approval emails now go to {where}")
    return True


def _clean_ids(values):
    """Only well-formed ids reach the query (a bad id would be a 500 on a UUID column)."""
    import uuid

    ids = []
    for value in values or []:
        try:
            ids.append(uuid.UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            continue
    return ids
