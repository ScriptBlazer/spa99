from django.http import HttpResponse

from common.permissions import staff_required


@staff_required  # login enforced by LoginRequiredMiddleware; staff only
def control_index(request):
    """Placeholder until the control app is built."""
    return HttpResponse("Spa 99 Control", content_type="text/plain")
