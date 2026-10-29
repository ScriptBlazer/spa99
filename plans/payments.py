"""The payment window: after Spa 99 opens, registered members have a set time to set up a paid membership. No card payments here
(Stripe is the next phase): this is the state, the emails, the close, and `mark_paid` for Stripe or a manual set-up to call.

Safety, in short. One active window: a conditional unique index on `PaymentWindow.is_active`. Opening twice: the second call finds
it open and does nothing (a lock on the SiteSettings row serialises the writers; SQLite serialises them anyway). Emails: one
`PaymentNotice` row per (window, member, kind), unique in the database, and a row is CLAIMED (queued -> sending, a conditional update)
before it is sent, so two workers or two clicks never send twice; a send that dies is marked failed, never retried. Plain ORM,
nothing Postgres-only (`select_for_update` is ignored by SQLite)."""
import logging
import time
from datetime import datetime, time as dt_time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from simple_history.utils import bulk_update_with_history

from common.tasks import enqueue
from plans import sales
from plans.models import PaymentMark, PaymentNotice, PaymentStaffAlert, PaymentWindow, Plan, Subscription
from users.models import InterestRegistration

logger = logging.getLogger("spa99.payments")

BATCH = 500
ALERT_HOUR = 9
SLICE_SECONDS = 50
STALE_SECONDS = 600


def _defaults():
    from system import defaults

    return defaults.get()


def lock():
    """Serialise window writers: a row lock on the SiteSettings singleton (the same one the sales use)."""
    sales.lock()


# ---------- words ----------

def window_phrase(days):
    """'2 weeks' for 14, '1 week' for 7, else 'N days'."""
    if days % 7 == 0:
        weeks = days // 7
        return "1 week" if weeks == 1 else f"{weeks} weeks"
    return "1 day" if days == 1 else f"{days} days"


def day_text(moment):
    local = timezone.localtime(moment)
    return f"{local.day} {local:%B}"


def when_text(moment):
    local = timezone.localtime(moment)
    return f"{local.day} {local:%B %Y}, {local:%H:%M}"


def site_window_phrase():
    return window_phrase(_defaults().payment_window_days)


def whatsapp_url(source="other"):
    """The WhatsApp short link on our own domain (counted, then forwarded), or "" while no link is set in System > Settings."""
    from pages.links import short_url

    return short_url(source)


# ---------- the window ----------

def current():
    """The scheduled or open window, or None."""
    return PaymentWindow.objects.filter(is_active=True).first()


def latest():
    return PaymentWindow.objects.order_by("-created_at").first()


def _closes_at(opened_at, days):
    """The end of the last day (London time, 23:59:59), so 'until 13 November' is true for the whole day."""
    last = timezone.localtime(opened_at).date() + timedelta(days=days)
    return timezone.make_aware(datetime.combine(last, dt_time(23, 59, 59)))


def _log(kind, user, sentence, detail=None):
    from system import audit

    audit.log_event(kind, user=user, detail=detail or {}, sentence=sentence)


def eligible():
    """Members the window is for: active accounts with a confirmed email (an unproven address is not emailed). Gold members are in too:
    same window, emails and dates as everyone, with Gold pricing."""
    return InterestRegistration.objects.filter(user__is_active=True, user__email_verified_at__isnull=False)


def _set_status(registrations, status, now, reason):
    rows = list(registrations)
    for row in rows:
        row.payment_status = status
        row.updated_at = now
    for start in range(0, len(rows), BATCH):
        bulk_update_with_history(rows[start:start + BATCH], InterestRegistration, ["payment_status", "updated_at"], default_change_reason=reason)
    return len(rows)


def _invite(ids, now, due, reason):
    rows = list(InterestRegistration.objects.filter(pk__in=ids).exclude(payment_status=InterestRegistration.PAID))
    for row in rows:
        row.payment_status, row.payment_due_at, row.updated_at = InterestRegistration.INVITED, due, now
    bulk_update_with_history(rows, InterestRegistration, ["payment_status", "payment_due_at", "updated_at"], default_change_reason=reason)


