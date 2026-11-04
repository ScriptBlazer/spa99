"""Sticky notes, the approach list and one-to-one messages. Short functions that return a result word, so the views stay thin."""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from gold import audit
from gold.models import ApplicationEvent, GoldApplication

from . import people
from .models import (NOTE_MAX, REASON_MAX, ArchivedLead, LeadArchiveEvent, NextMorningEmail, NoteEvent, OutreachEntry, PersonEdit,
                     PersonMessage, StickyNote)

logger = logging.getLogger("spa99.outreach")

DONE, DUPLICATE, EMPTY, TOO_LONG, MISSING = "done", "duplicate", "empty", "too_long", "missing"
INVALID = "invalid"
ALREADY, UNCHANGED = "already", "unchanged"
DUPLICATE_WINDOW = timedelta(seconds=60)


def label(user):
    return audit.label_for(user)


def _actor(user):
    return user if getattr(user, "pk", None) else None


# ---------- sticky notes ----------

def notes_for(addresses):
    """The live notes of a person (all his addresses), newest first."""
    return list(StickyNote.objects.filter(email__in=list(addresses), deleted_at__isnull=True).select_related("author"))


def add_note(main, actor, text, source_event=None, at=None):
    """Store a note on the person's main address. Returns (result, note)."""
    text, main = audit.clean_text(text), (main or "").strip().lower()
    if not text or not main:
        return EMPTY, None
    if len(text) > NOTE_MAX:
        return TOO_LONG, None
    when = at or timezone.now()
    if source_event is None:
        recent = StickyNote.objects.filter(email=main, text=text, created_at__gte=when - DUPLICATE_WINDOW)
        recent = recent.filter(author=actor) if getattr(actor, "pk", None) else recent.filter(author__isnull=True)
        if recent.exists():
            return DUPLICATE, None
    note = StickyNote.objects.create(email=main, text=text, author=_actor(actor), author_label=label(actor), created_at=when, source_event=source_event)
    return DONE, note


def delete_note(note, actor):
    """Soft delete, and leave the history record with the text: a NoteEvent (the person's timeline) and a Gold 'note deleted' event
    on each of his applications. Returns DONE, or MISSING when it was already deleted."""
    with transaction.atomic():
        fresh = StickyNote.objects.select_for_update().filter(pk=note.pk, deleted_at__isnull=True).first()
        if fresh is None:
            return MISSING
        now = timezone.now()
        fresh.deleted_at, fresh.deleted_by, fresh.deleted_by_label = now, _actor(actor), label(actor)
        fresh.save(update_fields=["deleted_at", "deleted_by", "deleted_by_label"])
        NoteEvent.objects.create(note=fresh, kind=NoteEvent.DELETED, at=now, by=_actor(actor), by_label=label(actor))
        for application in _applications_of(fresh.email):
            audit.record(application, ApplicationEvent.NOTE_DELETED, actor=actor, channel=audit.OFFICE, message=fresh.text, meta={"note": str(fresh.pk)})
    return DONE


def edit_note(note, actor, text):
    """Change the text of a live note (R9). The author and date stay; `edited_at` / `edited_by` say who changed it last. Leaves "Note edited
    by X" with the PREVIOUS text in the timeline (a NoteEvent) and a Gold `note_edited` event on each of his applications. Returns
    EMPTY, UNCHANGED, TOO_LONG, MISSING (deleted meanwhile) or DONE."""
    text = audit.clean_text(text)
    if not text:
        return EMPTY
    with transaction.atomic():
        fresh = StickyNote.objects.select_for_update().filter(pk=note.pk, deleted_at__isnull=True).first()
        if fresh is None:
            return MISSING
        if text == audit.clean_text(fresh.text):
            return UNCHANGED
        if len(text) > NOTE_MAX:
            return TOO_LONG
        before, now = fresh.text, timezone.now()
        fresh.text, fresh.edited_at, fresh.edited_by, fresh.edited_by_label = text, now, _actor(actor), label(actor)
        fresh.save(update_fields=["text", "edited_at", "edited_by", "edited_by_label"])
        NoteEvent.objects.create(note=fresh, kind=NoteEvent.EDITED, at=now, by=_actor(actor), by_label=label(actor), text=before)
        for application in _applications_of(fresh.email):
            audit.record(application, ApplicationEvent.NOTE_EDITED, actor=actor, channel=audit.OFFICE, message=before, meta={"note": str(fresh.pk)}, at=now)
    return DONE


