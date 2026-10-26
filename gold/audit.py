"""The Gold audit trail: one helper writes every row (docs/features/gold-actions.md). Call it inside the same transaction
as the change it describes, so the change and its record stand or fall together."""
from datetime import timedelta

from django.utils import timezone

from .models import ApplicationEvent as E

OFFICE, EMAIL_LINK, ADMIN, SYSTEM, SHELL = E.OFFICE, E.EMAIL_LINK, E.ADMIN, E.SYSTEM, E.SHELL
CHANNELS = {OFFICE, EMAIL_LINK, ADMIN, SYSTEM, SHELL}
DUPLICATE_WINDOW = timedelta(seconds=60)


def label_for(user):
    """'Name (email)' or the email: a snapshot, so the trail still reads right after an account is renamed or deleted."""
    if user is None or not getattr(user, "pk", None):
        return ""
    name = (user.get_full_name() or "").strip()
    return (f"{name} ({user.email})" if name else user.email)[:254]


def clean_text(text):
    return (text or "").replace("\x00", "").strip()  # NUL is refused by Postgres


def record(application, action, actor=None, channel=SYSTEM, from_status="", to_status="", message="", meta=None, at=None):
    """Append one event and return it. `from_status`/`to_status` are left empty when the status did not change."""
    if channel not in CHANNELS:
        channel = SYSTEM
    return E.objects.create(
        application=application, at=at or timezone.now(), actor=actor if getattr(actor, "pk", None) else None, actor_label=label_for(actor),
        action=action, channel=channel, from_status=from_status or "", to_status=to_status or "", message=clean_text(message), meta=meta or {})


def is_repeat(application, action, actor, message):
    """The same text from the same person on the same application in the last minute: a double submit."""
    rows = E.objects.filter(application=application, action=action, message=clean_text(message), at__gte=timezone.now() - DUPLICATE_WINDOW)
    rows = rows.filter(actor=actor) if getattr(actor, "pk", None) else rows.filter(actor__isnull=True)
    return rows.exists()


def timeline(application):
    """Newest first, for the Office page."""
    return list(application.events.select_related("actor"))
