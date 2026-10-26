"""Who may see the Memberships page. One rule, used by the view, the nav and every link (docs/features/journey.md)."""
from journey import services as journey_services
from plans.models import SiteSettings


def _gave_email(request):
    """True when this browser's journey session holds an email (he passed the gate). One small query, cached on the request."""
    if not hasattr(request, "_spa99_gave_email"):
        session = journey_services.session_from_cookies(request.COOKIES, getattr(request, "user", None))
        request._spa99_gave_email = bool(session is not None and session.lead_email)
    return request._spa99_gave_email


def memberships_visible(request):
    """Public once `memberships_public` is on. Before that: signed-in people (we know them), team members, and anyone who
    has given his email at the journey gate in this browser. Everyone else is sent to the journey."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return True
    if SiteSettings.load().memberships_public:
        return True
    return _gave_email(request)
