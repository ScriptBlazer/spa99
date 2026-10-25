"""Group sends: start, schedule, cancel, and the background batches (mailings and invites).

Flow. `start()` checks the SES gate, snapshots the group into MailingRecipient rows (once; the unique (mailing, email) pair means a
person is in a mailing at most once), marks it `sending` and queues `mailings.tasks.send_mailing`. The task works through the
queued rows in slices of about a minute, paced to the per-second rate, then queues itself again until none are left. It is safe
to run twice at once or to re-run after a crash: a row is first CLAIMED (queued -> sending) with a conditional update, so only one
worker can send it, and a row left in `sending` by a crashed worker is never retried (marked failed after a few minutes): at most
once beats twice. Cancel stops the queued rows (they become skipped). Everything that starts, schedules or cancels writes a
SystemEvent with counts."""
import logging
import time
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from common.tasks import enqueue
from notifications import emailbody, ses
from notifications.models import EmailLog
from notifications.services import send_templated, subject_for
from system.models import SystemEvent

from . import segments, tokens
from .models import Invite, Mailing, MailingRecipient

logger = logging.getLogger("spa99.email")

SLICE_SECONDS = 60  # one task works this long, then queues the next (django-q kills a task after 120 s)
STALE_SECONDS = 300  # a row 'sending' for longer than this belongs to a worker that died
MIN_SCHEDULE_SECONDS = 60
_sleep = time.sleep  # tests replace this
NEWS_NOTICE = "You are receiving this because you opted in to news from Spa 99."
INVITE_NOTICE = "You are receiving this because Spa 99 invited you to register."


class MailingError(Exception):
    """A plain-words reason a mailing cannot do what was asked."""


# ---------- shared ----------

def rate_per_second():
    """Messages a second: MAILING_RATE_PER_SECOND (default 10), never above what SES says the account may send."""
    rate = int(getattr(settings, "MAILING_RATE_PER_SECOND", 10))
    max_rate = ses.ses_status().get("max_rate")
    if max_rate:
        rate = min(rate, max(1, int(max_rate)))
    return max(rate, 0)


class Pacer:
    """Lets at most `rate` sends through per second. No pacing when the queue runs inline (development) or the rate is 0."""

    def __init__(self, rate):
        self.rate = 0 if settings.Q_CLUSTER.get("sync") else rate
        self.window, self.used = None, 0

    def wait(self):
        if not self.rate:
            return
        now = time.monotonic()
        if self.window is None or now - self.window >= 1:
            self.window, self.used = now, 0
        if self.used >= self.rate:
            _sleep(max(0.0, 1 - (now - self.window)))
            self.window, self.used = time.monotonic(), 0
        self.used += 1


def _event(kind, user, sentence, detail, request=None, outcome=None):
    from system import audit

    audit.log_event(kind, request, user=user, detail=detail, sentence=sentence[:1000], outcome=outcome)


def _who(user):
    return getattr(user, "email", "") or "A script"


def _reason_word(log):
    return (log.error or "failed").split(":")[0][:200]


def subject_line(subject, first_name):
    return subject.replace("{first_name}", first_name.strip() or "there")


def _count_rows(model, **filters):
    return dict(model.objects.filter(**filters).values_list("status").annotate(n=Count("pk")).order_by().values_list("status", "n"))


# ---------- mailings: checks ----------

def check_mailing(mailing):
    """Plain-words problems that stop a mailing being sent or scheduled: {field: [messages]}. Empty = fine."""
    errors = emailbody.validate(emailbody.SPECS["mailing"], subject=mailing.subject, body=mailing.body)
    if not mailing.body.strip():
        errors.setdefault("body", []).append("Write the message.")
    params, group_errors = segments.clean_params(mailing.group, mailing.params)
    if group_errors:
        errors.update(group_errors)
    elif not segments.count(mailing.group, params, mailing.kind):
        errors["group"] = ["Nobody in this group can be emailed (suppressed, inactive or not opted in)."]
    if mailing.kind not in (Mailing.NEWS, Mailing.SERVICE):
        errors["kind"] = ["Choose News or Service message."]
    return errors


def _require_ready(mailing):
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        raise MailingError(str(error)) from None
    errors = check_mailing(mailing)
    if errors:
        raise MailingError(" ".join(m for messages in errors.values() for m in messages))


