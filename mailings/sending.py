"""Group sends: start, schedule, cancel, and the background batches (a group send of an uploaded list, or of the Invitation email, is the same).

Flow. `start()` checks the SES gate, snapshots the group into MailingRecipient rows (once; the unique (mailing, email) pair means a
person is in a mailing at most once), marks it `sending` and queues `mailings.tasks.send_mailing`. The task works through the
queued rows in slices of about a minute, paced to the per-second rate, then queues itself again until none are left. It is safe
to run twice at once or to re-run after a crash: a row is first CLAIMED (queued -> sending) with a conditional update, so only one
worker can send it, and a row left in `sending` by a crashed worker is never retried (marked failed after a few minutes): at most
once beats twice. Cancel stops the queued rows (they become skipped). Everything that starts, schedules or cancels writes a
SystemEvent with counts."""
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from common.tasks import enqueue
from notifications import emailbody, ses
from notifications.models import EmailLog, NotificationTemplate
from notifications.seed import DEFAULT_SUBJECTS
from notifications.services import send_templated, subject_for
from system.models import SystemEvent

from . import automatic, blocks, segments, tokens
from .models import ContactListMember, EmailOptOut, Invite, Mailing, MailingRecipient

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

def wording_errors(subject, body, parts):
    """Subject and message problems: {field: [messages]}. Parts are checked part by part (messages say which part); no parts = the old body."""
    errors = emailbody.validate(emailbody.SPECS["mailing"], subject=subject)
    if parts:
        problems = blocks.check_stored(parts)
        if problems:
            errors["blocks"] = problems
        return errors
    errors.update(emailbody.validate(emailbody.SPECS["mailing"], body=body))
    if not (body or "").strip():
        errors.setdefault("body", []).append("Write the message.")
    return errors


def _wording_errors(mailing):
    if mailing.automatic_key:  # the wording is the automatic email's own (edited on its page), checked when it was saved
        return {} if mailing.automatic_key in automatic.SENDABLE else {"kind": ["This automatic email cannot be sent to a group."]}
    return wording_errors(mailing.subject, mailing.body, mailing.blocks)


def check_mailing(mailing):
    """Plain-words problems that stop a mailing being sent or scheduled: {field: [messages]}. Empty = fine."""
    errors = _wording_errors(mailing)
    params, group_errors = segments.clean_params(mailing.group, mailing.params)
    valid_kind = mailing.kind in dict(Mailing.KIND_CHOICES)
    if not valid_kind:
        errors["kind"] = ["Choose News or Service message."]
    elif mailing.automatic_key in automatic.SENDABLE and mailing.kind != automatic.SENDABLE[mailing.automatic_key]:
        errors["kind"] = [f"This email is sent as: {automatic.SENDABLE[mailing.automatic_key]}."]
    if group_errors:
        errors.update(group_errors)
    elif valid_kind and mailing.kind == Mailing.INVITATION and not mailing.automatic_key:
        errors["kind"] = ["An invitation is sent from the Invitation to register email (Send to a group)."]
    elif valid_kind and not segments.GROUPS[mailing.group].allows(mailing.kind):
        errors["group"] = [segments.GROUPS[mailing.group].kind_error()]
    elif valid_kind and not segments.count(mailing.group, params, mailing.kind):
        errors["group"] = ["Nobody in this group can be emailed (suppressed, inactive, not opted in or already invited)."]
    return errors


def require_confirmed(confirm, expected, current=None):
    """The server-side guard behind every real send: the POST must say `confirm=yes` and carry the `expected_count` the pop-up showed, and
    that number must still be right (`current`, when the send has a count). A stray POST, a script or a double click cannot send."""
    if (confirm or "").strip().lower() != "yes":
        raise MailingError("Nothing was sent: the send was not confirmed.")
    if current is not None:
        if not str(expected or "").isdigit():
            raise MailingError("Nothing was sent: the number of people was not confirmed.")
        if int(expected) != current:
            raise MailingError(f"The number changed: {current} now. Check and send again.")


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
        Invite.objects.filter(batch_id=mailing.pk, status=Invite.QUEUED).delete()
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
    if mailing.automatic_key == "invite":
        _make_invites(mailing)
    return mailing.recipients.count()


