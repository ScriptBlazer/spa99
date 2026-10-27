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
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from common.tasks import enqueue
from notifications import emailbody, ses
from notifications.models import EmailLog
from notifications.services import send_templated, subject_for
from system.models import SystemEvent

from . import blocks, segments, tokens
from .models import Invite, Mailing, MailingRecipient

logger = logging.getLogger("spa99.email")

SLICE_SECONDS = 60  # one task works this long, then queues the next (django-q kills a task after 120 s)
STALE_SECONDS = 300  # a row 'sending' for longer than this belongs to a worker that died
MIN_SCHEDULE_SECONDS = 60
_sleep = time.sleep  # tests replace this
LOCK_SECONDS = SLICE_SECONDS + 60
MAX_ATTEMPTS = 5  # a throttled send is tried this often (30 s, 60 s, 120 s ... apart) before it fails
TRANSIENT = ("Throttling", "MaxSendingRateExceeded", "TooManyRequests", "ServiceUnavailable", "InternalFailure", "InternalServerError",
             "RequestTimeout", "ConnectTimeout", "ReadTimeout", "EndpointConnectionError")
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


def _acquire(name):
    """One active worker per mailing or batch (so two cannot double the rate). Shared through the cache (the database cache in
    production); a worker that dies frees it after LOCK_SECONDS. If the cache is unreachable the worker goes ahead."""
    try:
        return cache.add(f"mailings:lock:{name}", 1, LOCK_SECONDS)
    except Exception:  # noqa: BLE001
        return True


def _release(name):
    try:
        cache.delete(f"mailings:lock:{name}")
    except Exception:  # noqa: BLE001
        pass


def _transient(log):
    """SES asked us to slow down, or a passing server or network problem: try again later instead of failing."""
    return any(word in (log.error or "") for word in TRANSIENT)


def _ready(qs):
    now = timezone.now()
    return qs.filter(Q(retry_at__isnull=True) | Q(retry_at__lte=now))


def _wait_for_retry(qs, deadline):
    """No row is ready but some wait for their backoff: sleep until the first is due (within this slice). False when nothing waits or
    the slice has no time left."""
    first = qs.exclude(retry_at__isnull=True).order_by("retry_at").values_list("retry_at", flat=True).first()
    if first is None:
        return False
    seconds = (first - timezone.now()).total_seconds()
    if seconds > deadline - time.monotonic():
        return False
    _sleep(max(seconds, 0) + 0.01)
    return True


def _back_off(model, pk, attempts):
    """Put a throttled row back in the queue. True when it will be retried, False when it has used its attempts."""
    attempts += 1
    if attempts >= MAX_ATTEMPTS:
        return False
    delay = 30 * 2 ** (attempts - 1)
    model.objects.filter(pk=pk).update(status="queued", attempts=attempts, retry_at=timezone.now() + timedelta(seconds=delay),
                                       reason="Waiting: Amazon SES asked us to slow down", updated_at=timezone.now())
    return True


def subject_line(subject, first_name):
    return subject.replace("{first_name}", first_name.strip() or "there")


def _count_rows(model, **filters):
    return dict(model.objects.filter(**filters).values_list("status").annotate(n=Count("pk")).order_by().values_list("status", "n"))


# ---------- mailings: checks ----------

def _wording_errors(mailing):
    """Subject and message problems: {field: [messages]}. A mailing with parts is checked part by part (messages say which part)."""
    errors = emailbody.validate(emailbody.SPECS["mailing"], subject=mailing.subject)
    if mailing.blocks:
        problems = blocks.check_stored(mailing.blocks)
        if problems:
            errors["blocks"] = problems
        return errors
    errors.update(emailbody.validate(emailbody.SPECS["mailing"], body=mailing.body))
    if not mailing.body.strip():
        errors.setdefault("body", []).append("Write the message.")
    return errors


