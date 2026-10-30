"""The full picture of one person for the Office person page: every journey with every answer, suggested vs picked
tier, Gold potential and applications, where they came from, consent, and one merged timeline. Works for an account
(`account_profile`) and for a lead who has not registered (`lead_profile`). Plain dicts and lists, JSON friendly, so the
templates only draw them. Source reads of one person: nothing here is a stored figure (docs/features/office-leads.md)."""
from urllib.parse import urlparse

from django.db.models import Prefetch
from django.urls import reverse

from gold.models import ApplicationEvent, GoldApplication
from journey.models import Answer, JourneySession
from notifications.models import EmailLog
from plans.models import Plan
from users.models import InterestRegistration, User

from system import defaults

from . import lists



def _iso(value):
    return value.isoformat() if value else ""


def _href(name, *args):
    """A link into the Office, or '' when the current URL configuration does not have it (never raises)."""
    try:
        return reverse(name, args=args, urlconf="config.urls_office")
    except Exception:  # noqa: BLE001
        return ""


def referrer_host(referrer):
    host = urlparse(referrer or "").netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def source_of(session):
    """Where a journey came from: referrer site (host only), UTM values, device. `label` is the one short phrase to show."""
    host = referrer_host(session.referrer)
    return {"host": host, "utm_source": session.utm_source, "utm_medium": session.utm_medium, "utm_campaign": session.utm_campaign,
            "utm_term": session.utm_term, "utm_content": session.utm_content, "device": session.device_type,
            "label": session.utm_source or host or "Direct"}


def sessions_with_answers(queryset):
    """The sessions with their answers loaded (question and options), in question order, so reading is a few queries."""
    answers = Answer.objects.select_related("question").prefetch_related("options").order_by("question__screen", "question__order")
    return queryset.select_related("suggested_plan").prefetch_related(Prefetch("answers", answers))


def answer_labels(session):
    """{question key: [labels]} for the answers that have choices (typed text is added as one label)."""
    out = {}
    for a in session.answers.all():
        labels = [o.label for o in a.options.all()] + ([a.text_value] if a.text_value else [])
        if labels and not a.skipped:
            out[a.question.key] = labels
    return out


def journey_item(session):
    """One journey, every answer readable. Keeps the keys the person page already used (started, completed, device,
    suggested_plan, gold_potential, lead_email, answers[question, options, text, skipped])."""
    detail = session.suggestion_detail or {}
    answers = []
    for a in session.answers.all():
        options = [o.label for o in a.options.all()]
        shown = "Skipped" if a.skipped else ", ".join([*options, *([a.text_value] if a.text_value else [])])
        answers.append({"key": a.question.key, "question": a.question.text, "options": options, "text": a.text_value,
                        "skipped": a.skipped, "display": shown, "answered_at": _iso(a.answered_at)})
    return {
        "id": str(session.pk), "started": _iso(session.created_at), "last_seen": _iso(session.last_seen_at), "visits": session.visit_count,
        "completed": session.completed, "completed_at": _iso(session.completed_at), "furthest_step": session.furthest_step,
        "device": session.device_type, "is_linked": session.user_id is not None,
        "suggested_plan": session.suggested_plan.name if session.suggested_plan_id else "",
        "suggested_plan_slug": session.suggested_plan.slug if session.suggested_plan_id else "",
        "tier_reasons": list(detail.get("reasons", [])),
        "gold_potential": session.gold_potential, "gold_score": session.gold_score, "gold_reasons": list(detail.get("gold_reasons", [])),
        "lead_email": session.lead_email, "lead_at": _iso(session.lead_at), "lead_privacy_version": session.lead_privacy_version,
        "source": source_of(session), "answers": answers,
    }


def _latest_finished(sessions):
    done = [s for s in sessions if s.completed]
    return max(done, key=lambda s: s.completed_at or s.updated_at) if done else None


def tier_block(sessions, interest=None):
    """Suggested (latest finished journey) vs picked (registration). `match` is None while either is missing."""
    latest = _latest_finished(sessions)
    suggested = latest.suggested_plan if latest is not None and latest.suggested_plan_id else None
    picked = interest.plan if interest is not None and interest.plan_id else None
    return {"suggested": suggested.name if suggested else "", "suggested_slug": suggested.slug if suggested else "",
            "suggested_at": _iso(latest.completed_at) if latest else "", "picked": picked.name if picked else "",
            "picked_slug": picked.slug if picked else "", "picked_at": _iso(interest.created_at) if interest is not None else "",
            "match": (suggested.pk == picked.pk) if suggested and picked else None}


