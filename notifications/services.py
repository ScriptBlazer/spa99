"""Sending email. Every send is logged (EmailLog). A failure is logged, never raised, so a broken mail server
cannot break a sign-up or a Gold application."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from plans.models import SiteSettings

from .models import EmailLog, NotificationTemplate
from .seed import DEFAULT_SUBJECTS

logger = logging.getLogger("spa99.email")


def base_context():
    site = SiteSettings.load()
    return {
        "site_name": "Spa 99",
        "tagline": "Beyond Luxury",
        "contact_email": site.contact_email,
        "site_url": settings.SITE_URL,
        "address": site.address_one_line,
    }


def subject_for(key, **values):
    """The subject line for an email: the NotificationTemplate row (edited in Control), or the built-in default.
    {placeholders} are replaced from `values`; unknown ones are left as typed."""
    row = NotificationTemplate.objects.filter(key=key).first()
    text = row.subject if row else DEFAULT_SUBJECTS[key][0]
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def send_templated(template, to, subject, context=None, cc=None, subject_email=""):
    """Render notifications/emails/<template>.html and .txt, send, and log. Returns the EmailLog.
    `to` and `cc` are lists of addresses. `subject_email` is the person the message is about when it goes to
    someone else (Barry's Gold email), so deleting that person's data finds the log row."""
    to, cc = list(to or []), list(cc or [])
    ctx = {**base_context(), **(context or {})}
    log = EmailLog(
        to=", ".join(to), cc=", ".join(cc), subject=subject[:300], template=template,
        subject_email=(subject_email or "").strip().lower(),
    )
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
        log.status, log.error = EmailLog.FAILED, f"{type(error).__name__}: {error}"[:1000]
    log.save()
    if log.status == EmailLog.FAILED:  # no address, no traceback (SMTP errors repeat the address): the log row has the detail
        logger.error("Email %s failed (email log %s, %s)", template, log.pk, log.error.split(":")[0])
    return log
