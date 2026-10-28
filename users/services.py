"""Person-data services: register interest (sign-up), email verification, password reset, and GDPR export/delete
(UK GDPR). Other apps add their own sections to export/delete here."""
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from chat import services as chat_services
from common.models import LoginEvent
from common.tasks import enqueue, erase_task_records
from gold import services as gold_services
from insights import metrics
from journey import services as journey_services
from journey.models import Answer, JourneySession, new_session_key
from notifications.models import EmailLog
from plans.models import Plan, SiteSettings

from . import tokens
from plans import sales as sale_services

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
            interest = InterestRegistration.objects.create(
                user=user, plan=plan,
                source=InterestRegistration.JOURNEY if journey_session else InterestRegistration.DIRECT,
                journey_session=journey_session, **sale_services.snapshot_fields(plan),
            )
            metrics.registered(plan.slug if plan else None, interest.source, interest.created_at, marketing=user.marketing_consent)
            journey_services.link_user(journey_session, user)  # this browser's own session; Gold applications and other leads wait for the verify
    except IntegrityError:  # two people (or two clicks) raced for the same email or mobile
        raise SignUpError({"email": ["That email or mobile number is already registered."]}) from None
    _after_registration(user, bool(data.get("marketing_opt_in")))
    queue_verification_email(user)
    return SignUpResult(user, created=True)


def _after_registration(user, opted_in):
    """Invites for this address become 'registered'; ticking the news box lifts an earlier unsubscribe. Never raises."""
    from mailings import invites, optout

    invites.on_registered(user)
    if opted_in:
        try:
            optout.clear(user.email)
        except Exception:  # noqa: BLE001
            logger.exception("Could not clear the unsubscribe for a new account")


def link_earlier_data(user):
    """The account's email is now its owner's: attach the journeys that left this email at the gate and the Gold
    applications made with it (only those nobody owns). Idempotent; logs counts only. When something moved, the Office
    figures are refreshed in the background so the person counts once (counting rule C1/C5). Returns (sessions, applications)."""
    sessions = journey_services.link_leads(user)
    applications = gold_services.link_user_applications(user)
    if sessions or applications:
        from office import snapshots

        snapshots.request_refresh()
        logger.info("Linked %s journey(s) and %s Gold application(s) to account %s", sessions, applications, user.pk)
    return sessions, applications


def set_interest(user, plan):
    """Change the plan a person is interested in (account page). History keeps the old one."""
    with transaction.atomic():
        interest, created = InterestRegistration.objects.get_or_create(user=user, defaults={"plan": plan, **sale_services.snapshot_fields(plan)})
        if created:
            metrics.registered(plan.slug if plan else None, interest.source, interest.created_at, marketing=user.marketing_consent)
        elif interest.plan_id != (plan.pk if plan else None):
            for name, value in sale_services.snapshot_fields(plan, held=interest).items():
                setattr(interest, name, value)  # the kept sale price follows the plan rules (plans.sales.snapshot_fields)
            interest.plan = plan
            interest.save()  # the plan split follows this save (insights.signals), so the admin path counts too
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
    with transaction.atomic():
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at", "updated_at"])
        metrics.email_verified(user.email_verified_at)
        link_earlier_data(user)  # the address is proven: earlier leads and applications with it become his
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
    had_password = user.has_usable_password()  # a team member choosing a first password from an invite had none
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    if had_password:
        password_changed(user)
    return user


def password_changed(user):
    """Queue the "your password was changed" email. Called after a signed-in change and a completed reset (never after a
    first password from an invite, never for an admin or command setting one). Never raises."""
    try:
        enqueue("users.tasks.send_password_changed_email", str(user.pk), timezone.now().isoformat())
    except Exception:  # noqa: BLE001
        logger.exception("Could not queue the password-changed email for %s", user.pk)


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
    delivery = getattr(user, "approver_delivery", None)
    return {
        "id": str(user.pk),
        "profile": profile,
        **({"approval_emails": {"use_account_email": delivery.use_account_email, "other_email": delivery.other_email}} if delivery else {}),
        "interest": _export_interest(user),
        "journey_sessions": _export_sessions(user),
        "chats": chat_services.export_conversations(user=user, email=user.email if user.email_verified_at else None),
        "gold_applications": gold_services.export_applications(user.email) if user.email_verified_at else [],  # by email only once the address is proven his
        "emails": [
            {"template": e.template, "subject": e.subject, "status": e.status, "sent_at": _plain(e.sent_at)}
            for e in _email_logs(user.email).order_by("created_at") if user.email_verified_at
        ],
        "group_emails": [
            {"mailing": r.mailing.subject, "status": r.status, "sent_at": _plain(r.sent_at)}
            for r in _mailing_rows(user).select_related("mailing").order_by("created_at")
        ],
        "invites": [
            {"name": i.name, "status": i.status, "sent_at": _plain(i.sent_at), "opened_at": _plain(i.opened_at), "registered_at": _plain(i.registered_at)}
            for i in _invites(user.email).order_by("created_at")
        ],
        "login_events": logins,
        "history": history,
    }


def _email_logs(email):
    """Emails sent to the person, plus emails about them sent to someone else (Barry's Gold email)."""
    return EmailLog.objects.filter(Q(to__iexact=email) | Q(subject_email__iexact=email))


def _mailing_rows(user):
    """Group-send rows for the person (by account or address)."""
    from mailings.models import MailingRecipient

    return MailingRecipient.objects.filter(Q(user=user) | Q(email__iexact=user.email))


def _invites(email):
    from mailings.models import Invite

    return Invite.objects.filter(email__iexact=email)


