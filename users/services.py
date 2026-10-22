"""Person-data services. GDPR export and delete (UK GDPR). Other apps will add their own sections later."""
from django.db import transaction
from django.db.models import Q

from common.models import LoginEvent

from .models import User

PERSON_FIELDS = [
    "email", "public_id", "first_name", "last_name", "mobile", "date_of_birth", "email_verified_at",
    "marketing_consent", "marketing_consent_at", "privacy_accepted_version", "privacy_accepted_at",
    "created_at", "updated_at", "last_login",
]


def export_user_data(user):
    """Everything we hold about a person, as plain JSON-friendly data."""
    profile = {name: getattr(user, name) for name in PERSON_FIELDS}
    profile = {key: (value.isoformat() if hasattr(value, "isoformat") else value) for key, value in profile.items()}
    logins = [
        {
            "event": e.event, "at": e.created_at.isoformat(), "attempted_email": e.attempted_email,
            "ip_address": e.ip_address, "user_agent": e.user_agent,
        }
        for e in _login_events(user).order_by("created_at")
    ]
    history = [
        {
            "changed_at": row.history_date.isoformat(), "change": row.get_history_type_display(),
            **{name: _plain(getattr(row, name)) for name in PERSON_FIELDS if name != "last_login" and hasattr(row, name)},
        }
        for row in User.history.filter(id=user.pk).order_by("history_date")
    ]
    return {"id": str(user.pk), "profile": profile, "login_events": logins, "history": history}


def _plain(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _login_events(user):
    """Events linked to the person, plus failed attempts typed with their email (same set delete removes)."""
    return LoginEvent.objects.filter(Q(user=user) | Q(attempted_email__iexact=user.email))


@transaction.atomic
def delete_user_data(user):
    """Erase a person: account, login events and the history rows that copy their details.
    Erasure overrides the "history is never deleted" rule because history holds personal data."""
    pk = user.pk
    removed_logins = _login_events(user).delete()[0]
    user.delete()
    removed_history = User.history.model.objects.filter(id=pk).delete()[0]
    return {"login_events": removed_logins, "history_rows": removed_history}