def opened_ever():
    """Have payments been opened at least once (a window is open, or was)? After that, a sale no longer snapshots a kept price."""
    return PaymentWindow.objects.filter(opened_at__isnull=False).exists()


def ensure_notices(window, now=None, late=False):
    """Make sure every eligible member who is not set up has an invite notice and is `invited`. New rows only: the unique constraint
    ignores the rest, so calling it again (the tick, a second click) creates nothing twice. Returns the new count.
    `late=False` (opening): everyone shares the window's end as their due date; a member invited in an earlier window is invited again.
    `late=True` (payments already open or closed): someone who registered, or confirmed their email, after it opened gets the open email
    so they can set up straight away, with NO personal window, due date, lapse or reminder (`payment_due_at` stays empty). A member who
    registered before it opened and confirms while it is still open shares the window's end; one who confirms after it closed gets their
    own due date (confirmation + window days) if they hold a kept sale price (so it cannot last forever), else no due date."""
    now = now or timezone.now()
    notices = PaymentNotice.objects.filter(kind=PaymentNotice.INVITE)
    have = (notices if late else notices.filter(window=window)).values("registration_id")
    todo = list(eligible().exclude(payment_status=InterestRegistration.PAID).exclude(pk__in=have).values_list("pk", "created_at", "sale_percent_off"))
    shared = window.closes_at if window.status == PaymentWindow.OPEN and window.closes_at and window.closes_at > now else None
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        PaymentNotice.objects.bulk_create([PaymentNotice(window=window, registration_id=pk, kind=PaymentNotice.INVITE) for pk, _, _ in chunk], ignore_conflicts=True)
        if not late:
            _invite([pk for pk, _, _ in chunk], now, window.closes_at, "Payment window opened")
        else:
            own = _closes_at(now, _defaults().payment_window_days)  # registered before opening with a kept price, confirming after it closed
            before = [(pk, sale) for pk, made, sale in chunk if made < window.opened_at]
            if shared:
                _invite([pk for pk, _ in before], now, shared, "Payments open: invited on confirming email")
            else:
                _invite([pk for pk, sale in before if sale], now, own, "Payments closed: own window from confirming email")
                _invite([pk for pk, sale in before if not sale], now, None, "Payments closed: no sale price, no window")
            _invite([pk for pk, made, _ in chunk if made >= window.opened_at], now, None, "Payments open: registered after opening")
    return len(todo)


def _open(window, user, now):
    days = _defaults().payment_window_days
    window.status, window.opened_at, window.window_days = PaymentWindow.OPEN, now, days
    window.closes_at = _closes_at(now, days)
    window.opened_by = user or window.opened_by
    window.save()
    return ensure_notices(window, now)


def open_now(user, now=None):
    """Open payments now. Returns (window, opened). Calling it again while open changes nothing and returns opened=False."""
    now = now or timezone.now()
    with transaction.atomic():
        lock()
        window = PaymentWindow.objects.select_for_update().filter(is_active=True).first()
        if window is not None and window.status == PaymentWindow.OPEN:
            return window, False
        window = window or PaymentWindow()
        window._history_user = user
        queued = _open(window, user, now)
    _log("payments_opened", user, f"{getattr(user, 'email', 'The system')} opened payments: {queued} member(s) invited, closes {when_text(window.closes_at)}",
         {"members": queued, "closes_at": window.closes_at.isoformat(), "window_days": window.window_days})
    enqueue("plans.tasks.send_payment_notices", str(window.pk))
    return window, True


def schedule(user, when, now=None, confirmed=None):
    """Schedule opening for `when` (a later time). Replaces the time of an already scheduled window. Refused while one is open."""
    now = now or timezone.now()
    if when <= now + timedelta(minutes=1):
        raise ValidationError("Pick a time at least a minute from now.")
    try:
        with transaction.atomic():
            lock()
            window = PaymentWindow.objects.select_for_update().filter(is_active=True).first()
            if window is not None and window.status == PaymentWindow.OPEN:
                raise ValidationError("Payments are already open.")
            window = window or PaymentWindow()
            window._history_user = user
            window.status, window.scheduled_for, window.opened_by = PaymentWindow.SCHEDULED, when, user
            window.confirmed_count, window.note = confirmed, ""
            window.save()
    except IntegrityError:
        raise ValidationError("A payment window is already scheduled or open.") from None
    _log("payments_scheduled", user, f"{user.email} scheduled payments to open on {when_text(when)}", {"scheduled_for": when.isoformat()})
    return window


