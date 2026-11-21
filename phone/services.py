"""The voicemail logic, kept out of the views: what the webhooks do, the processing (download, then email) with its caps, the sweep, and the Office helpers.

Cost safety (docs/features/voicemail.md): every webhook is idempotent (a Twilio retry storm makes no duplicate rows and no duplicate emails), every run of
the processing counts an attempt, at MAX_ATTEMPTS it stops for good and last_error says why, retries back off, and the sweep handles at most SWEEP_BATCH rows
per run. Nothing here re-queues itself. Only GET calls to Twilio are possible (phone.twilio_api)."""
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.db.models import F, Q
from django.utils import timezone

from . import naming, twilio_api
from .models import MAX_ATTEMPTS, Call

logger = logging.getLogger("spa99.phone")

SWEEP_BATCH = 10
SWEEP_BUDGET_SECONDS = 90  # django-q kills a task at 120 s: the sweep stops taking new rows after this
CLAIM_MINUTES = 5
BACKOFF_MINUTES = (5, 10, 20, 40, 80, 160, 320, 640)  # after the 1st failed attempt, the 2nd ...


def enabled():
    return bool(settings.PHONE_ENABLED)


# ---------- the webhooks ----------

def start_call(call_sid, from_number, to_number, now=None):
    """/phone/voice/: the row for this call (made once; a repeat of the webhook changes nothing). Starts as "No message"."""
    now = now or timezone.now()
    call = Call.objects.filter(call_sid=call_sid).first()
    if call:
        for field, value in (("from_number", from_number), ("to_number", to_number)):  # a row made by an early recording callback has no numbers yet
            if value and not getattr(call, field):
                Call.objects.filter(pk=call.pk, **{field: ""}).update(**{field: value[:32]})
                setattr(call, field, value[:32])
        return call
    try:
        return Call.objects.create(call_sid=call_sid, from_number=from_number[:32], to_number=to_number[:32], received_at=now, kind=Call.MISSED, source=Call.LIVE)
    except IntegrityError:  # two copies of the webhook at once
        return Call.objects.get(call_sid=call_sid)


def record_callback(call_sid, recording_sid, status, duration, now=None):
    """/phone/recording/: the call now has a recording (or Twilio says it is absent: nothing was recorded). Returns the call when this is NEW
    information that needs processing, else None (a repeat of the callback, an unknown status, a second recording of the same call)."""
    if status not in (Call.COMPLETED, Call.ABSENT) or not call_sid:
        return None
    now = now or timezone.now()
    try:
        seconds = max(int(duration or 0), 0)
    except (TypeError, ValueError):
        seconds = 0
    call = Call.objects.filter(call_sid=call_sid).first()
    if call is None:  # the callback beat the voice webhook, or that webhook failed and Twilio used the fallback
        call = start_call(call_sid, "", "", now=now - timedelta(seconds=seconds))
    if call.recording_status:
        return None  # already recorded: a repeat, or a second recording; the first one stays
    if recording_sid and Call.objects.filter(recording_sid=recording_sid).exclude(pk=call.pk).exists():
        return None
    try:  # conditional: of two copies of the callback arriving together, only one changes the row, and only that one queues the work
        changed = Call.objects.filter(pk=call.pk, recording_status="").update(kind=Call.VOICEMAIL, recording_sid=recording_sid or None, recording_status=status, duration_seconds=seconds)
    except IntegrityError:
        return None
    if not changed:
        return None
    call.refresh_from_db()
    return call if (call.audio_pending or call.email_pending) else None


# ---------- processing ----------

def _claim(pk, now):
    """Take the row for one run: refused when it has run out of attempts, another worker has it, or it is backing off. Counts the attempt."""
    return Call.objects.filter(pk=pk, attempts__lt=MAX_ATTEMPTS).filter(Q(claimed_until__isnull=True) | Q(claimed_until__lt=now)).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)).update(claimed_until=now + timedelta(minutes=CLAIM_MINUTES), attempts=F("attempts") + 1)


def _save_audio(call):
    data = twilio_api.download_recording(call.recording_sid)
    if not data:
        raise twilio_api.TwilioError("Twilio sent an empty file")
    name = naming.store(data, call.received_at, call.from_number)
    Call.objects.filter(pk=call.pk).update(audio=name, audio_saved_at=timezone.now())