def _make_invites(mailing):
    """One Invite per person for an invitation sent from the automatic 'Invitation to register' email: the personal register link and the
    per-person tracking (sent, opened, registered) are the same as ever. batch_id is the mailing's id. Safe to run twice."""
    from system import defaults

    have = set(Invite.objects.filter(batch_id=mailing.pk).values_list("email", flat=True))
    names = {}
    if (mailing.params or {}).get("list_id"):
        names = {e: n for e, n in ContactListMember.objects.filter(list_id=mailing.params["list_id"]).values_list("email", "name")}
    expires_at = timezone.now() + timedelta(days=defaults.get().register_invite_days)
    batch = []
    for email in mailing.recipients.order_by("email").values_list("email", flat=True).iterator(chunk_size=500):
        if email in have:
            continue
        batch.append(Invite(name=names.get(email, "")[:100], email=email, batch_id=mailing.pk, expires_at=expires_at, created_by=mailing.created_by))
        if len(batch) >= 500:
            Invite.objects.bulk_create(batch)
            batch = []
    if batch:
        Invite.objects.bulk_create(batch)


def schedule(mailing, when, user=None, request=None, confirmed=None):
    """Send at `when` (django-q runs a one-off schedule). Only a draft can be scheduled."""
    if when < timezone.now() + timedelta(seconds=MIN_SCHEDULE_SECONDS):
        raise MailingError("Choose a time at least a minute from now.")
    _require_ready(mailing)
    with transaction.atomic():
        claimed = Mailing.objects.filter(pk=mailing.pk, status=Mailing.DRAFT).update(
            status=Mailing.SCHEDULED, scheduled_at=when, error="", confirmed_count=confirmed, updated_at=timezone.now())
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


def _counted_now(mailing):
    params, errors = segments.clean_params(mailing.group, mailing.params) if mailing.group in segments.GROUPS else ({}, True)
    return 0 if errors else segments.count(mailing.group, params, mailing.kind)


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
        Invite.objects.filter(batch_id=row.pk, status=Invite.QUEUED).update(status=Invite.SKIPPED, reason="Cancelled before it was sent", updated_at=timezone.now())
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
    stale = MailingRecipient.objects.filter(mailing=mailing, status=MailingRecipient.SENDING, updated_at__lt=cutoff)
    if mailing.automatic_key:
        Invite.objects.filter(batch_id=mailing.pk, status=Invite.QUEUED, email__in=list(stale.values_list("email", flat=True))).update(
            status=Invite.FAILED, reason="Interrupted; not retried so nobody gets it twice", updated_at=timezone.now())
    stale.update(status=MailingRecipient.FAILED, reason="Interrupted; not retried so nobody gets it twice", updated_at=timezone.now())


def _skip_reason(mailing, recipient):
    """Checked again at send time: people can unsubscribe or be suppressed between the snapshot and their turn."""
    from users.models import User

    if mailing.kind == Mailing.INVITATION:
        if User.objects.filter(email__iexact=recipient.email).exists():
            return "Already has an account"
        if EmailOptOut.objects.filter(email=recipient.email).exists():
            return "Unsubscribed since the list was made"
        if Invite.objects.filter(email=recipient.email, status__in=Invite.PENDING, expires_at__gt=timezone.now()).exclude(batch_id=mailing.pk).exists():
            return "Already invited and waiting"
        return ""
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
        invite = Invite.objects.filter(batch_id=mailing.pk, email=recipient.email).first() if mailing.automatic_key == "invite" else None
        if not reason and invite is not None and invite.expired:
            reason = "The invite expired before it was sent"
        if reason:
            _finish_row(mailing, recipient, MailingRecipient.SKIPPED, reason)
            return
        context, headers = {"first_name": recipient.first_name}, None
        if mailing.kind in Mailing.MARKETING:
            url = tokens.unsubscribe_url(recipient.email)
            context.update({"unsubscribe_url": url, "notice": INVITE_NOTICE if mailing.kind == Mailing.INVITATION else NEWS_NOTICE})
            headers = tokens.list_unsubscribe_headers(url)
        else:
            context["notice"] = f"You are receiving this message {group.reason}."
        if mailing.automatic_key == "invite":
            if invite is None:
                _finish_row(mailing, recipient, MailingRecipient.FAILED, "No invite row")
                return
            context.update(_invite_context(invite))
            log = send_templated("invite", [recipient.email], subject_for("invite", first_name=context["first_name"] or "there"), context,
                                 headers=headers, subject_email=recipient.email)
        else:
            log = send_templated("mailing", [recipient.email], subject_line(mailing.subject, recipient.first_name), context,
                                 headers=headers, body=mailing.body, blocks=mailing.blocks, subject_email=recipient.email)
    except Exception as error:  # noqa: BLE001 - one bad address must not stop the others
        logger.error("Mailing %s: a send failed (%s)", mailing.pk, type(error).__name__)
        _finish_row(mailing, recipient, MailingRecipient.FAILED, type(error).__name__)
        return
    if log.status == EmailLog.SENT:
        _finish_row(mailing, recipient, MailingRecipient.SENT, "", sent_at=log.sent_at, message_id=log.message_id)
    elif log.status == EmailLog.SUPPRESSED:
        _finish_row(mailing, recipient, MailingRecipient.SKIPPED, "On the suppression list (bounce or complaint)")
    elif _transient(log) and _back_off(MailingRecipient, recipient.pk, recipient.attempts):
        return "throttled"
    else:
        _finish_row(mailing, recipient, MailingRecipient.FAILED, _reason_word(log))