def cancel_schedule(user):
    with transaction.atomic():
        lock()
        window = PaymentWindow.objects.select_for_update().filter(is_active=True, status=PaymentWindow.SCHEDULED).first()
        if window is None:
            return False
        window._history_user = user
        window.status = PaymentWindow.CANCELLED
        window.save()
    _log("payments_cancelled", user, f"{user.email} cancelled the scheduled opening of payments")
    return True


def lapse_due(now=None, everyone=False):
    """Invited, unpaid members whose own due date has passed (everyone invited, when the window is closed early) become `lapsed`; those
    holding a sale price get `sale_expired_at`. The snapshot and the account stay. Returns {"lapsed", "sale_expired"}."""
    now = now or timezone.now()
    with transaction.atomic():
        rows = InterestRegistration.objects.filter(payment_status=InterestRegistration.INVITED)
        if not everyone:
            rows = rows.filter(payment_due_at__lte=now)
        else:
            rows = rows.filter(payment_due_at__isnull=False)  # a registrant after opening has no window and so no lapse
        rows = list(rows)
        expired = 0
        for row in rows:
            row.payment_status, row.updated_at = InterestRegistration.LAPSED, now
            if row.sale_percent_off and row.sale_expired_at is None:
                row.sale_expired_at = now
                expired += 1
        for start in range(0, len(rows), BATCH):
            bulk_update_with_history(rows[start:start + BATCH], InterestRegistration, ["payment_status", "sale_expired_at", "updated_at"],
                                     default_change_reason="Payment window closed")
    return {"lapsed": len(rows), "sale_expired": expired}


def close(user=None, now=None, early=False):
    """Close the open window. Invited members past their own due date (all of them on an early close) become `lapsed`, and those
    holding a sale price get `sale_expired_at` (the snapshot stays, the account stays). Paid members are untouched. Members who
    registered late keep their own later due date, and `tick` lapses them then. Running it twice does nothing the second time.
    Returns the counts, or None when nothing was open."""
    now = now or timezone.now()
    with transaction.atomic():
        lock()
        window = PaymentWindow.objects.select_for_update().filter(is_active=True, status=PaymentWindow.OPEN).first()
        if window is None:
            return None
        window._history_user = user
        window.status, window.closed_at = PaymentWindow.CLOSED, now
        window.save()
        counts = lapse_due(now, everyone=early)
    who = user.email if user is not None else "The system"
    _log("payments_closed", user, f"{who} closed payments{' early' if early else ''}: {counts['lapsed']} not set up, {counts['sale_expired']} launch price(s) ended", counts)
    return counts


# ---------- the emails ----------

def _member_url():
    return f"{settings.SITE_URL}/account/membership/"


def _sale_line(registration, closes_at):  # closes_at: this member's own due date
    if not registration.sale_percent_off or registration.sale_expired_at:
        return ""
    months = registration.sale_months or 1
    period = "your first month" if months == 1 else f"your first {months} months"
    return (f"Your launch price of {registration.sale_percent_off}% off for {period} is kept when you set up by {day_text(closes_at)}.")


def _skip_reason(notice, now):
    reg = notice.registration
    if not reg.user.is_active:
        return "The account is no longer active"
    if not reg.user.email_verified_at:
        return "Email not confirmed"
    if reg.payment_status != InterestRegistration.INVITED:
        return "Already set up" if reg.payment_status == InterestRegistration.PAID else "Not in a payment window"
    if notice.kind == PaymentNotice.REMINDER and not reg.payment_due_at:
        return "No window"
    if reg.payment_due_at and reg.payment_due_at <= now:
        return "The window is over"
    return ""


