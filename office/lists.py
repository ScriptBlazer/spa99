"""People and Gold lists and details (source rows, 50 at a time, no counts of filtered results: the unfiltered totals
are stored counters)."""
import csv

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone

from system import defaults
from gold import services as gold_services
from gold.models import GoldApplication
from users.models import InterestRegistration, User

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def page_number(request):
    try:
        return max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        return 1


def cut(queryset, page, size=None):
    """(rows of this page, has_next): fetches one extra row instead of counting. `size` defaults to System > Defaults > People
    and Gold lists rows per page (views pass it from their per-request copy)."""
    size = size or defaults.get().list_page_size
    start = (page - 1) * size
    rows = list(queryset[start:start + size + 1])
    return rows[:size], len(rows) > size


# ---------- people ----------

def people_filters(request):
    return {"q": request.GET.get("q", "").strip(), "plan": request.GET.get("plan", ""),
            "verified": request.GET.get("verified", ""), "marketing": request.GET.get("marketing", "")}


def people_queryset(filters):
    people = User.objects.filter(interest__isnull=False).select_related("interest__plan").order_by("-interest__created_at", "email")
    if filters["q"]:
        for word in filters["q"].split():
            people = people.filter(Q(email__icontains=word) | Q(first_name__icontains=word) | Q(last_name__icontains=word)
                                   | Q(mobile__icontains=word) | Q(public_id__icontains=word.replace(" ", "").upper()))
    if filters["plan"]:
        people = people.filter(interest__plan__slug=filters["plan"])
    if filters["verified"] in ("yes", "no"):
        people = people.filter(email_verified_at__isnull=filters["verified"] == "no")
    if filters["marketing"] in ("yes", "no"):
        people = people.filter(marketing_consent=filters["marketing"] == "yes")
    return people


def journey_state(sessions):
    if any(s.completed for s in sessions):
        return "completed"
    return "started" if sessions else "not_started"


def person_row(user):
    interest = user.interest
    sessions = list(user.journey_sessions.all())
    gold = list(user.gold_applications.all())
    return {
        "id": str(user.pk), "name": user.get_full_name() or user.email, "email": user.email, "public_id": user.public_id_display,
        "plan": interest.plan.name if interest.plan_id else "", "plan_slug": interest.plan.slug if interest.plan_id else "",
        "verified": bool(user.email_verified_at), "marketing": user.marketing_consent,
        "journey": journey_state(sessions), "registered": interest.created_at.isoformat(),
        "gold_application_id": str(gold[0].pk) if gold else "",
    }


def people_page(filters, page, size=None):
    queryset = people_queryset(filters).prefetch_related("journey_sessions", "gold_applications")
    users, has_next = cut(queryset, page, size)
    return [person_row(u) for u in users], has_next


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def people_csv(filters):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="spa99-people.csv"'
    writer = csv.writer(response)
    writer.writerow(["account_id", "first_name", "last_name", "email", "mobile", "membership", "source", "email_verified",
                     "marketing_consent", "registered_at"])
    for user in people_queryset(filters).iterator():
        interest = user.interest
        writer.writerow([safe_cell(x) for x in (
            user.public_id, user.first_name, user.last_name, user.email, user.mobile or "",
            interest.plan.name if interest.plan_id else "", interest.source,
            "yes" if user.email_verified_at else "no", "yes" if user.marketing_consent else "no",
            timezone.localtime(interest.created_at).strftime("%Y-%m-%d %H:%M"))])
    return response


def person_detail(user):
    """The account person page. The long picture (journeys with every answer, tier, Gold, source, consent, timeline) comes
    from office.profile; the keys the page always had are kept."""
    from . import profile

    interest = InterestRegistration.objects.filter(user=user).select_related("plan").first()
    return {
        "kind": "account", "id": str(user.pk), "name": user.get_full_name() or user.email, "email": user.email, "mobile": user.mobile or "",
        "public_id": user.public_id_display, "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else "",
        "verified_at": user.email_verified_at.isoformat() if user.email_verified_at else "",
        "marketing": user.marketing_consent, "privacy_version": user.privacy_accepted_version,
        "last_login": user.last_login.isoformat() if user.last_login else "",
        "is_staff": user.is_staff,
        "interest": None if interest is None else {"plan": interest.plan.name if interest.plan_id else "", "source": interest.source,
                                                   "registered": interest.created_at.isoformat()},
        "gold_applications": [{"id": str(a.pk), "reference": a.reference, "status": a.status, "potential": a.potential_level}
                              for a in user.gold_applications.all()],
        **profile.account_profile(user, interest),
    }


