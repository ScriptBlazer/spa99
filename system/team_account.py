"""System > Team > a person: their login email, their password, and a password reset link (user rule book U4).

Every change is guarded by common.levels.can_manage through team._guard (never yourself, strictly below you, a superuser may manage another superuser),
written to the change list and the audit log, and ends the person's sessions where it should. Nothing here ever logs or stores a password in plain text."""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from common.tasks import enqueue
from common.validators import normalise_email
from notifications import sender as sender_mod
from outreach import services as outreach
from users import services as user_services

from . import audit, team
from .models import SystemEvent
from .services import ChangeRefused, record_direct

logger = logging.getLogger("spa99.system")
User = get_user_model()
OWN_EMAIL = "You cannot change your own email here. Ask another Developer or a superuser."
OWN_PASSWORD = "You cannot set your own password here. Use Change password in the menu."
MERGE_HINT = "Another account already uses that address. To combine the two accounts, use Merge two accounts on the Team page."


def _name(user):
    return user.get_full_name() or user.email


def _follow_email(target, old, new, actor):
    """Everything stored under the old address follows it. The Office data (notes, messages, Approach entries, timeline edits, archive rows, follow-up, chat, email log) moves through
    outreach.services.move_address_data, the same helper a lead's email correction uses. On top, the rows linked to this account move with their history rows (journey sessions
    `lead_email`, Gold applications `email`), as a merge does, so export and erasure (which find people by address) still find them. Left on purpose: sign-in attempts, uploaded
    lists and invites (they record that address, not the account)."""
    from gold.models import GoldApplication
    from journey.models import JourneySession
    from outreach import services as outreach

    for model, field in ((JourneySession, "lead_email"), (GoldApplication, "email")):
        ids = list(model.objects.filter(user=target, **{f"{field}__iexact": old}).values_list("pk", flat=True))
        model.objects.filter(pk__in=ids).update(**{field: new})
        model.history.model.objects.filter(id__in=ids).update(**{field: new})
    outreach.move_address_data(old, new, actor, keep_history=True)
    outreach._figures_changed()


def _send_notices(user_id, old, actor_id):
    from users import tasks

    try:
        tasks.send_email_changed_notices(str(user_id), old, str(actor_id))
    except Exception:  # noqa: BLE001 - the change is made and audited; a mail fault must not undo it
        logger.exception("Could not send the email-changed notices for %s", user_id)


@transaction.atomic
def change_email(actor, target, new_email):
    """Change a team member's login email on the same account (same id: every membership, application and history row stays). Returns True, or False when it is the same address.
    Refused when another account (any case) or another person's sending address already has it. Signs the person out everywhere and emails both addresses."""
    team._guard(actor, target, team_only=True, own=OWN_EMAIL)
    try:
        new = normalise_email(new_email)
    except ValidationError as error:
        raise ChangeRefused(" ".join(error.messages)) from error
    old = target.email  # email_verified_at is kept on purpose: an address a Developer types counts as verified (decision 2026-11-16)
    if new == old:
        return False
    if User.objects.filter(email__iexact=new).exclude(pk=target.pk).exists():
        raise ChangeRefused(MERGE_HINT)
    owner = outreach.owner_of_email(new, exclude=old, exclude_user=target)  # a lead, a Gold applicant or an archived lead who is not this person (their own rows carry the old address)
    if owner:
        kind = {"lead": "a lead", "gold": "a Gold applicant", "archived": "an archived lead"}.get(owner["kind"], "someone else")
        raise ChangeRefused(f"That address belongs to {kind} ({owner['name']}). Choose a different one.")
    if sender_mod.belongs_to_someone_else(new, target):
        raise ChangeRefused("That address is another team member's sending address. Choose a different one.")
    target.email = new
    target._history_user = actor
    try:
        with transaction.atomic():
            target.save(update_fields=["email", "updated_at"])
    except IntegrityError as error:  # two people saved the same address at once
        raise ChangeRefused(MERGE_HINT) from error
    _follow_email(target, old, new, actor)
    team._log(actor, target, "email", old, new, f"Changed the login email for {old} to {new}", detail={"signed_out": True})
    user_services.sign_out_everywhere(target)
    transaction.on_commit(lambda: _send_notices(target.pk, old, actor.pk))
    return True


def _may_set_password(actor, target):
    team._guard(actor, target, team_only=True, own=OWN_PASSWORD)
    if not target.is_active:
        raise ChangeRefused("That account is deactivated. Reactivate it first.")


@transaction.atomic
def set_password(actor, target, password, again):
    """A Developer or superuser types a new password for someone below them. Django's validators run; the password is never logged or kept anywhere but as a hash;
    the audit entry says who set it, not what. The person is signed out everywhere and emailed (their id and the actor's id only go to the queue)."""
    _may_set_password(actor, target)
    if password != again:
        raise ChangeRefused("The two passwords are not the same.")
    try:
        validate_password(password, user=target)
    except ValidationError as error:
        raise ChangeRefused(" ".join(error.messages)) from error
    target.set_password(password)
    target._history_user = actor
    target.save(update_fields=["password", "updated_at"])
    sentence = f"Password set by {actor.email} for {target.email}"
    record_direct(actor, "team", "users.user", target, "password", "", "", sentence=sentence)  # no value, either side
    audit.log_event(SystemEvent.PASSWORD_CHANGED, user=actor, detail={"person": target.email, "set_by": actor.email}, sentence=sentence)
    user_services.sign_out_everywhere(target)
    transaction.on_commit(lambda: _queue("users.tasks.send_password_set_email", target.pk, actor.pk))
    return True


def send_reset_link(actor, target):
    """Email the person a link to choose their own password (one hour, once). Someone who has no password yet gets the team invite; everyone else the reset email."""
    _may_set_password(actor, target)
    task = "users.tasks.send_password_reset_email" if target.has_usable_password() else "users.tasks.send_team_invite_email"
    try:
        enqueue(task, str(target.pk))
    except Exception as error:  # noqa: BLE001
        logger.exception("Could not queue %s", task)
        raise ChangeRefused("The email could not be queued. Try again in a moment.") from error
    audit.log_event(SystemEvent.PASSWORD_CHANGED, user=actor, detail={"person": target.email, "kind": "reset_link"}, sentence=f"Sent a password reset link to {target.email}")
    return True


def _queue(task, *ids):
    try:
        enqueue(task, *[str(i) for i in ids])
    except Exception:  # noqa: BLE001 - the change is made; the link can be sent again
        logger.exception("Could not queue %s", task)