def _plain(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _export_interest(user):
    interest = InterestRegistration.objects.filter(user=user).select_related("plan").first()
    if interest is None:
        return None
    return {
        "plan": interest.plan.name if interest.plan else None, "source": interest.source,
        "registered_at": interest.created_at.isoformat(),
        "sale_price": {"sale": interest.sale_name, "percent_off": interest.sale_percent_off, "months": interest.sale_months,
                       "locked_at": _plain(interest.sale_locked_at)} if interest.sale_percent_off else None,
        "changes": [
            {"at": row.history_date.isoformat(), "plan_id": row.plan_id} for row in interest.history.order_by("history_date")
        ],
    }


def _export_sessions(user):
    by_email = Q(lead_email__iexact=user.email) if user.email_verified_at else Q(pk__in=[])  # an unproven address is not his
    sessions = JourneySession.objects.filter(Q(user=user) | by_email).select_related("suggested_plan").order_by("created_at")
    result = []
    for session in sessions:
        if session.user_id != user.pk:  # matched only by the address he gave: his lead details, nothing more about that visit
            result.append({"started_at": session.created_at.isoformat(), "lead_email": session.lead_email, "lead_at": _plain(session.lead_at)})
            continue
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
            "utm_term": session.utm_term, "utm_content": session.utm_content,
            "lead_email": session.lead_email, "lead_at": _plain(session.lead_at),  # the address given before the result
            "completed": session.completed, "completed_at": _plain(session.completed_at),
            "suggested_plan": session.suggested_plan.name if session.suggested_plan else None,
            "suggestion_detail": session.suggestion_detail,
            "gold_potential": session.gold_potential, "gold_score": session.gold_score, "answers": answers,
        })
    return result


def _login_events(user):
    """Events linked to the person, plus failed attempts typed with their email (same set delete removes)."""
    return LoginEvent.objects.filter(Q(user=user) | Q(attempted_email__iexact=user.email))


def _anonymise_sessions(user):
    """Journey sessions are kept for the statistics but stop being about this person: unlinked, cookie value
    replaced, person key cleared, referrer and any typed text removed (also in the history rows)."""
    ids = list(JourneySession.objects.filter(user=user).values_list("pk", flat=True))
    for session_id in ids:
        JourneySession.objects.filter(pk=session_id).update(user=None, key=new_session_key(), person_key="", referrer="",
                                                            lead_email="", lead_at=None, lead_privacy_version="")
    Answer.objects.filter(session_id__in=ids).update(text_value="")
    JourneySession.history.model.objects.filter(id__in=ids).update(user=None, key="", person_key="", referrer="",
                                                                   lead_email="", lead_at=None, lead_privacy_version="")
    Answer.history.model.objects.filter(session_id__in=ids).update(text_value="")
    return len(ids)


@transaction.atomic
def delete_user_data(user):
    """Erase a person: account, interest, Gold applications by their email, email log (including emails about them sent to staff), django-q task records, login events and the history
    rows that copy their details. Journey sessions are anonymised (kept for statistics, no longer linked).
    Erasure overrides the "history is never deleted" rule because history holds personal data."""
    pk, email = user.pk, user.email
    chat_services.erase_conversations(user=user)  # before the sessions are unlinked (chats are also found through the account's sessions)
    anonymised = _anonymise_sessions(user)
    proven = bool(user.email_verified_at)  # rows found only by email are his only once the address is proven (an unverified account may carry someone else's address)
    if proven:
        journey_services.erase_lead(email)  # an address given at the journey gate before he had an account
    removed_logins = _login_events(user).delete()[0]
    removed_emails = _email_logs(email).delete()[0] if proven else 0  # EmailLog has no account link: an unproven address deletes none
    from mailings.erasure import erase_address

    if proven:
        removed_emails += erase_address(email, user)  # group sends, invites and the unsubscribe key hold the address too
        gold = gold_services.delete_applications(email)
    else:
        from mailings.models import MailingRecipient

        removed_emails += MailingRecipient.objects.filter(user=user).delete()[0]
        gold = {"gold_applications": 0, "gold_history_rows": 0, "queue_records": 0}
    queue = erase_task_records([pk], ["users.tasks."])
    interest = InterestRegistration.objects.filter(user=user).select_related("plan").first()
    interest_ids = [interest.pk] if interest else []
    if interest is not None:  # the stored figures describe the data we hold: take this person out of them
        metrics.registered(interest.plan.slug if interest.plan_id else None, interest.source, interest.created_at,
                           marketing=user.marketing_consent, amount=-1)
    if user.email_verified_at:
        metrics.email_verified(user.email_verified_at, amount=-1)
    user.delete()  # cascades the InterestRegistration
    interest_history = InterestRegistration.history.model.objects.filter(id__in=interest_ids).delete()[0]
    removed_history = User.history.model.objects.filter(id=pk).delete()[0]
    return {
        "login_events": removed_logins, "history_rows": removed_history, "email_logs": removed_emails,
        "interest_history_rows": interest_history, "journey_sessions_anonymised": anonymised, **gold,
        "queue_records": gold["queue_records"] + queue,
    }



def choose_tier(user, slug):
    """A signed-in person picks a tier, whichever page they picked it on. Returns (outcome, plan): "saved", "same",
    "gold" (a Gold member is never switched to a tier this way) or "invalid" (not a plan anyone can register interest in)."""
    current = InterestRegistration.objects.filter(user=user).select_related("plan").first()
    if current is not None and current.plan is not None and current.plan.slug == "gold":
        return "gold", current.plan
    plan = interest_plans().filter(slug=slug or "").first()
    if plan is None:
        return "invalid", None
    if current is not None and current.plan_id == plan.pk:
        return "same", plan
    set_interest(user, plan)
    return "saved", plan
