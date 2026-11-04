"""The Postmark inbound webhook (public site host, no sign-in, no CSRF: HTTP Basic user and password in the webhook URL are the proof). 404 until
EMAIL_INBOUND_USER and EMAIL_INBOUND_PASSWORD are both set (and the domain). Postmark retries anything but 200 up to 10 times and stops on 403, so everything we
cannot or will not store (unknown token, too big, no MessageID) answers 200 and is logged without personal data."""
import base64
import binascii
import hmac
import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services

logger = logging.getLogger("spa99.emailchat")


def authorised(header):
    scheme, _, token = (header or "").partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        user, sep, password = base64.b64decode(token.strip(), validate=True).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    if not sep:
        return False
    ok_user = hmac.compare_digest(user.encode(), settings.EMAIL_INBOUND_USER.encode())  # both always run: timing does not say which part was wrong
    ok_password = hmac.compare_digest(password.encode(), settings.EMAIL_INBOUND_PASSWORD.encode())
    return ok_user and ok_password


@login_not_required  # PUBLIC on purpose: Postmark calls it. The Basic credentials in its URL are the proof.
@csrf_exempt  # a server-to-server call has no CSRF token
@require_POST
def inbound(request):
    if not services.inbound_configured():
        raise Http404
    if not authorised(request.META.get("HTTP_AUTHORIZATION")):
        logger.warning("Inbound email refused: bad credentials")
        return HttpResponse(status=401, headers={"WWW-Authenticate": 'Basic realm="postmark"'})
    length = request.META.get("CONTENT_LENGTH") or "0"
    if not length.isdigit() or int(length) > settings.EMAILCHAT_MAX_INBOUND_BYTES:
        logger.warning("Inbound email dropped: body over the size limit")  # 200, not 413: a retry would be the same size
        return HttpResponse(status=200)
    try:
        payload = json.loads(request.read(settings.EMAILCHAT_MAX_INBOUND_BYTES + 1))  # read(), not .body: Django's 2.5 MB body check would refuse a mail with files
    except (ValueError, RecursionError):
        logger.warning("Inbound email refused: body is not JSON")
        return HttpResponse(status=400)
    if not isinstance(payload, dict):
        return HttpResponse(status=400)
    thread = services.thread_for_token(payload)
    if thread is None:
        logger.info("Inbound email for an unknown or missing reply token: not stored")
        return HttpResponse(status=200)
    if services.is_group_copy(payload):
        logger.warning("Inbound email carries the group copy header: not stored (it would loop)")
        return HttpResponse(status=200)
    if not isinstance(payload.get("MessageID"), str) or not payload["MessageID"].strip():
        logger.warning("Inbound email without a MessageID: not stored")
        return HttpResponse(status=200)
    message, created = services.record_inbound(payload, thread)
    if not created and not message.incomplete:
        return HttpResponse(status=200)  # Postmark sent it again and it is already whole
    if not created and not services.claim_inbound(message):
        return HttpResponse(status=500)  # an earlier attempt may still be working on it: Postmark tries again later
    try:
        services.finish_inbound(message, payload, resumed=not created)
    except services.StoreError:  # noqa: BLE001 - the files could not be stored: take the email back out so Postmark's retry stores it whole
        logger.exception("Inbound email files could not be stored")
        services.erase_message(message)
        return HttpResponse(status=500)
    except Exception:  # noqa: BLE001 - stored, but the worker task could not be queued: it stays incomplete and the retry finishes it
        logger.exception("Could not queue the email chat follow-up for message %s", message.pk)
        return HttpResponse(status=500)
    return HttpResponse(status=200)
