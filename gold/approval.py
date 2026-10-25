"""Who approves Gold, and the final approval step (docs/features/gold-final-approval.md).

Recipients are people, not typed addresses: every active person holding the Approver group (Office level or higher) or the
Final approver group (Admin level or higher), each at their account email or their own other address
(gold.ApproverDelivery, set in System > Approval).

Flow: an approver approves a Low potential application and, when at least one final approver exists, it becomes
`awaiting_final` (not approved, the applicant is told nothing). A final approver then confirms (the normal approval runs)
or sends it back (status back to new, every approver is emailed, and the next approval goes through at once because
`sent_back_at` is set). The final approver cannot decline. No final approver: Low goes through as before."""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.utils import timezone

from common import levels
from common.tasks import enqueue

from . import invites, rating
from .models import GoldApplication

logger = logging.getLogger("spa99.gold")

AWAITING = "awaiting_final"  # result of approve(): sent for final approval (not approved)
FINAL_SALT = "spa99.gold.final"
FINAL_DAYS = 14


class NoteTooLong(ValueError):
    pass


# ---------- people and addresses ----------

def _people(group, minimum_level):
    """Active people holding `group` whose level (as of now) still allows it. Stale groups on demoted people are ignored."""
    users = (get_user_model().objects.filter(is_active=True, groups__name=group).distinct()
             .select_related("approver_delivery").prefetch_related("groups").order_by("email"))
    return [u for u in users if levels.rank(levels.level_of(u)) >= levels.rank(minimum_level)]


def approvers():
    return _people(levels.APPROVER_GROUP, levels.APPROVER_MIN_LEVEL)


def final_approvers():
    return _people(levels.FINAL_APPROVER_GROUP, levels.FINAL_APPROVER_MIN_LEVEL)


def address_for(user):
    delivery = getattr(user, "approver_delivery", None)  # a missing row is an AttributeError subclass: no row = account email
    return delivery.address if delivery is not None else user.email


def addresses(people):
    """Their delivery addresses, once each (case-insensitive), in a stable order."""
    seen, result = set(), []
    for user in people:
        address = address_for(user)
        if address.lower() not in seen:
            seen.add(address.lower())
            result.append(address)
    return result


def approver_addresses():
    return addresses(approvers())


def final_approver_addresses():
    return addresses(final_approvers())


def final_approver_exists():
    return bool(final_approvers())


# ---------- the one-tap link for final approvers ----------

def make_final_token(application):
    """Signed copy of the application id and the moment it was sent for final approval: it dies when the application
    leaves `awaiting_final` (confirmed, sent back) and cannot be reused for a later round."""
    return signing.dumps({"id": str(application.pk), "t": int(application.final_requested_at.timestamp())}, salt=FINAL_SALT)


def token_is_valid(token, application):
    """Bad signature, expired (14 days), another application, a spent round: all the same answer, False."""
    try:
        data = signing.loads(token, salt=FINAL_SALT, max_age=FINAL_DAYS * 86400)
    except signing.BadSignature:
        return False
    return (isinstance(data, dict) and application.status == GoldApplication.AWAITING_FINAL
            and application.final_requested_at is not None
            and data.get("id") == str(application.pk) and data.get("t") == int(application.final_requested_at.timestamp()))


def final_email_context(application):
    from . import services

    office, token = settings.OFFICE_URL, make_final_token(application)
    base = f"{office}/gold/{application.pk}/final/{token}/"
    return {**services.approver_email_context(application), "confirm_url": f"{base}?do=confirm", "send_back_url": f"{base}?do=send_back"}


def sent_back_email_context(application):
    from . import services

    context = services.approver_email_context(application)
    return {**context, "decline_url": f"{context['view_url']}#decision-h", "note": application.sent_back_note,
            "sent_back_by": (application.sent_back_by.get_full_name() or application.sent_back_by.email) if application.sent_back_by_id else ""}


# ---------- the steps ----------

def _queue(function, *args):
    try:
        enqueue(function, *args)
    except Exception:  # noqa: BLE001 - the step is saved; nothing is lost if the queue is down
        logger.exception("Could not queue %s", function)


def needs_final_review(application):
    return (application.potential_level == rating.LOW and not application.final_review_done and final_approver_exists())


def approve(application, actor):
    """An approver's Approve. Returns AWAITING (sent for final approval) or what invites.approve_and_invite returns
    (INVITED, ACTIVATED, SKIPPED)."""
    if needs_final_review(application):
        with transaction.atomic():
            fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
            sent = (fresh.status in GoldApplication.WAITING and fresh.potential_level == rating.LOW and not fresh.final_review_done)
            if sent:
                fresh.status, fresh.final_requested_at, fresh.final_requested_by = GoldApplication.AWAITING_FINAL, timezone.now(), actor
                fresh.save()
        if sent:
            logger.info("Gold %s sent for final approval by %s", application.reference, actor.pk)
            _queue("gold.tasks.send_gold_final_email", str(application.pk))
            application.refresh_from_db()
            return AWAITING
    return invites.approve_and_invite(application, actor)


def final_confirm(application, actor):
    """A final approver's Confirm: the normal approval runs (invite, or Gold on the existing account). SKIPPED when it is not
    awaiting final approval any more (nothing changes)."""
    result = invites.approve_and_invite(application, actor, from_final=True)
    if result != invites.SKIPPED:
        logger.info("Gold %s confirmed by final approver %s", application.reference, actor.pk)
    return result


def clean_note(note):
    note = (note or "").replace("\x00", "").strip()  # NUL is refused by Postgres
    if len(note) > GoldApplication.NOTE_MAX:
        raise NoteTooLong(f"Keep the note to {GoldApplication.NOTE_MAX} characters.")
    return note


def send_back(application, actor, note=""):
    """A final approver's Send back: the application returns to the approvers' queue (status new), with who, when and the
    optional note, and every approver is emailed. Returns False when it was not awaiting final approval."""
    note = clean_note(note)
    with transaction.atomic():
        fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if fresh.status != GoldApplication.AWAITING_FINAL:
            return False
        fresh.status, fresh.sent_back_at, fresh.sent_back_by, fresh.sent_back_note = GoldApplication.NEW, timezone.now(), actor, note
        fresh.save()
    logger.info("Gold %s sent back by final approver %s", application.reference, actor.pk)
    _queue("gold.tasks.send_gold_sent_back_email", str(application.pk))
    application.refresh_from_db()
    return True
