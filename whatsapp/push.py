"""Web Push to the staff who can see the chats (VAPID, pywebpush). Everyone with an Office team level and at least one subscribed device
gets a notification for each new message from him, unless they muted. A device the push service says is gone (404, 410) is removed."""
import json
import logging

from django.conf import settings
from django.utils import timezone

from common import levels

from . import formatting
from .models import Message, PushSubscription

logger = logging.getLogger("spa99.whatsapp")

try:  # pywebpush is pinned in requirements.txt; tests replace `webpush`
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - a broken install must not break the site
    webpush, WebPushException = None, Exception


def configured():
    return bool(webpush and settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY and settings.VAPID_SUBJECT)


def body_for(message):
    """The notification text: the first line without its marks, or what kind of file it is."""
    if message.kind == Message.IMAGE:
        return "Sent a photo"
    if message.kind == Message.DOCUMENT:
        return f"Sent a PDF: {message.media_filename}" if message.media_filename else "Sent a PDF"
    if message.kind == Message.AUDIO:
        return "Sent a voice note"
    if message.kind == Message.VIDEO:
        return "Sent a video"
    if message.kind == Message.FILE:
        return "Sent a file"
    return formatting.plain(message.body)[:80] or "New message"


def payload_for(message):
    from . import services

    contact = message.contact
    return {"title": contact.display_name, "body": body_for(message), "url": services._office("office_whatsapp_thread", contact.pk), "tag": str(contact.pk)}


def recipients():
    """Subscriptions of unmuted staff with an Office level."""
    out = []
    for sub in PushSubscription.objects.filter(user__is_active=True).exclude(user__whatsapp_prefs__muted=True).select_related("user"):
        if levels.level_of(sub.user) != levels.NONE:
            out.append(sub)
    return out


def notify_inbound(message):
    """Send the push for one inbound message. Returns how many devices were sent to."""
    if not configured():
        return 0
    data = json.dumps(payload_for(message))
    sent = 0
    for sub in recipients():
        try:
            webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, data=data,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY, vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=3600)
            sub.last_used_at = timezone.now()
            sub.save(update_fields=["last_used_at"])
            sent += 1
        except WebPushException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status in (404, 410):
                sub.delete()
            else:
                logger.warning("Push failed (status %s)", status)
        except Exception:  # noqa: BLE001 - one bad device must not stop the others
            logger.exception("Push failed")
    return sent


def send_test(user):
    """'Send a test' on this staff member's devices. Returns how many were sent."""
    if not configured():
        return 0
    sent = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                    data=json.dumps({"title": "Spa 99 Office", "body": "Notifications are on.", "url": "/", "tag": "test"}),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY, vapid_claims={"sub": settings.VAPID_SUBJECT}, ttl=300)
            sent += 1
        except WebPushException as error:
            if getattr(getattr(error, "response", None), "status_code", None) in (404, 410):
                sub.delete()
        except Exception:  # noqa: BLE001
            logger.exception("Push test failed")
    return sent
