"""Sticky notes, the approach list and one-to-one messages. Short functions that return a result word, so the views stay thin."""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from common.tasks import enqueue
from gold import audit
from gold.models import ApplicationEvent, GoldApplication

from . import people
from .models import (MESSAGE_MAX, NOTE_MAX, REASON_MAX, ArchivedLead, LeadArchiveEvent, NextMorningEmail, NoteEvent, OutreachEntry, PersonEdit,
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
    """The person's entries that are on the list now: open, and not left behind by registering (an entry whose account was verified AFTER he was added no longer counts: registering takes him
    off the list, and nothing is rewritten for that: this lookup, and the list, simply leave such rows out)."""
    from . import listing

    query = Q(lead_email__in=list(addresses)) | Q(gold_application__email__in=list(addresses))
    for address in addresses:
        query |= Q(user__email__iexact=address) | Q(gold_application__email__iexact=address)
    if user is not None:
        query |= Q(user=user) | Q(gold_application__user=user)
    if application is not None:
        query |= Q(gold_application=application)
    return listing.with_state(OutreachEntry.objects.filter(query, done_at__isnull=True)).filter(listing.NOT_AFTER_ADDED)


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
        except IntegrityError:  # an open entry for this target exists: a double submit that raced past the check, or one hidden because he registered after he was added
            return _revive_or_already(target, actor, reason)
    _figures_changed()  # a lead on the list is not in Leads: the stored Leads total follows
    return DONE, entry


def _revive_or_already(target, actor, reason):
    """The target already has an open entry. If the list shows it, he is already on it (ALREADY). If registering hid it (see `open_entries`), put it back as a fresh add: new time, adder and reason,
    so staff adding him again really gets him on the list. Returns (DONE | ALREADY, entry)."""
    from . import listing

    entry = OutreachEntry.objects.filter(**target, done_at__isnull=True).first()
    if entry is None:
        return ALREADY, None
    if listing.with_state(OutreachEntry.objects.filter(pk=entry.pk)).filter(listing.NOT_AFTER_ADDED).exists():
        return ALREADY, entry
    entry.added_at, entry.added_by, entry.added_by_label, entry.reason = timezone.now(), _actor(actor), label(actor), reason
    entry.save(update_fields=["added_at", "added_by", "added_by_label", "reason"])
    _figures_changed()
    return DONE, entry


def mark_done(entry, actor):
    if entry.done_at is not None:
        return ALREADY
    entry.done_at, entry.done_by, entry.done_by_label = timezone.now(), _actor(actor), label(actor)
    entry.save(update_fields=["done_at", "done_by", "done_by_label"])
    return DONE


def remove_entry(entry):
    entry.delete()
    _figures_changed()
    return DONE


# ---------- messages: the Email button (a plain text email from the logged-in person) ----------

def send_message(actor, to_email, text):
    """Record a one-to-one email and queue it (task outreach.tasks.send_office_message: template `office_message`, From and Reply-To the logged-in person, his signature). An unsubscribed person
    still gets it: it is not marketing. A queue that cannot take it marks the row failed. Returns (result, message)."""
    text, to_email = audit.clean_text(text), (to_email or "").strip().lower()
    if not text or not to_email:
        return EMPTY, None
    if len(text) > MESSAGE_MAX:
        return TOO_LONG, None
    recent = PersonMessage.objects.filter(email=to_email, text=text, sent_at__gte=timezone.now() - DUPLICATE_WINDOW).exclude(status=PersonMessage.FAILED)  # a failed send may be tried again
    recent = recent.filter(author=actor) if getattr(actor, "pk", None) else recent.filter(author__isnull=True)
    if recent.exists():
        return DUPLICATE, None
    message = PersonMessage.objects.create(email=to_email, text=text, author=_actor(actor), author_label=label(actor), status=PersonMessage.QUEUED)
    try:
        enqueue("outreach.tasks.send_office_message", str(message.pk))
    except Exception:  # noqa: BLE001 - the message is recorded as failed; the problem is logged
        logger.exception("Could not queue the Office email to a person")
        PersonMessage.objects.filter(pk=message.pk).update(status=PersonMessage.FAILED)
    message.refresh_from_db()  # inline (tests) or a fast worker may already have finished it
    return DONE, message


def email_block(address):
    """"" when the address can be emailed, else the plain reason it cannot (no valid address, bounced, or marked as spam)."""
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    from notifications.models import EmailSuppression

    address = (address or "").strip().lower()
    try:
        validate_email(address)
    except ValidationError:
        return "No valid email address."
    row = EmailSuppression.objects.filter(email=address).first()
    if row is None:
        return ""
    return "This address marked an email as spam, so he cannot be emailed." if row.reason == EmailSuppression.COMPLAINT else "This address bounced, so he cannot be emailed."

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


# ---------- the approach list and Leads: who is where ----------

def approach_entries(email_expr):
    """OutreachEntry rows (open or done) that put this lead address on the approach list: a lead entry, or a Gold application of the same address. Used inside Exists(): `email_expr` is the
    outer row's lower-cased address (OuterRef). A lead on the list is not in Leads; taking the entry away (Back to Leads) puts him back."""
    return OutreachEntry.objects.annotate(application_key=Lower("gold_application__email")).filter(Q(lead_email=email_expr) | Q(application_key=email_expr))


def has_mobile_q(email_expr):
    """Exists(): the address has a mobile: any journey of his holds one, or a Gold application of his does."""
    from django.db.models import Exists

    from journey.models import JourneySession

    sessions = JourneySession.objects.filter(is_bot=False).exclude(lead_mobile="").annotate(k=Lower("lead_email")).filter(k=email_expr)
    applications = GoldApplication.objects.exclude(mobile="").annotate(k=Lower("email")).filter(k=email_expr)
    return Exists(sessions) | Exists(applications)


def has_mobile(email):
    from django.db.models import OuterRef  # noqa: F401 - for readers: the same test, one address

    email = (email or "").strip().lower()
    from journey.models import JourneySession

    return (JourneySession.objects.filter(is_bot=False, lead_email__iexact=email).exclude(lead_mobile="").exists()
            or GoldApplication.objects.filter(email__iexact=email).exclude(mobile="").exists())


def entry_to_leads(entry):
    """Back to Leads: a LEAD entry (an address, no account, no Gold application) is taken off the list, so he shows in Leads again. Returns (DONE | MISSING, lead_email, reason)."""
    if not entry.lead_email:
        return MISSING, "", ""
    email, reason = entry.lead_email, entry.reason
    OutreachEntry.objects.filter(lead_email=email).delete()  # his older Done entries too: any row (open or done) keeps a lead out of Leads (see approach_entries)
    _figures_changed()
    return DONE, email, reason


def entry_archive(entry, actor, reason=""):
    """Archive from the list: the lead is put away (the usual Archive, with its optional reason) and the entry goes, so he is on neither list. Returns (result, lead_email)."""
    if not entry.lead_email:
        return MISSING, ""
    email = entry.lead_email
    with transaction.atomic():
        result, _ = archive_lead(email, actor, reason)
        if result in (DONE, ALREADY):
            OutreachEntry.objects.filter(lead_email=email).delete()  # his older Done entries too, or they would keep him out of Leads after Unarchive
    return result, email


EMAILED_NO_NUMBER = "Emailed, no number"
GROUP_EMAIL_LABEL = "Group email"


def archive_after_group_email(email):
    """A group send reached this lead: with no mobile he moves to Archived, reason "Emailed, no number", "by" the group email (not a person). A lead with a mobile stays. Already archived: nothing
    changes. Returns DONE, ALREADY or UNCHANGED (he has a mobile)."""
    email = (email or "").strip().lower()
    if not email or has_mobile(email):
        return UNCHANGED
    with transaction.atomic():
        if ArchivedLead.objects.filter(email=email).exists():
            return ALREADY
        try:
            with transaction.atomic():
                ArchivedLead.objects.create(email=email, reason=EMAILED_NO_NUMBER, archived_by=None, archived_by_label=GROUP_EMAIL_LABEL)
        except IntegrityError:
            return ALREADY
        LeadArchiveEvent.objects.create(email=email, kind=LeadArchiveEvent.ARCHIVED, reason=EMAILED_NO_NUMBER, by=None, by_label=GROUP_EMAIL_LABEL)
    _figures_changed()
    return DONE


def _number_arrived(email, actor):
    """Staff added a number to a lead the group email archived for having none ("Emailed, no number"): he leaves Archived and joins the approach list, as if he had used his link. Any other lead is left
    exactly where he is (adding a number to a lead is not a reason to move him)."""
    row = ArchivedLead.objects.filter(email=email, reason=EMAILED_NO_NUMBER, archived_by_label=GROUP_EMAIL_LABEL).first()
    if row is None:
        return
    row.delete()
    LeadArchiveEvent.objects.create(email=email, kind=LeadArchiveEvent.RESTORED, by=_actor(actor), by_label=label(actor))
    add_to_list(actor, lead_email=email, reason="Number added after the group email")
    _figures_changed()


def return_bounced_lead(email):
    """A permanent bounce arrived for this address. If he was archived by the group email for having no number, he comes back to Leads (where he shows Possible fake). Only rows archived for that
    reason come back: someone a person archived stays archived. Returns True when he came back."""
    email = (email or "").strip().lower()
    with transaction.atomic():
        row = ArchivedLead.objects.filter(email=email, reason=EMAILED_NO_NUMBER, archived_by_label=GROUP_EMAIL_LABEL).first()
        if row is None:
            return False
        row.delete()
        LeadArchiveEvent.objects.create(email=email, kind=LeadArchiveEvent.RESTORED, by=None, by_label="Bounce")
    _figures_changed()
    return True


# ---------- the add-your-number link (the public page, mailings.addnumber) ----------

USED, REGISTERED = "used", "registered"
SELF_LABEL = "His own link"


def add_number_state(email):
    """What the link page shows for this address: "open" (he can give a number), "used" (he already has a number, or has registered), "ended" (no journey of his is left)."""
    from journey.models import JourneySession
    from users.models import User

    email = (email or "").strip().lower()
    if not JourneySession.objects.filter(lead_email__iexact=email, is_bot=False).exists():
        return "ended"
    if User.objects.filter(email__iexact=email, email_verified_at__isnull=False).exists() or has_mobile(email):
        return "used"
    return "open"


def add_number_from_link(email, mobile, country=None):
    """He opened his personal link and gave a mobile. `email` comes only from the signed token. Writes the number on his journeys (the same place staff write it), records "Mobile added by His own link" in
    his timeline (a PersonEdit), records the consent version he ticked, brings him back from Archived, and puts him on the approach list with the source. Refused with nothing changed: no journey
    of his address left (MISSING), an account has taken the address (REGISTERED), he already has a number (USED), the number is on someone else (INVALID, `taken`), the number is not valid (INVALID).
    Returns (result, info). Does not say whose number it is."""
    from django.core.exceptions import ValidationError

    from common.validators import normalise_mobile
    from journey.copy import CONSENT_VERSION
    from journey.models import JourneySession
    from users.models import User

    email = (email or "").strip().lower()
    sessions = list(JourneySession.objects.filter(lead_email__iexact=email, is_bot=False))
    if not sessions:
        return MISSING, ""
    if User.objects.filter(email__iexact=email, email_verified_at__isnull=False).exists():
        return REGISTERED, ""
    if any(s.lead_mobile for s in sessions) or GoldApplication.objects.filter(email__iexact=email).exclude(mobile="").exists():
        return USED, ""
    try:
        number = normalise_mobile(str(mobile or "").strip(), country)
    except ValidationError as error:
        return INVALID, error.messages[0]
    if owner_of_phone(number, exclude_email=email):
        return INVALID, "taken"
    with transaction.atomic():
        for session in sessions:
            session.lead_mobile = number
            session.lead_consent_version = CONSENT_VERSION
            session.save(update_fields=["lead_mobile", "lead_consent_version", "updated_at"])
        PersonEdit.objects.create(email=email, what=PersonEdit.MOBILE, before="", after=number, by=None, by_label=SELF_LABEL)
        if ArchivedLead.objects.filter(email=email).delete()[0]:
            LeadArchiveEvent.objects.create(email=email, kind=LeadArchiveEvent.RESTORED, by=None, by_label=SELF_LABEL)
        if not open_entries({email}, None, None).exists():
            try:
                with transaction.atomic():
                    OutreachEntry.objects.create(lead_email=email, reason="Gave his number through the group email link", added_by=None, added_by_label=SELF_LABEL)
            except IntegrityError:  # a double submit that raced past the check: he is on the list
                pass
    _figures_changed()
    return DONE, number


# ---------- the Emailed tag ----------

def emailed_at(addresses):
    """{address: the latest time a person or a group send emailed him}: the Email pop-up (PersonMessage sent) or a group send (a MailingRecipient sent). The automatic emails do not count.
    Two queries for a page of addresses."""
    from django.db.models import Max

    from mailings.models import MailingRecipient

    wanted = {(a or "").strip().lower() for a in addresses if a}
    if not wanted:
        return {}
    found = {}
    for address, at in PersonMessage.objects.filter(email__in=wanted, status=PersonMessage.SENT).values_list("email").annotate(at=Max("sent_at")).order_by().values_list("email", "at"):
        found[address] = at
    for address, at in MailingRecipient.objects.filter(email__in=wanted, status__in=(MailingRecipient.SENT, MailingRecipient.BOUNCED), sent_at__isnull=False).values_list("email").annotate(at=Max("sent_at")).order_by().values_list("email", "at"):
        if address not in found or at > found[address]:
            found[address] = at
    return found


def emailed_q(email_expr):
    """Exists(): the address was emailed by a person or a group send (for the Emailed filter)."""
    from django.db.models import Exists

    from mailings.models import MailingRecipient

    return (Exists(PersonMessage.objects.filter(email=email_expr, status=PersonMessage.SENT))
            | Exists(MailingRecipient.objects.filter(email=email_expr, status=MailingRecipient.SENT, sent_at__isnull=False)))


# ---------- erasure and the timeline ----------

def export_messages(addresses):
    """UK GDPR export: the staff emails sent to these addresses (text, who wrote it, status, time), oldest first."""
    addresses = [(a or "").strip().lower() for a in addresses if a]
    return [{"to": m.email, "subject": m.subject, "text": m.text, "written_by": m.author_label, "status": m.status, "sent_at": m.sent_at.isoformat()}
            for m in PersonMessage.objects.filter(email__in=addresses).order_by("sent_at", "id")]


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
        out.append((message.sent_at, "message_sent", f"Email {'failed' if message.status == PersonMessage.FAILED else 'sent'} by {message.author_label or 'the team'}", message.text, ""))
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


def _office_url(name, *args):
    from django.urls import reverse

    return reverse(name, args=args, urlconf="config.urls_office")


def owner_of_phone(phone, exclude_email="", exclude_user=None):
    """Who already has this number ({name, url}), or None. The same number is never kept on two people (an account, a lead's journeys or a Gold application)."""
    from journey.models import JourneySession
    from users.models import User

    if not phone:
        return None
    users = User.objects.filter(mobile=phone)
    if exclude_user is not None:
        users = users.exclude(pk=exclude_user.pk)
    other = users.filter(interest__isnull=False).first() or users.first()
    if other is not None:
        return {"name": other.get_full_name() or other.email, "url": _office_url("office_person", other.pk) if hasattr(other, "interest") else ""}
    sessions = JourneySession.objects.filter(lead_mobile=phone, is_bot=False).exclude(lead_email="")
    if exclude_email:
        sessions = sessions.exclude(lead_email__iexact=exclude_email)
    if exclude_user is not None and exclude_user.email:
        sessions = sessions.exclude(lead_email__iexact=exclude_user.email)
    found = sessions.order_by("-created_at").first()
    if found is not None:
        return {"name": found.lead_first_name or found.lead_email.lower(), "url": _office_url("office_lead", found.pk)}
    applications = GoldApplication.objects.filter(mobile=phone)  # a Gold applicant's number counts too; a person's own application does not
    if exclude_email:
        applications = applications.exclude(email__iexact=exclude_email)
    if exclude_user is not None:
        applications = applications.exclude(user=exclude_user)
        if exclude_user.email:
            applications = applications.exclude(email__iexact=exclude_user.email)
    gold = applications.order_by("-created_at").first()
    if gold is not None:
        return {"name": gold.full_name or gold.email.lower(), "url": _office_url("office_gold_application", gold.pk)}
    return None


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
        owner = owner_of_phone(new_mobile, exclude_email=main) if new_mobile and "mobile" not in errors else None
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
            if new_mobile and not current_mobile:
                _number_arrived(main, actor)
    return DONE, {}


def set_person_mobile(user, actor, mobile, mobile_country=None):
    """Add or fix a registered person's mobile (any country, E.164, unique). Returns (DONE | UNCHANGED | INVALID, errors)."""
    from django.core.exceptions import ValidationError

    from common.validators import normalise_mobile

    text = (mobile or "").strip()
    try:
        new = normalise_mobile(text, mobile_country) if text else ""
    except ValidationError as error:
        return INVALID, {"mobile": error.messages[0]}
    owner = owner_of_phone(new, exclude_user=user) if new else None
    if owner:
        return INVALID, {"mobile": f"This number is already on {owner['name']}.", "owner": owner}
    before = user.mobile or ""
    if new == before:
        return UNCHANGED, {}
    user.mobile = new or None
    user.save(update_fields=["mobile", "updated_at"])
    _edit((user.email or "").lower(), PersonEdit.MOBILE, before, new, actor)
    return DONE, {}


def set_gold_mobile(application, actor, mobile, mobile_country=None):
    """Add or fix a Gold applicant's mobile (any country, E.164, unique). An applicant with a verified account: the account's mobile (set_person_mobile). Otherwise the application's,
    and any journey of his that already holds a number is kept in step, so the number the page shows is the number just fixed. Audited like the lead and person ones (a line in his
    timeline). Returns (DONE | UNCHANGED | INVALID, errors)."""
    from django.core.exceptions import ValidationError

    from common.validators import normalise_mobile
    from journey.models import JourneySession

    if application.user_id and application.user.email_verified_at:  # an unverified account is not him (the page shows the application's number): its mobile is left alone
        return set_person_mobile(application.user, actor, mobile, mobile_country)
    text = (mobile or "").strip()
    try:
        new = normalise_mobile(text, mobile_country) if text else ""
    except ValidationError as error:
        return INVALID, {"mobile": error.messages[0]}
    email = (application.email or "").strip().lower()
    owner = owner_of_phone(new, exclude_email=email) if new else None
    if owner:
        return INVALID, {"mobile": f"This number is already on {owner['name']}.", "owner": owner}
    sessions = list(JourneySession.objects.filter(lead_email__iexact=email, is_bot=False).exclude(lead_mobile="")) if email else []
    before = application.mobile or (sessions[0].lead_mobile if sessions else "")
    if new == (application.mobile or "") and all(session.lead_mobile == new for session in sessions):
        return UNCHANGED, {}
    with transaction.atomic():
        application.mobile = new
        application.save(update_fields=["mobile", "updated_at"])
        for session in sessions:
            session.lead_mobile = new
            session.save(update_fields=["lead_mobile", "updated_at"])
        _edit(email, PersonEdit.MOBILE, before, new, actor)
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
    """Who already holds this address: {"kind": "account"|"lead"|"gold"|"archived", "name", "url"} or None. An account (any, verified or not), another lead's journeys,
    a Gold application or an archived lead."""
    from django.urls import reverse

    from gold.models import GoldApplication
    from journey.models import JourneySession
    from users.models import User

    user = User.objects.filter(email__iexact=new).first()
    if user is not None:
        name = user.get_full_name() or user.email
        return {"kind": "account", "name": name, "url": reverse("office_person", args=[user.pk], urlconf="config.urls_office") if hasattr(user, "interest") else ""}
    session = JourneySession.objects.filter(lead_email__iexact=new, is_bot=False).exclude(lead_email__iexact=exclude).order_by("-created_at").first()
    if session is not None:
        return {"kind": "lead", "name": session.lead_first_name or new, "url": reverse("office_lead", args=[session.pk], urlconf="config.urls_office")}
    application = GoldApplication.objects.filter(email__iexact=new).order_by("-created_at").first()
    if application is not None:
        return {"kind": "gold", "name": application.full_name or new, "url": reverse("office_gold_application", args=[application.pk], urlconf="config.urls_office")}
    if ArchivedLead.objects.filter(email=new).exists():
        return {"kind": "archived", "name": new, "url": ""}
    return None


def _move_follow_up(old, new, bounced):
    """The next-morning row follows the address, so what already went is not sent again to the new one. A bounced old address: the row is dropped (a resend is then the staff action).
    The unique email: when the new address has a row of its own, the one that was sent wins."""
    row = NextMorningEmail.objects.filter(email=old).first()
    if row is None:
        return
    other = NextMorningEmail.objects.filter(email=new).first()
    if bounced or (other is not None and (other.sent_at or not row.sent_at)):
        row.delete()
        return
    if other is not None:
        other.delete()
    row.email = new
    row.save(update_fields=["email"])


def correct_lead_email(old, new, actor):
    """Change a lead's address (a typo or a new one he gave; after a bounce or not): written on every journey that left the old one, and his notes, messages, list entries and history follow it.
    Refused when the new address already belongs to another lead, an account, a Gold application, or an archived lead (the answer says whose), or when the old one is on a Gold application. The old address stays on the suppression
    list if it was on it. Audited ("Email changed by X"). Returns (DONE | UNCHANGED | INVALID | TAKEN | MISSING, info): info is the message for INVALID, or
    the owner {kind, name, url} for TAKEN."""
    from django.core.exceptions import ValidationError

    from chat import services as chat_services
    from common.validators import normalise_email
    from gold.models import GoldApplication
    from journey.models import JourneySession
    from mailings.models import EmailOptOut
    from notifications.models import EmailLog

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
    if GoldApplication.objects.filter(email__iexact=old).exists():  # one person on two addresses would split him: the application holds the address
        return INVALID, "This address is on a Gold application. Change it there."
    owner = owner_of_email(new, exclude=old)
    if owner:
        return TAKEN, owner
    bounced = is_bounced(old)
    with transaction.atomic():
        for session in sessions:
            session.lead_email = new
            session.save(update_fields=["lead_email", "updated_at"])
        for model, field in ((StickyNote, "email"), (PersonMessage, "email"), (OutreachEntry, "lead_email"), (PersonEdit, "email"), (ArchivedLead, "email"), (LeadArchiveEvent, "email")):
            model.objects.filter(**{field: old}).update(**{field: new})
        _move_follow_up(old, new, bounced)
        if EmailOptOut.objects.filter(email=old).exists():  # he asked us to stop: that follows him (the old one stays, as the record of the request)
            EmailOptOut.objects.get_or_create(email=new, defaults={"source": "moved"})
        chat_services.move_lead_email(old, new)  # an Ask us chat where he gave the old address
        if bounced:  # what went to a bouncing address is not his on the new one; otherwise the sent emails are his and follow the address (the timeline reads them by address)
            EmailLog.objects.filter(Q(to__iexact=old) | Q(subject_email__iexact=old)).delete()
        else:
            EmailLog.objects.filter(to__iexact=old).update(to=new)
            EmailLog.objects.filter(subject_email__iexact=old).update(subject_email=new)
        _edit(new, PersonEdit.EMAIL, old, new, actor)
    _figures_changed()
    return DONE, ""


def follow_up_state(email):
    """For the lead page: {corrected (a staff correction exists), sent (the next-morning email already went to this address)}."""
    email = (email or "").strip().lower()
    return {"corrected": PersonEdit.objects.filter(email=email, what=PersonEdit.EMAIL).exists(),
            "sent": NextMorningEmail.objects.filter(email=email, sent_at__isnull=False).exists()}


def resend_follow_up(email, actor):
    """Send the next-morning email to this address now, once (after a correction). Works with the automatic switch off; not while the address is still bounced. A missing sender
    is no reason to refuse: it goes from hello@. Returns SENT, BOUNCED, ALREADY (it went before), MISSING or NOT_SENT (info: why)."""
    from journey.models import JourneySession
    from plans.models import SiteSettings

    from . import nextmorning

    email = (email or "").strip().lower()
    if not JourneySession.objects.filter(lead_email__iexact=email, is_bot=False).exists():
        return MISSING, ""
    if is_bounced(email):
        return BOUNCED, ""
    site, now = SiteSettings.load(), timezone.now()
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
