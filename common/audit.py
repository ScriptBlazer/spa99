"""Audit helpers: client IP and login events."""
import logging

from django.conf import settings

logger = logging.getLogger("spa99.audit")


def client_ip(request):
    """Real client IP.

    Behind our own proxy (settings.TRUST_FORWARDED_FOR) two things are trusted, in this order:
      1. the header named by settings.CLIENT_IP_HEADER (off when empty). Caddy writes it from `{client_ip}`, which it
         works out from Cloudflare's CF-Connecting-IP only when the connection really came from a Cloudflare range
         (see the Caddyfile), and overwrites whatever the visitor sent. This is the one that cannot be forged.
      2. the first X-Forwarded-For entry (fine with Caddy alone, but a visitor can put a fake first entry when
         Cloudflare is in front, so do not rely on it there).
    Anywhere else it is the socket address."""
    if request is None:
        return None
    if settings.TRUST_FORWARDED_FOR:
        header = getattr(settings, "CLIENT_IP_HEADER", "")
        if header:
            value = request.META.get("HTTP_" + header.upper().replace("-", "_"), "").strip()
            if value:
                return value
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