def _applications_of(email):
    return GoldApplication.objects.filter(Q(email__iexact=email) | Q(user__email__iexact=email))


def restore_note(note, actor):
    """Bring a deleted note back on the board (its author and date are kept) and write "Note restored by X" where the delete line
    went. Idempotent: returns DONE, or ALREADY when it is not deleted (restoring twice does nothing)."""
    with transaction.atomic():
        fresh = StickyNote.objects.select_for_update().filter(pk=note.pk, deleted_at__isnull=False).first()
        if fresh is None:
            return ALREADY
        fresh.deleted_at, fresh.deleted_by, fresh.deleted_by_label = None, None, ""
        fresh.save(update_fields=["deleted_at", "deleted_by", "deleted_by_label"])
        NoteEvent.objects.create(note=fresh, kind=NoteEvent.RESTORED, by=_actor(actor), by_label=label(actor))
        for application in _applications_of(fresh.email):
            audit.record(application, ApplicationEvent.NOTE_RESTORED, actor=actor, channel=audit.OFFICE, message=fresh.text, meta={"note": str(fresh.pk)})
    return DONE


# ---------- the approach list ----------

def open_entries(addresses, user, application):
    query = Q(lead_email__in=list(addresses)) | Q(gold_application__email__in=list(addresses))
    for address in addresses:
        query |= Q(user__email__iexact=address) | Q(gold_application__email__iexact=address)
    if user is not None:
        query |= Q(user=user) | Q(gold_application__user=user)
    if application is not None:
        query |= Q(gold_application=application)
    return OutreachEntry.objects.filter(query, done_at__isnull=True)


def add_to_list(actor, user=None, lead_email="", application=None, reason=""):
    """Put a person on the approach list from a lead, person or Gold page. One open entry per PERSON: an address that also
    has an account, or an application, is the same person. Returns (DONE | ALREADY | TOO_LONG | MISSING, entry)."""
    reason = audit.clean_text(reason)
    if len(reason) > REASON_MAX:
        return TOO_LONG, None
    main, addresses, found = people.resolve(user=user, email=lead_email, application=application)
    user = found
    if user is None and application is None and not main:
        return MISSING, None
    with transaction.atomic():
        existing = open_entries(addresses, user, application).first()
        if existing is not None:
            return ALREADY, existing
        target = {"user": user} if user is not None else ({"gold_application": application} if application is not None else {"lead_email": main})
        try:
            with transaction.atomic():
                entry = OutreachEntry.objects.create(reason=reason, added_by=_actor(actor), added_by_label=label(actor), **target)
        except IntegrityError:  # a double submit that raced past the check
            return ALREADY, OutreachEntry.objects.filter(**target, done_at__isnull=True).first()
    return DONE, entry


def mark_done(entry, actor):
    if entry.done_at is not None:
        return ALREADY
    entry.done_at, entry.done_by, entry.done_by_label = timezone.now(), _actor(actor), label(actor)
    entry.save(update_fields=["done_at", "done_by", "done_by_label"])
    return DONE


def remove_entry(entry):
    entry.delete()
    return DONE


# ---------- messages: staff now write by WhatsApp (whatsapp.services); old PersonMessage rows still show in timelines ----------

def is_unsubscribed(addresses, user=None):
    from mailings.models import EmailOptOut

    if EmailOptOut.objects.filter(email__in=[a.lower() for a in addresses]).exists():
        return True
    return bool(user is not None and user.marketing_consent is False)


