"""Permission helpers. Views are locked by default (LoginRequiredMiddleware); public views use @login_not_required with
a comment saying why. Who may do what comes from the team levels in common.levels; never check group names or emails."""
from functools import wraps

from django.core.exceptions import PermissionDenied

from . import levels


def level_required(level, deny=PermissionDenied):
    """View decorator: signed in, active and at this team level or above. `deny` is the exception raised otherwise:
    PermissionDenied (403) by default; pass Http404 for hosts that never admit what is there."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not levels.at_least(request.user, level):
                raise deny
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
