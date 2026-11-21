"""Twilio's webhooks, on the public site host. POST only, CSRF exempt (a server calls them), the X-Twilio-Signature is the proof. Off (blank Twilio
settings) = 503, so Twilio uses the number's fallback URL. A bad signature is 403 and leaves no row. Short views: the logic is in phone.services."""
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from common.audit import client_ip
from common.ratelimit import hit

from . import services, signature, twiml

logger = logging.getLogger("spa99.phone")
RATE_LIMIT, RATE_WINDOW = 300, 60  # signed requests a minute, all of Twilio together (a normal day is a handful)


def twilio_webhook(view):
    """The checks every webhook shares, in order: feature on (503), signature (403), our own Twilio account only (403), rate limit (429)."""
    @login_not_required
    @csrf_exempt
    @require_POST
    @never_cache
    def wrapper(request):
        if not services.enabled():
            return HttpResponse(status=503)
        if not signature.valid(request):
            logger.error("Twilio webhook %s refused: bad signature (ip %s). If real calls fail, the Twilio URL and SITE_URL no longer match.", request.path, client_ip(request))
            return HttpResponse(status=403)
        if request.POST.get("AccountSid", "") != settings.TWILIO_ACCOUNT_SID:  # Twilio always sends it; a missing or other account is refused
            logger.warning("Twilio webhook %s refused: another account", request.path)
            return HttpResponse(status=403)
        if not hit("phone-webhook", "twilio", RATE_LIMIT, RATE_WINDOW):
            return HttpResponse(status=429)
        return view(request)
    wrapper.__name__ = view.__name__
    return wrapper


@twilio_webhook
def voice(request):
    """A call comes in: note it, then greet and record."""
    services.start_call(request.POST.get("CallSid", ""), request.POST.get("From", ""), request.POST.get("To", ""))
    return twiml.voice()


@twilio_webhook
def after_record(request):
    """The caller finished or hung up: say goodbye and hang up. Never records again, never redirects."""
    return twiml.after_record()


@twilio_webhook
def recording(request):
    """recordingStatusCallback: completed or absent. Queue the download and the email once, answer 204 at once."""
    post = request.POST
    call = services.record_callback(post.get("CallSid", ""), post.get("RecordingSid", ""), post.get("RecordingStatus", ""), post.get("RecordingDuration", "0"))
    if call is not None:
        try:
            from common.tasks import enqueue

            enqueue("phone.tasks.process", str(call.pk))
        except Exception:  # noqa: BLE001 - the sweep picks it up within five minutes
            logger.exception("Could not queue voicemail %s", call.pk)
    return HttpResponse(status=204)
