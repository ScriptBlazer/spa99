"""Office sign-ins in the System audit log (Security). Office has no log of its own for these: the LoginEvent rows are
only in the Django admin. Only requests on the Office host count; System writes its own sign-in rows, and the public
site (members) is left out on purpose. Failed tries: one row per IP and typed email per minute, and at most 200 an hour in all, so the hidden admin sign-in
(which has no wrong-try limit of its own) cannot flood the log. Admin sign-ins show as Office sign-ins; `path` tells them apart."""
from django.contrib.auth.signals import user_logged_in, user_login_failed

OFFICE_URLCONF = "config.urls_office"


def _on_office(request):
    return request is not None and getattr(request, "urlconf", "") == OFFICE_URLCONF


def on_login(sender, request, user, **kwargs):
    if not _on_office(request):
        return
    from . import audit
    from .models import SystemEvent

    audit.log_event(SystemEvent.SIGN_IN, request, user=user, detail={"site": "office"},
                    sentence=f"{user.email} signed in to Office")


def on_login_failed(sender, credentials, request=None, **kwargs):
    if not _on_office(request):
        return
    from common.ratelimit import hit

    from . import audit
    from .models import SystemEvent

    email = str(credentials.get("email") or credentials.get("username") or "").strip().lower()[:254]
    ip = (audit.client_ip(request) or "")[:45]
    if audit.recent_exists(SystemEvent.SIGN_IN_FAILED, ip, email, 60):  # first: a repeat must not spend the shared budget
        return
    if not hit("office-signin-failed-total", "all", 200, 3600):
        return
    audit.log_event(SystemEvent.SIGN_IN_FAILED, request, email=email, detail={"site": "office", "reason": "wrong email or password"},
                    sentence=f"Office sign-in failed for {email or 'an unknown email'}")


def connect():
    user_logged_in.connect(on_login, dispatch_uid="system_office_sign_in")
    user_login_failed.connect(on_login_failed, dispatch_uid="system_office_sign_in_failed")
