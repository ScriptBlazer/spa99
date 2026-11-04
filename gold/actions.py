"""The approver's WhatsApp contact mark and Send guide (Approve, Decline and the final steps live in gold.approval and gold.invites). Every
action writes the audit trail inside the transaction that changes the application (docs/features/gold-actions.md)."""
import logging

from django.db import transaction

from common.tasks import enqueue
from plans.models import SiteSettings

from . import audit
from .models import ApplicationEvent, GoldApplication

logger = logging.getLogger("spa99.gold")

DONE, CLOSED, DUPLICATE, NO_GUIDE = "done", "closed", "duplicate", "no_guide"  # results: CLOSED = already approved or declined; DUPLICATE = a double submit
OPEN = (GoldApplication.NEW, GoldApplication.CONTACTED, GoldApplication.AWAITING_FINAL)


def whatsapp_sent(application, actor, text="", channel=audit.OFFICE, via="whatsapp"):
    """A WhatsApp (or, `via="email"`, an email from the Email button) went to the applicant (it replaces Respond): New becomes Contacted, with an audit event. Only the
    first message does anything; the application stays open and the text is in the chat, not repeated here. Returns True when the
    status changed."""
    with transaction.atomic():
        fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if fresh.status != GoldApplication.NEW:
            return False
        fresh.status = GoldApplication.CONTACTED
        fresh.save(update_fields=["status", "updated_at"])
        audit.record(fresh, ApplicationEvent.RESPONDED, actor=actor, channel=channel, from_status=GoldApplication.NEW, to_status=GoldApplication.CONTACTED, meta={via: True})
    application.refresh_from_db()
    return True


def send_guide(application, actor, channel=audit.OFFICE):
    """Email the applicant the Gold Card guide (the PDF uploaded in System, attached; template `gold_guide`, From the site sender,
    Reply-To the contact address). Any status. Returns (result, event); NO_GUIDE when no PDF is uploaded."""
    if not SiteSettings.load().gold_guide:
        return NO_GUIDE, None
    with transaction.atomic():
        fresh = GoldApplication.objects.select_for_update().get(pk=application.pk)
        if audit.is_repeat(fresh, ApplicationEvent.GUIDE_SENT, actor, ""):
            return DUPLICATE, None
        event = audit.record(fresh, ApplicationEvent.GUIDE_SENT, actor=actor, channel=channel, meta={"email_applicant": True})
    try:
        enqueue("gold.tasks.send_gold_guide_email", str(application.pk), str(event.pk))
    except Exception:  # noqa: BLE001 - the send is recorded; a queue problem is logged
        logger.exception("Could not queue the Gold guide email for %s", application.reference)
    return DONE, event


@transaction.atomic
def delete_application(application, actor, request=None):
    """Delete a Gold application and everything of it: its events (the audit trail), invites, history rows, the WhatsApp chats linked to it (unless an account owns them), and the queue records of
    its email tasks. For tests and junk (Admin and up, the view guards it). Notes belong to the person's email and stay. The deletion
    is written to the System change log (who, when, reference, applicant email). Returns the reference."""
    from common.tasks import erase_task_records
    from system import services as system_services

    from .models import GoldInvite

    pk, reference, email = application.pk, application.reference, application.email
    invite_ids = list(GoldInvite.objects.filter(application_id=pk).values_list("pk", flat=True))
    from whatsapp import services as whatsapp

    whatsapp.erase_for_application(application)  # an applicant with no account has no person or lead page to erase this from: it goes with the application
    application.delete()  # events and invites go with it (Django's cascade; the trail refuses only a direct delete)
    GoldApplication.history.model.objects.filter(id=pk).delete()
    erase_task_records([pk, *invite_ids], ["gold.tasks."])
    system_services.record_deleted(actor, "gold", "gold.goldapplication", pk, f"{reference} ({email})", f"Deleted Gold application {reference} ({email})", request=request)
    return reference
