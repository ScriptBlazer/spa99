"""Office roles (Django Groups from `setup_roles`; superusers always pass). Everyone in READERS can look at everything;
only WRITERS can act (approve, decline, resend, export); only Owners can delete a person. Login is enforced first by
LoginRequiredMiddleware. A Viewer is refused (403) on any action, and the templates do not render the buttons."""
from django.contrib.auth.decorators import login_not_required  # noqa: F401 - re-exported for office views that are public

from common.permissions import group_required, user_in_groups

READERS = ("Owner", "Manager", "Viewer")
WRITERS = ("Owner", "Manager")
OWNERS = ("Owner",)

reader = group_required(*READERS)
writer = group_required(*WRITERS)
owner = group_required(*OWNERS)


def abilities(user):
    """What the signed-in person may do, for the templates (hide buttons a Viewer cannot use)."""
    return {
        "can_act": user_in_groups(user, *WRITERS),
        "can_export": user_in_groups(user, *WRITERS),
        "can_delete": user_in_groups(user, *OWNERS),
    }
