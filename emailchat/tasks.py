"""Background jobs (django-q2; inline in tests). Only ids go into the queue: no email text and no file bytes sit in the task table."""
import logging

from django.utils import timezone

from whatsapp import push

from . import services
from .models import Message

logger = logging.getLogger("spa99.emailchat")


def send_message(message_id):
    """One send for a queued message. Returns 'sent', 'failed' or 'skipped' (taken already, or gone)."""
    message = Message.objects.select_related("thread").filter(pk=message_id, direction=Message.OUT).first()
    return services.deliver(message) if message is not None else "skipped"


def process_inbound(message_id):
    """His email arrived (the webhook stored it and its files): check each file's first bytes, then notify the team (never for spam)."""
    message = Message.objects.select_related("thread").filter(pk=message_id, direction=Message.IN).first()
    if message is None:
        return "skipped"
    try:
        services.check_files(message)
    except Exception:  # noqa: BLE001 - whatever went wrong with his files, the team is still told he wrote
        logger.exception("Could not check the files of email message %s", message.pk)
    if message.spam:
        return "spam, not pushed"
    if not Message.objects.filter(pk=message.pk, notified_at__isnull=True).update(notified_at=timezone.now()):  # the push is taken once, even if the task runs again
        return "already pushed"
    return f"pushed {push.notify_payload(services.push_payload(message))}"


def give_up_incomplete_scheduled():
    """Hourly (common/management/commands/register_schedules.py): emails incomplete over a day stop saying they are loading."""
    return f"gave up on {services.give_up_incomplete()} incomplete emails"