def _send_one(notice, window):
    from notifications.models import EmailLog
    from notifications.services import send_templated, subject_for

    claimed = PaymentNotice.objects.filter(pk=notice.pk, status=PaymentNotice.QUEUED).update(status=PaymentNotice.SENDING, updated_at=timezone.now())
    if not claimed:
        return
    reg, now = notice.registration, timezone.now()
    reason = _skip_reason(notice, now)
    if reason:
        PaymentNotice.objects.filter(pk=notice.pk).update(status=PaymentNotice.SKIPPED, reason=reason, updated_at=now)
        return
    key = "payment_window_open" if notice.kind == PaymentNotice.INVITE else "payment_window_reminder"
    user, due = reg.user, reg.payment_due_at
    try:
        log = send_templated(
            key, [user.email], subject_for(key, first_name=user.first_name),
            {"first_name": user.first_name, "closes_on": day_text(due) if due else "", "sale_line": _sale_line(reg, due) if due else "", "url": _member_url()},
            subject_email=user.email)
        status, error = log.status, ""
    except Exception as exc:  # noqa: BLE001 - one bad send never stops the batch
        status, error = EmailLog.FAILED, type(exc).__name__
    if status == EmailLog.SENT:
        PaymentNotice.objects.filter(pk=notice.pk).update(status=PaymentNotice.SENT, sent_at=now, updated_at=now)
        field = "payment_invite_sent_at" if notice.kind == PaymentNotice.INVITE else "payment_reminder_sent_at"
        InterestRegistration.objects.filter(pk=reg.pk).update(**{field: now})
    elif status == EmailLog.SUPPRESSED:
        PaymentNotice.objects.filter(pk=notice.pk).update(status=PaymentNotice.SKIPPED, reason="Address is on the suppression list", updated_at=now)
    else:
        PaymentNotice.objects.filter(pk=notice.pk).update(status=PaymentNotice.FAILED, reason=error or "Send failed", updated_at=now)


def send_slice(window_id, budget=SLICE_SECONDS):
    """Send queued notices for one window for about `budget` seconds, paced like the group sends, then queue itself again if more
    are left. Returns a plain status string (django-q keeps results: no personal data)."""
    from mailings.sending import Pacer, rate_per_second
    from notifications import ses

    window = PaymentWindow.objects.filter(pk=window_id).first()
    if window is None:
        return "missing"
    cutoff = timezone.now() - timedelta(seconds=STALE_SECONDS)
    PaymentNotice.objects.filter(window=window, status=PaymentNotice.SENDING, updated_at__lt=cutoff).update(
        status=PaymentNotice.FAILED, reason="Interrupted; not retried so nobody gets it twice")
    queued = PaymentNotice.objects.filter(window=window, status=PaymentNotice.QUEUED)
    if not queued.exists():
        return "idle"
    try:
        ses.require_sending_allowed()
    except ses.SendingRefused as error:
        return f"paused: {error}"
    deadline, pacer = time.monotonic() + budget, Pacer(rate_per_second())
    while time.monotonic() < deadline:
        batch = list(queued.select_related("registration__user").order_by("created_at")[:50])
        if not batch:
            return "done"
        for notice in batch:
            if time.monotonic() >= deadline:
                break
            pacer.wait()
            _send_one(notice, window)
    if queued.exists():
        enqueue("plans.tasks.send_payment_notices", str(window.pk))
        return "more"
    return "done"


