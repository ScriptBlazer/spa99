"""Person-data services. GDPR export and delete (UK GDPR). Other apps will add their own sections later."""
from django.db import transaction

from common.models import LoginEvent

from .models import User

PERSON_FIELDS = [
    "email", "public_id", "first_name", "last_name", "mobile", "date_of_birth", "email_verified_at",
    "marketing_consent", "marketing_consent_at", "privacy_accepted_version", "privacy_accepted_at",
    "status", "created_at", "updated_at", "last_login",
]


def export_user_data(user):
    """Everything we hold about a person, as plain JSON-friendly data."""
    profile = {name: getattr(user, name) for name in PERSON_FIELDS}
    profile = {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in profile.items()}
    logins = [
        {"event": e.event, "at": e.created_at.isoformat(), "ip_address": e.ip_address, "user_agent": e.user_agent}
        for e in LoginEvent.objects.filter(user=user).order_by("created_at")
    ]
    return {"id": str(user.pk), "profile": profile, "login_events": logins}


@transaction.atomic
def delete_user_data(user):
    """Erase a person: account, login events and the history rows that copy their details.
    Erasure overrides the "history is never deleted" rule because history holds personal data."""
    pk, email = user.pk, user.email
    removed_logins = LoginEvent.objects.filter(user=user).delete()[0]
    removed_logins += LoginEvent.objects.filter(attempted_email__iexact=email).delete()[0]
    user.delete()
    removed_history = User.history.model.objects.filter(id=pk).delete()[0]
    return {"login_events": removed_logins, "history_rows": removed_history}
