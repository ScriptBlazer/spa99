"""The approver's Respond and Add note (Approve, Decline and the final steps live in gold.approval and gold.invites). Every
action writes the audit trail inside the transaction that changes the application (docs/features/gold-actions.md)."""
import logging

from django.db import transaction

from common.tasks import enqueue

from . import audit
from .models import ApplicationEvent, GoldApplication

logger = logging.getLogger("spa99.gold")

DONE, CLOSED, DUPLICATE = "done", "closed", "duplicate"  # results: CLOSED = already approved or declined; DUPLICATE = a double submit
OPEN = (GoldApplication.NEW, GoldApplication.CONTACTED, GoldApplication.AWAITING_FINAL)


def respond(application, actor, message, channel=audit.OFFICE):
    """Message the applicant (email, editable template `gold_respond`, Reply-To is the contact address). New becomes Contacted;
    the application stays open. Awaiting final approval keeps its status. Returns (result, event)."""
    message = audit.clean_text(message)
    with transaction.atomic():
        fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if fresh.status not in OPEN:
            return CLOSED, None
        if audit.is_repeat(fresh, ApplicationEvent.RESPONDED, actor, message):
            return DUPLICATE, None
        before = fresh.status
        if before == GoldApplication.NEW:
            fresh.status = GoldApplication.CONTACTED
            fresh.save(update_fields=["status", "updated_at"])
        event = audit.record(fresh, ApplicationEvent.RESPONDED, actor=actor, channel=channel, message=message,
                             from_status=before if fresh.status != before else "", to_status=fresh.status if fresh.status != before else "",
                             meta={"email_applicant": True})
    application.refresh_from_db()
    try:
        enqueue("gold.tasks.send_gold_applicant_email", str(application.pk), str(event.pk))
    except Exception:  # noqa: BLE001 - the response is recorded; a queue problem is shown as "email not sent" by the trail
        logger.exception("Could not queue the Gold response email for %s", application.reference)
    return DONE, event


def add_note(application, actor, note, channel=audit.OFFICE):
    """An internal note (e.g. 'He replied by phone: ...'). Allowed in any status. Returns (result, event)."""
    note = audit.clean_text(note)
    with transaction.atomic():
        fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if audit.is_repeat(fresh, ApplicationEvent.NOTE_ADDED, actor, note):
            return DUPLICATE, None
        event = audit.record(fresh, ApplicationEvent.NOTE_ADDED, actor=actor, channel=channel, message=note)
    return DONE, event
