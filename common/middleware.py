from django.contrib.auth.middleware import LoginRequiredMiddleware as _DjangoLoginRequired
from django.http import JsonResponse
from django.conf import settings


class HostRoutingMiddleware:
    """Serve each Spa 99 site on its own host.

    OFFICE_HOST uses config.urls_office (the business back office), CONTROL_HOST uses config.urls_control (the
    building control room, parked), SYSTEM_HOST uses config.urls_system (developers only); everything else uses config.urls. Sessions are per host, so a login on one host
    never logs you into another. The three staff hosts are never indexed (X-Robots-Tag).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()  # raises DisallowedHost for unknown hosts
        staff_host = True
        if host == settings.OFFICE_HOST.lower():
            request.urlconf = "config.urls_office"
        elif host == settings.SYSTEM_HOST.lower():
            request.urlconf = "config.urls_system"
        elif host == settings.CONTROL_HOST.lower():
            request.urlconf = "config.urls_control"
        else:
            request.urlconf, staff_host = "config.urls", False
        response = self.get_response(request)
        if staff_host:
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response


class LoginRequiredMiddleware(_DjangoLoginRequired):
    """Django's login lock, except that a background request (fetch asking for JSON, or `X-Requested-With: fetch`) gets a
    401 JSON answer instead of a redirect to the sign-in page. A fetch follows redirects, so a redirect would come back as
    a 200 sign-in page and the script would wrongly say "Saved." after the session had ended."""

    def handle_no_permission(self, request, view_func):
        wants_json = "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "fetch"
        if wants_json:
            return JsonResponse({"ok": False, "signed_out": True, "message": "You've been signed out. Please sign in again."}, status=401)
        return super().handle_no_permission(request, view_func)
