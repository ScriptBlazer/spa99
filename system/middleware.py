from django.contrib.auth import get_user
from django.http import Http404
from django.shortcuts import redirect
from django.views.defaults import page_not_found

from . import audit, changes, services

OPEN_PATHS = ("/login/", "/health/", "/robots.txt")
# browsers ask for these on their own: still a plain 404, but never written to the audit log as an access attempt
QUIET_PATHS = ("/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png")


class SystemGateMiddleware:
    """On the System host, answer a plain 404 to anyone who may not be there BEFORE the CSRF check, so a stranger cannot
    tell real routes (403 CSRF) from unknown ones (404). The sign-in, health and robots.txt stay open (the sign-in POST
    still needs its CSRF token). A developer whose 12 hour sign-in has ended is sent to the sign-in. Must sit after
    SessionMiddleware and before CsrfViewMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(request, "urlconf", "") == "config.urls_system" and request.path not in OPEN_PATHS:
            user = get_user(request)
            if not services.may_use_system(user) or not request.session.get(services.SIGNED_IN_KEY):
                request.user = user  # for the log row (CSRF and auth middleware have not set it yet)
                if request.path not in QUIET_PATHS:
                    audit.note_access_denied(request)
                return page_not_found(request, Http404())
            if not services.sign_in_valid(request.session):
                audit.log_event(audit.SystemEvent.SESSION_EXPIRED, request, user=user, detail={"max_hours": services.session_age_seconds() // 3600})
                request.session.flush()  # the 12 hour sign-in is over: signed out, back to the sign-in
                return redirect("/login/")
        return self.get_response(request)


class AuditContextMiddleware:
    """Staff requests (Django admin included) carry their IP, browser and path into the change log: edits saved anywhere by a
    signed-in staff member are recorded with where they came from. System views start their own batch over this one.
    Must sit after AuthenticationMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_staff or changes.current_batch():
            return self.get_response(request)
        changes.start_batch(request)
        try:
            return self.get_response(request)
        finally:
            changes.end_batch()
