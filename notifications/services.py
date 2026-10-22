"""Sending email. Every send is logged (EmailLog). A failure is logged, never raised, so a broken mail server
cannot break a sign-up or a Gold application."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from plans.models import SiteSettings

from .models import EmailLog

logger = logging.getLogger("spa99.email")


def base_context():
    site = SiteSettings.load()
    return {
        "site_name": "Spa 99",
        "tagline": "Beyond Luxury",
        "contact_email": site.contact_email,
        "site_url": settings.SITE_URL,
        "address": "99 Vale Road, London N4 1PR",
    }


def send_templated(template, to, subject, context=None, cc=None):
    """Render notifications/emails/<template>.html and .txt, send, and log. Returns the EmailLog.
    `to` and `cc` are lists of addresses."""
    to, cc = list(to or []), list(cc or [])
    ctx = {**base_context(), **(context or {})}
    log = EmailLog(to=", ".join(to), cc=", ".join(cc), subject=subject[:300], template=template)
    try:
        text = render_to_string(f"notifications/emails/{template}.txt", ctx)
        html = render_to_string(f"notifications/emails/{template}.html", ctx)
        message = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to,
            cc=cc,
            reply_to=[ctx["contact_email"]],
        )
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        log.status, log.sent_at = EmailLog.SENT, timezone.now()
    except Exception as error:  # noqa: BLE001 - any failure is recorded, then the caller carries on
        logger.exception("Email %s to %s failed", template, to)
        log.status, log.error = EmailLog.FAILED, f"{type(error).__name__}: {error}"[:1000]
    log.save()
    return log
