"""The two Twilio webhooks (public site host, no sign-in, no CSRF: the X-Twilio-Signature is the proof) and the signed media link.
Both webhooks answer an empty TwiML <Response/> quickly; the work that takes time (his file, the push) is a background job.
They are 404 until WhatsApp is configured, and accept only messages for the Spa 99 sender (BML shares the Twilio account)."""
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from common.tasks import enqueue

from . import services, signature, twilio_api

logger = logging.getLogger("spa99.whatsapp")
TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'
MAX_BODY_BYTES = 64 * 1024


def _empty():
    return HttpResponse(TWIML, content_type="text/xml")


def _checked(request):
    """404 when not configured, 413 for a huge body, 403 for a bad signature; else None."""
    if not twilio_api.configured():
        raise Http404
    length = request.META.get("CONTENT_LENGTH") or "0"
    if not length.isdigit() or int(length) > MAX_BODY_BYTES:
        return HttpResponse(status=413)
    if not signature.valid(request):
        logger.warning("WhatsApp webhook refused: bad signature")
        return HttpResponse(status=403)
    return None


@login_not_required  # PUBLIC on purpose: Twilio calls it. The signature is the proof.
@csrf_exempt  # a server-to-server call has no CSRF token
@require_POST
def incoming(request):
    """A message from him. Idempotent on MessageSid."""
    refused = _checked(request)
    if refused:
        return refused
    params = request.POST.dict()
    if services.to_e164(params.get("To", "")) != services.sender():  # not for Spa 99 (the account also holds BML)
        return _empty()
    if not services.to_e164(params.get("From", "")) or not params.get("MessageSid"):
        return _empty()
    message, created = services.record_inbound(params)
    if created:
        try:
            enqueue("whatsapp.tasks.process_inbound", message.pk)
        except Exception:  # noqa: BLE001 - the message is stored; only the file copy and the push are lost
            logger.exception("Could not queue the WhatsApp follow-up for message %s", message.pk)
    return _empty()


@login_not_required  # PUBLIC on purpose: Twilio calls it. The signature is the proof.
@csrf_exempt
@require_POST
def status(request):
    """A delivery tick for a message we sent."""
    refused = _checked(request)
    if refused:
        return refused
    if services.to_e164(request.POST.get("From", "")) == services.sender():
        services.apply_status(request.POST.dict())
    return _empty()


@login_not_required  # PUBLIC on purpose: Twilio fetches the file we are sending. The link is signed and expires in an hour.
@require_GET
def media(request, token):
    message = services.message_for_media_token(token)
    if message is None or not default_storage.exists(message.media_key):
        raise Http404
    response = FileResponse(default_storage.open(message.media_key, "rb"), content_type=message.media_type or "application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