# ---------- mailings: start, schedule, cancel ----------

def start(mailing, user=None, request=None):
    """Send now (or, from the schedule, when the time came). Returns the Mailing. Raises MailingError."""
    _require_ready(mailing)
    now = timezone.now()
    claimed = Mailing.objects.filter(pk=mailing.pk, status__in=(Mailing.DRAFT, Mailing.SCHEDULED)).update(
        status=Mailing.SENDING, started_at=now, scheduled_at=mailing.scheduled_at, error="", updated_at=now)
    if not claimed:
        raise MailingError("This mailing has already been started.")
    mailing.refresh_from_db()
    _drop_schedule(mailing)
    try:
        mailing.total_count = snapshot(mailing)
        mailing.save(update_fields=["total_count", "updated_at"])
    except Exception as error:  # noqa: BLE001 - leave it as a draft that can be fixed, never half started
        logger.exception("Could not build the recipient list for mailing %s", mailing.pk)
        mailing.recipients.all().delete()
        Mailing.objects.filter(pk=mailing.pk).update(status=Mailing.DRAFT, error=f"Could not build the list ({type(error).__name__}).")
        raise MailingError("Could not build the list of people. Nothing was sent.") from None
    _event(SystemEvent.MAILING_SENT, user or mailing.created_by,
           f"{_who(user or mailing.created_by)} sent the {mailing.get_kind_display().split(' (')[0].lower()} mailing '{mailing.name}' to {mailing.total_count} people",
           {"mailing": str(mailing.pk), "name": mailing.name, "kind": mailing.kind, "group": mailing.group, "params": mailing.params,
            "recipients": mailing.total_count, "scheduled": bool(mailing.scheduled_at)}, request)
    enqueue("mailings.tasks.send_mailing", str(mailing.pk))
    mailing.refresh_from_db()
    return mailing


def snapshot(mailing):
    """Write the recipient rows for this mailing once (a second call changes nothing). Returns the number of rows."""
    if not mailing.recipients.exists():
        batch = []
        for email, first_name, user_id in segments.rows(mailing.group, mailing.params, mailing.kind):
            batch.append(MailingRecipient(mailing=mailing, email=email, first_name=first_name[:100], user_id=user_id))
            if len(batch) >= 500:
                MailingRecipient.objects.bulk_create(batch, ignore_conflicts=True)
                batch = []
        if batch:
            MailingRecipient.objects.bulk_create(batch, ignore_conflicts=True)
    return mailing.recipients.count()


def schedule(mailing, when, user=None, request=None):
    """Send at `when` (django-q runs a one-off schedule). Only a draft can be scheduled."""
    if when < timezone.now() + timedelta(seconds=MIN_SCHEDULE_SECONDS):
        raise MailingError("Choose a time at least a minute from now.")
    _require_ready(mailing)
    with transaction.atomic():
        claimed = Mailing.objects.filter(pk=mailing.pk, status=Mailing.DRAFT).update(
            status=Mailing.SCHEDULED, scheduled_at=when, error="", updated_at=timezone.now())
        if not claimed:
            raise MailingError("Only a draft can be scheduled.")
        from django_q.models import Schedule

        Schedule.objects.update_or_create(name=mailing.schedule_name, defaults={
            "func": "mailings.tasks.start_scheduled", "args": repr(str(mailing.pk)), "schedule_type": Schedule.ONCE,
            "next_run": when, "repeats": -1})
    mailing.refresh_from_db()
    _event(SystemEvent.MAILING_SCHEDULED, user,
           f"{_who(user)} scheduled the mailing '{mailing.name}' for {timezone.localtime(when):%-d %b %Y %H:%M}",
           {"mailing": str(mailing.pk), "name": mailing.name, "kind": mailing.kind, "group": mailing.group,
            "recipients_now": segments.count(mailing.group, mailing.params, mailing.kind), "scheduled_at": when.isoformat()}, request)
    return mailing


def _drop_schedule(mailing):
    from django_q.models import Schedule

    Schedule.objects.filter(name=mailing.schedule_name).delete()


