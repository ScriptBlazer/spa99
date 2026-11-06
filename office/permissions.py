"""Office access by team level (common.levels, docs/features/user-rules.md U2/U3). Superusers pass everything.
  reader    any team level (Office and up): sees everything, view only
  approver  approve, decline, resend Gold: the Approver permission on top of a level (superusers always)
  final     confirm or send back a Low potential Gold approval: the Final approver permission on top of Admin level or higher
  editor    approver or Admin and up: sticky notes, the approach list, Message
  admin     Admin and up: export members, delete a member
Login is enforced first by LoginRequiredMiddleware. Someone with no team level at all gets a plain 404 (U5: the staff
address never admits what is there). A team member who lacks the permission for an action gets a 403, and the
templates do not render the buttons."""
from functools import wraps

from django.contrib.auth.decorators import login_not_required  # noqa: F401 - re-exported for office views that are public
from django.core.exceptions import PermissionDenied
from django.http import Http404

from common import levels


def _guard(allowed):
    """View decorator: no level -> 404; a level without `allowed(user)` -> 403."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if levels.level_of(request.user) == levels.NONE:
                raise Http404
            if not allowed(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


reader = _guard(lambda user: True)
admin = _guard(lambda user: levels.at_least(user, levels.ADMIN))
approver = _guard(levels.is_approver)
final_approver = _guard(levels.is_final_approver)


def can_edit(user):
    """Sticky notes, the approach list and Message: the Approver permission (the same people who could add Gold notes) or Admin
    level and up. Superusers always. View-only team members get a 403."""
    return levels.is_approver(user) or levels.at_least(user, levels.ADMIN)


editor = _guard(can_edit)


def abilities(user):
    """What the signed-in person may do, for the templates (buttons they cannot use are not rendered)."""
    level = levels.level_of(user)
    admin_up = levels.rank(level) >= levels.rank(levels.ADMIN)
    approves = levels.is_approver(user)
    return {"can_act": approves, "can_final": levels.is_final_approver(user), "can_see_all": level != levels.NONE, "can_export": admin_up, "can_delete": admin_up, "can_delete_gold": admin_up, "can_setup": admin_up, "can_edit": approves or admin_up, "can_outreach": level != levels.NONE,
            "can_approvals": approves or admin_up, "can_revenue": approves or admin_up}  # Barry's view: Approvals and Revenue, their tabs and the Home cards
