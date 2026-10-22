"""Person-data services: register interest (sign-up), email verification, password reset, and GDPR export/delete
(UK GDPR). Other apps add their own sections to export/delete here."""
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from common.models import LoginEvent
from common.tasks import enqueue, erase_task_records
from gold import services as gold_services
from journey import services as journey_services
from journey.models import Answer, JourneySession, new_session_key
from notifications.models import EmailLog
from plans.models import Plan, SiteSettings

from . import tokens
from .models import InterestRegistration, User

logger = logging.getLogger("spa99.users")

DOUBLE_SUBMIT_WINDOW = timedelta(minutes=2)

PERSON_FIELDS = [
    "email", "public_id", "first_name", "last_name", "mobile", "date_of_birth", "email_verified_at",
    "marketing_consent", "marketing_consent_at", "privacy_accepted_version", "privacy_accepted_at",
    "men_only_accepted_at", "created_at", "updated_at", "last_login",
]


# ---------- register interest ----------

class RegistrationClosed(Exception):
    """Stage switch register_interest_open is off."""


class SignUpError(Exception):
    """Sign-up refused. `errors` is {field: [messages]}, safe to show."""

    def __init__(self, errors):
        super().__init__(errors)
        self.errors = errors


@dataclass
class SignUpResult:
    user: User
    created: bool


def email_is_registered(email):
    """Yes/no only. Used by the live 'already registered' check."""
    return User.objects.filter(email__iexact=(email or "").strip()).exists()


def interest_plans():
    """Plans a person can register interest in: visible monthly memberships (same rule as Plan.interest_allowed)."""
    return Plan.objects.filter(visible=True, kind=Plan.MONTHLY)


def interest_plan_slug(slug):
    """`slug` if a person can register interest in that plan, else '' (a stale or hand-typed link is just ignored)."""
    return slug if slug and interest_plans().filter(slug=slug).exists() else ""


def _plan_for(slug):
    if not slug:
        return None
    plan = interest_plans().filter(slug=slug).first()
    if plan is None:
        raise SignUpError({"plan": ["Choose one of the memberships."]})
    return plan


def _existing_double_submit(data):
    """A second click of the same form: same email and password, still unverified, created seconds ago."""
    existing = User.objects.filter(email__iexact=data["email"]).first()
    recent = existing and timezone.now() - existing.created_at < DOUBLE_SUBMIT_WINDOW
    if existing and recent and not existing.email_verified_at and existing.check_password(data["password"]):
        return existing
    return None


def register_interest(data, journey_session=None):
    """Create the account and the interest record from validated form data (see users.forms.SignUpForm).
    Links the journey session and queues the verification email. Returns SignUpResult."""
    site = SiteSettings.load()
    if not site.register_interest_open:
        raise RegistrationClosed
    if journey_session is not None and journey_session.user_id is not None:
        journey_session = None  # a session already owned by someone (shared device) is never linked to a new person
    again = _existing_double_submit(data)
    if again is not None:
        return SignUpResult(again, created=False)
    plan = _plan_for(data.get("plan"))

    errors = {}
    if User.objects.filter(email__iexact=data["email"]).exists():
        errors["email"] = ["That email is already registered. Sign in instead."]
    if User.objects.filter(mobile=data["mobile"]).exists():
        errors["mobile"] = ["That mobile number is already registered."]
    if errors:
        raise SignUpError(errors)

    now = timezone.now()
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                data["email"], data["password"],
                first_name=data["first_name"], last_name=data["last_name"], mobile=data["mobile"],
                date_of_birth=data["date_of_birth"],
                men_only_accepted_at=now,
                privacy_accepted_version=site.privacy_version, privacy_accepted_at=now,
                marketing_consent=bool(data.get("marketing_opt_in")),
                marketing_consent_at=now if data.get("marketing_opt_in") else None,
            )
            InterestRegistration.objects.create(
                user=user, plan=plan,
                source=InterestRegistration.JOURNEY if journey_session else InterestRegistration.DIRECT,
                journey_session=journey_session,
            )
            journey_services.link_user(journey_session, user)
            gold_services.link_user_applications(user)
    except IntegrityError:  # two people (or two clicks) raced for the same email or mobile
        raise SignUpError({"email": ["That email or mobile number is already registered."]}) from None
    queue_verification_email(user)
    return SignUpResult(user, created=True)


def set_interest(user, plan):
    """Change the plan a person is interested in (account page). History keeps the old one."""
    interest, _ = InterestRegistration.objects.get_or_create(user=user, defaults={"plan": plan})
    if interest.plan_id != (plan.pk if plan else None):
        interest.plan = plan
        interest.save()
    return interest


# ---------- verification and password reset ----------

def queue_verification_email(user):
    try:
        enqueue("users.tasks.send_verification_email", str(user.pk))
    except Exception:  # noqa: BLE001 - the account exists; the person can ask for a new link
        logger.exception("Could not queue the verification email for %s", user.pk)


def resend_verification(user):
    """Queue a fresh link, unless already verified. Returns True if queued."""
    if user is None or user.email_verified_at:
        return False
    queue_verification_email(user)
    return True


