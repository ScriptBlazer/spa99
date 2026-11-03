"""The person tools shared by the lead, person and Gold application pages: sticky notes, the approach list and Message. One
person = a set of addresses (outreach.people.resolve), so the same notes show on all three pages. The views stay thin and call
these; the services are in outreach.services."""
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from django.urls import reverse

from gold.models import GoldApplication
from journey.models import JourneySession
from outreach import people, services
from outreach.models import NOTE_MAX, REASON_MAX, OutreachEntry
from plans.models import SiteSettings
from users.models import User

from . import leads as lead_lists
from .permissions import can_edit


class Target:
    """One page's person: where to redirect, his main address, all his addresses, the account (if any) and the application."""

    def __init__(self, kind, pk, user=None, email="", application=None):
        self.kind, self.pk, self.user, self.application = kind, pk, user, application
        self.main, self.addresses, self.user = people.resolve(user=user, email=email, application=application)
        self.lead_email = "" if self.user is not None else self.main

    @property
    def page_url(self):
        name = {"person": "office_person", "lead": "office_lead", "gold": "office_gold_application"}[self.kind]
        return reverse(name, args=[self.pk])

    def url(self, what, *extra):
        return reverse(f"office_{self.kind}_{what}", args=[self.pk, *extra])


def person_target(pk):
    user = get_object_or_404(User, pk=pk, interest__isnull=False)
    return Target("person", user.pk, user=user)


def gold_target(pk):
    application = get_object_or_404(GoldApplication.objects.select_related("user"), pk=pk)
    return Target("gold", application.pk, application=application)


def lead_target(pk):
    """By the opaque id of any of his sessions. Once the address has an account, the person's page is the page."""
    session = get_object_or_404(JourneySession, pk=pk)
    found = lead_lists.lead_for(session)
    if found is None:
        from django.http import Http404

        raise Http404
    kind, data = found
    if kind == "account":
        return Target("person", data.pk, user=data)
    return Target("lead", pk, email=data["email"])


def target_for(kind, pk):
    return {"person": person_target, "lead": lead_target, "gold": gold_target}[kind](pk)


def notes_context(target, user):
    live = services.notes_for(target.addresses)
    can = can_edit(user)
    return {"notes": [{"id": str(n.pk), "text": n.text, "author": n.author_label, "created_at": n.created_at.isoformat(),
                       "edited_at": n.edited_at.isoformat() if n.edited_at else "", "edited_by": n.edited_by_label,
                       "delete_url": target.url("note_delete", n.pk) if can else "", "edit_url": target.url("note_edit", n.pk) if can else ""} for n in live],
            "notes_count": len(live), "note_max": NOTE_MAX, "can_note": can, "note_add_url": target.url("note_add")}


def outreach_context(target, user):
    entry = services.open_entries(target.addresses, target.user, target.application).first()
    return {"outreach": {"on_list": entry is not None, "entry_id": str(entry.pk) if entry else "", "add_url": target.url("outreach_add"),
                         "reason_max": REASON_MAX, "title": SiteSettings.load().outreach_title, "can_add": can_edit(user),
                         "added_by": entry.added_by_label if entry else "", "added_at": entry.added_at.isoformat() if entry else ""}}


def mobile_and_name(target):
    """(mobile, first name) known for this person: the account's, else the one given at the email step or typed by staff, else the Gold
    application's. '' when there is none."""
    if target.user is not None and target.user.mobile:
        return target.user.mobile, target.user.first_name or ""
    session = (JourneySession.objects.filter(is_bot=False).exclude(lead_mobile="").annotate(k=Lower("lead_email")).filter(k__in=list(target.addresses))
               .order_by("-created_at").first()) if target.addresses else None
    if session is not None:
        return session.lead_mobile, session.lead_first_name
    if target.application is not None and target.application.mobile:
        return target.application.mobile, target.application.first_name or ""
    return "", (target.user.first_name if target.user is not None else "")