# ---------- gold ----------

WAITING = list(GoldApplication.WAITING)  # the approvers' queue
UNDECIDED = [*WAITING, GoldApplication.AWAITING_FINAL]  # the "waiting" list also shows what is waiting for a final approver


def gold_filters(request):
    status = request.GET.get("status", "waiting")
    return {"q": request.GET.get("q", "").strip(), "status": status if status in ("waiting", "awaiting_final", "approved", "declined", "all") else "waiting",
            "potential": request.GET.get("potential", "")}


def gold_queryset(filters):
    applications = GoldApplication.objects.prefetch_related("invites").order_by("-created_at")
    if filters["status"] == "waiting":
        applications = applications.filter(status__in=UNDECIDED)
    elif filters["status"] != "all":
        applications = applications.filter(status=filters["status"])
    if filters["potential"] in ("high", "medium", "low"):
        applications = applications.filter(potential_level=filters["potential"])
    for word in filters["q"].split():
        applications = applications.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(email__icontains=word)
                                           | Q(reference__icontains=word) | Q(company__icontains=word))
    return applications


def invite_state(application):
    """{'state', 'sent_at', 'expires_at'}: state is '' (not approved), none, waiting_to_send, sent, expired, account_set_up."""
    if application.status != GoldApplication.APPROVED:
        return {"state": "", "sent_at": None, "expires_at": None}
    invites = list(application.invites.all())  # newest first (Meta ordering); prefetched
    if any(i.used_at for i in invites) or application.user_id:
        return {"state": "account_set_up", "sent_at": None, "expires_at": None}
    latest = next((i for i in invites if i.revoked_at is None), None)
    if latest is None:
        return {"state": "none", "sent_at": None, "expires_at": None}
    state = "expired" if latest.expires_at <= timezone.now() else ("sent" if latest.sent_at else "waiting_to_send")
    return {"state": state, "sent_at": latest.sent_at.isoformat() if latest.sent_at else None, "expires_at": latest.expires_at.isoformat()}


def gold_row(application):
    return {"id": str(application.pk), "reference": application.reference, "name": application.full_name, "email": application.email,
            "potential": application.potential_level, "score": application.potential_score, "status": application.status,
            "can_approve": application.status in WAITING, "awaiting_final": application.status == GoldApplication.AWAITING_FINAL,
            "sent_back": application.sent_back_at is not None, "invite": invite_state(application), "applied": application.created_at.isoformat()}


def gold_page(filters, page, size=None):
    applications, has_next = cut(gold_queryset(filters), page, size)
    return [gold_row(a) for a in applications], has_next


def gold_history(application):
    """'Applied', then each status change with who made it, oldest first."""
    entries, previous = [], None
    for record in application.history.select_related("history_user").order_by("history_date"):
        who = (record.history_user.get_full_name() or record.history_user.email) if record.history_user_id else ""
        if previous is None:
            entries.append({"at": record.history_date.isoformat(), "text": "Applied", "status": record.status, "who": ""})
        elif record.status != previous:
            if record.status == GoldApplication.AWAITING_FINAL:
                text = "Sent for final approval"
            elif previous == GoldApplication.AWAITING_FINAL and record.status in WAITING:
                text = "Sent back"
            else:
                text = record.get_status_display()
            entries.append({"at": record.history_date.isoformat(), "text": text + (f" by {who}" if who else ""),
                            "status": record.status, "who": who})
        previous = record.status
    return entries


def _name(user):
    return (user.get_full_name() or user.email) if user is not None else ""


STATUS_NAMES = dict(GoldApplication.STATUS_CHOICES)
EMAIL_NAMES = {"gold_approver": "Approver email", "gold_invite": "Invite email", "gold_active": "Gold-added email",
               "gold_respond": "Response email", "gold_ack": "Thank-you email", "gold_final": "Final approval email", "gold_sent_back": "Sent-back email", "gold_declined": "Decline email"}


