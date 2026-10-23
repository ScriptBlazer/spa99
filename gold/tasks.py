"""Background tasks for Gold emails (run by django-q2; inline in tests)."""
from django.utils import timezone

from notifications.services import send_templated, subject_for
from plans.models import SiteSettings

from . import services
from .models import GoldApplication


def send_gold_emails(application_id, acknowledge=True):
    """Email Barry (to + cc from Site settings), then thank the applicant. The result is stored on the application
    so Control can show 'email not sent' with a resend button. Returns a status string, never the EmailLog (django-q
    would keep the applicant's details in its result table)."""
    application = GoldApplication.objects.select_related("repeat_of").get(pk=application_id)
    context = services.barry_email_context(application)
    recipients = context.pop("recipients")
    cc = SiteSettings.load().gold_alert_cc_list
    log = send_templated(
        "gold_barry", recipients, services.barry_subject(application), context, cc=cc, subject_email=application.email
    )
    if log.status == log.SENT:
        application.email_sent_at, application.email_error = timezone.now(), ""
    else:
        application.email_error = log.error[:300]
    application.save(update_fields=["email_sent_at", "email_error", "updated_at"])
    if acknowledge and application.email:
        send_templated(
            "gold_ack", [application.email], subject_for("gold_ack"),
            {"first_name": application.first_name, "reference": application.reference},
            subject_email=application.email,
        )
    return log.status


def send_gold_invite_email(invite_id):
    """The 'set up your account' email. Takes only the invite id and builds the link now, so no token sits in the
    queue. Returns a status string, never the EmailLog."""
    from django.conf import settings

    from .invites import INVITE_DAYS, make_token
    from .models import GoldInvite

    invite = GoldInvite.objects.select_related("application").filter(pk=invite_id).first()
    if invite is None or not invite.is_usable:
        return None
    application = invite.application
    url = f"{settings.SITE_URL}/gold/invite/{make_token(invite)}/"
    log = send_templated(
        "gold_invite", [application.email], subject_for("gold_invite"),
        {"first_name": application.first_name, "url": url, "valid_days": INVITE_DAYS},
        subject_email=application.email,
    )
    if log.status == log.SENT:
        invite.sent_at = timezone.now()
        invite.save(update_fields=["sent_at", "updated_at"])
    return log.status


def send_gold_active_email(application_id):
    from django.conf import settings

    application = GoldApplication.objects.filter(pk=application_id).first()
    if application is None:
        return None
    log = send_templated(
        "gold_active", [application.email], subject_for("gold_active"),
        {"first_name": application.first_name, "url": f"{settings.SITE_URL}/account/"},
        subject_email=application.email,
    )
    return log.status