def start_reminders(now=None):
    """One reminder per member and window, `payment_reminder_days_before` days before their own due date, to those still invited and not
    set up. The window is the one of their newest invite; skipped when their window is too short for it (it would fall before they were
    invited). New notice rows only (unique), so running it again sends nothing twice; a restored member's old reminder was cleared, so
    they get one again. Returns the number owed."""
    now = now or timezone.now()
    lead = timedelta(days=_defaults().payment_reminder_days_before)
    rows = (InterestRegistration.objects.filter(payment_status=InterestRegistration.INVITED, user__is_active=True, payment_due_at__gt=now,
                                                payment_due_at__lte=now + lead).prefetch_related("payment_notices"))
    made = 0
    for row in rows:
        notices = list(row.payment_notices.all())
        invites = sorted((n for n in notices if n.kind == PaymentNotice.INVITE), key=lambda n: n.created_at)
        if not invites or invites[-1].created_at >= row.payment_due_at - lead:
            continue
        newest = invites[-1]
        if any(n.kind == PaymentNotice.REMINDER and n.window_id == newest.window_id for n in notices):
            continue
        _, created = PaymentNotice.objects.get_or_create(window=newest.window, registration=row, kind=PaymentNotice.REMINDER)
        made += created
    if made:
        PaymentWindow.objects.filter(reminder_sent_at__isnull=True, pk__in=PaymentNotice.objects.filter(kind=PaymentNotice.REMINDER).values("window_id")).update(reminder_sent_at=now)
    return made


# ---------- paid, and manual set-up ----------

def mark_paid(registration, source, key=None, now=None):
    """Record that this member has set up (Stripe webhook later, or a manual set-up). Idempotent on `key` (default one per member and
    source): the same key twice changes nothing and returns False. A first call returns True. The sale snapshot is never touched, and a
    paid member is never lapsed by the close job."""
    now = now or timezone.now()
    key = key or f"{source}:{registration.pk}"
    with transaction.atomic():
        _, created = PaymentMark.objects.get_or_create(idempotency_key=key, defaults={"registration": registration, "source": source})
        if not created:
            return False
        row = InterestRegistration.objects.select_for_update().get(pk=registration.pk)
        row.payment_status, row.payment_source, row.paid_at = InterestRegistration.PAID, source, row.paid_at or now
        row._change_reason = f"Set up ({source})"
        row.save(update_fields=["payment_status", "payment_source", "paid_at", "updated_at"])
        registration.refresh_from_db()
    return True


def lock_in(registration, source, key=None):
    """Sibling name of `mark_paid` for a set-up that is not a card payment (the sale price is kept the same way)."""
    return mark_paid(registration, source, key=key)


def _unset(registration, now):
    """Back to the state before set-up. Window open: invited, with the due date they would have had (the window's end, or none for someone
    who registered after it opened: never a fresh 14 days). Window closed (payments opened before): invited, and a member holding a kept
    sale price gets their own due date so the price cannot last forever. Payments never opened: not started."""
    window = PaymentWindow.objects.filter(is_active=True, status=PaymentWindow.OPEN).first()
    holder = bool(registration.sale_percent_off) and registration.sale_expired_at is None
    if window is not None:
        status = InterestRegistration.INVITED
        due = window.closes_at if registration.created_at < window.opened_at else None
    elif opened_ever():
        status = InterestRegistration.INVITED
        due = _closes_at(now, _defaults().payment_window_days) if holder else None
    else:
        status, due = InterestRegistration.NOT_STARTED, None
    registration.payment_status, registration.payment_due_at = status, due
    registration.payment_source, registration.paid_at = "", None
    registration._change_reason = "Manual set-up cancelled"
    registration.save(update_fields=["payment_status", "payment_source", "paid_at", "payment_due_at", "updated_at"])


def active_subscription(registration):
    return Subscription.objects.filter(registration=registration, status=Subscription.ACTIVE).first()


