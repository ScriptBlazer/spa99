"""The System bounce log: every Postmark Bounce and SpamComplaint record, soft ones too (EmailBounce). Suppression is separate."""
import datetime
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import EmailBounce

logger = logging.getLogger("spa99.email")

RETENTION_DAYS = 365
SOFT_TYPES = {"SoftBounce", "Transient", "DnsError", "MailboxFull", "SMTPApiError", "Blocked", "AutoResponder"}
HARD_TYPES = {"HardBounce", "BadEmailAddress", "ManuallyDeactivated"}
COMPLAINT_TYPES = {"SpamComplaint", "Unsubscribe"}


def _text(value):
    return value if isinstance(value, str) else ""


def when(record, *fields):
    """The first of these fields that parses as a date, else now."""
    for field in fields:
        parsed = parse_datetime(_text(record.get(field))[:40]) if _text(record.get(field)) else None
        if parsed is not None:
            return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed, datetime.timezone.utc)
    return timezone.now()


def kind_of(record, record_type):
    bounce_type = _text(record.get("Type"))
    if record_type == "SpamComplaint" or bounce_type in COMPLAINT_TYPES:
        return EmailBounce.COMPLAINT
    if bounce_type in HARD_TYPES or record.get("Inactive") is True:
        return EmailBounce.HARD
    return EmailBounce.SOFT if bounce_type in SOFT_TYPES else EmailBounce.OTHER


def record(data, record_type):
    """Store one record unless its Postmark id was stored already. Returns True when a row was added."""
    email = _text(data.get("Email")).strip().lower()
    if not email or len(email) > 254 or "\x00" in email:
        return False
    record_id = str(data.get("ID") or "")[:100]
    if record_id and EmailBounce.objects.filter(record_id=record_id).exists():
        return False
    bounce_type = _text(data.get("Type")) or record_type
    detail = f"{_text(data.get('Details')) or _text(data.get('Description'))}".strip()[:300]
    try:
        with transaction.atomic():
            EmailBounce.objects.create(
                email=email, kind=kind_of(data, record_type), postmark_type=bounce_type[:60], detail=detail, record_id=record_id,
                message_id=_text(data.get("MessageID"))[:100], received_at=when(data, "BouncedAt", "ReceivedAt"))
    except IntegrityError:  # two deliveries of the same record raced
        return False
    return True


def prune(days=RETENTION_DAYS):
    return EmailBounce.objects.filter(received_at__lt=timezone.now() - datetime.timedelta(days=days)).delete()[0]