# ---------- archived leads (R6) ----------

def archived_row(email):
    return ArchivedLead.objects.filter(email=(email or "").strip().lower()).first()


def _figures_changed():
    """The Leads totals and tiles are stored figures: ask for a rebuild (debounced, after commit; never raises)."""
    from office import snapshots

    snapshots.request_refresh()


def archive_lead(email, actor, reason=""):
    """Put a lead away: he leaves Leads, its counts and the next-morning email (if not sent yet); nothing is deleted. Records
    "Archived by X" for his timeline. Returns (DONE | ALREADY | TOO_LONG | MISSING, row)."""
    email, reason = (email or "").strip().lower(), audit.clean_text(reason)
    if not email:
        return MISSING, None
    if len(reason) > REASON_MAX:
        return TOO_LONG, None
    with transaction.atomic():
        existing = ArchivedLead.objects.filter(email=email).first()
        if existing is not None:
            return ALREADY, existing
        try:
            with transaction.atomic():
                row = ArchivedLead.objects.create(email=email, reason=reason, archived_by=_actor(actor), archived_by_label=label(actor))
        except IntegrityError:  # a double submit that raced past the check
            return ALREADY, ArchivedLead.objects.filter(email=email).first()
        LeadArchiveEvent.objects.create(email=email, kind=LeadArchiveEvent.ARCHIVED, reason=reason, by=_actor(actor), by_label=label(actor))
    _figures_changed()
    return DONE, row


def unarchive_lead(email, actor):
    """Move a lead back to Leads. Records "Moved back by X". Returns DONE, or ALREADY when he was not archived."""
    email = (email or "").strip().lower()
    with transaction.atomic():
        if not ArchivedLead.objects.filter(email=email).delete()[0]:
            return ALREADY
        LeadArchiveEvent.objects.create(email=email, kind=LeadArchiveEvent.RESTORED, by=_actor(actor), by_label=label(actor))
    _figures_changed()
    return DONE


# ---------- erasure and the timeline ----------

def erase_email(email):
    """UK GDPR: notes, messages and approach-list entries held for this address go with the person."""
    email = (email or "").strip().lower()
    if not email:
        return 0
    return (StickyNote.objects.filter(email=email).delete()[0] + PersonMessage.objects.filter(email=email).delete()[0]
            + OutreachEntry.objects.filter(lead_email=email).delete()[0] + ArchivedLead.objects.filter(email=email).delete()[0]
            + LeadArchiveEvent.objects.filter(email=email).delete()[0] + NextMorningEmail.objects.filter(email=email).delete()[0]
            + PersonEdit.objects.filter(email=email).delete()[0])