def check_mailing(mailing):
    """Plain-words problems that stop a mailing being sent or scheduled: {field: [messages]}. Empty = fine."""
    errors = _wording_errors(mailing)
    params, group_errors = segments.clean_params(mailing.group, mailing.params)
    if group_errors:
        errors.update(group_errors)
    elif mailing.kind == Mailing.SERVICE and segments.GROUPS[mailing.group].news_only:
        errors["group"] = ["This group can only get News: these people never registered, so a service message has no reason to reach them."]
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
        if row.status not in (Mailing.SCHEDULED, Mailing.SENDING, Mailing.PAUSED):
            raise MailingError("Only a scheduled, sending or paused mailing can be cancelled.")
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
    """Queue the worker again for a sending or paused mailing (safe: it never sends twice). Needs SES to allow sending."""
    if mailing.status not in (Mailing.SENDING, Mailing.PAUSED):
        raise MailingError("Only a mailing that is sending or paused can be resumed.")
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        raise MailingError(str(error)) from None
    Mailing.objects.filter(pk=mailing.pk, status=Mailing.PAUSED).update(status=Mailing.SENDING, error="", updated_at=timezone.now())
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

def _pause(mailing, reason):
    Mailing.objects.filter(pk=mailing.pk, status=Mailing.SENDING).update(status=Mailing.PAUSED, error=reason[:300], updated_at=timezone.now())
    logger.warning("Mailing %s paused: %s", mailing.pk, reason)


def run_mailing(mailing_id, budget=SLICE_SECONDS):
    """One slice of work. Returns a plain status string (never personal data: django-q keeps task results). One worker at a time per
    mailing; SES must still allow sending at the start of every slice, else the mailing is paused with the reason."""
    mailing = Mailing.objects.filter(pk=mailing_id).first()
    if mailing is None:
        return "missing"
    if mailing.status != Mailing.SENDING:
        return mailing.status
    errors = _wording_errors(mailing)
    if errors or mailing.group not in segments.GROUPS:
        Mailing.objects.filter(pk=mailing.pk, status=Mailing.SENDING).update(status=Mailing.FAILED, finished_at=timezone.now(), error="The text or the group is no longer valid.")
        return "failed"
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        _pause(mailing, str(error))
        return "paused"
    if not _acquire(f"mailing:{mailing.pk}"):
        return "busy"  # another worker is on it
    try:
        _slice(mailing, budget)
    finally:
        _release(f"mailing:{mailing.pk}")
    counts = refresh_counts(mailing)
    mailing.refresh_from_db()
    if mailing.status != Mailing.SENDING:
        return mailing.status
    if counts.get("queued", 0):
        enqueue("mailings.tasks.send_mailing", str(mailing.pk))
        return "sending"
    if counts.get("sending", 0):  # a send is in flight (or died: it is marked failed after a few minutes)
        return "sending"
    return _finish(mailing, counts)


def _slice(mailing, budget):
    _fail_stale(mailing)
    group = segments.GROUPS[mailing.group]
    queued = mailing.recipients.filter(status=MailingRecipient.QUEUED)
    deadline, pacer = time.monotonic() + budget, Pacer(rate_per_second())
    while time.monotonic() < deadline:
        batch = list(_ready(queued).order_by("email")[:50])
        if not batch:
            if _wait_for_retry(queued, deadline):
                continue
            return
        for recipient in batch:
            if time.monotonic() >= deadline or not Mailing.objects.filter(pk=mailing.pk, status=Mailing.SENDING).exists():  # time up, or cancelled
                return
            pacer.wait()
            if _send_one(mailing, group, recipient) == "throttled":
                _sleep(1)  # SES said slow down: ease off for everyone, not just this row


def _fail_stale(mailing):
    cutoff = timezone.now() - timedelta(seconds=STALE_SECONDS)
    MailingRecipient.objects.filter(mailing=mailing, status=MailingRecipient.SENDING, updated_at__lt=cutoff).update(
        status=MailingRecipient.FAILED, reason="Interrupted; not retried so nobody gets it twice", updated_at=timezone.now())