def whatsapp_context(target, user):
    """`whatsapp` for the lead, person and Gold pages (design brief section 6): {configured, has_mobile, mobile, first_name, contact_url (opens his chat),
    start_url, edit_url (POST first_name, mobile_country, mobile; empty on the Gold page), can_send, can_edit, has_chat, window_open, window_closes_at,
    opted_out, unread, thread_url}, plus `mobile_countries` for the add-a-mobile dialog."""
    from common import phone
    from whatsapp import services as whatsapp

    mobile, first = mobile_and_name(target)
    edit = target.url("contact") if target.kind == "lead" else (target.url("mobile") if target.kind == "person" else "")
    return {"whatsapp": whatsapp.page_context(mobile, user, can_edit(user), target.url("whatsapp"), edit, first), "mobile_countries": phone.countries()}


def archive_context(target, user):
    """The lead page only: `archive` {archived, reason, by, at, archive_url, unarchive_url, reason_max, can_edit}."""
    if target.kind != "lead":
        return {}
    row = services.archived_row(target.main)
    return {"archive": {"archived": row is not None, "reason": row.reason if row else "", "by": row.archived_by_label if row else "",
                        "at": row.archived_at.isoformat() if row else "", "archive_url": target.url("archive"), "unarchive_url": target.url("unarchive"),
                        "reason_max": REASON_MAX, "can_edit": can_edit(user)}}


def bounce_context(target, user):
    """The lead page only: `bounce` {bounced, email, notice, can_edit, correct_url, resend_url, can_resend, sent}. `can_resend`: staff corrected the address
    (so the follow-up never went to it) and it does not bounce now."""
    if target.kind != "lead":
        return {}
    bounced = services.is_bounced(target.main)
    state = services.follow_up_state(target.main)
    editor = can_edit(user)
    return {"bounce": {"bounced": bounced, "email": target.main, "notice": services.BOUNCE_NOTICE, "can_edit": editor, "correct_url": target.url("email"), "resend_url": target.url("resend"),
                       "can_resend": bool(editor and state["corrected"] and not state["sent"] and not bounced), "sent": state["sent"]}}


def tools_context(target, user):
    """Everything the three pages add to their context: notes_*, outreach and whatsapp, and `archive` on the lead page."""
    return {**notes_context(target, user), **outreach_context(target, user), **whatsapp_context(target, user), **archive_context(target, user), **bounce_context(target, user)}


def outreach_rows(entries):
    """Plain dicts for the approach list page (one per entry): name, contact, where from, link and the two actions."""
    rows = []
    entries = list(entries)
    emails = {e.lead_email for e in entries if e.lead_email}
    sessions = {}  # one query for the page: the newest session of each lead address
    for pk, address in (JourneySession.objects.filter(is_bot=False).annotate(k=Lower("lead_email")).filter(k__in=emails)
                        .order_by("created_at").values_list("pk", "lead_email")):
        sessions[address.lower()] = pk  # oldest first, so the newest wins
    for e in entries:
        mobile = ""
        if e.user_id:
            name, email, mobile, source = e.user.get_full_name() or e.user.email, e.user.email, e.user.mobile or "", "Person"
            href = reverse("office_person", args=[e.user_id])
        elif e.gold_application_id:
            a = e.gold_application
            name, email, mobile, source = a.full_name, a.email, a.mobile or "", "Gold"
            href = reverse("office_gold_application", args=[a.pk])
        else:
            name, email, source = e.lead_email, e.lead_email, "Lead"
            href = reverse("office_lead", args=[sessions[e.lead_email]]) if e.lead_email in sessions else ""
        rows.append({"id": str(e.pk), "name": name, "email": email, "mobile": mobile, "source": source, "href": href, "reason": e.reason,
                     "registered_at": e.registered_at.isoformat() if getattr(e, "registered_at", None) and e.registered_at > e.added_at else "",  # only an account verified after he was added
                     "added_by": e.added_by_label, "added_at": e.added_at.isoformat(), "done_at": e.done_at.isoformat() if e.done_at else "",
                     "done_by": e.done_by_label, "done_url": reverse("office_outreach_done", args=[e.pk]),
                     "remove_url": reverse("office_outreach_remove", args=[e.pk])})
    return rows