def timeline_entries(addresses):
    """[(at, kind, label, detail, note_id)] for the person's timeline (`note_id` is set only on a deleted-note line that can be restored): deleted notes, messages sent, archived / moved back, and the
    next-morning email (sent, or skipped and why)."""
    addresses = list(addresses)
    out, listed = [], set()
    for event in NoteEvent.objects.filter(note__email__in=addresses).select_related("note"):
        note = event.note
        if event.kind == NoteEvent.EDITED:  # the line shows the text the note had BEFORE the edit
            out.append((event.at, "note_edited", f"Note edited by {event.by_label or 'someone'}", event.text, ""))
            continue
        verb = "deleted" if event.kind == NoteEvent.DELETED else "restored"
        can_restore = event.kind == NoteEvent.DELETED and note.deleted_at is not None and note.deleted_at == event.at  # only the latest delete line, while it is deleted
        out.append((event.at, f"note_{verb}", f"Note {verb} by {event.by_label or 'someone'}", note.text, str(note.pk) if can_restore else ""))
        listed.add(note.pk)
    for note in StickyNote.objects.filter(email__in=addresses, deleted_at__isnull=False).exclude(pk__in=listed):  # deleted before the events existed
        out.append((note.deleted_at, "note_deleted", f"Note deleted by {note.deleted_by_label or 'someone'}", note.text, str(note.pk)))
    for message in PersonMessage.objects.filter(email__in=addresses):
        out.append((message.sent_at, "message_sent", f"Message sent by {message.author_label or 'the team'}", message.text, ""))
    for edit in PersonEdit.objects.filter(email__in=addresses):
        noun = {PersonEdit.MOBILE: "Mobile", PersonEdit.EMAIL: "Email"}.get(edit.what, "First name")
        verb = "added" if not edit.before else ("removed" if not edit.after else "changed")
        detail = f"{edit.before} to {edit.after}" if edit.what == PersonEdit.EMAIL else (edit.after or edit.before)
        out.append((edit.at, "person_edit", f"{noun} {verb} by {edit.by_label or 'someone'}", detail, ""))
    for event in LeadArchiveEvent.objects.filter(email__in=addresses):
        verb = "Archived" if event.kind == LeadArchiveEvent.ARCHIVED else "Moved back"
        out.append((event.at, f"lead_{event.kind}", f"{verb} by {event.by_label or 'someone'}", event.reason, ""))
    for row in NextMorningEmail.objects.filter(email__in=addresses):
        if row.sent_at:
            out.append((row.sent_at, "next_morning_sent", "Next-morning email sent", "", ""))
        elif row.skipped_at:
            out.append((row.skipped_at, "next_morning_skipped", f"Next-morning email skipped: {row.skip_reason}", "", ""))
    return out


# ---------- first name and mobile typed by staff (lead page, person page) ----------

def _edit(main, what, before, after, actor):
    PersonEdit.objects.create(email=main, what=what, before=before or "", after=after or "", by=_actor(actor), by_label=label(actor))


def set_lead_contact(email, actor, first_name=None, mobile=None, mobile_country=None):
    """Add or fix a lead's first name and mobile (`None` = leave as it is, "" = clear it). Written on every journey that left this
    address, so Leads, the chat and the next-morning email all see it; each change is a line in his timeline. Returns (result, errors):
    DONE, UNCHANGED or INVALID (errors {field: message}; a mobile that belongs to someone else adds `owner` {name, url})."""
    from django.core.exceptions import ValidationError

    from common.validators import normalise_mobile
    from journey.models import JourneySession
    from whatsapp import services as whatsapp

    main = (email or "").strip().lower()
    sessions = list(JourneySession.objects.filter(lead_email__iexact=main, is_bot=False))
    if not sessions:
        return MISSING, {}
    current_name = next((s.lead_first_name for s in sessions if s.lead_first_name), "")
    current_mobile = next((s.lead_mobile for s in sessions if s.lead_mobile), "")
    errors, new_name, new_mobile = {}, current_name, current_mobile
    if first_name is not None:
        new_name = " ".join(str(first_name).replace("\x00", "").split())
        if len(new_name) > 100:
            errors["first_name"], new_name = "First name: keep it to 100 characters.", current_name
    if mobile is not None:
        text = str(mobile).strip()
        try:
            new_mobile = normalise_mobile(text, mobile_country) if text else ""
        except ValidationError as error:
            errors["mobile"], new_mobile = error.messages[0], current_mobile
        owner = whatsapp.owner_of_phone(new_mobile, exclude_email=main) if new_mobile and "mobile" not in errors else None
        if owner:
            errors["mobile"], errors["owner"] = f"This number is already on {owner['name']}.", owner
    if errors:
        return INVALID, errors
    if (new_name, new_mobile) == (current_name, current_mobile):
        return UNCHANGED, {}
    with transaction.atomic():
        for session in sessions:
            session.lead_first_name, session.lead_mobile = new_name, new_mobile
            session.save(update_fields=["lead_first_name", "lead_mobile", "updated_at"])
        if new_name != current_name:
            _edit(main, PersonEdit.FIRST_NAME, current_name, new_name, actor)
        if new_mobile != current_mobile:
            _edit(main, PersonEdit.MOBILE, current_mobile, new_mobile, actor)
    whatsapp.relink(current_mobile, new_mobile)
    return DONE, {}


