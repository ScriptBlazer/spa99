"""Statistics endpoint for the Control dashboard. Staff only (roles are Django Groups)."""
from datetime import date

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from office.permissions import reader

from . import services

READERS = ("Owner", "Manager", "Viewer")  # superusers always pass


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return False


@require_GET
@reader  # login enforced by LoginRequiredMiddleware; then role check
def summary(request):
    """GET ?from=YYYY-MM-DD&to=YYYY-MM-DD&source=instagram&completed=yes|no  ->  all statistics cards as JSON."""
    date_from, date_to = _date(request.GET.get("from")), _date(request.GET.get("to"))
    if date_from is False or date_to is False:
        return JsonResponse({"error": "Dates must look like 2026-10-22."}, status=400)
    completed = {"yes": True, "no": False}.get(request.GET.get("completed", ""))
    data = services.summary(date_from, date_to, source=request.GET.get("source") or None, completed=completed)
    return JsonResponse(data)
