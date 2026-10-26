"""The email suppression list: addresses SES told us bounce for good or complained. One place decides who may be emailed."""
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import EmailSuppression

logger = logging.getLogger("spa99.email")


def clean(email):
    return (email or "").strip().lower()


def suppressed_set(addresses):
    """The lower-cased addresses in `addresses` that are suppressed."""
    wanted = {clean(a) for a in addresses if clean(a)}
    if not wanted:
        return set()
    return set(EmailSuppression.objects.filter(email__in=wanted).values_list("email", flat=True))


def is_suppressed(email):
    return bool(suppressed_set([email]))


def add(email, reason, feedback_id="", detail=""):
    """Suppress an address. A repeat of the same feedback id changes nothing. Returns True when something was recorded.
    Invites and group-mailing rows sent to the address are then shown as bounced."""
    recorded = _add(email, reason, feedback_id, detail)
    if recorded:
        try:
            from mailings.invites import mark_bounced

            mark_bounced(email)
        except Exception:  # noqa: BLE001 - the suppression itself is what matters
            logger.exception("Could not mark invites as bounced")
    return recorded


def _add(email, reason, feedback_id="", detail=""):
    email = clean(email)
    if not email or "@" not in email:
        return False
    if len(email) > 254:  # cannot be a real address (and would not fit the column)
        logger.warning("Suppression skipped: address longer than 254 characters")
        return False
    now = timezone.now()
    detail = (detail or "")[:300]
    for _attempt in range(2):  # two deliveries can race to create the row: the loser updates it
        with transaction.atomic():
            row = EmailSuppression.objects.select_for_update().filter(email=email).first()
            if row is None:
                try:
                    EmailSuppression.objects.create(email=email, reason=reason, first_seen=now, last_seen=now,
                                                    last_feedback_id=feedback_id[:100], detail=detail)
                    return True
                except IntegrityError:
                    continue
            if feedback_id and row.last_feedback_id == feedback_id:
                return False
            row.count += 1
            row.last_seen, row.last_feedback_id, row.detail = now, feedback_id[:100], detail
            if reason == EmailSuppression.COMPLAINT:  # a complaint is the stronger reason
                row.reason = reason
            row.save()
            return True
    return False


def remove(email):
    """Take an address off the list. Returns True if it was there."""
    deleted, _ = EmailSuppression.objects.filter(email=clean(email)).delete()
    return bool(deleted)