def verify_email(token):
    """Use a verification link. Returns (status, user): 'verified' (first use), 'already' (replayed, nobody is
    signed in by this), 'expired' or 'invalid'."""
    status, user = tokens.read_verify_token(token)
    if user is None:
        return status, None
    if user.email_verified_at:
        return tokens.ALREADY, user
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at", "updated_at"])
    try:
        enqueue("users.tasks.send_welcome_email", str(user.pk))
    except Exception:  # noqa: BLE001
        logger.exception("Could not queue the welcome email for %s", user.pk)
    return tokens.VERIFIED, user


def request_password_reset(email):
    """Queue a reset email if the address belongs to an active account. Always looks the same to the caller."""
    user = User.objects.filter(email__iexact=(email or "").strip(), is_active=True).first()
    if user is not None:
        try:
            enqueue("users.tasks.send_password_reset_email", str(user.pk))
        except Exception:  # noqa: BLE001
            logger.exception("Could not queue the password reset for %s", user.pk)
    return None


def reset_password(uidb64, token, new_password):
    """Set a new password from a reset link. Returns the user, or None if the link is bad/used/expired.
    Raises ValidationError (with plain messages) if the password is not allowed."""
    user = tokens.read_reset_token(uidb64, token)
    if user is None:
        return None
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    return user


# ---------- GDPR ----------

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
    return {
        "id": str(user.pk),
        "profile": profile,
        "interest": _export_interest(user),
        "journey_sessions": _export_sessions(user),
        "gold_applications": gold_services.export_applications(user.email),
        "emails": [
            {"template": e.template, "subject": e.subject, "status": e.status, "sent_at": _plain(e.sent_at)}
            for e in _email_logs(user.email).order_by("created_at")
        ],
        "login_events": logins,
        "history": history,
    }


def _email_logs(email):
    """Emails sent to the person, plus emails about them sent to someone else (Barry's Gold email)."""
    return EmailLog.objects.filter(Q(to__iexact=email) | Q(subject_email__iexact=email))


def _plain(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _export_interest(user):
    interest = InterestRegistration.objects.filter(user=user).select_related("plan").first()
    if interest is None:
        return None
    return {
        "plan": interest.plan.name if interest.plan else None, "source": interest.source,
        "registered_at": interest.created_at.isoformat(),
        "changes": [
            {"at": row.history_date.isoformat(), "plan_id": row.plan_id} for row in interest.history.order_by("history_date")
        ],
    }


def _export_sessions(user):
    sessions = JourneySession.objects.filter(user=user).select_related("suggested_plan").order_by("created_at")
    result = []
    for session in sessions:
        answers = [
            {
                "question": a.question.text, "options": [o.label for o in a.options.all()],
                "text": a.text_value, "skipped": a.skipped, "answered_at": a.answered_at.isoformat(),
            }
            for a in session.answers.select_related("question").prefetch_related("options").order_by("answered_at")
        ]
        result.append({
            "started_at": session.created_at.isoformat(), "device": session.device_type, "referrer": session.referrer,
            "utm_source": session.utm_source, "utm_medium": session.utm_medium, "utm_campaign": session.utm_campaign,
            "completed": session.completed,
            "suggested_plan": session.suggested_plan.name if session.suggested_plan else None,
            "gold_potential": session.gold_potential, "answers": answers,
        })
    return result


def _login_events(user):
    """Events linked to the person, plus failed attempts typed with their email (same set delete removes)."""
    return LoginEvent.objects.filter(Q(user=user) | Q(attempted_email__iexact=user.email))


def _anonymise_sessions(user):
    """Journey sessions are kept for the statistics but stop being about this person: unlinked, cookie value
    replaced, referrer and any typed text removed (also in the history rows)."""
    ids = list(JourneySession.objects.filter(user=user).values_list("pk", flat=True))
    for session_id in ids:
        JourneySession.objects.filter(pk=session_id).update(user=None, key=new_session_key(), referrer="")
    Answer.objects.filter(session_id__in=ids).update(text_value="")
    JourneySession.history.model.objects.filter(id__in=ids).update(user=None, key="", referrer="")
    Answer.history.model.objects.filter(session_id__in=ids).update(text_value="")
    return len(ids)


@transaction.atomic
def delete_user_data(user):
    """Erase a person: account, interest, Gold applications by their email, email log (including emails about them sent to staff), django-q task records, login events and the history
    rows that copy their details. Journey sessions are anonymised (kept for statistics, no longer linked).
    Erasure overrides the "history is never deleted" rule because history holds personal data."""
    pk, email = user.pk, user.email
    anonymised = _anonymise_sessions(user)
    removed_logins = _login_events(user).delete()[0]
    removed_emails = _email_logs(email).delete()[0]
    gold = gold_services.delete_applications(email)
    queue = erase_task_records([pk], ["users.tasks."])
    interest_ids = list(InterestRegistration.objects.filter(user=user).values_list("pk", flat=True))
    user.delete()  # cascades the InterestRegistration
    interest_history = InterestRegistration.history.model.objects.filter(id__in=interest_ids).delete()[0]
    removed_history = User.history.model.objects.filter(id=pk).delete()[0]
    return {
        "login_events": removed_logins, "history_rows": removed_history, "email_logs": removed_emails,
        "interest_history_rows": interest_history, "journey_sessions_anonymised": anonymised, **gold,
        "queue_records": gold["queue_records"] + queue,
    }

