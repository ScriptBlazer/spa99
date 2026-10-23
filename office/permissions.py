"""Office roles (Django Groups from `setup_roles`; superusers always pass). Everyone in READERS can look at everything;
only WRITERS can act (approve, decline, resend, export); only Owners can delete a person. Login is enforced first by
LoginRequiredMiddleware. A Viewer is refused (403) on any action, and the templates do not render the buttons."""
from django.contrib.auth.decorators import login_not_required  # noqa: F401 - re-exported for office views that are public

from common.permissions import group_required

READERS = ("Owner", "Manager", "Viewer")
WRITERS = ("Owner", "Manager")
OWNERS = ("Owner",)

reader = group_required(*READERS)
writer = group_required(*WRITERS)
owner = group_required(*OWNERS)


def role_names(user):
    """The Office roles this person holds, from one query."""
    return set(user.groups.filter(name__in=READERS).values_list("name", flat=True))


def abilities(user, roles=None):
    """What the signed-in person may do, for the templates (hide buttons a Viewer cannot use)."""
    roles = role_names(user) if roles is None else roles
    everything = user.is_authenticated and user.is_superuser
    return {
        "can_act": everything or bool(roles & set(WRITERS)),
        "can_export": everything or bool(roles & set(WRITERS)),
        "can_delete": everything or bool(roles & set(OWNERS)),
    }
