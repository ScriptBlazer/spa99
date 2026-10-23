from django.http import Http404, HttpResponse

from common import levels
from common.permissions import level_required


@level_required(levels.ADMIN, deny=Http404)  # Admin and up; anyone else gets a plain 404 (login enforced by LoginRequiredMiddleware)
def control_index(request):
    """Placeholder until the control app is built."""
    return HttpResponse("Spa 99 Control", content_type="text/plain")
