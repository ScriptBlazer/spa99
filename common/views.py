import logging

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .ratelimit import rate_limited_json
from .validators import normalise_uk_mobile

logger = logging.getLogger("spa99.health")


@login_not_required  # PUBLIC on purpose: uptime monitor and the container health check call it without a login.
@never_cache
def health(request):
    """200 {"status": "ok"} when the database answers, 503 otherwise. Reveals nothing else."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check: database did not answer")
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


@login_not_required  # PUBLIC on purpose: live mobile check on the sign-up and Gold forms; stores nothing, rate limited.
# POST (with the CSRF token) so the number never appears in a URL or an access log
@require_POST
@rate_limited_json("check-mobile", 30, 60)
def check_mobile(request):
    """Is this a UK mobile number the server would accept? The browser asks (debounced) so it never disagrees with
    common.validators.normalise_uk_mobile. {"valid": true} or {"valid": false, "message": "..."}."""
    try:
        normalise_uk_mobile(request.POST.get("mobile", ""))
    except ValidationError as error:
        return JsonResponse({"valid": False, "message": error.messages[0]})
    return JsonResponse({"valid": True})


def csrf_failure(request, reason=""):
    """Friendly page when a form's security token is missing or expired (e.g. a stale tab)."""
    return render(request, "403.html", status=403)
