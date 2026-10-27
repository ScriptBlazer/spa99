"""Who may see the Memberships page. One rule, used by the view, the nav and every link (docs/features/journey.md)."""
from journey import services as journey_services
from journey.models import JourneySession
from plans.models import SiteSettings


def _gave_email(request, site):
    """True when this browser's journey session holds an email (he passed the gate). One small query, cached on the request."""
    if not hasattr(request, "_spa99_gave_email"):
        session = journey_services.session_from_cookies(request.COOKIES, getattr(request, "user", None))
        # gate on: he gave his email. Gate off: he reached the result (nothing was asked, so nothing else can be required)
        if session is None:
            reached = False
        elif site.journey_email_gate:
            reached = bool(session.lead_email)
        else:  # any finished journey by this person in this browser (a plain restart carries the person_key, "Not you?" does not)
            reached = session.completed or bool(session.person_key and JourneySession.objects.filter(
                person_key=session.person_key, completed=True).exists())
        request._spa99_gave_email = reached
    return request._spa99_gave_email


def memberships_visible(request):
    """Public once `memberships_public` is on. Before that: signed-in people (we know them), team members, and anyone who
    has given his email at the journey gate in this browser. Everyone else is sent to the journey."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return True
    site = SiteSettings.load()  # once per request
    if site.memberships_public:
        return True
    return _gave_email(request, site)