def set_person_mobile(user, actor, mobile, mobile_country=None):
    """Add or fix a registered person's mobile (any country, E.164, unique). Returns (DONE | UNCHANGED | INVALID, errors)."""
    from django.core.exceptions import ValidationError

    from common.validators import normalise_mobile
    from whatsapp import services as whatsapp

    text = (mobile or "").strip()
    try:
        new = normalise_mobile(text, mobile_country) if text else ""
    except ValidationError as error:
        return INVALID, {"mobile": error.messages[0]}
    owner = whatsapp.owner_of_phone(new, exclude_user=user) if new else None
    if owner:
        return INVALID, {"mobile": f"This number is already on {owner['name']}.", "owner": owner}
    before = user.mobile or ""
    if new == before:
        return UNCHANGED, {}
    user.mobile = new or None
    user.save(update_fields=["mobile", "updated_at"])
    _edit((user.email or "").lower(), PersonEdit.MOBILE, before, new, actor)
    whatsapp.relink(before, new)
    return DONE, {}


# ---------- bounced lead emails: Possible fake, correct the address, send the follow-up again ----------

TAKEN, BOUNCED, NO_SENDER, SENT, NOT_SENT = "taken", "bounced", "no_sender", "sent", "not_sent"
BOUNCE_NOTICE = "This email bounced, so it may not be real. Remove the lead if it looks like spam, or correct the address if it's a typo and resend the follow-up."


def bounced_set(addresses):
    """The lower-cased addresses among `addresses` that are on the suppression list for a PERMANENT BOUNCE (a spam complaint does not count). One query."""
    from notifications.models import EmailSuppression

    wanted = {(a or "").strip().lower() for a in addresses if a}
    if not wanted:
        return set()
    return set(EmailSuppression.objects.filter(email__in=wanted, reason=EmailSuppression.HARD_BOUNCE).values_list("email", flat=True))


def is_bounced(email):
    return bool(bounced_set([email]))


def owner_of_email(new, exclude=""):
    """Who already holds this address: {"kind": "account"|"lead", "name", "url"} or None. An account (any, verified or not) or another lead's journeys."""
    from django.urls import reverse

    from journey.models import JourneySession
    from users.models import User

    user = User.objects.filter(email__iexact=new).first()
    if user is not None:
        name = user.get_full_name() or user.email
        return {"kind": "account", "name": name, "url": reverse("office_person", args=[user.pk], urlconf="config.urls_office") if hasattr(user, "interest") else ""}
    session = JourneySession.objects.filter(lead_email__iexact=new, is_bot=False).exclude(lead_email__iexact=exclude).order_by("-created_at").first()
    if session is not None:
        return {"kind": "lead", "name": session.lead_first_name or new, "url": reverse("office_lead", args=[session.pk], urlconf="config.urls_office")}
    return None