def set_up_manually(registration, user, plan, start_date, agreed_price=None, note=""):
    """Office: a member who pays directly, outside the website. Creates the Subscription (source manual) and marks the member set up,
    so the close job never lapses them. One active subscription per member (database constraint): a second click is refused, not
    duplicated. Nothing is charged. Returns the Subscription."""
    if plan is None or plan.kind == Plan.ONE_OFF:
        raise ValidationError("Choose a membership plan.")
    try:
        with transaction.atomic():
            row = InterestRegistration.objects.select_for_update().get(pk=registration.pk)
            if Subscription.objects.filter(registration=row, status=Subscription.ACTIVE).exists():
                raise ValidationError("This member already has an active membership.")
            sub = Subscription(registration=row, plan=plan, source=Subscription.MANUAL, start_date=start_date, agreed_price_ex_vat=agreed_price,
                               billing_note=note.strip(), created_by=user)
            sub._history_user = user
            sub.full_clean(exclude=["external_id"])
            sub.save()
            mark_paid(row, "manual", key=f"manual:{sub.pk}")
    except IntegrityError:
        raise ValidationError("This member already has an active membership.") from None
    _log("setup_manual", user, f"{user.email} set up {plan.name} for {row.user.public_id} manually (starts {start_date:%d %B %Y})",
         {"subscription": str(sub.pk), "plan": plan.slug, "member": row.user.public_id})
    return sub


def edit_manual(sub, user, plan, start_date, agreed_price, note):
    if sub.status != Subscription.ACTIVE or sub.source != Subscription.MANUAL:
        raise ValidationError("Only an active manual membership can be edited.")
    if plan is None or plan.kind == Plan.ONE_OFF:
        raise ValidationError("Choose a membership plan.")
    old = {"plan": sub.plan.slug, "start_date": sub.start_date.isoformat(), "agreed_price_ex_vat": str(sub.agreed_price_ex_vat) if sub.agreed_price_ex_vat is not None else None}
    note_changed = sub.billing_note != note.strip()
    sub.plan, sub.start_date, sub.agreed_price_ex_vat, sub.billing_note = plan, start_date, agreed_price, note.strip()
    sub._history_user = user
    sub.full_clean(exclude=["external_id"])
    sub.save()
    new = {"plan": plan.slug, "start_date": start_date.isoformat(), "agreed_price_ex_vat": str(agreed_price) if agreed_price is not None else None}
    _log("setup_edited", user, f"{user.email} edited the manual membership of {sub.registration.user.public_id}",
         {"subscription": str(sub.pk), "member": sub.registration.user.public_id, "old": old, "new": new, "billing_note_changed": note_changed})  # the note text stays on the subscription (erased with the member)
    return sub


def cancel_manual(sub, user, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)
        if sub.status != Subscription.ACTIVE:
            return False
        sub.status, sub.cancelled_at, sub.cancelled_by = Subscription.CANCELLED, now, user
        sub._history_user = user
        sub.save()
        _unset(sub.registration, now)
    _log("setup_cancelled", user, f"{user.email} cancelled the manual membership of {sub.registration.user.public_id}", {"subscription": str(sub.pk), "member": sub.registration.user.public_id})
    return True


# ---------- counts and who is at risk ----------

def at_risk():
    """Sale holders still inside an open window who have not set up (the price ends when it closes)."""
    return (InterestRegistration.objects.filter(payment_status=InterestRegistration.INVITED, sale_percent_off__isnull=False, sale_expired_at__isnull=True,
                    user__is_active=True)
            .select_related("user", "plan").order_by("user__first_name", "user__last_name"))


def counts():
    base = InterestRegistration.objects
    paid = base.filter(payment_status=InterestRegistration.PAID)
    return {
        "registered": eligible().count(),
        "unconfirmed": base.filter(user__is_active=True, user__email_verified_at__isnull=True).count(),
        "sale_holders": base.filter(sale_percent_off__isnull=False, sale_expired_at__isnull=True).count(),
        "sale_expired": base.filter(sale_expired_at__isnull=False).count(),
        "invited": base.filter(payment_status=InterestRegistration.INVITED).count(),
        "paid_online": paid.filter(payment_source="stripe").count(),
        "set_up_manually": paid.filter(payment_source="manual").count(),
        "at_risk": at_risk().count(),
        "lapsed": base.filter(payment_status=InterestRegistration.LAPSED).count(),
    }


def anchor():
    """The window the notices and alerts hang on: the open one, else the latest that ever opened (late registrants join after it
    closed). None until payments have been opened once."""
    return PaymentWindow.objects.filter(opened_at__isnull=False).order_by("-opened_at").first()