def cancel(mailing, user=None, request=None):
    """Stop a scheduled or sending mailing: queued people are skipped, those already sent stay sent."""
    with transaction.atomic():
        row = Mailing.objects.select_for_update().get(pk=mailing.pk)
        if row.status not in (Mailing.SCHEDULED, Mailing.SENDING):
            raise MailingError("Only a scheduled or sending mailing can be cancelled.")
        was = row.status
        row.status, row.finished_at = Mailing.CANCELLED, timezone.now()
        row.save(update_fields=["status", "finished_at", "updated_at"])
        MailingRecipient.objects.filter(mailing=row, status=MailingRecipient.QUEUED).update(
            status=MailingRecipient.SKIPPED, reason="Cancelled before it was sent", updated_at=timezone.now())
        _drop_schedule(row)
    refresh_counts(row)
    row.refresh_from_db()
    _event(SystemEvent.MAILING_CANCELLED, user, f"{_who(user)} cancelled the mailing '{row.name}' ({was}): {row.sent_count} already sent, {row.skipped_count} stopped",
           {"mailing": str(row.pk), "name": row.name, "was": was, "sent": row.sent_count, "skipped": row.skipped_count}, request)
    return row


def resume(mailing):
    """Queue the worker again for a sending mailing (safe: it never sends twice). For a stuck or restarted worker."""
    if mailing.status != Mailing.SENDING:
        raise MailingError("Only a mailing that is sending can be resumed.")
    enqueue("mailings.tasks.send_mailing", str(mailing.pk))


def refresh_counts(mailing):
    counts = _count_rows(MailingRecipient, mailing=mailing)
    Mailing.objects.filter(pk=mailing.pk).update(
        sent_count=counts.get("sent", 0) + counts.get("bounced", 0), skipped_count=counts.get("skipped", 0), failed_count=counts.get("failed", 0))
    return counts


def progress(mailing):
    """What the detail page polls: status and the counts (one aggregate query)."""
    counts = _count_rows(MailingRecipient, mailing=mailing)
    total = sum(counts.values())
    done = total - counts.get("queued", 0) - counts.get("sending", 0)
    return {"status": mailing.status, "status_label": mailing.get_status_display(), "total": total or mailing.total_count,
            "sent": counts.get("sent", 0), "bounced": counts.get("bounced", 0), "skipped": counts.get("skipped", 0),
            "failed": counts.get("failed", 0), "queued": counts.get("queued", 0), "sending": counts.get("sending", 0),
            "percent": int(done * 100 / total) if total else (100 if mailing.status == Mailing.SENT else 0),
            "finished": mailing.status in (Mailing.SENT, Mailing.CANCELLED, Mailing.FAILED),
            "started_at": mailing.started_at, "finished_at": mailing.finished_at, "error": mailing.error}


# ---------- mailings: the background work ----------

def run_mailing(mailing_id, budget=SLICE_SECONDS):
    """One slice of work. Returns a plain status string (never personal data: django-q keeps task results)."""
    mailing = Mailing.objects.filter(pk=mailing_id).first()
    if mailing is None:
        return "missing"
    if mailing.status != Mailing.SENDING:
        return mailing.status
    errors = emailbody.validate(emailbody.SPECS["mailing"], subject=mailing.subject, body=mailing.body)
    if errors or mailing.group not in segments.GROUPS:
        Mailing.objects.filter(pk=mailing.pk, status=Mailing.SENDING).update(status=Mailing.FAILED, finished_at=timezone.now(), error="The text or the group is no longer valid.")
        return "failed"
    _fail_stale(mailing)
    group = segments.GROUPS[mailing.group]
    deadline, pacer = time.monotonic() + budget, Pacer(rate_per_second())
    while time.monotonic() < deadline:
        batch = list(mailing.recipients.filter(status=MailingRecipient.QUEUED).order_by("email")[:50])
        if not batch:
            break
        for recipient in batch:
            if not Mailing.objects.filter(pk=mailing.pk, status=Mailing.SENDING).exists():  # cancelled meanwhile
                break
            if time.monotonic() >= deadline:
                break
            pacer.wait()
            _send_one(mailing, group, recipient)
        else:
            continue
        break
    counts = refresh_counts(mailing)
    mailing.refresh_from_db()
    if mailing.status != Mailing.SENDING:
        return mailing.status
    if counts.get("queued", 0):
        enqueue("mailings.tasks.send_mailing", str(mailing.pk))
        return "sending"
    if counts.get("sending", 0):  # another worker is mid-send; it finishes the mailing
        return "sending"
    return _finish(mailing, counts)


