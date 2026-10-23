"""System access. Three steps: be allowed (superuser or System group, staff, signed in on THIS host), be unlocked
(password asked again, 15 idle minutes), then the view. Anyone not allowed gets a plain 404, anonymous included."""
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_not_required
from django.http import Http404
from django.shortcuts import redirect

from . import changes, services


def _allowed(request):
    return services.may_use_system(request.user) and request.session.get(services.SIGNED_IN_KEY)


def signed_in(view):
    """Allowed, but not necessarily unlocked (the unlock page and Lock)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not _allowed(request):
            raise Http404
        return view(request, *args, **kwargs)
    # System answers 404 itself, so the host never shows a sign-in redirect to strangers
    return login_not_required(wrapper)


def unlocked(view):
    """Allowed and unlocked; every request slides the 15 minute window."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not _allowed(request):
            raise Http404
        if not services.is_unlocked(request.session):
            return redirect(f"/unlock/?{urlencode({'next': request.get_full_path()})}")
        services.unlock(request.session)
        changes.start_batch()  # changes saved by this request are grouped
        try:
            return view(request, *args, **kwargs)
        finally:
            changes.end_batch()
    return login_not_required(wrapper)