def staff_warning(now=None):
    """The in-app notice for staff (Office dashboard, System > Payments): None unless someone holding a sale price is invited, not set up,
    and within `payment_staff_alert_days_before` days of their own due date. {count, closes_on, days_left, people: [{name, id, due_on}], more};
    `closes_on` is the earliest due date (a late registrant's is their own)."""
    now = now or timezone.now()
    last_day = timezone.localdate(now) + timedelta(days=_defaults().payment_staff_alert_days_before)  # London dates: the first alert lands on day 7
    horizon = timezone.make_aware(datetime.combine(last_day, dt_time(23, 59, 59)))
    rows = list(at_risk().filter(payment_due_at__gt=now, payment_due_at__lte=horizon).order_by("payment_due_at", "user__first_name"))
    if not rows:
        return None
    first = rows[0].payment_due_at
    days = max((timezone.localtime(first).date() - timezone.localtime(now).date()).days, 0)
    people = [{"name": r.user.get_full_name() or r.user.email, "id": str(r.user_id), "due_on": day_text(r.payment_due_at)} for r in rows[:50]]
    return {"count": len(rows), "closes_on": day_text(first), "days_left": days, "people": people, "more": max(len(rows) - 50, 0),
            "same_day": len({day_text(r.payment_due_at) for r in rows}) == 1}


def _office_person_url(user_id):
    return f"{settings.OFFICE_URL}{reverse('office_person', args=[user_id], urlconf='config.urls_office')}"


def alert_addresses():
    """Only the addresses set in System > Defaults (never a role, never hard-coded). Empty: no email is sent."""
    from common.validators import split_emails

    site = _defaults()
    if not site.staff_alert_emails_on:  # switched off in System > Defaults without clearing the addresses
        return []
    return list(dict.fromkeys(a.lower() for a in split_emails(site.staff_alert_emails)))[:5]


def run_staff_alert(now=None):
    """Once a day (unique window + day) while sale holders are at risk: email the System > Defaults alert addresses (none set: no email), listing who. Returns the alert or None."""
    from notifications.emailbody import LINK_STYLE, Rich
    from notifications.services import send_templated, subject_for

    now = now or timezone.now()
    if timezone.localtime(now).hour < ALERT_HOUR:  # a sensible hour: from 09:00 London time, once a day
        return None
    warning = staff_warning(now)
    if warning is None:
        return None
    window = anchor()
    alert, created = PaymentStaffAlert.objects.get_or_create(window=window, day=timezone.localdate(now), defaults={"at_risk": warning["count"]})
    if not created:
        return None
    noun = "member" if warning["count"] == 1 else "members"
    when = f"on {warning['closes_on']}" if warning["same_day"] else f"from {warning['closes_on']}"
    line = f"{warning['count']} {noun} will lose their launch price {when} ({warning['days_left']} day{'' if warning['days_left'] == 1 else 's'} left)."
    items = [(f"{p['name']} (until {p['due_on']})", _office_person_url(p["id"])) for p in warning["people"]]
    html = "<br>".join(f'<a href="{escape(url)}" style="{LINK_STYLE}">{escape(name)}</a>' for name, url in items)
    text = "\n".join(f"{name}: {url}" for name, url in items)
    if warning["more"]:
        html += f"<br>and {warning['more']} more"
        text += f"\nand {warning['more']} more"
    sent = 0
    for address in alert_addresses():
        log = send_templated("payment_staff_alert", [address], subject_for("payment_staff_alert", first_name="", count=warning["count"]),
                             {"first_name": "", "count_line": line, "people": Rich(html, text),
                              "url": f"{settings.OFFICE_URL}/people/?sale=at_risk"}, subject_email="")
        sent += log.status == "sent"
    PaymentStaffAlert.objects.filter(pk=alert.pk).update(emailed=sent)
    return alert


# ---------- restoring a lapsed sale price ----------

