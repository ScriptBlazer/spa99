from django.contrib.auth import get_user
from django.http import Http404
from django.shortcuts import redirect
from django.views.defaults import page_not_found

from . import services

OPEN_PATHS = ("/login/", "/health/", "/robots.txt")


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
                return page_not_found(request, Http404())
            if not services.sign_in_valid(request.session):
                request.session.flush()  # the 12 hour sign-in is over: signed out, back to the sign-in
                return redirect("/login/")
        return self.get_response(request)
