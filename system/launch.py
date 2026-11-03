"""System > Launch: the one button that opens Spa 99 (docs/features/office-outreach.md, "Launch button").

`plan(site)` is the list of steps with Now -> After, built from the live settings (a step already in its after-state is skipped).
`checks(site)` are warnings, never blockers. `launch(user)` makes the setting changes in ONE transaction under a row lock on
SiteSettings (a double click or two tabs: the second finds `launched_at` set and does nothing), through the change log like any
System edit, writes one "Launched Spa 99" entry, then opens payments (plans.payments.open_now has its own lock and is idempotent)
unless a window is already open or scheduled. Payments are opened AFTER the commit so the queued email task always sees the window."""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from plans import payments
from plans.models import Plan, SiteSettings

from . import audit, services
from .models import SystemEvent

logger = logging.getLogger("spa99.launch")

WORD = "LAUNCH"  # typed to confirm; the server checks it too
PAYMENT_EMAILS = ("payment_window_open", "payment_window_reminder")


def _onoff(value):
    return "On" if value else "Off"


def _window_state():
    """(window, 'open'|'scheduled'|None)."""
    window = payments.current()
    return window, (window.status if window is not None else None)


def plan(site):
    """The steps, in order. Each: key, label, now, after, effect (what visitors and members notice), already_done."""
    window, state = _window_state()
    if state == "open":
        pay_now, pay_done = f"Open until {payments.day_text(window.closes_at)}", True
    elif state == "scheduled":
        pay_now, pay_done = f"Scheduled for {payments.when_text(window.scheduled_for)}", True
    else:
        pay_now, pay_done = "Not open", False
    members = payments.counts()["registered"]
    return [
        {"key": "memberships_public", "label": "Memberships page public", "now": _onoff(site.memberships_public), "after": "On",
         "effect": "The Memberships page, its links and prices open to everyone. Register no longer needs the questions first.",
         "already_done": site.memberships_public},
        {"key": "journey_email_gate", "label": "Email gate", "now": _onoff(site.journey_email_gate), "after": "Off",
         "effect": "The questions show the suggested membership and price without asking for an email. No new leads come from the questions after this, "
                   "so the next-morning email stops getting new people.",
         "already_done": not site.journey_email_gate},
        {"key": "join_wording", "label": "Wording", "now": site.get_join_wording_display(), "after": dict(SiteSettings.WORDING_CHOICES)[SiteSettings.JOIN],
         "effect": 'Buttons and headings say "Join" instead of "Register".', "already_done": site.join_wording == SiteSettings.JOIN},
        {"key": "payments", "label": "Open payments", "now": pay_now, "after": "Open now",
         "effect": (f"Every registered member ({members}) gets the \"set up your membership\" email and has "
                    f"{payments.window_phrase(_days())} to set up. Emails cannot be unsent."
                    if not pay_done else
                    "Payments are already open or scheduled, so Launch does not open another window."),
         "already_done": pay_done},
    ]


def _days():
    from . import defaults

    return defaults.get().payment_window_days


def checks(site):
    """Warnings above the button: [{key, ok, text}]. Nothing here blocks the launch."""
    out = []
    plans = list(Plan.objects.filter(kind=Plan.MONTHLY, visible=True, price_ex_vat__gt=0).values_list("name", flat=True))
    out.append({"key": "plans", "ok": bool(plans),
                "text": f"{len(plans)} visible monthly plan{'s' if len(plans) != 1 else ''} with a price ({', '.join(plans)})." if plans
                else "No visible monthly plan has a price. The Memberships page would be empty."})
    from notifications.models import NotificationTemplate

    have = set(NotificationTemplate.objects.filter(key__in=PAYMENT_EMAILS).values_list("key", flat=True))
    out.append({"key": "emails", "ok": have == set(PAYMENT_EMAILS),
                "text": "The payment emails are in System > Emails." if have == set(PAYMENT_EMAILS)
                else "A payment email is missing in System > Emails (the built-in wording would be used)."})
    if not settings.ONLINE_PAYMENTS_LIVE:
        out.append({"key": "online", "ok": False, "text": "Card payments are not live yet. Members are told we will be in touch (or to WhatsApp or email us) "
                                                         "and staff set their memberships up manually in the Office."})
    window, state = _window_state()
    if state == "open":
        out.append({"key": "window", "ok": True, "text": f"Payments are already open until {payments.day_text(window.closes_at)}. Launch will not open another window."})
    elif state == "scheduled":
        out.append({"key": "window", "ok": True, "text": f"Payments are already scheduled for {payments.when_text(window.scheduled_for)}. Launch will not open another window."})
    members = payments.counts()["registered"]
    out.append({"key": "members", "ok": True, "text": f"{members} member{'s' if members != 1 else ''} will be emailed when payments open." if state is None
                else f"{members} registered member{'s' if members != 1 else ''}."})
    return out


def last_launch():
    """The newest 'Launched Spa 99' entry (its detail lists what changed), or None."""
    return SystemEvent.objects.filter(kind=SystemEvent.LAUNCHED).first()


def launch(user):
    """Press the button. Returns {launched, message, changed: [labels], payments_opened, members}. Does nothing when already launched."""
    with transaction.atomic():
        payments.lock()  # the SiteSettings row lock, held to the commit
        site = SiteSettings.objects.select_for_update().get(pk=SiteSettings.load().pk)
        if site.launched_at:
            return {"launched": False, "message": f"Spa 99 was already launched on {_when(site.launched_at)}. Nothing was changed.",
                    "changed": [], "payments_opened": False, "members": 0}
        steps = plan(site)
        todo = [s for s in steps if s["key"] != "payments" and not s["already_done"]]
        site.memberships_public, site.journey_email_gate, site.join_wording = True, False, SiteSettings.JOIN
        site.launched_at, site.launched_by = timezone.now(), user
        services.save_logged(site, user, fields=[s["key"] for s in todo] + ["launched_at", "launched_by"])
        pay_step = next(s for s in steps if s["key"] == "payments")
        changed = [s["label"] for s in todo]
        audit.log_event(SystemEvent.LAUNCHED, user=user, section="launch", detail={"changed": changed, "payments": "left as it was" if pay_step["already_done"] else "opened"},
                        sentence=f"{getattr(user, 'email', 'Someone')} launched Spa 99 ({', '.join(changed) or 'no settings needed changing'})")
    opened, members = False, 0
    if not pay_step["already_done"]:
        try:
            window, opened = payments.open_now(user)
            members = payments.counts()["registered"]
        except Exception:  # the settings are saved and logged; say so plainly rather than hide it
            logger.exception("Launch: settings saved but payments did not open")
            return {"launched": True, "message": "Spa 99 is launched, but payments did not open. Open them in System > Payments.",
                    "changed": changed, "payments_opened": False, "members": 0, "payments_failed": True}
    return {"launched": True, "changed": changed, "payments_opened": opened, "members": members,
            "message": "Spa 99 is launched." + (f" Payments are open and {members} member{'s' if members != 1 else ''} are being emailed." if opened
                                                else " Payments were already open or scheduled, so none were opened again.")}


def _when(moment):
    local = timezone.localtime(moment)
    return f"{local.day} {local:%b %Y} at {local:%H:%M}"


when_text = _when


def short_when(moment):
    local = timezone.localtime(moment)
    return f"{local.day} {local:%b}"
