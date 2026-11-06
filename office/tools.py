"""The person tools shared by the lead, person and Gold application pages: sticky notes, the approach list and the Email button. One
person = a set of addresses (outreach.people.resolve), so the same notes show on all three pages. The views stay thin and call
these; the services are in outreach.services."""
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from django.urls import reverse

from gold.models import GoldApplication
from journey.models import JourneySession
from outreach import people, services
from outreach.models import MESSAGE_MAX, NOTE_MAX, REASON_MAX, OutreachEntry
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
    application's. The name is the newest one given even when there is no mobile. '' when there is none."""
    application = target.application
    if target.user is not None and target.user.mobile:
        return target.user.mobile, target.user.first_name or ""
    sessions = (JourneySession.objects.filter(is_bot=False).annotate(k=Lower("lead_email")).filter(k__in=list(target.addresses)).order_by("-created_at")) if target.addresses else []
    sessions = list(sessions)
    mobile = next((s.lead_mobile for s in sessions if s.lead_mobile), "")
    name = (next((s.lead_first_name for s in sessions if s.lead_first_name), "") or (target.user.first_name if target.user is not None else "")
            or (application.first_name if application is not None and application.first_name else ""))
    if mobile:
        return mobile, name
    if application is not None and application.mobile:
        return application.mobile, name
    return "", name


def display_name(target):
    """The person's name for a sentence on a page: his full name, the applicant's, the lead's first name, else the address."""
    if target.user is not None:
        return target.user.get_full_name() or target.user.email
    if target.application is not None and target.application.full_name:
        return target.application.full_name
    return mobile_and_name(target)[1] or target.main


def wa_link(mobile):
    """`https://wa.me/<digits>` for a stored E.164 mobile, '' when there is none. Digits only, no plus: that is the form wa.me wants."""
    digits = "".join(ch for ch in (mobile or "") if ch.isdigit())
    return f"https://wa.me/{digits}" if digits else ""


def whatsapp_context(target, user):
    """`whatsapp` for the lead, person and Gold pages: {state ("mobile" or "none"), wa_link (https://wa.me/<digits>, "" with no mobile), has_mobile, mobile, first_name, edit_url (POST
    first_name, mobile_country, mobile on a lead; mobile_country, mobile on a person or Gold page), can_edit, can_add_number, reason}, plus `mobile_countries` for the add-a-mobile dialog.
    The button is a plain link: nothing here says a message was sent, because a wa.me click cannot be proven."""
    from common import phone

    mobile, first = mobile_and_name(target)
    edit = target.url("contact") if target.kind == "lead" else target.url("mobile")
    link = wa_link(mobile)
    editor = can_edit(user)
    return {"whatsapp": {"state": "mobile" if link else "none", "wa_link": link, "has_mobile": bool(link), "mobile": mobile or "", "first_name": first, "edit_url": edit, "can_edit": bool(editor),
                         "can_add_number": bool(editor and not link), "reason": "" if link else ("Add a number to WhatsApp him." if editor else "No mobile on file.")},
            "mobile_countries": phone.countries()}


def email_context(target, user):
    """`email_msg` for the lead, person and Gold pages (the Email button and its pop-up): {url, to, name, max, can_send, blocked (why he cannot be emailed, or ''), unsubscribed, from_label,
    reply_to}. `from_label` is the logged-in person's From line and `reply_to` where his reply goes (notifications.sender)."""
    from notifications import sender as sender_mod

    sender = sender_mod.sender_for(user)
    reply = sender.address if sender.source != "site" else SiteSettings.load().contact_address
    return {"email_msg": {"url": target.url("message"), "to": target.main, "name": display_name(target), "max": MESSAGE_MAX, "can_send": can_edit(user), "blocked": services.email_block(target.main),
                          "unsubscribed": services.is_unsubscribed(target.addresses, target.user), "from_label": f"{sender.name} <{sender.address}>", "reply_to": reply}}


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
    return {**notes_context(target, user), **outreach_context(target, user), **whatsapp_context(target, user), **email_context(target, user), **archive_context(target, user), **bounce_context(target, user)}


def outreach_rows(entries):
    """Plain dicts for the approach list page (one per entry): name, contact, where from, link and the actions. A lead entry (an address, no account, no Gold application) also gets
    `is_lead` with `to_leads_url` (Back to Leads) and `archive_url`; other rows (a person, a Gold applicant) keep only Remove. `emailed_at` is set when a person or a group send emailed him."""
    from outreach.services import bounced_set, emailed_at

    rows = []
    entries = list(entries)
    emails = {e.lead_email for e in entries if e.lead_email}
    sessions = {}  # one query for the page: the newest session of each lead address
    for pk, address in (JourneySession.objects.filter(is_bot=False).annotate(k=Lower("lead_email")).filter(k__in=emails)
                        .order_by("created_at").values_list("pk", "lead_email")):
        sessions[address.lower()] = pk  # oldest first, so the newest wins
    addresses = {(e.user.email if e.user_id else e.gold_application.email if e.gold_application_id else e.lead_email or "").lower() for e in entries}
    emailed, bounced = emailed_at(addresses), bounced_set(addresses)
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
        key = (email or "").lower()
        rows.append({"id": str(e.pk), "name": name, "email": email, "mobile": mobile, "source": source, "href": href, "reason": e.reason,
                     "emailed_at": emailed[key].isoformat() if key in emailed and key not in bounced else "",  # a bounced address shows Possible fake instead
                     "bounced": key in bounced, "is_lead": source == "Lead",
                     "added_by": e.added_by_label, "added_at": e.added_at.isoformat(), "done_at": e.done_at.isoformat() if e.done_at else "",
                     "done_by": e.done_by_label, "done_url": reverse("office_outreach_done", args=[e.pk]),
                     "remove_url": reverse("office_outreach_remove", args=[e.pk]),
                     "to_leads_url": reverse("office_outreach_to_leads", args=[e.pk]) if source == "Lead" else "",
                     "archive_url": reverse("office_outreach_archive", args=[e.pk]) if source == "Lead" else ""})
    return rows
