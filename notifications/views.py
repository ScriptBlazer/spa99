import logging

from django.contrib.auth.decorators import login_not_required
from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from common.ratelimit import rate_limited_json

from . import postmark, sns

logger = logging.getLogger("spa99.email")


@login_not_required  # PUBLIC on purpose: Amazon SNS calls it. It trusts only messages signed by Amazon for our one topic.
@csrf_exempt  # a server-to-server call has no CSRF token; the signature is the proof instead
@require_POST
def ses_notifications(request):
    """SES bounce and complaint feedback via SNS. 404 when SES_SNS_TOPIC_ARN is empty (off by default)."""
    if not settings.SES_SNS_TOPIC_ARN:
        raise Http404
    length = request.META.get("CONTENT_LENGTH") or "0"
    if not length.isdigit() or int(length) > sns.MAX_BODY_BYTES:
        return HttpResponse(status=413)
    try:
        sns.handle(request.body)
    except sns.Malformed as error:
        logger.warning("SES feedback refused: %s", error)
        return HttpResponse(status=400)
    except sns.Rejected as error:
        logger.warning("SES feedback refused: %s", error)
        return HttpResponse(status=403)
    return HttpResponse(status=200)


@login_not_required  # PUBLIC on purpose: Postmark calls it. HTTP Basic credentials from the webhook URL are the proof.
@csrf_exempt  # a server-to-server call has no CSRF token
@require_POST
@rate_limited_json("postmark-webhook", 300, 60)
def postmark_webhook(request):
    """Postmark bounce and spam-complaint feedback. 404 unless POSTMARK_WEBHOOK_USER and _PASSWORD are both set.
    Valid records we ignore (soft bounces, other types) still answer 200, because Postmark retries anything else."""
    if not postmark.configured():
        raise Http404
    if not postmark.authorised(request.META.get("HTTP_AUTHORIZATION")):
        logger.warning("Postmark feedback refused: bad credentials")
        return HttpResponse(status=401, headers={"WWW-Authenticate": 'Basic realm="postmark"'})
    length = request.META.get("CONTENT_LENGTH") or "0"
    if not length.isdigit() or int(length) > postmark.MAX_BODY_BYTES:
        return HttpResponse(status=413)
    try:
        postmark.handle(request.body)
    except ValueError as error:
        logger.warning("Postmark feedback refused: %s", error)
        return HttpResponse(status=400)
    return HttpResponse(status=200)
