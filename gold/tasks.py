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