def _fail_stale(mailing):
    cutoff = timezone.now() - timedelta(seconds=STALE_SECONDS)
    MailingRecipient.objects.filter(mailing=mailing, status=MailingRecipient.SENDING, updated_at__lt=cutoff).update(
        status=MailingRecipient.FAILED, reason="Interrupted; not retried so nobody gets it twice", updated_at=timezone.now())


def _skip_reason(mailing, recipient):
    """Checked again at send time: people can unsubscribe or be suppressed between the snapshot and their turn."""
    from mailings.models import EmailOptOut
    from users.models import User

    if recipient.user_id:
        user = User.objects.filter(pk=recipient.user_id).only("is_active", "marketing_consent").first()
        if user is None or not user.is_active:
            return "The account is no longer active"
        if mailing.kind == Mailing.NEWS and not user.marketing_consent:
            return "Unsubscribed since the list was made"
    if mailing.kind == Mailing.NEWS and EmailOptOut.objects.filter(email=recipient.email).exists():
        return "Unsubscribed since the list was made"
    return ""


def _send_one(mailing, group, recipient):
    claimed = MailingRecipient.objects.filter(pk=recipient.pk, status=MailingRecipient.QUEUED).update(
        status=MailingRecipient.SENDING, updated_at=timezone.now())
    if not claimed:  # another worker has it
        return
    try:
        reason = _skip_reason(mailing, recipient)
        if reason:
            _mark(recipient, MailingRecipient.SKIPPED, reason)
            return
        context, headers = {"first_name": recipient.first_name}, None
        if mailing.kind == Mailing.NEWS:
            url = tokens.unsubscribe_url(recipient.email)
            context.update({"unsubscribe_url": url, "notice": NEWS_NOTICE})
            headers = tokens.list_unsubscribe_headers(url)
        else:
            context["notice"] = f"You are receiving this message {group.reason}."
        log = send_templated("mailing", [recipient.email], subject_line(mailing.subject, recipient.first_name), context,
                             headers=headers, body=mailing.body, subject_email=recipient.email)
    except Exception as error:  # noqa: BLE001 - one bad address must not stop the others
        logger.error("Mailing %s: a send failed (%s)", mailing.pk, type(error).__name__)
        _mark(recipient, MailingRecipient.FAILED, type(error).__name__)
        return
    if log.status == EmailLog.SENT:
        _mark(recipient, MailingRecipient.SENT, "", sent_at=log.sent_at, message_id=log.message_id)
    elif log.status == EmailLog.SUPPRESSED:
        _mark(recipient, MailingRecipient.SKIPPED, "On the suppression list (bounce or complaint)")
    else:
        _mark(recipient, MailingRecipient.FAILED, _reason_word(log))


def _mark(recipient, status, reason, sent_at=None, message_id=""):
    MailingRecipient.objects.filter(pk=recipient.pk).update(
        status=status, reason=reason[:200], sent_at=sent_at, message_id=(message_id or "")[:100], updated_at=timezone.now())


def _finish(mailing, counts):
    status = Mailing.FAILED if not counts.get("sent", 0) and counts.get("failed", 0) else Mailing.SENT
    error = "Nothing could be sent." if status == Mailing.FAILED else ""
    done = Mailing.objects.filter(pk=mailing.pk, status=Mailing.SENDING).update(status=status, finished_at=timezone.now(), error=error, updated_at=timezone.now())
    return status if done else "finished"


# ---------- scheduled start (called by the django-q schedule) ----------

def start_scheduled(mailing_id):
    mailing = Mailing.objects.filter(pk=mailing_id, status=Mailing.SCHEDULED).first()
    if mailing is None:
        return "not scheduled"
    try:
        start(mailing, user=mailing.created_by)
    except MailingError as error:  # e.g. SES changed state: back to a draft with the reason, never lost
        Mailing.objects.filter(pk=mailing.pk, status=Mailing.SCHEDULED).update(
            status=Mailing.DRAFT, scheduled_at=None, error=str(error)[:300], updated_at=timezone.now())
        _drop_schedule(mailing)
        return "refused"
    return "started"


