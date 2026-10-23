"""Merge two accounts of the same person (user rule book U1: one login per person). Developers do it in System > Team.

`keep` stays; `remove` is deleted after everything that belongs to the person has moved across: the membership
(interest), journey sessions, Gold applications and sign-in records. Blank profile fields on `keep` are filled from
`remove`. Nothing moves that would change what either account is allowed to do: team levels and passwords stay as
they are on `keep`. Both accounts with a membership are refused unless it is the same plan. Pure data: the caller
(system.team) checks who may do it and writes the audit log."""
from django.db import transaction
from django.db.models import Q

from common import levels
from common.models import LoginEvent
from common.tasks import erase_task_records
from gold.models import GoldApplication
from insights import metrics
from journey.models import JourneySession
from notifications.models import EmailLog

from .models import InterestRegistration, User

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
        raise MergeRefused("You cannot merge your own account away.")
    if levels.held_level(remove) != levels.NONE and not levels.can_manage(actor, remove):
        raise MergeRefused("You cannot merge away someone at your own level or above.")
    if not actor_is_superuser:  # the account that stays gains everything, so the same rule applies to it
        if keep.pk == actor.pk:
            raise MergeRefused("You cannot merge other accounts into your own. Ask a superuser.")
        if levels.held_level(keep) != levels.NONE and not levels.can_manage(actor, keep):
            raise MergeRefused("You cannot merge into someone at your own level or above.")
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
    removed_email = remove.email
    sessions = list(JourneySession.objects.filter(user=remove).values_list("pk", flat=True))
    JourneySession.objects.filter(pk__in=sessions).update(user=keep)
    JourneySession.history.model.objects.filter(id__in=sessions).update(user=keep)
    # Gold applications (linked to the removed account or made with its email) now belong to keep and carry keep's email,
    # because export and erasure find them by email; their history rows follow.
    apps = list(GoldApplication.objects.filter(Q(user=remove) | Q(email__iexact=removed_email)).values_list("pk", flat=True))
    GoldApplication.objects.filter(pk__in=apps).update(user=keep, email=keep.email)
    GoldApplication.history.model.objects.filter(id__in=apps).update(user=keep, email=keep.email)
    GoldApplication.objects.filter(approved_by=remove).update(approved_by=keep)
    LoginEvent.objects.filter(user=remove).update(user=keep)
    LoginEvent.objects.filter(attempted_email__iexact=removed_email).update(attempted_email=keep.email)
    EmailLog.objects.filter(subject_email__iexact=removed_email).update(subject_email=keep.email)
    EmailLog.objects.filter(to__iexact=removed_email).update(to=keep.email)
    values = {name: getattr(remove, name) for name in summary["fill"]}
    if remove.email_verified_at:
        metrics.email_verified(remove.email_verified_at, amount=-1)  # the person is counted once, by the account that stays
    remove.mobile = None  # the unique number can move to the account that stays
    remove.save(update_fields=["mobile", "updated_at"])
    for name, value in values.items():
        setattr(keep, name, value)
    keep._history_user = actor
    keep.save()
    removed_pk = remove.pk
    remove.delete()
    # The removed person's own personal history (name, email, mobile in old rows) and queued task records go, as in an erasure.
    # The audit log (System) is append-only and is not touched.
    User.history.model.objects.filter(id=removed_pk).delete()
    if theirs is not None and mine is not None:
        InterestRegistration.history.model.objects.filter(id=theirs.pk).delete()
    erase_task_records([removed_pk], ["users.tasks."])
    return {**summary, "removed_email": removed_email}
