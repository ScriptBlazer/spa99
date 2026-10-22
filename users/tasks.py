"""Background tasks for account emails. They take only a user id and build links at send time, so no token is
ever stored in the task queue or the database."""
from django.conf import settings

from notifications.services import send_templated
from plans.models import SiteSettings

from . import tokens
from .models import User


def send_verification_email(user_id):
    user = User.objects.filter(pk=user_id).first()
    if user is None or user.email_verified_at:
        return None
    url = f"{settings.SITE_URL}/verify/{tokens.make_verify_token(user)}/"
    return send_templated("verify", [user.email], "Confirm your email for Spa 99", {"first_name": user.first_name, "url": url})


def send_password_reset_email(user_id):
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return None
    uid, token = tokens.make_reset_link_parts(user)
    url = f"{settings.SITE_URL}/reset/{uid}/{token}/"
    return send_templated(
        "password_reset", [user.email], "Reset your Spa 99 password", {"first_name": user.first_name, "url": url}
    )


def send_welcome_email(user_id):
    user = User.objects.select_related("interest__plan").filter(pk=user_id).first()
    if user is None:
        return None
    interest = getattr(user, "interest", None)
    opening = SiteSettings.load().opening_date
    return send_templated(
        "welcome", [user.email], "Welcome to Spa 99",
        {
            "first_name": user.first_name,
            "plan_name": interest.plan.name if interest and interest.plan else "",
            "account_id": user.public_id_display,
            "opening_text": f"and we plan to open on {opening.day} {opening:%B %Y}" if opening else "",
        },
    )