def restore_sale(registration, user, reason, now=None):
    """Office, Admin and up: give a lapsed sale price back (a reason is required). Clears `sale_expired_at`, sets a new due date
    (now + the window length) and puts a lapsed member back to invited. Audited with who, why and when. Returns the registration."""
    reason = " ".join((reason or "").split())
    if len(reason) < 3:
        raise ValidationError("Write the reason for restoring the sale price.")
    now = now or timezone.now()
    with transaction.atomic():
        row = InterestRegistration.objects.select_for_update().select_related("user").get(pk=registration.pk)
        if not row.sale_percent_off or row.sale_expired_at is None:
            raise ValidationError("This member has no ended sale price to restore.")
        row.sale_expired_at = None
        row.payment_due_at = _closes_at(now, _defaults().payment_window_days)
        if row.payment_status == InterestRegistration.LAPSED:
            row.payment_status = InterestRegistration.INVITED
        row.sale_restore_reason = reason[:300]  # on the member's own record (and its history): erased with the member, never in the audit log
        row.payment_reminder_sent_at = None
        PaymentNotice.objects.filter(registration=row, kind=PaymentNotice.REMINDER).delete()  # a restored member gets a reminder again
        row._history_user, row._change_reason = user, "Sale price restored"
        row.save(update_fields=["sale_expired_at", "payment_due_at", "payment_status", "sale_restore_reason", "payment_reminder_sent_at", "updated_at"])
    _log("sale_restored", user, f"{user.email} restored the {row.sale_name} price ({row.sale_percent_off}%) for {row.user.public_id} until {day_text(row.payment_due_at)}",
         {"member": row.user.public_id, "due_at": row.payment_due_at.isoformat(), "at": now.isoformat()})
    return row


# ---------- the job ----------

def tick(now=None):
    """The scheduled job (every few minutes): open a due scheduled window; close an open one at its end; give late registrants (and
    people who confirmed their email since) their own window and the open email; send the reminders due; lapse members past their own
    due date; warn staff; send what is queued. Returns a status string."""
    now = now or timezone.now()
    window = current()
    parts = []
    if window is not None and window.status == PaymentWindow.SCHEDULED:
        if window.scheduled_for and window.scheduled_for <= now:
            with transaction.atomic():
                lock()
                fresh = PaymentWindow.objects.select_for_update().get(pk=window.pk)
                if fresh.status != PaymentWindow.SCHEDULED:
                    return "already opened"
                eligible_now = eligible().count()
                held = fresh.confirmed_count is not None and eligible_now > fresh.confirmed_count  # more members than were confirmed: do not open
                fresh._history_user = fresh.opened_by
                if held:
                    fresh.status = PaymentWindow.CANCELLED
                    fresh.note = f"Did not open: {eligible_now} members now, {fresh.confirmed_count} confirmed. Schedule it again."
                    fresh.save()
                else:
                    invited = _open(fresh, fresh.opened_by, now)
            if held:
                _log("payments_cancelled", fresh.opened_by, f"Scheduled payments did not open: {eligible_now} members now, {fresh.confirmed_count} confirmed",
                     {"now": eligible_now, "confirmed": fresh.confirmed_count})
                parts.append("scheduled opening held back")
                window = None
            else:
                _log("payments_opened", fresh.opened_by, f"Payments opened as scheduled: {invited} member(s) invited, closes {when_text(fresh.closes_at)}",
                     {"members": invited, "closes_at": fresh.closes_at.isoformat(), "scheduled": True})
                window = fresh
        else:
            parts.append("next window scheduled")  # only the opening waits; late invites, reminders, lapses, alerts and sends carry on
    if window is not None and window.status == PaymentWindow.OPEN and window.closes_at <= now:
        close(now=now)
        parts.append("closed")
    base = anchor()
    if base is None:
        return "no window"
    parts.append(f"{ensure_notices(base, now, late=True)} invited late")
    parts.append(f"{start_reminders(now)} reminders")
    parts.append(f"{lapse_due(now)['lapsed']} lapsed")
    parts.append(f"staff alert {'sent' if run_staff_alert(now) else 'no'}")
    parts.append(f"send {send_slice(str(base.pk))}")
    return ", ".join(parts)
