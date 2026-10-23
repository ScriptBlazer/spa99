"""Gold application logic: submit (no account), rate, link repeats, build the email sections, queue the email."""
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from common.tasks import enqueue, erase_task_records
from journey import services as journey_services
from notifications.services import subject_for
from plans.models import SiteSettings

from . import rating
from .models import BML, PROPERTY_LINK, SIZE, WHERE, GoldApplication

logger = logging.getLogger("spa99.gold")

DOUBLE_SUBMIT_WINDOW = timedelta(minutes=2)
POTENTIAL_LABELS = {rating.HIGH: "High", rating.MEDIUM: "Medium", rating.LOW: "Low"}


class ApplicationsClosed(Exception):
    """Stage switch register_interest_open is off."""


def rate_application(application):
    """Fill potential_level / score / reasons from the editable GoldRule rows."""
    result = rating.rate_potential({
        "property_link": application.property_link,
        "size": application.size_range,
        "where": application.location,
        "bml": application.bml_relationship,
        "referred": "yes" if application.referred_by.strip() else "",
    })
    application.potential_level = result.level
    application.potential_score = result.score
    application.potential_reasons = result.reasons
    return result


# ---------- what the site collected ----------

JOURNEY_SUMMARY = [
    ("time", "When he would come"),
    ("frequency", "How often"),
    ("facilities", "Facilities he wants"),
    ("company", "Alone or with someone"),
    ("industry", "What he does"),
    ("heard_via", "How he heard about us"),
]


def interest_snapshot(session):
    """Journey answers as readable text, for the application and the email. {} when there is no journey."""
    if session is None:
        return {}
    answers = journey_services.effective_answers(session)
    snapshot = {}
    for key, _ in JOURNEY_SUMMARY:
        answer = answers.get(key)
        if answer is not None:
            snapshot[key] = [o.label for o in answer.options.all()]
    if session.suggested_plan_id:
        snapshot["suggested_plan"] = session.suggested_plan.name
    minutes = max(1, round((session.last_seen_at - session.created_at).total_seconds() / 60))
    snapshot["journey"] = {
        "completed": session.completed,
        "minutes": minutes,
        "visits": session.visit_count,
    }
    return snapshot


def _journey_sentence(info):
    state = "completed" if info.get("completed") else "not finished"
    text = f"{state} in about {info.get('minutes', 1)} min"
    visits = info.get("visits", 1)
    return text + (f", visited {visits} times before applying" if visits > 1 else ", one visit")


def application_sections(application):
    """The three sections of the email to Barry, as [{'title', 'rows': [(label, value)]}]. Control shows the same."""
    created = timezone.localtime(application.created_at).strftime("%d/%m/%Y, %H:%M")
    personal = [
        ("Name", application.full_name),
        ("Email", application.email),
        ("Mobile", application.mobile or "Not given"),
        ("Date applied", created),
        ("Reference", application.reference),
    ]
    prop = [
        ("Link to property", rating.label_for(PROPERTY_LINK, application.property_link)),
        ("Company and role", " / ".join(p for p in (application.company, application.role) if p) or "Not given"),
        ("Size", rating.label_for(SIZE, application.size_range) or "Not given"),
        ("Where", rating.label_for(WHERE, application.location) or "Not given"),
        ("Works with BML", rating.label_for(BML, application.bml_relationship) or "Not given"),
        ("Referred by", application.referred_by or "Nobody named"),
        ("Potential", f"{POTENTIAL_LABELS.get(application.potential_level, '')} ({application.potential_score} points)"),
        ("Why", "\n".join(application.potential_reasons) or "No scoring signals"),
    ]
    if application.note:
        prop.append(("Note from applicant", application.note))
    info = application.spa_interest or {}
    collected = []
    for key, label in JOURNEY_SUMMARY:
        if key in info:
            collected.append((label, ", ".join(info[key]) or "Skipped"))
    if "suggested_plan" in info:
        collected.append(("Suggested membership", info["suggested_plan"]))
    if "journey" in info:
        collected.append(("Journey", _journey_sentence(info["journey"])))
    if not collected:
        collected = [("Journey", "He did not use the guided journey.")]
    return [
        {"title": "Personal details", "rows": personal},
        {"title": "Property profile", "rows": prop},
        {"title": "What the site collected", "rows": collected},
    ]


