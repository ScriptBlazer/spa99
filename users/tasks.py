"""Background tasks for account emails. They take only a user id and build links at send time, so no token is
ever stored in the task queue or the database. They return a plain status string, never the EmailLog: django-q
stores a task's return value, and that would keep the person's address in the queue tables after they delete
their data."""
from django.conf import settings

from notifications.services import send_templated, subject_for
from plans.models import SiteSettings

from . import tokens
from .models import User


def send_verification_email(user_id):
    user = User.objects.filter(pk=user_id).first()
    if user is None or user.email_verified_at:
        return None
    url = f"{settings.SITE_URL}/verify/{tokens.make_verify_token(user)}/"
    log = send_templated(
        "verify", [user.email], subject_for("verify"), {"first_name": user.first_name, "url": url},
        subject_email=user.email,
    )
    return log.status


def send_password_reset_email(user_id):
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return None
    uid, token = tokens.make_reset_link_parts(user)
    url = f"{settings.SITE_URL}/reset/{uid}/{token}/"
    log = send_templated(
        "password_reset", [user.email], subject_for("password_reset"), {"first_name": user.first_name, "url": url},
        subject_email=user.email,
    )
    return log.status


def send_welcome_email(user_id):
    user = User.objects.select_related("interest__plan").filter(pk=user_id).first()
    if user is None:
        return None
    interest = getattr(user, "interest", None)
    opening = SiteSettings.load().opening_label
    log = send_templated(
        "welcome", [user.email], subject_for("welcome"),
        {
            "first_name": user.first_name,
            "plan_name": interest.plan.name if interest and interest.plan else "",
            "account_id": user.public_id_display,
            "opening_text": f"and we plan to open in {opening}" if opening else "",
        },
        subject_email=user.email,
    )
    return log.status
