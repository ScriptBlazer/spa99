"""Who may see the Memberships page. One rule, used by the view, the nav and every link (docs/features/journey.md)."""
from plans.models import SiteSettings


def memberships_visible(request):
    """Public once `memberships_public` is on; before that only signed-in team members (is_staff) can open it."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return True
    return SiteSettings.load().memberships_public