def _event_detail(event):
    """One short plain line under an event, from its meta (who was emailed, the result)."""
    meta = event.meta or {}
    if event.action in ("email_sent", "email_failed"):
        name = EMAIL_NAMES.get(meta.get("template"), "Email")
        if event.action == "email_sent":
            return f"{name} sent to {meta.get('recipient', '')}".strip()
        return f"{name} to {meta.get('recipient', '')} failed: {meta.get('error', 'unknown reason')}".replace("  ", " ")
    if event.action == "declined":
        return "The applicant was emailed." if meta.get("email_applicant") else "The applicant was not emailed."
    if event.action in ("approved", "final_confirmed"):
        return {"invited": "An invite to set up his account was queued.", "activated": "Gold was added to his existing account."}.get(meta.get("result"), "")
    if event.action == "responded":
        return "Emailed to the applicant."
    return ""


def gold_events(application):
    """The audit trail, newest first, as plain rows for the History card."""
    rows = []
    for event in application.events.select_related("actor"):
        rows.append({
            "id": str(event.pk), "at": event.at.isoformat(), "action": event.action, "label": event.get_action_display(),
            "who": event.actor_label, "channel": event.channel, "channel_label": event.get_channel_display(),
            "from": STATUS_NAMES.get(event.from_status, ""), "to": STATUS_NAMES.get(event.to_status, ""), "message": event.message,
            "detail": _event_detail(event),
        })
    return rows


def gold_detail(application):
    sections = [{"title": s["title"], "rows": [{"label": label, "value": value} for label, value in s["rows"]]}
                for s in gold_services.application_sections(application)]
    application = GoldApplication.objects.select_related("approved_by", "final_requested_by", "sent_back_by").prefetch_related("invites").get(pk=application.pk)
    state = invite_state(application)
    history = gold_history(application)
    decided = next((h for h in reversed(history) if h["status"] == application.status and h["text"] != "Applied"), None)
    return {
        "id": str(application.pk), "reference": application.reference, "name": application.full_name, "status": application.status,
        "potential": application.potential_level, "invite": state, "sections": sections, "history": history,
        "decided_at": decided["at"] if decided else "", "decided_by": decided["who"] if decided else "",
        "approved_at": application.approved_at.isoformat() if application.approved_at else "",
        "approved_by": (application.approved_by.get_full_name() or application.approved_by.email) if application.approved_by_id else "",
        "person_id": str(application.user_id) if application.user_id else "",
        "can_approve": application.status in WAITING,
        "can_decline": application.status in WAITING,
        "can_respond": application.status in (*WAITING, GoldApplication.AWAITING_FINAL),
        "events": gold_events(application),
        "awaiting_final": application.status == GoldApplication.AWAITING_FINAL,
        "can_final": application.status == GoldApplication.AWAITING_FINAL,
        "final_requested_at": application.final_requested_at.isoformat() if application.final_requested_at else "",
        "final_requested_by": _name(application.final_requested_by),
        "sent_back": {"at": application.sent_back_at.isoformat(), "by": _name(application.sent_back_by), "note": application.sent_back_note}
                     if application.sent_back_at else None,
        "note_max": GoldApplication.NOTE_MAX,
        "can_resend": application.status == GoldApplication.APPROVED and state["state"] != "account_set_up" and not application.user_id,
    }


def gold_confirm(application):
    """What the one-tap approve page shows: who, potential, one property line and the applied date."""
    sections = {t["title"]: dict(t["rows"]) for t in gold_services.application_sections(application)}
    about = sections.get("About him", {})
    line = [about.get("What he does", ""), about.get("Link to property", ""), about.get("Size", ""), about.get("Where", "")]
    return {"id": str(application.pk), "name": application.full_name, "first_name": application.first_name, "status": application.status,
            "potential": application.potential_level, "property_line": " · ".join(p for p in line if p and p != "Not given"),
            "applied": application.created_at, "can_approve": application.status in WAITING,
            "awaiting_final": application.status == GoldApplication.AWAITING_FINAL, "sent_back": application.sent_back_at is not None,
            "final_requested_by": _name(application.final_requested_by), "final_requested_at": application.final_requested_at.isoformat() if application.final_requested_at else ""}