def _length(seconds):
    return f"{seconds} second{'' if seconds == 1 else 's'}" if seconds < 60 else f"{seconds // 60} min {seconds % 60} s"


def email_context(call):
    from django.utils.html import escape

    from notifications.emailbody import Rich

    caller = naming.friendly_number(call.from_number)
    when = f"{timezone.localtime(call.received_at):%d %B %Y, %H:%M}"
    lines = [f"From: {caller}", f"Received: {when}", f"Length: {_length(call.duration_seconds)}"]
    if not call.has_sound:  # unreachable while short ones (0 s included) are not emailed; kept so that rule can be undone
        lines.append("No sound was recorded.")
    return caller, {"details": Rich("<br>".join(escape(line) for line in lines), "\n".join(lines)), "url": f"{settings.OFFICE_URL}/calls/{call.pk}/"}


def _send_email(call):
    """One email, once. Returns (error, note). emailed_at is taken BEFORE sending (a conditional update), so two workers can never both send; a failed send gives it back."""
    from notifications.models import EmailLog
    from notifications.services import send_templated, subject_for
    from plans.models import SiteSettings

    if call.duration_seconds < SHORT_SECONDS:
        Call.objects.filter(pk=call.pk, emailed_at__isnull=True).update(email_skipped=True)
        return "", f"Shorter than {SHORT_SECONDS} seconds: no email sent."
    recipients = SiteSettings.load().voicemail_to_list
    if not recipients:
        Call.objects.filter(pk=call.pk, emailed_at__isnull=True).update(email_skipped=True)
        return "", "No one is on the Voicemail email to list (System > Emails): no email sent."
    if not Call.objects.filter(pk=call.pk, emailed_at__isnull=True, email_skipped=False).update(emailed_at=timezone.now()):
        return "", ""
    caller, context = email_context(call)
    log = send_templated("voicemail_new", recipients, subject_for("voicemail_new", caller=caller), context)
    if log.status == EmailLog.SENT:
        return "", ""
    if log.status == EmailLog.SUPPRESSED:
        Call.objects.filter(pk=call.pk).update(emailed_at=None, email_skipped=True)
        return "", "Every address is suppressed: no email sent."
    Call.objects.filter(pk=call.pk).update(emailed_at=None)
    return f"Email failed: {log.error}"[:300], ""


def process(pk):
    """The queued task and the sweep's step: download the audio (if due), then send the email (if due). Safe to run twice and to retry; never raises;
    returns a short status text. Each run that does anything counts one attempt, and the 8th failure is the last."""
    call = Call.objects.filter(pk=pk).first()
    if call is None or not (call.audio_pending or call.email_pending):
        return "nothing to do"
    if not call.email_pending and not (call.audio_pending and twilio_api.configured()):
        return "off" if call.audio_pending else "nothing to do"  # audio waits for the API key; it costs no attempt
    now = timezone.now()
    if not _claim(pk, now):
        return "skipped"
    call.refresh_from_db()
    errors, note = [], ""
    try:
        if call.audio_pending and twilio_api.configured():
            try:
                _save_audio(call)
            except Exception as error:  # noqa: BLE001 - recorded, retried later by the sweep (capped)
                errors.append(f"Audio: {error}"[:150])
        if call.email_pending:
            error, note = _send_email(call)
            if error:
                errors.append(error)
    except Exception as error:  # noqa: BLE001
        logger.exception("Voicemail %s processing failed", pk)
        errors.append(f"{type(error).__name__}: {error}"[:200])
    call.refresh_from_db()
    backoff = timedelta(minutes=BACKOFF_MINUTES[min(call.attempts, len(BACKOFF_MINUTES)) - 1])
    last = " | ".join(errors)[:300] or note
    Call.objects.filter(pk=pk).update(claimed_until=None, last_error=last, next_attempt_at=timezone.now() + backoff if errors else None)
    if errors and call.attempts >= MAX_ATTEMPTS:
        logger.error("Voicemail %s gave up after %s attempts: %s", pk, call.attempts, last)
    return "failed: " + last if errors else "done"


