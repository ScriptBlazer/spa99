"""Office roles (Django Groups from `setup_roles`; superusers always pass). Everyone in READERS can look at everything;
only WRITERS can act (approve, decline, resend, export); only Owners can delete a person. Login is enforced first by
LoginRequiredMiddleware. A Viewer is refused (403) on any action, and the templates do not render the buttons."""
from django.contrib.auth.decorators import login_not_required  # noqa: F401 - re-exported for office views that are public

from functools import wraps

from django.core.exceptions import PermissionDenied

from common.permissions import staff_in_groups

READERS = ("Owner", "Manager", "Viewer")
WRITERS = ("Owner", "Manager")
OWNERS = ("Owner",)
APPROVER = "Approver"  # Gold only: may look at and decide Gold applications, sees nothing else (no People, export or delete)
GOLD_READERS = READERS + (APPROVER,)
GOLD_WRITERS = WRITERS + (APPROVER,)

def _role(*groups):
    """View decorator: signed in, is_staff AND in one of the groups (superusers are staff too). A member account in a
    role group is refused."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not staff_in_groups(request.user, *groups):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


reader = _role(*READERS)
writer = _role(*WRITERS)
owner = _role(*OWNERS)
gold_reader = _role(*GOLD_READERS)
gold_writer = _role(*GOLD_WRITERS)


def role_names(user):
    """The Office roles this person holds, from one query."""
    return set(user.groups.filter(name__in=GOLD_READERS).values_list("name", flat=True))


def abilities(user, roles=None):
    """What the signed-in person may do, for the templates (hide buttons a Viewer cannot use)."""
    roles = role_names(user) if roles is None else roles
    everything = user.is_authenticated and user.is_staff and user.is_superuser
    return {
        "can_act": everything or user.is_staff and bool(roles & set(GOLD_WRITERS)),
        "can_see_all": everything or user.is_staff and bool(roles & set(READERS)),
        "can_export": everything or user.is_staff and bool(roles & set(WRITERS)),
        "can_delete": everything or user.is_staff and bool(roles & set(OWNERS)),
    }
