"""System > WhatsApp (Developer level, unlocked, CSRF): is Twilio set up, the Twilio check, the `spa99_` templates and their sync, and push.
The numbers and the site WhatsApp button setting stay where they are (System > Settings). Secrets are never shown: only which names are empty."""
import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_GET, require_POST

from common.tasks import enqueue
from whatsapp import push, services, twilio_api
from whatsapp.models import Template

from .permissions import unlocked
from .views import page

logger = logging.getLogger("spa99.whatsapp")
CHECK_KEY = "whatsapp_check"  # the last Check, kept in this person's session (no secrets in it)


@unlocked
@require_GET
def whatsapp_page(request):
    """Context: configured, missing (setting names), sender, webhook_urls{incoming, status}, check {ok, steps[{label, ok, detail}]} (the last Check),
    templates[{name, label, language, category, approval_status, body, synced_at, sendable}], last_synced, push_configured, devices."""
    from whatsapp.models import PushSubscription

    rows = Template.objects.order_by("name")
    context = {"configured": twilio_api.configured(), "missing": twilio_api.missing(), "sender": services.sender(), "check": request.session.get(CHECK_KEY),
               "webhook_urls": {"incoming": f"{settings.SITE_URL}/twilio/whatsapp/incoming/", "status": f"{settings.SITE_URL}/twilio/whatsapp/status/"},
               "templates": [{"name": t.name, "label": t.label, "language": t.language, "category": t.category, "approval_status": t.approval_status, "body": t.body,
                              "synced_at": t.synced_at, "sendable": t.sendable} for t in rows],
               "last_synced": max((t.synced_at for t in rows if t.synced_at), default=None), "push_configured": push.configured(), "devices": PushSubscription.objects.count()}
    return page(request, "system/whatsapp.html", "whatsapp", context)


@unlocked
@require_POST
def whatsapp_check(request):
    """Ask Twilio: does our key work and is the Spa 99 sender online? The answer is shown on the page."""
    result = services.check_twilio()
    request.session[CHECK_KEY] = result
    (messages.success if result["ok"] else messages.error)(request, "Twilio is connected and the sender is online." if result["ok"] else "The Twilio check found a problem. See below.")
    return redirect("system_whatsapp")


@unlocked
@require_POST
def whatsapp_sync(request):
    """Read the templates and their approval from Twilio (a background job)."""
    if not twilio_api.configured():
        messages.error(request, "WhatsApp is not set up yet, so there is nothing to sync.")
        return redirect("system_whatsapp")
    try:
        enqueue("whatsapp.tasks.sync_templates")
        messages.success(request, "Syncing the templates. Reload in a moment.")
    except Exception:  # noqa: BLE001
        logger.exception("Could not queue the template sync")
        messages.error(request, "The sync could not be started.")
    return redirect("system_whatsapp")
