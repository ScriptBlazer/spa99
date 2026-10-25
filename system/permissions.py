"""System access. Three steps: be allowed (Developer level or superuser, signed in on THIS host within 12 hours),
be unlocked (password asked again, 15 idle minutes), then the view. Anyone not allowed gets a plain 404, anonymous
included (system.middleware does the same check before CSRF)."""
from functools import wraps
from urllib.parse import urlencode, urlsplit

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.http import Http404
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from . import audit, changes, services

SECTIONS = {"plans", "hours", "gold", "journey", "emails", "settings", "team", "approval", "changes", "suppressions"}


def gate(request):
    """None when the person may be here; a redirect to sign-in when their 12 hour System sign-in has ended; else 404."""
    if not services.may_use_system(request.user) or not request.session.get(services.SIGNED_IN_KEY):
        audit.note_access_denied(request)
        raise Http404
    if not services.sign_in_valid(request.session):
        audit.log_event(audit.SystemEvent.SESSION_EXPIRED, request, user=request.user, detail={"max_hours": services.session_age_seconds() // 3600})
        logout(request)
        return redirect("/login/")
    return None


def unlock_target(request):
    """Where to come back to after unlocking: this page for a GET; for a POST (which a page cannot be opened with) the
    page it came from if the Referer is on this host, else its section page."""
    if request.method in ("GET", "HEAD"):
        return request.get_full_path()
    referer = request.META.get("HTTP_REFERER", "")
    if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        parts = urlsplit(referer)
        return parts.path + (f"?{parts.query}" if parts.query else "")
    first = request.path.strip("/").split("/")[0]
    return f"/{first}/" if first in SECTIONS else "/"


def signed_in(view):
    """Allowed, but not necessarily unlocked (the unlock page and Lock)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        refused = gate(request)
        if refused:
            return refused
        return view(request, *args, **kwargs)
    # System answers 404 itself, so the host never shows a sign-in redirect to strangers
    return login_not_required(wrapper)


def unlocked(view):
    """Allowed and unlocked; every request slides the 15 minute window."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        refused = gate(request)
        if refused:
            return refused
        if not services.is_unlocked(request.session):
            services.note_idle_lock(request)
            return redirect(f"/unlock/?{urlencode({'next': unlock_target(request)})}")
        services.unlock(request.session)
        changes.start_batch(request)  # changes saved by this request are grouped
        try:
            return view(request, *args, **kwargs)
        finally:
            changes.end_batch()
    return login_not_required(wrapper)