def _invite_context(invite):
    """What the Invitation email needs for one person: his personal register link and how long it works."""
    return {"first_name": invite.name.split(" ")[0] if invite.name else "", "url": f"{settings.SITE_URL}/invite/{invite.token}/",
            "valid_days": max(1, round((invite.expires_at - invite.created_at).total_seconds() / 86400))}


def _finish_row(mailing, recipient, status, reason, sent_at=None, message_id=""):
    """Record the result for one person; for an invitation the Invite row (the per-person tracking) gets the same result."""
    _mark(recipient, status, reason, sent_at=sent_at, message_id=message_id)
    if mailing.automatic_key == "invite":
        Invite.objects.filter(batch_id=mailing.pk, email=recipient.email, status__in=(Invite.QUEUED, Invite.SENDING)).update(
            status={"sent": Invite.SENT, "skipped": Invite.SKIPPED, "failed": Invite.FAILED}[status], reason=reason[:200], sent_at=sent_at,
            message_id=(message_id or "")[:100], updated_at=timezone.now())


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
    now_count = _counted_now(mailing)
    if mailing.confirmed_count is not None and now_count > mailing.confirmed_count:  # more people than were confirmed: nothing is sent
        note = f"Went back to draft: {now_count} people now, {mailing.confirmed_count} confirmed. Check and send again."
        Mailing.objects.filter(pk=mailing.pk, status=Mailing.SCHEDULED).update(
            status=Mailing.DRAFT, scheduled_at=None, error=note, confirmed_count=None, updated_at=timezone.now())
        _drop_schedule(mailing)
        _event(SystemEvent.MAILING_RETURNED, mailing.created_by, f"The scheduled send '{mailing.name}' went back to draft and sent nothing: {now_count} people now, {mailing.confirmed_count} confirmed",
               {"mailing": str(mailing.pk), "name": mailing.name, "now": now_count, "confirmed": mailing.confirmed_count}, outcome=SystemEvent.BLOCKED)
        return "returned to draft"
    try:
        start(mailing, user=mailing.created_by)
    except MailingError as error:  # e.g. SES changed state: back to a draft with the reason, never lost
        Mailing.objects.filter(pk=mailing.pk, status=Mailing.SCHEDULED).update(
            status=Mailing.DRAFT, scheduled_at=None, error=str(error)[:300], updated_at=timezone.now())
        _drop_schedule(mailing)
        return "refused"
    return "started"


# ---------- the send pop-up ----------

def confirm_details(mailing):
    """What the send pop-up shows, read fresh from the server: the email, who gets it, the exact count and how many are skipped (and
    why), the From address (and Reply-To when it differs) and who delivers it. {"count", "title", "subject", "to", "skipped",
    "skipped_why", "from", "reply_to", "through", "kind"}."""
    params, errors = segments.clean_params(mailing.group, mailing.params)
    valid = not errors and mailing.kind in dict(Mailing.KIND_CHOICES) and segments.GROUPS[mailing.group].allows(mailing.kind)
    people = segments.count(mailing.group, params, mailing.kind) if valid else 0
    skipped, why = segments.skipped_summary(mailing.group, params, mailing.kind) if valid else (0, "")
    if mailing.automatic_key:
        spec = emailbody.SPECS.get(mailing.automatic_key)
        row = NotificationTemplate.objects.filter(key=mailing.automatic_key).first()
        title = spec.title if spec else mailing.name
        subject = row.subject if row else DEFAULT_SUBJECTS[mailing.automatic_key][0]
    else:
        title, subject = mailing.name, mailing.subject
    return {"count": people, "title": title, "subject": subject, "to": segments.to_label(mailing.group, params), "skipped": skipped,
            "skipped_why": why, "kind": mailing.get_kind_display().split(" (")[0], **sender_details()}


def sender_details():
    """The From address, the Reply-To (only when it differs) and who delivers the mail: the last rows of every send pop-up."""
    from email.utils import parseaddr

    from plans.models import SiteSettings

    sender = settings.DEFAULT_FROM_EMAIL
    reply = (SiteSettings.load().contact_address or "").strip()
    return {"from": sender, "reply_to": reply if reply and reply.lower() != parseaddr(sender)[1].lower() else "", "through": ses.through_label()}