def gold_block(sessions, applications):
    """Gold potential from the latest finished journey, and the person's Gold applications with their history."""
    latest = _latest_finished(sessions)
    detail = (latest.suggestion_detail or {}) if latest else {}
    return {
        "potential": latest.gold_potential if latest else "", "score": latest.gold_score if latest else None,
        "reasons": list(detail.get("gold_reasons", [])),
        "applications": [{"id": str(a.pk), "reference": a.reference, "status": a.status, "status_label": a.get_status_display(),
                          "potential": a.potential_level, "score": a.potential_score, "reasons": list(a.potential_reasons or []),
                          "applied": _iso(a.created_at), "linked_to_account": a.user_id is not None, "events": lists.gold_events(a)}
                         for a in applications],
    }


def consent_block(emails, sessions, user=None, applications=()):
    """What the person agreed to: the gate (email for news of the opening, with the privacy version), the account, any Gold
    application, and whether the address has unsubscribed."""
    from mailings.models import EmailOptOut

    seen, gate = set(), []
    for s in sorted(sessions, key=lambda s: s.lead_at or s.created_at):
        if s.lead_email and (s.lead_at, s.lead_privacy_version) not in seen:
            seen.add((s.lead_at, s.lead_privacy_version))
            gate.append({"email": s.lead_email, "at": _iso(s.lead_at), "privacy_version": s.lead_privacy_version,
                         "text": "Agreed that we may email about Spa 99 opening"})
    account = None
    if user is not None:
        account = {"privacy_version": user.privacy_accepted_version, "accepted_at": _iso(user.privacy_accepted_at),
                   "men_only_accepted_at": _iso(user.men_only_accepted_at), "marketing": user.marketing_consent,
                   "marketing_at": _iso(user.marketing_consent_at)}
    opt_out = EmailOptOut.objects.filter(email__in=[e.lower() for e in emails if e]).exists()
    return {"lead": gate, "account": account, "unsubscribed": opt_out,
            "gold": [{"reference": a.reference, "marketing": a.marketing_consent, "privacy_version": a.privacy_accepted_version, "at": _iso(a.privacy_accepted_at)}
                     for a in applications]}


# ---------- the timeline ----------

def _entry(at, kind, label, detail="", href=""):
    return {"_at": at, "at": _iso(at), "kind": kind, "label": label, "detail": detail, "href": href}


def timeline(sessions, user=None, interest=None, applications=(), email=""):
    """Everything that happened to this person, newest first: journey started, email given, journey finished, registered,
    verified, membership choice changed, news opt in or out, Gold steps and emails sent (when recorded)."""
    out, given = [], set()
    for s in sessions:
        out.append(_entry(s.created_at, "journey_started", "Started the journey", f"Seen on {s.device_type}" if s.device_type else ""))
        if s.lead_email and s.lead_at and (s.lead_email.lower(), s.lead_at) not in given:  # a restart copies the address: one event
            given.add((s.lead_email.lower(), s.lead_at))
            out.append(_entry(s.lead_at, "lead_given", "Left their email before the result", s.lead_email))
        if s.completed and s.completed_at:
            plan = f"Suggested {s.suggested_plan.name}" if s.suggested_plan_id else ""
            potential = f"Gold potential {s.gold_potential}" if s.gold_potential else ""
            out.append(_entry(s.completed_at, "journey_finished", "Finished the journey", ". ".join(x for x in (plan, potential) if x)))
    if user is not None:
        if interest is not None:
            out.append(_entry(interest.created_at, "registered", "Registered interest",
                              ". ".join(x for x in (f"Picked {interest.plan.name}" if interest.plan_id else "No plan chosen",
                                                    "After the journey" if interest.source == InterestRegistration.JOURNEY else "Directly") if x)))
            names = dict(Plan.objects.values_list("pk", "name"))
            before = None
            for row in interest.history.order_by("history_date"):
                if before is not None and row.plan_id != before:
                    out.append(_entry(row.history_date, "plan_changed", "Changed their membership choice",
                                      f"{names.get(before, 'No plan')} to {names.get(row.plan_id, 'No plan')}"))
                before = row.plan_id
        if user.email_verified_at:
            out.append(_entry(user.email_verified_at, "verified", "Verified their email"))
        previous = None
        for row in User.history.filter(id=user.pk).order_by("history_date"):
            if previous is not None and row.marketing_consent != previous:
                out.append(_entry(row.history_date, "marketing_changed", "Opted in to news" if row.marketing_consent else "Opted out of news"))
            previous = row.marketing_consent
    for a in applications:
        events = list(a.events.all())
        if not any(e.action == ApplicationEvent.SUBMITTED for e in events):
            out.append(_entry(a.created_at, "gold_applied", "Applied for Gold", a.reference, _href("office_gold_application", a.pk)))
        for e in events:
            if e.action in (ApplicationEvent.EMAIL_SENT, ApplicationEvent.EMAIL_FAILED):
                continue  # the email rows below and the Gold page hold these
            text = e.get_action_display()
            out.append(_entry(e.at, "gold_applied" if e.action == ApplicationEvent.SUBMITTED else "gold_event",
                              "Applied for Gold" if e.action == ApplicationEvent.SUBMITTED else f"Gold: {text}",
                              " ".join(x for x in (a.reference, f"by {e.actor_label}" if e.actor_label else "") if x), _href("office_gold_application", a.pk)))
    if email:
        for log in EmailLog.objects.filter(to__iexact=email).order_by("-created_at")[:defaults.get().person_emails_shown]:
            out.append(_entry(log.sent_at or log.created_at, "email", f"Email: {log.subject}", log.get_status_display()))
    out.sort(key=lambda e: e["_at"], reverse=True)
    for e in out:
        del e["_at"]
    return out


