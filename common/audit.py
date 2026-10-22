"""Audit helpers: client IP and login events."""
import logging

from django.conf import settings

logger = logging.getLogger("spa99.audit")


def client_ip(request):
    """Real client IP. X-Forwarded-For is only trusted behind our own proxy (settings.TRUST_FORWARDED_FOR)."""
    if request is None:
        return None
    if settings.TRUST_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def record_login_event(event, request, user=None, attempted_email=""):
    """Write one LoginEvent. Never raises: a broken audit log must not block a login."""
    from .models import LoginEvent

    try:
        meta = getattr(request, "META", {})
        return LoginEvent.objects.create(
            event=event,
            user=user if user is not None and user.pk else None,
            attempted_email=(attempted_email or getattr(user, "email", "") or "")[:254].lower(),
            ip_address=client_ip(request),
            user_agent=meta.get("HTTP_USER_AGENT", "")[:300],
        )
    except Exception:
        logger.exception("Could not write login audit event")
        return None