def _skip_reason(mailing, recipient):
    """Checked again at send time: people can unsubscribe or be suppressed between the snapshot and their turn."""
    from mailings.models import EmailOptOut
    from users.models import User

    user = None
    if recipient.user_id:
        user = User.objects.filter(pk=recipient.user_id).only("is_active", "marketing_consent").first()
        if user is None:
            return "The account is no longer active"
    elif mailing.kind == Mailing.NEWS:  # a lead or applicant who registered after the list was made: his account's choice rules now
        user = User.objects.filter(email__iexact=recipient.email).only("is_active", "marketing_consent").first()
    if user is not None:
        if not user.is_active:
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
                             headers=headers, body=mailing.body, blocks=mailing.blocks, subject_email=recipient.email)
    except Exception as error:  # noqa: BLE001 - one bad address must not stop the others
        logger.error("Mailing %s: a send failed (%s)", mailing.pk, type(error).__name__)
        _mark(recipient, MailingRecipient.FAILED, type(error).__name__)
        return
    if log.status == EmailLog.SENT:
        _mark(recipient, MailingRecipient.SENT, "", sent_at=log.sent_at, message_id=log.message_id)
    elif log.status == EmailLog.SUPPRESSED:
        _mark(recipient, MailingRecipient.SKIPPED, "On the suppression list (bounce or complaint)")
    elif _transient(log) and _back_off(MailingRecipient, recipient.pk, recipient.attempts):
        return "throttled"
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
    """Queue the invite worker again for a batch with invites still waiting (it never sends one twice). Needs SES to allow sending."""
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        raise MailingError(str(error)) from None
    if not Invite.objects.filter(batch_id=batch_id, status=Invite.QUEUED).exists():
        raise MailingError("No invites are waiting in this batch.")
    enqueue("mailings.tasks.send_invites", str(batch_id))


def run_invites(batch_id, budget=SLICE_SECONDS):
    """One slice of invite sending, the same rules as run_mailing (gate checked first: invites stay queued and the slice stops when SES
    refuses; one worker per batch). Returns a plain status string."""
    try:
        batch_id = uuid.UUID(str(batch_id))
    except ValueError:
        return "missing"
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        logger.warning("Invites %s paused: %s", batch_id, error)
        return "paused"
    if not _acquire(f"invites:{batch_id}"):
        return "busy"
    try:
        Invite.objects.filter(batch_id=batch_id, status=Invite.SENDING, updated_at__lt=timezone.now() - timedelta(seconds=STALE_SECONDS)).update(
            status=Invite.FAILED, reason="Interrupted; not retried so nobody gets it twice", updated_at=timezone.now())
        queued = Invite.objects.filter(batch_id=batch_id, status=Invite.QUEUED)
        deadline, pacer = time.monotonic() + budget, Pacer(rate_per_second())
        while time.monotonic() < deadline:
            batch = list(_ready(queued).order_by("email")[:50])
            if not batch:
                if _wait_for_retry(queued, deadline):
                    continue
                break
            stop = False
            for invite in batch:
                if time.monotonic() >= deadline:
                    stop = True
                    break
                pacer.wait()
                if _send_invite(invite) == "throttled":
                    _sleep(1)
            if stop:
                break
    finally:
        _release(f"invites:{batch_id}")
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
                   "unsubscribe_url": unsub, "notice": INVITE_NOTICE,
                   "valid_days": max(1, round((invite.expires_at - invite.created_at).total_seconds() / 86400))}
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
    elif _transient(log) and _back_off(Invite, invite.pk, invite.attempts):
        return "throttled"
    else:
        _invite_mark(invite, Invite.FAILED, _reason_word(log))


def _invite_mark(invite, status, reason, sent_at=None, message_id=""):
    Invite.objects.filter(pk=invite.pk).update(
        status=status, reason=reason[:200], sent_at=sent_at, message_id=(message_id or "")[:100], updated_at=timezone.now())
