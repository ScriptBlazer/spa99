import logging

from django.contrib.auth.decorators import login_not_required
from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import sns

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
    except sns.Rejected as error:
        logger.warning("SES feedback refused: %s", error)
        return HttpResponse(status=403)
    return HttpResponse(status=200)