# ---------- invites ----------

def start_invites(batch_id, user=None, request=None):
    """Queue the sending of every `queued` invite in the batch. The SES gate applies. Returns the number waiting."""
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        raise MailingError(str(error)) from None
    waiting = Invite.objects.filter(batch_id=batch_id, status=Invite.QUEUED).count()
    if not waiting:
        raise MailingError("There are no invites waiting to be sent in this batch.")
    skipped = Invite.objects.filter(batch_id=batch_id, status=Invite.SKIPPED).count()
    _event(SystemEvent.INVITES_SENT, user, f"{_who(user)} sent {waiting} invite{'' if waiting == 1 else 's'} ({skipped} skipped)",
           {"batch": str(batch_id), "invites": waiting, "skipped": skipped}, request)
    enqueue("mailings.tasks.send_invites", str(batch_id))
    return waiting


def start_invites_resume(batch_id):
    """Queue the invite worker again for a batch with invites still waiting (it never sends one twice)."""
    if not Invite.objects.filter(batch_id=batch_id, status=Invite.QUEUED).exists():
        raise MailingError("No invites are waiting in this batch.")
    enqueue("mailings.tasks.send_invites", str(batch_id))


def run_invites(batch_id, budget=SLICE_SECONDS):
    """One slice of invite sending, the same claim-then-send rules as run_mailing. Returns a plain status string."""
    try:
        batch_id = uuid.UUID(str(batch_id))
    except ValueError:
        return "missing"
    deadline, pacer = time.monotonic() + budget, Pacer(rate_per_second())
    Invite.objects.filter(batch_id=batch_id, status=Invite.SENDING, updated_at__lt=timezone.now() - timedelta(seconds=STALE_SECONDS)).update(
        status=Invite.FAILED, reason="Interrupted; not retried so nobody gets it twice", updated_at=timezone.now())
    while time.monotonic() < deadline:
        batch = list(Invite.objects.filter(batch_id=batch_id, status=Invite.QUEUED).order_by("email")[:50])
        if not batch:
            break
        for invite in batch:
            if time.monotonic() >= deadline:
                break
            pacer.wait()
            _send_invite(invite)
        else:
            continue
        break
    if Invite.objects.filter(batch_id=batch_id, status=Invite.QUEUED).exists():
        enqueue("mailings.tasks.send_invites", str(batch_id))
        return "sending"
    return "done"


def _send_invite(invite):
    from .models import EmailOptOut

    claimed = Invite.objects.filter(pk=invite.pk, status=Invite.QUEUED).update(status=Invite.SENDING, updated_at=timezone.now())
    if not claimed:
        return
    try:
        if EmailOptOut.objects.filter(email=invite.email).exists():
            _invite_mark(invite, Invite.SKIPPED, "Unsubscribed")
            return
        if invite.expired:
            _invite_mark(invite, Invite.SKIPPED, "The invite expired before it was sent")
            return
        unsub = tokens.unsubscribe_url(invite.email)
        context = {"first_name": invite.name.split(" ")[0] if invite.name else "", "url": f"{settings.SITE_URL}/invite/{invite.token}/",
                   "unsubscribe_url": unsub, "notice": INVITE_NOTICE}
        log = send_templated("invite", [invite.email], subject_for("invite", first_name=context["first_name"] or "there"), context,
                             headers=tokens.list_unsubscribe_headers(unsub), subject_email=invite.email)
    except Exception as error:  # noqa: BLE001
        logger.error("Invite send failed (%s)", type(error).__name__)
        _invite_mark(invite, Invite.FAILED, type(error).__name__)
        return
    if log.status == EmailLog.SENT:
        _invite_mark(invite, Invite.SENT, "", sent_at=log.sent_at, message_id=log.message_id)
    elif log.status == EmailLog.SUPPRESSED:
        _invite_mark(invite, Invite.SKIPPED, "On the suppression list (bounce or complaint)")
    else:
        _invite_mark(invite, Invite.FAILED, _reason_word(log))


def _invite_mark(invite, status, reason, sent_at=None, message_id=""):
    Invite.objects.filter(pk=invite.pk).update(
        status=status, reason=reason[:200], sent_at=sent_at, message_id=(message_id or "")[:100], updated_at=timezone.now())
