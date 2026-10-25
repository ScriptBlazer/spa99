"""Background tasks for Gold emails (run by django-q2; inline in tests)."""
import logging

from django.conf import settings
from django.utils import timezone

from plans.models import SiteSettings
from notifications.services import send_templated, subject_for

from . import approval, services
from .models import GoldApplication


logger = logging.getLogger("spa99.email")
_warned = []


def _warn_no_approver_once():
    if not _warned:
        _warned.append(True)
        logger.warning("There are no Gold approvers (System > Approval): Gold application emails are not sent to anyone.")


def send_gold_emails(application_id, acknowledge=True):
    """Email the approvers (the team members picked in System > Approval, each at their own address; the CC list is in
    System > Emails), then thank the applicant. The result is stored on the application so Control can show 'email not
    sent' with a resend button. Returns a status string, never the EmailLog (django-q2 would keep the applicant's details
    in its result table)."""
    application = GoldApplication.objects.select_related("repeat_of").get(pk=application_id)
    site = SiteSettings.load()
    recipients, cc = approval.approver_addresses(), site.approver_cc_list
    if recipients:
        log = send_templated(
            "gold_approver", recipients, services.approver_subject(application),
            services.approver_email_context(application), cc=cc, subject_email=application.email,
        )
        status = log.status
        if log.status == log.SENT:
            application.email_sent_at, application.email_error = timezone.now(), ""
        else:
            application.email_error = log.error[:300]
    else:  # nobody to send to: record it (Control shows 'email not sent'), warn once, carry on
        _warn_no_approver_once()
        status = "no_recipients"
        application.email_error = "There are no approvers (System > Approval)."
    application.save(update_fields=["email_sent_at", "email_error", "updated_at"])
    if acknowledge and application.email:
        send_templated(
            "gold_ack", [application.email], subject_for("gold_ack"),
            {"first_name": application.first_name, "reference": application.reference},
            subject_email=application.email,
        )
    return status


def _send_to_group(template, application_id, people_addresses, context_builder):
    application = GoldApplication.objects.select_related("repeat_of", "sent_back_by").filter(pk=application_id).first()
    if application is None:
        return None
    recipients = people_addresses()
    if not recipients:
        logger.warning("No one to email for %s (%s): check System > Approval.", template, application.reference)
        return "no_recipients"
    subject = subject_for(template, name=application.full_name)
    log = send_templated(template, recipients, subject, context_builder(application),
                         cc=SiteSettings.load().approver_cc_list, subject_email=application.email)
    return log.status


def send_gold_final_email(application_id):
    """To every final approver: Confirm / Send back, with signed links built now (no token sits in the queue). Only while
    the application is still awaiting final approval. Returns a status string, never the EmailLog."""
    application = GoldApplication.objects.filter(pk=application_id).first()
    if application is None or application.status != GoldApplication.AWAITING_FINAL:
        return None
    return _send_to_group("gold_final", application_id, approval.final_approver_addresses, approval.final_email_context)


def send_gold_sent_back_email(application_id):
    """To every approver after a final approver sent it back: 'approved, but the potential is Low. Are you sure?' with the note
    and the normal approve / decline links. Returns a status string."""
    application = GoldApplication.objects.filter(pk=application_id).first()
    if application is None or application.sent_back_at is None or application.status not in GoldApplication.WAITING:
        return None
    return _send_to_group("gold_sent_back", application_id, approval.approver_addresses, approval.sent_back_email_context)


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
