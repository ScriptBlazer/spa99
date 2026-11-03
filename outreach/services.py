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
        noun = "Mobile" if edit.what == PersonEdit.MOBILE else "First name"
        verb = "added" if not edit.before else ("removed" if not edit.after else "changed")
        out.append((edit.at, "person_edit", f"{noun} {verb} by {edit.by_label or 'someone'}", edit.after or edit.before, ""))
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
