"""Office access by team level (common.levels, docs/features/user-rules.md U2/U3). Superusers pass everything.
  reader    any team level (Office and up): sees everything, view only
  approver  approve, decline, resend Gold: the Approver permission on top of a level (superusers always)
  admin     Admin and up: export members, delete a member
Login is enforced first by LoginRequiredMiddleware. A refused action is a 403 and the templates do not render the buttons."""
from functools import wraps

from django.contrib.auth.decorators import login_not_required  # noqa: F401 - re-exported for office views that are public
from django.core.exceptions import PermissionDenied

from common import levels
from common.permissions import level_required

reader = level_required(levels.OFFICE)
admin = level_required(levels.ADMIN)


def approver(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not levels.is_approver(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def abilities(user):
    """What the signed-in person may do, for the templates (buttons they cannot use are not rendered)."""
    level = levels.level_of(user)
    admin_up = levels.rank(level) >= levels.rank(levels.ADMIN)
    return {"can_act": levels.is_approver(user), "can_see_all": level != levels.NONE, "can_export": admin_up, "can_delete": admin_up}