# ---------- submit ----------

def _recent_duplicate(email):
    cutoff = timezone.now() - DOUBLE_SUBMIT_WINDOW
    return GoldApplication.objects.filter(email__iexact=email, created_at__gte=cutoff).first()


def submit_application(data, session=None):
    """Save an application from validated form data. Creates no account. Returns (application, created).
    A second identical submit within two minutes (double click) returns the first one and sends nothing new."""
    site = SiteSettings.load()
    if not site.register_interest_open:
        raise ApplicationsClosed
    email = data["email"].strip().lower()
    duplicate = _recent_duplicate(email)
    if duplicate is not None:
        return duplicate, False

    previous = GoldApplication.objects.filter(email__iexact=email).order_by("created_at").first()
    person = get_user_model().objects.filter(email__iexact=email).first()
    now = timezone.now()
    application = GoldApplication(
        first_name=data["first_name"], last_name=data["last_name"], email=email, mobile=data.get("mobile", ""),
        property_link=data["property_link"], size_range=data.get("size_range", ""), location=data.get("location", ""),
        company=data.get("company", ""), role=data.get("role", ""), bml_relationship=data.get("bml_relationship", ""),
        referred_by=data.get("referred_by", ""), note=data.get("note", ""),
        journey_session=session, user=person, repeat_of=previous,
        spa_interest=interest_snapshot(session),
        marketing_consent=bool(data.get("marketing_opt_in")),
        privacy_accepted_version=site.privacy_version, privacy_accepted_at=now,
    )
    rate_application(application)
    with transaction.atomic():
        application.save()
    queue_emails(application)
    return application, True


def queue_emails(application, acknowledge=True):
    """Queue the emails. The application is already saved, so a queue problem never loses it."""
    try:
        enqueue("gold.tasks.send_gold_emails", str(application.pk), acknowledge)
    except Exception:  # noqa: BLE001
        logger.exception("Could not queue Gold emails for %s", application.reference)
        GoldApplication.objects.filter(pk=application.pk).update(email_error="Could not be queued")


def resend_barry_email(application):
    """Control's 'resend' button: only Barry's email goes again."""
    queue_emails(application, acknowledge=False)


# ---------- linking ----------

def link_user_applications(user):
    """When someone registers with the email of earlier Gold applications, link them (no approval implied)."""
    return GoldApplication.objects.filter(email__iexact=user.email, user__isnull=True).update(user=user)


def barry_email_context(application):
    site = SiteSettings.load()
    return {
        "name": application.full_name,
        "potential_label": POTENTIAL_LABELS.get(application.potential_level, ""),
        "sections": application_sections(application),
        "is_repeat": application.is_repeat,
        "repeat_reference": application.repeat_of.reference if application.repeat_of_id else "",
        "recipients": site.gold_alert_to_list,
    }


def barry_subject(application):
    key = "gold_barry_repeat" if application.is_repeat else "gold_barry"
    return subject_for(key, name=application.full_name, potential=POTENTIAL_LABELS.get(application.potential_level, ""))


# ---------- GDPR ----------

def export_applications(email):
    return [
        {
            "reference": a.reference, "created_at": a.created_at.isoformat(), "name": a.full_name, "email": a.email,
            "mobile": a.mobile, "property_link": a.property_link, "size_range": a.size_range, "where": a.location,
            "company": a.company, "role": a.role, "bml_relationship": a.bml_relationship,
            "referred_by": a.referred_by, "note": a.note, "potential": a.potential_level, "status": a.status,
            "spa_interest": a.spa_interest,
        }
        for a in GoldApplication.objects.filter(email__iexact=email).order_by("created_at")
    ]


@transaction.atomic
def delete_applications(email):
    """Erase Gold applications made with this email: the rows, their history, the emails about them (Barry's
    included, found by EmailLog.subject_email) and the queue records of their email tasks. Returns counts."""
    applications = GoldApplication.objects.filter(email__iexact=email)
    ids = list(applications.values_list("pk", flat=True))
    removed = applications.delete()[0]
    history = GoldApplication.history.model.objects.filter(id__in=ids).delete()[0]
    queue = erase_task_records(ids, ["gold.tasks."])
    return {"gold_applications": removed, "gold_history_rows": history, "queue_records": queue}
