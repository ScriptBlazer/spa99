"""Office access by team level (common.levels, docs/features/user-rules.md U2/U3). Superusers pass everything.
  reader     any team level (Viewer and up): sees leads, people and Gold; no action works
  editor     Office and up: Message, WhatsApp, sticky notes, the approach list, fix a lead's email, mark genuine, archive
  approver   Gold approver permission on top of Office or higher (superusers always): approve, decline, resend Gold
  final      Final approver permission on top of Admin or higher: confirm or send back a Low potential Gold approval
  approvals  Developer and up always; Office or Admin with the Membership approver permission: the Approvals page and its decisions
  calls      Office and up (above Viewer): the Calls tab, voicemail recordings
  admin      Admin and up: Revenue, Assistant chats, export, delete, payment setup
  developer  Developer and up: the Activity page
Login is enforced first by LoginRequiredMiddleware. Someone with no team level at all gets a plain 404 (U5: the staff
address never admits what is there). A team member who lacks the permission for an action gets a 403, and the
templates do not render the buttons."""
from functools import wraps

from django.contrib.auth.decorators import login_not_required  # noqa: F401 - re-exported for office views that are public
from django.core.exceptions import PermissionDenied
from django.db.models import prefetch_related_objects
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


def can_edit(user):
    """Message, WhatsApp, sticky notes, the approach list and lead fixes: Office level and up (superusers always). A Viewer gets a 403."""
    return levels.at_least(user, levels.OFFICE)


reader = _guard(lambda user: True)
editor = _guard(can_edit)
admin = _guard(lambda user: levels.at_least(user, levels.ADMIN))  # Revenue, Assistant chats, export, delete, payment setup
approver = _guard(levels.is_approver)
approvals = _guard(levels.can_approve_memberships)
calls = _guard(levels.can_hear_calls)  # Calls tab and recordings: above Viewer
final_approver = _guard(levels.is_final_approver)
developer = _guard(lambda user: levels.at_least(user, levels.DEVELOPER))  # Developer and Superuser only (Activity, Analytics > Visitors for now)


def abilities(user):
    """What the signed-in person may do, for the templates (buttons they cannot use are not rendered)."""
    if getattr(user, "pk", None) and "groups" not in getattr(user, "_prefetched_objects_cache", {}):
        prefetch_related_objects([user], "groups")  # one read of the groups for the many checks below (and the rest of the request)
    level = levels.level_of(user)
    admin_up = levels.rank(level) >= levels.rank(levels.ADMIN)
    office_up = levels.rank(level) >= levels.rank(levels.OFFICE)
    return {"can_act": levels.is_approver(user), "can_final": levels.is_final_approver(user), "can_see_all": level != levels.NONE, "can_export": admin_up, "can_delete": admin_up, "can_delete_gold": admin_up, "can_setup": admin_up,
            "can_edit": office_up, "can_outreach": office_up, "can_approvals": levels.can_approve_memberships(user), "can_revenue": admin_up, "can_chats": admin_up,
            "can_activity": levels.at_least(user, levels.DEVELOPER), "can_visitors": levels.at_least(user, levels.DEVELOPER), "can_calls": levels.can_hear_calls(user)}
