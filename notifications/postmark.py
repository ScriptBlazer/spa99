"""Postmark bounce and spam-complaint webhooks (the launch mail provider; SES feedback is in notifications/sns.py).

Postmark POSTs JSON to /postmark/webhook/ with HTTP Basic credentials taken from the webhook URL. A permanent bounce or a
spam complaint puts the address on the same suppression list as SES feedback (notifications.suppression). Soft and
transient bounces are not stored."""
import base64
import binascii
import hmac
import json
import logging

from django.conf import settings

from . import suppression
from .models import EmailSuppression

logger = logging.getLogger("spa99.email")

MAX_BODY_BYTES = 256 * 1024
# Bounce "Type" values that mean the address is bad for good (Postmark bounce API reference). Any bounce that made
# Postmark itself deactivate the address (Inactive true) is stored too. SoftBounce, Transient, AutoResponder etc. are not.
PERMANENT_TYPES = {"HardBounce", "BadEmailAddress", "ManuallyDeactivated"}
COMPLAINT_TYPES = {"SpamComplaint", "Unsubscribe"}  # Unsubscribe: the recipient asked to be removed, so treated like a complaint


def configured():
    return bool(settings.POSTMARK_WEBHOOK_USER and settings.POSTMARK_WEBHOOK_PASSWORD)


def authorised(header):
    """True when the Authorization header is Basic with exactly the configured user and password."""
    scheme, _, token = (header or "").partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        user, sep, password = base64.b64decode(token.strip(), validate=True).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    if not sep:
        return False
    # both comparisons always run, so timing does not reveal which part was wrong
    user_ok = hmac.compare_digest(user.encode(), settings.POSTMARK_WEBHOOK_USER.encode())
    password_ok = hmac.compare_digest(password.encode(), settings.POSTMARK_WEBHOOK_PASSWORD.encode())
    return user_ok and password_ok


def apply(record):
    """Act on one webhook record (a dict). Returns 1 when an address was recorded, else 0."""
    kind = _text(record.get("RecordType"))
    email = _text(record.get("Email"))
    feedback_id = str(record.get("ID") or record.get("MessageID") or "")
    if kind == "SpamComplaint":
        return int(suppression.add(email, EmailSuppression.COMPLAINT, feedback_id, _detail(record)))
    if kind == "Bounce":
        bounce_type = _text(record.get("Type"))
        if bounce_type in COMPLAINT_TYPES:
            return int(suppression.add(email, EmailSuppression.COMPLAINT, feedback_id, _detail(record)))
        if bounce_type in PERMANENT_TYPES or record.get("Inactive") is True:
            return int(suppression.add(email, EmailSuppression.HARD_BOUNCE, feedback_id, _detail(record)))
        logger.debug("Postmark feedback: %s bounce ignored", bounce_type or "unknown")
        return 0
    logger.debug("Postmark feedback: %s ignored", kind)
    return 0


def _text(value):
    """Only a string counts; a number, list or object becomes "" so the record is ignored (200, no retry)."""
    return value if isinstance(value, str) else ""


def _detail(record):
    text = f"{_text(record.get('Type'))} {_text(record.get('Details')) or _text(record.get('Description'))}".strip()
    return text[:300]


def handle(body):
    """Parse one POST body and act on it. Raises ValueError when it is not a JSON object."""
    try:
        record = json.loads(body)
    except (ValueError, RecursionError):
        raise ValueError("body is not JSON")
    if not isinstance(record, dict):
        raise ValueError("body is not an object")
    count = apply(record)
    logger.info("Postmark feedback: %s handled, %d address(es) recorded", _text(record.get("RecordType"))[:30], count)
    return count
