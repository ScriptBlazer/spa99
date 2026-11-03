"""Background jobs (django-q2; inline in tests). Only ids go into the queue: no message text sits in the task table."""
import logging

from . import push, services
from .models import Message

logger = logging.getLogger("spa99.whatsapp")


def send_message(message_id):
    """One Twilio send for a queued message. Returns 'sent', 'failed' or 'skipped' (taken already, or gone)."""
    message = Message.objects.select_related("contact", "template").filter(pk=message_id, direction=Message.OUT).first()
    return services.deliver(message) if message is not None else "skipped"


def process_inbound(message_id):
    """His message arrived: copy his file from Twilio into storage (if any), then notify the team."""
    message = Message.objects.select_related("contact").filter(pk=message_id, direction=Message.IN).first()
    if message is None:
        return "skipped"
    if message.media_source_url:
        services.store_media(message)
        message.refresh_from_db()
    return f"pushed {push.notify_inbound(message)}"


def sync_templates():
    """System > WhatsApp "Sync templates"."""
    return services.sync_templates()
