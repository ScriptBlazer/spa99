from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import sales


@login_not_required  # PUBLIC on purpose: opened from a signed, single-use preview link; only a POST (CSRF checked) spends it.
@require_POST
def preview_start(request):
    sales.start_preview(request, request.POST.get("token", ""))
    target = request.POST.get("next", "/")
    return redirect(target if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}) and target.startswith("/") else "/")
