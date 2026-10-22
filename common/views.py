import logging

from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

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
