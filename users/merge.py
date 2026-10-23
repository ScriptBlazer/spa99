"""Merge two accounts of the same person (user rule book U1: one login per person). Developers do it in System > Team.

`keep` stays; `remove` is deleted after everything that belongs to the person has moved across: the membership
(interest), journey sessions, Gold applications and sign-in records. Blank profile fields on `keep` are filled from
`remove`. Nothing moves that would change what either account is allowed to do: team levels and passwords stay as
they are on `keep`. Both accounts with a membership are refused unless it is the same plan. Pure data: the caller
(system.team) checks who may do it and writes the audit log."""
from django.db import transaction

from common import levels
from common.models import LoginEvent
from gold.models import GoldApplication
from insights import metrics
from journey.models import JourneySession

from .models import InterestRegistration

PROFILE_FIELDS = ("first_name", "last_name", "mobile", "date_of_birth")


class MergeRefused(Exception):
    """A merge that is not allowed; the message is shown to the person."""


def _interest(user):
    return InterestRegistration.objects.filter(user=user).select_related("plan").first()


def check(actor, keep, remove):
    """Raise MergeRefused unless `actor` may merge `remove` into `keep`."""
    if keep.pk == remove.pk:
        raise MergeRefused("Choose two different accounts.")
    actor_is_superuser = levels.level_of(actor) == levels.SUPERUSER
    if (keep.is_superuser or remove.is_superuser) and not actor_is_superuser:
        raise MergeRefused("Only a superuser can merge an account that belongs to a superuser.")
    if remove.pk == actor.pk:
        raise MergeRefused("You cannot merge your own account away. Keep it and merge the other one into it.")
    if levels.held_level(remove) != levels.NONE and not levels.can_manage(actor, remove):
        raise MergeRefused("You cannot merge away someone at your own level or above.")
    mine, theirs = _interest(keep), _interest(remove)
    if mine and theirs and (mine.plan_id != theirs.plan_id):
        raise MergeRefused(
            f"Both accounts hold a membership and they are different ({mine.plan.name if mine.plan else 'no plan'} and "
            f"{theirs.plan.name if theirs.plan else 'no plan'}). Memberships are never combined automatically: "
            "change one of them first, or ask a superuser.")


def preview(actor, keep, remove):
    """What would move, as plain numbers and words, for the confirm screen. Raises MergeRefused."""
    check(actor, keep, remove)
    mine, theirs = _interest(keep), _interest(remove)
    fill = [name for name in PROFILE_FIELDS if not getattr(keep, name) and getattr(remove, name)]
    return {
        "membership": "Moves the membership" if theirs and not mine else "The same membership is on both: one copy is kept" if theirs else "None",
        "sessions": JourneySession.objects.filter(user=remove).count(),
        "gold": GoldApplication.objects.filter(user=remove).count(),
        "sign_ins": LoginEvent.objects.filter(user=remove).count(),
        "fill": fill,
        "drops_team_level": levels.held_level(remove) != levels.NONE,
    }


@transaction.atomic
def merge(actor, keep, remove):
    """Do the merge. Returns the preview numbers that were moved."""
    summary = preview(actor, keep, remove)
    mine, theirs = _interest(keep), _interest(remove)
    if theirs is not None and mine is None:
        theirs.user = keep
        theirs.save(update_fields=["user", "updated_at"])
    elif theirs is not None:  # the same plan on both: one copy stays, and the stored figures forget the extra one
        metrics.registered(theirs.plan.slug if theirs.plan_id else None, theirs.source, theirs.created_at,
                           marketing=remove.marketing_consent, amount=-1)
        theirs.delete()
    JourneySession.objects.filter(user=remove).update(user=keep)
    GoldApplication.objects.filter(user=remove).update(user=keep)
    GoldApplication.objects.filter(approved_by=remove).update(approved_by=keep)
    LoginEvent.objects.filter(user=remove).update(user=keep)
    values = {name: getattr(remove, name) for name in summary["fill"]}
    if remove.email_verified_at:
        metrics.email_verified(remove.email_verified_at, amount=-1)  # the person is counted once, by the account that stays
    removed_email = remove.email
    remove.mobile = None  # the unique number can move to the account that stays
    remove.save(update_fields=["mobile", "updated_at"])
    for name, value in values.items():
        setattr(keep, name, value)
    keep._history_user = actor
    keep.save()
    remove.delete()
    return {**summary, "removed_email": removed_email}
