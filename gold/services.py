"""Gold application logic: submit (no account), rate, link repeats, build the email sections, queue the email."""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from common.tasks import enqueue, erase_task_records
from journey import engine as journey_engine
from journey import services as journey_services
from notifications.services import subject_for
from plans.models import SiteSettings

from . import rating
from .models import BML, PROPERTY_LINK, SIZE, WHERE, GoldApplication, GoldInvite

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
    what = rating.industry_label(application.industry) or "Not given"
    if application.industry_other:
        what += f" ({application.industry_other})"
    prop = [("What he does", what)]
    if application.property_link:  # only people in Property are asked
        prop.append(("Link to property", rating.label_for(PROPERTY_LINK, application.property_link)))
    prop += [
        ("Company and role", " / ".join(p for p in (application.company, application.role) if p) or "Not given"),
    ]
    # Size is only asked in Property (older applications have no industry: keep showing it for them).
    if application.industry == rating.PROPERTY_INDUSTRY or (not application.industry and application.property_link):
        prop.append(("Size", rating.label_for(SIZE, application.size_range) or "Not given"))
    prop += [
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
        {"title": "About him", "rows": prop},
        {"title": "What the site collected", "rows": collected},
    ]


# ---------- submit ----------

def _recent_duplicate(email):
    cutoff = timezone.now() - DOUBLE_SUBMIT_WINDOW
    return GoldApplication.objects.filter(email__iexact=email, created_at__gte=cutoff).first()


def _serialise_submissions(site):
    """Take the write lock first (a row lock on Postgres, the database write lock on SQLite) so the duplicate check below
    and the insert cannot interleave with another submission. Same code on both."""
    SiteSettings.objects.filter(pk=site.pk).update(updated_at=timezone.now())


def submit_application(data, session=None):
    """Save an application from validated form data. Creates no account. Returns (application, created).
    A second identical submit within two minutes (double click) returns the first one and sends nothing new."""
    site = SiteSettings.load()
    if not site.register_interest_open:
        raise ApplicationsClosed
    email = data["email"].strip().lower()
    with transaction.atomic():
        _serialise_submissions(site)  # two clicks at the same instant are handled one after the other
        duplicate = _recent_duplicate(email)
        if duplicate is not None:
            return duplicate, False

        if data.get("industry") == rating.LAW_INDUSTRY and not data.get("property_link") and session is not None:
            # A lawyer who told the journey it is property law still counts as a property lawyer (as the journey rates him).
            if journey_engine.gold_signals(session)[0].get("property_link") == rating.PROPERTY_LAWYER:
                data = {**data, "property_link": rating.PROPERTY_LAWYER}

        previous = GoldApplication.objects.filter(email__iexact=email).order_by("created_at").first()
        person = get_user_model().objects.filter(email__iexact=email).first()
        now = timezone.now()
        application = GoldApplication(
            first_name=data["first_name"], last_name=data["last_name"], email=email, mobile=data.get("mobile", ""),
            industry=data.get("industry", ""), industry_other=data.get("industry_other", ""),
            property_link=data.get("property_link", ""), size_range=data.get("size_range", ""), location=data.get("location", ""),
            company=data.get("company", ""), role=data.get("role", ""), bml_relationship=data.get("bml_relationship", ""),
            referred_by=data.get("referred_by", ""), note=data.get("note", ""),
            journey_session=session, user=person, repeat_of=previous,
            spa_interest=interest_snapshot(session),
            marketing_consent=bool(data.get("marketing_opt_in")),
            privacy_accepted_version=site.privacy_version, privacy_accepted_at=now,
        )
        rate_application(application)
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


def resend_approver_email(application):
    """Control's 'resend' button: only the approver's email goes again."""
    queue_emails(application, acknowledge=False)


# ---------- linking ----------

def link_user_applications(user):
    """When someone registers with the email of earlier Gold applications, link them (no approval implied)."""
    return GoldApplication.objects.filter(email__iexact=user.email, user__isnull=True).update(user=user)


def approver_email_context(application):
    office = settings.OFFICE_URL  # links hold only the application id: the Office asks for sign-in and checks the role
    return {
        "approve_url": f"{office}/gold/{application.pk}/approve/confirm/",
        "view_url": f"{office}/gold/{application.pk}/",
        "name": application.full_name,
        "potential_label": POTENTIAL_LABELS.get(application.potential_level, ""),
        "sections": application_sections(application),
        "is_repeat": application.is_repeat,
        "repeat_reference": application.repeat_of.reference if application.repeat_of_id else "",
    }


def approver_subject(application):
    key = "gold_approver_repeat" if application.is_repeat else "gold_approver"
    return subject_for(key, name=application.full_name, potential=POTENTIAL_LABELS.get(application.potential_level, ""))


# ---------- GDPR ----------

def export_applications(email):
    return [
        {
            "reference": a.reference, "created_at": a.created_at.isoformat(), "name": a.full_name, "email": a.email,
            "mobile": a.mobile, "industry": a.industry, "industry_other": a.industry_other, "property_link": a.property_link, "size_range": a.size_range, "where": a.location,
            "company": a.company, "role": a.role, "bml_relationship": a.bml_relationship,
            "referred_by": a.referred_by, "note": a.note, "potential": a.potential_level, "status": a.status,
            "potential_score": a.potential_score, "potential_reasons": a.potential_reasons,
            "marketing_consent": a.marketing_consent, "privacy_accepted_version": a.privacy_accepted_version,
            "privacy_accepted_at": a.privacy_accepted_at.isoformat() if a.privacy_accepted_at else None,
            **({"internal_notes": a.internal_notes} if a.internal_notes else {}),
            "spa_interest": a.spa_interest,
            "approved_at": a.approved_at.isoformat() if a.approved_at else None,
            "invites": [
                {"created_at": i.created_at.isoformat(), "sent_at": i.sent_at.isoformat() if i.sent_at else None,
                 "expires_at": i.expires_at.isoformat(), "used_at": i.used_at.isoformat() if i.used_at else None,
                 "replaced_at": i.revoked_at.isoformat() if i.revoked_at else None}
                for i in a.invites.all().order_by("created_at")
            ],
        }
        for a in GoldApplication.objects.filter(email__iexact=email).prefetch_related("invites").order_by("created_at")
    ]


@transaction.atomic
def delete_applications(email):
    """Erase Gold applications made with this email: the rows, their history, the emails about them (Barry's
    included, found by EmailLog.subject_email) and the queue records of their email tasks. Returns counts."""
    applications = GoldApplication.objects.filter(email__iexact=email)
    ids = list(applications.values_list("pk", flat=True))
    invite_ids = list(GoldInvite.objects.filter(application_id__in=ids).values_list("pk", flat=True))  # invite emails are queued by invite id
    removed = applications.delete()[0]
    history = GoldApplication.history.model.objects.filter(id__in=ids).delete()[0]
    queue = erase_task_records([*ids, *invite_ids], ["gold.tasks."])
    return {"gold_applications": removed, "gold_history_rows": history, "queue_records": queue}
