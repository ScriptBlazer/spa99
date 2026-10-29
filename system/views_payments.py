"""System > Payments (Developer, unlocked, CSRF, audited): the state of the payment window and its four actions. The rules and the
safety (one window, no double send) live in plans/payments.py; the confirm modal is the page's `data-system-confirm`."""
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from plans import payments
from plans.models import PaymentNotice, PaymentWindow

from . import defaults
from .permissions import unlocked
from .views import page


def _notice_counts(window):
    if window is None:
        return {}
    return {row["status"]: row["n"] for row in window.notices.values("status").annotate(n=Count("pk"))}


@unlocked
@require_GET
def payments_page(request):
    window = payments.current() or payments.latest()
    site = defaults.get(request)
    context = {
        "window": window, "counts": payments.counts(), "warning": payments.staff_warning(),
        "notices": _notice_counts(window), "window_days": site.payment_window_days, "window_phrase": payments.window_phrase(site.payment_window_days),
        "no_alert_email": not payments.alert_addresses(), "alerts_off": not site.staff_alert_emails_on,
        "online_live": settings.ONLINE_PAYMENTS_LIVE, "invite_total": window.notices.filter(kind=PaymentNotice.INVITE).count() if window else 0,
    }
    return page(request, "system/payments.html", "payments", context)


@unlocked
@require_GET
def payments_confirm(request):
    """What the send pop-up shows for opening payments: the email, who, the exact count, From, Reply-To and the provider."""
    from django.http import JsonResponse

    from mailings import sending
    from notifications.models import NotificationTemplate
    from notifications.seed import DEFAULT_SUBJECTS

    counts = payments.counts()
    row = NotificationTemplate.objects.filter(key="payment_window_open").first()
    return JsonResponse({"ok": True, "count": counts["registered"], "title": "Payments are open", "to": "Registered members", "skipped": counts["unconfirmed"],
                         "skipped_why": "email not confirmed yet" if counts["unconfirmed"] else "",
                         "subject": row.subject if row else DEFAULT_SUBJECTS["payment_window_open"][0], **sending.sender_details()})


def _done(request, ok, text):
    (messages.success if ok else messages.error)(request, text)
    return redirect("system_payments")


def _unconfirmed(request, count):
    """A redirect with the reason when the POST is not a confirmed send of the number the pop-up showed, else None."""
    from mailings import sending

    try:
        sending.require_confirmed(request.POST.get("confirm"), request.POST.get("expected_count"), count)
    except sending.MailingError as error:
        return _done(request, False, str(error))
    return None


@unlocked
@require_POST
def payments_open(request):
    """Emails every registered member, so the pop-up's `confirm=yes` and the member count it showed must come with the POST."""
    refused = _unconfirmed(request, payments.counts()["registered"])
    if refused:
        return refused
    window, opened = payments.open_now(request.user)
    if not opened:
        return _done(request, True, "Payments are already open. Nothing was sent again.")
    return _done(request, True, f"Payments are open until {payments.day_text(window.closes_at)}. The emails are being sent.")


@unlocked
@require_POST
def payments_schedule(request):
    refused = _unconfirmed(request, payments.counts()["registered"])
    if refused:
        return refused
    try:
        naive = datetime.strptime(request.POST.get("when", "").strip(), "%Y-%m-%dT%H:%M")
        when = timezone.make_aware(naive)
        if timezone.localtime(when).replace(tzinfo=None) != naive:  # spring forward: that clock time does not exist
            return _done(request, False, "That time does not exist because the clocks change. Pick another minute.")
        window = payments.schedule(request.user, when, confirmed=int(request.POST["expected_count"]))
    except ValueError:
        return _done(request, False, "Pick a date and time.")
    except ValidationError as error:
        return _done(request, False, " ".join(error.messages))
    return _done(request, True, f"Payments will open on {payments.when_text(window.scheduled_for)} (London time).")


@unlocked
@require_POST
def payments_cancel_schedule(request):
    ok = payments.cancel_schedule(request.user)
    return _done(request, ok, "The scheduled opening was cancelled." if ok else "Nothing is scheduled.")


@unlocked
@require_POST
def payments_close(request):
    result = payments.close(request.user, early=True)
    if result is None:
        return _done(request, False, "Payments are not open.")
    return _done(request, True, f"Payments are closed. {result['lapsed']} member(s) had not set up; {result['sale_expired']} launch price(s) ended.")