def correct_lead_email(old, new, actor):
    """Fix a lead's address (a typo): written on every journey that left the old one, and his notes, messages, list entries and history follow it.
    Refused when the new address already belongs to another lead or an account (the answer says whose). The old address stays on the suppression
    list. Audited ("Email changed by X"). Returns (DONE | UNCHANGED | INVALID | TAKEN | MISSING, info): info is the message for INVALID, or
    the owner {kind, name, url} for TAKEN."""
    from django.core.exceptions import ValidationError

    from chat import services as chat_services
    from common.validators import normalise_email
    from journey.models import JourneySession
    from notifications.models import EmailLog
    from whatsapp import services as whatsapp

    old = (old or "").strip().lower()
    try:
        new = normalise_email(new)
    except ValidationError as error:
        return INVALID, error.messages[0]
    sessions = list(JourneySession.objects.filter(lead_email__iexact=old, is_bot=False))
    if not sessions:
        return MISSING, ""
    if new == old:
        return UNCHANGED, ""
    owner = owner_of_email(new, exclude=old)
    if owner:
        return TAKEN, owner
    with transaction.atomic():
        for session in sessions:
            session.lead_email = new
            session.save(update_fields=["lead_email", "updated_at"])
        for model, field in ((StickyNote, "email"), (PersonMessage, "email"), (OutreachEntry, "lead_email"), (PersonEdit, "email"), (ArchivedLead, "email"), (LeadArchiveEvent, "email")):
            model.objects.filter(**{field: old}).update(**{field: new})
        NextMorningEmail.objects.filter(email=old).delete()  # the old address is not kept (the suppression list is the one record of it); the new one may be sent its own follow-up
        chat_services.move_lead_email(old, new)  # an Ask us chat where he gave the old address
        EmailLog.objects.filter(Q(to__iexact=old) | Q(subject_email__iexact=old)).delete()  # emails sent to the old address (the bounce) are not his on the new one
        _edit(new, PersonEdit.EMAIL, old, new, actor)
    whatsapp.relink(*{s.lead_mobile for s in sessions if s.lead_mobile})  # his WhatsApp chat now links to the corrected address
    _figures_changed()
    return DONE, ""


def follow_up_state(email):
    """For the lead page: {corrected (a staff correction exists), sent (the next-morning email already went to this address)}."""
    email = (email or "").strip().lower()
    return {"corrected": PersonEdit.objects.filter(email=email, what=PersonEdit.EMAIL).exists(),
            "sent": NextMorningEmail.objects.filter(email=email, sent_at__isnull=False).exists()}


def resend_follow_up(email, actor):
    """Send the next-morning email to this address now, once (after a correction). Works with the automatic switch off, but needs the sender
    address; not while the address is still bounced. Returns SENT, BOUNCED, NO_SENDER, ALREADY (it went before), MISSING or NOT_SENT (info: why)."""
    from common.emaildefaults import SENDER_PERSON
    from journey.models import JourneySession
    from notifications import emailsettings
    from plans.models import SiteSettings

    from . import nextmorning

    email = (email or "").strip().lower()
    if not JourneySession.objects.filter(lead_email__iexact=email, is_bot=False).exists():
        return MISSING, ""
    if is_bounced(email):
        return BOUNCED, ""
    site, now = SiteSettings.load(), timezone.now()
    if emailsettings.options_for(nextmorning.TEMPLATE).sender == SENDER_PERSON and not site.auto_sender:
        return NO_SENDER, ""
    with transaction.atomic():
        row = NextMorningEmail.objects.filter(email=email).first()
        if row is not None and row.sent_at:
            return ALREADY, ""
        if row is None:
            first = JourneySession.objects.filter(lead_email__iexact=email, is_bot=False, lead_at__isnull=False).order_by("lead_at").values_list("lead_at", flat=True).first()
            try:
                with transaction.atomic():
                    row = NextMorningEmail.objects.create(email=email, lead_at=first or now, due_at=now, claimed_at=now)  # unique email: a second click cannot make a second row
            except IntegrityError:
                return ALREADY, ""
        else:  # the one winner of a conditional update on claimed_at sends: a double click, or the worker, can never send it twice
            same = Q(claimed_at=row.claimed_at) if row.claimed_at else Q(claimed_at__isnull=True)
            if not NextMorningEmail.objects.filter(same, pk=row.pk, sent_at__isnull=True).update(claimed_at=now, due_at=now, skipped_at=None, skip_reason=""):
                return ALREADY, ""
            row.refresh_from_db()
    outcome = nextmorning.send_one(row, site, now, force=True)
    return (SENT, "") if outcome == "sent" else (NOT_SENT, outcome)