def pending_q(now):
    due = Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
    free = Q(claimed_until__isnull=True) | Q(claimed_until__lt=now)
    audio = Q(recording_status=Call.COMPLETED, audio="") if twilio_api.configured() else Q(pk__isnull=True)  # no API key: audio rows are not picked, so they cannot crowd out the rest
    work = audio | Q(source=Call.LIVE, kind=Call.VOICEMAIL, emailed_at__isnull=True, email_skipped=False)
    return Q(attempts__lt=MAX_ATTEMPTS) & due & free & work


def sweep(clock=time.monotonic):
    """Scheduled every 5 minutes: at most SWEEP_BATCH voicemails whose audio or email is still waiting, oldest first, and no new one after SWEEP_BUDGET_SECONDS (the queue
    kills a task at 120 s). A voicemail that is out of attempts or backing off is not picked. Calls process() directly: nothing is queued from here."""
    started = clock()
    ids = list(Call.objects.filter(pending_q(timezone.now())).order_by("received_at").values_list("pk", flat=True)[:SWEEP_BATCH])
    results = []
    for pk in ids:
        if clock() - started >= SWEEP_BUDGET_SECONDS:
            break
        results.append(process(pk))
    return f"voicemail sweep: {len(results)} looked at, {sum(r == 'done' for r in results)} done"


# ---------- the Office ----------

UNHEARD_CAP = 100
SHORT_SECONDS = 3  # Moishe 2026-11-19: voicemails under 3 seconds (pocket calls, a breath) are hidden in the list, left out of the badge and not emailed


def short_q():
    """Voicemails under SHORT_SECONDS long (a no-sound one is 0 seconds, so it is short too)."""
    return Q(kind=Call.VOICEMAIL, duration_seconds__lt=SHORT_SECONDS)


def unheard_count():
    """Unheard voicemails for the badge, counted up to UNHEARD_CAP (100 means "100 or more"). A short indexed read of ids, not COUNT(*), because Office pages must not count source tables."""
    return len(Call.objects.filter(kind=Call.VOICEMAIL, heard_at__isnull=True).exclude(recording_status=Call.ABSENT).exclude(short_q()).values_list("pk", flat=True)[:UNHEARD_CAP])  # no-sound and short ones are hidden, so they never count


LIST_CAP = 5000


def capped_count(queryset, cap=LIST_CAP):
    """A count up to `cap` from a short read of ids (Office pages do not run COUNT(*) on source tables). Calls are a few a day, so the cap is never reached in practice."""
    return len(queryset.values_list("pk", flat=True)[:cap])


def callers(calls):
    """{from_number: {"name", "url"}} for the people whose stored mobile is one of these numbers: three reads for the whole page (leads, Gold applicants, registered people; the strongest match wins)."""
    from django.urls import reverse

    from gold.models import GoldApplication
    from journey.models import JourneySession
    from users.models import User

    numbers = {c.from_number for c in calls if c.from_number.startswith("+")}
    found = {}
    if not numbers:
        return found
    # Weakest first, so a stronger match overwrites: lead (journey email step), then Gold applicant, then registered person.
    for session in JourneySession.objects.filter(lead_mobile__in=numbers).exclude(lead_email="").order_by("lead_at").only("pk", "lead_mobile", "lead_first_name", "lead_email"):
        found[session.lead_mobile] = {"name": session.lead_first_name or session.lead_email, "url": reverse("office_lead", args=[session.pk]), "kind": "Lead"}
    for gold in GoldApplication.objects.filter(mobile__in=numbers).order_by("created_at"):
        found[gold.mobile] = {"name": gold.full_name, "url": reverse("office_gold_application", args=[gold.pk]), "kind": "Gold applicant"}
    for user in User.objects.filter(mobile__in=numbers, is_staff=False):
        found[user.mobile] = {"name": user.get_full_name() or user.email, "url": reverse("office_person", args=[user.pk]), "kind": "Registered"}
    return found


def mark_heard(call, user):
    """The first staff play only: later plays change nothing."""
    return Call.objects.filter(pk=call.pk, heard_at__isnull=True).update(heard_at=timezone.now(), heard_by=user)