# ---------- the two profiles ----------

def account_profile(user, interest=None):
    """Extra context for an account's person page (merged into `lists.person_detail`)."""
    interest = interest if interest is not None else InterestRegistration.objects.filter(user=user).select_related("plan").first()
    sessions = list(sessions_with_answers(user.journey_sessions.all()).order_by("created_at"))
    applications = list(user.gold_applications.prefetch_related("events").order_by("created_at"))
    pending = (list(sessions_with_answers(JourneySession.objects.filter(lead_email__iexact=user.email, user__isnull=True)).order_by("created_at"))
               if user.email_verified_at else [])  # an unverified account never shows the address's other journeys (they may be someone else's)
    first = sessions[0] if sessions else None
    return {
        "journeys": [journey_item(s) for s in sessions],
        "unlinked_journeys": [journey_item(s) for s in pending],  # left this address without signing in, not (yet) his: shown, never merged silently
        "tier": tier_block(sessions, interest),
        "gold": gold_block(sessions, applications),
        "source": {**(source_of(first) if first else {}), "registered_via": interest.source if interest is not None else ""},
        "consent": consent_block([user.email], [*sessions, *pending], user, applications),
        "timeline": timeline(sessions, user, interest, applications, user.email),
    }


def lead_sessions_for(email):
    return sessions_with_answers(JourneySession.objects.filter(lead_email__iexact=email, is_bot=False, user__isnull=True)).order_by("created_at")


def lead_profile(email, session_id):
    """A lead who has not registered: all journeys that left this address, Gold applications made with it (not linked to an
    account), tier suggested, consent, source (the first visit), and the timeline."""
    sessions = list(lead_sessions_for(email))
    applications = list(GoldApplication.objects.filter(email__iexact=email, user__isnull=True).prefetch_related("events").order_by("created_at"))
    first = sessions[0] if sessions else None
    return {
        "kind": "lead", "id": str(session_id), "email": email.lower(), "registered": False,
        "first_seen": _iso(min((s.lead_at or s.created_at for s in sessions), default=None)),
        "last_seen": _iso(max((s.last_seen_at for s in sessions), default=None)),
        "journeys": [journey_item(s) for s in sessions],
        "tier": tier_block(sessions),
        "gold": gold_block(sessions, applications),
        "source": source_of(first) if first else {},
        "consent": consent_block([email], sessions, None, applications),
        "timeline": timeline(sessions, applications=applications, email=email),
    }


# ---------- what the person told us and asked ----------

CHATS_SHOWN = 5


def heard_via(journeys):
    """How he said he heard about us (the answer to "How did you hear about us?", plus the typed "Where?"), newest journey first;
    '' when never answered. `journeys` is the profile's list of journey_item dicts (oldest first)."""
    for journey in reversed(journeys):
        said = {a["key"]: a for a in journey["answers"]}
        answer = said.get("heard_via")
        if answer and not answer["skipped"] and answer["display"]:
            other = said.get("heard_via_other")
            return answer["display"] + (f" ({other['text']})" if other and other["text"] else "")
    return ""


def chats_card(user=None, email="", limit=CHATS_SHOWN):
    """The assistant chats of one person for the card: {rows[{id, at, messages, first_question}], more}. The newest `limit`; two
    queries (the page fetches one extra row to know if there are more). Same visibility as Office > Chats."""
    from django.db.models import OuterRef, Subquery

    from chat import services as chat_services
    from chat.models import Message

    first = Message.objects.filter(conversation=OuterRef("pk"), role=Message.USER).order_by("created_at").values("text")[:1]
    found = list(chat_services.person_conversations(user, email).annotate(preview=Subquery(first)).order_by("-created_at")[:limit + 1])
    return {"rows": [{"id": str(c.pk), "at": _iso(c.created_at), "messages": c.message_count, "first_question": c.preview or "", "href": _href("office_chat", c.pk)}
                     for c in found[:limit]], "more": len(found) > limit}
