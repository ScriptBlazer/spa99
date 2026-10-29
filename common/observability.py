"""Sentry error reporting. Everything comes from env; off when SENTRY_DSN is empty.

Privacy (UK GDPR): no default PII, no cookies, no request bodies, no sensitive headers or query strings, no emails
in messages. Only the user id and an is_staff tag identify who hit an error. Server side only (no browser SDK, so
the Content-Security-Policy needs no change).

django-q: its monitor logs every failed task with logger "django-q" at ERROR ("Failed '<func>' (<name>) - <result>"),
which the logging integration turns into a Sentry event. No extra hook needed (tested in common/tests/test_sentry.py).
"""
import re
from urllib.parse import parse_qsl

import sentry_sdk
from django.conf import settings
from django.core.exceptions import DisallowedHost, PermissionDenied, RequestAborted
from django.http import Http404
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger

FILTERED = "[Filtered]"
ALLOWED_HEADERS = {"accept", "accept-language", "user-agent", "host", "content-type", "content-length"}  # allowlist: no IP, Referer, cookies
SENSITIVE_PATHS = ("/journey/", "/register/", "/gold-card/apply/", "/login/", "/dev-login/", "/unlock/")
SENSITIVE_WORDS = ("password", "token", "secret", "key", "email", "phone", "mobile", "name", "address")
IGNORED_ERRORS = [Http404, PermissionDenied, DisallowedHost, RequestAborted]
DISCONNECT_ERRORS = (ConnectionResetError, BrokenPipeError)  # ignored only when the event has a request (a client left)
SENSITIVE_KEYS = {"q", "search"}  # too short to match as words
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
HOST_BY_URLCONF = {"config.urls_office": "office", "config.urls_control": "control", "config.urls_system": "system"}


def is_sensitive_key(key):
    key = str(key).lower()
    return key in SENSITIVE_KEYS or any(word in key for word in SENSITIVE_WORDS)


def _scrub_text(value):
    return EMAIL_RE.sub(FILTERED, value) if isinstance(value, str) else value


def _scrub(value):
    """Recursively hide values under sensitive keys and any email address in strings."""
    if isinstance(value, dict):
        return {k: (FILTERED if is_sensitive_key(k) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return _scrub_text(value)


def _scrub_request(request):
    request.pop("cookies", None)
    request.pop("data", None)
    headers = request.get("headers")
    if isinstance(headers, dict):
        request["headers"] = {k: v for k, v in headers.items() if k.lower() in ALLOWED_HEADERS}
    host_and_path = request.get("url", "").split("://", 1)[-1]
    host = host_and_path.split("/", 1)[0].split(":")[0].lower()
    path = "/" + host_and_path.split("/", 1)[1] if "/" in host_and_path else "/"
    path = path.split("?", 1)[0]
    request["url"] = request.get("url", "").split("?", 1)[0]
    staff_hosts = {settings.OFFICE_HOST.lower(), settings.CONTROL_HOST.lower(), settings.SYSTEM_HOST.lower()}
    query = request.get("query_string")
    if query:
        if host in staff_hosts or path.startswith(SENSITIVE_PATHS):
            request.pop("query_string")
        elif isinstance(query, str):
            pairs = parse_qsl(query, keep_blank_values=True)
            request["query_string"] = "&".join(f"{k}={FILTERED if is_sensitive_key(k) else _scrub_text(v)}" for k, v in pairs)
        else:
            request["query_string"] = _scrub(query)
    request.pop("env", None)  # REMOTE_ADDR etc.


def _is_rate_limited(event):
    """Only our own 429 responses (the rate limiter), never an outside service's 429 in a message."""
    return (event.get("contexts", {}).get("response") or {}).get("status_code") == 429


def before_send(event, hint):
    """Drop noise, then remove personal data from whatever is left. Returns None to drop the event."""
    if event.get("logger") == "django.security.DisallowedHost" or _is_rate_limited(event):
        return None
    exc_info = (hint or {}).get("exc_info")
    if exc_info and issubclass(exc_info[0], DISCONNECT_ERRORS) and (event.get("request") or {}).get("url"):
        return None
    if isinstance(event.get("request"), dict):
        _scrub_request(event["request"])
    user = event.get("user") or {}
    event["user"] = {"id": user["id"]} if "id" in user else {}
    for key in ("message", "transaction"):
        if key in event:
            event[key] = _scrub_text(event[key])
    if isinstance(event.get("logentry"), dict):
        event["logentry"] = {k: _scrub(v) if k == "params" else _scrub_text(v) for k, v in event["logentry"].items()}
    for exc in (event.get("exception") or {}).get("values", []):
        exc["value"] = _scrub_text(exc.get("value"))
        for frame in (exc.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)  # backstop: include_local_variables is also off
    for span in event.get("spans") or []:
        if "data" in span:
            span["data"] = _scrub(span["data"])
    if "extra" in event:
        event["extra"] = _scrub(event["extra"])
    for crumb in (event.get("breadcrumbs") or {}).get("values", []):
        crumb["message"] = _scrub_text(crumb.get("message"))
        if "data" in crumb:
            crumb["data"] = _scrub(crumb["data"])
    tags = event.setdefault("tags", {})
    tags.setdefault("host", "worker")  # no request: a background job (django-q) or a command
    return event


def _rate(env, key):
    try:
        return max(0.0, min(1.0, float(env.get(key, "0"))))
    except ValueError:
        return 0.0


def init_sentry(env, default_environment, transport=None):
    """Start Sentry from env. Returns "on(<environment>)" or "off". `transport` is for tests."""
    dsn = env.get("SENTRY_DSN")
    if not dsn:
        return "off"
    environment = env.get("SENTRY_ENVIRONMENT", default_environment)
    ignore_logger("django.security.DisallowedHost")
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=env.get("APP_VERSION") or env.get("SENTRY_RELEASE") or "",  # "" (not None) stops the SDK running git; set at build/deploy
        send_default_pii=False,
        traces_sample_rate=_rate(env, "SENTRY_TRACES_SAMPLE_RATE"),
        profiles_sample_rate=_rate(env, "SENTRY_PROFILES_SAMPLE_RATE"),
        integrations=[DjangoIntegration(), LoggingIntegration(level=20, event_level=40)],  # INFO breadcrumbs, ERROR+ events
        ignore_errors=IGNORED_ERRORS,
        before_send=before_send,
        before_send_transaction=before_send,
        include_local_variables=False,
        transport=transport,
    )
    return f"on({environment})"


class SentryContextMiddleware:
    """Tags each request with host and staff, and sets the user id (never email or name)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if sentry_sdk.get_client().is_active():
            user = getattr(request, "user", None)
            authenticated = bool(user and user.is_authenticated)
            sentry_sdk.set_tag("host", HOST_BY_URLCONF.get(getattr(request, "urlconf", ""), "public"))
            sentry_sdk.set_tag("staff", "true" if authenticated and user.is_staff else "false")
            sentry_sdk.set_user({"id": str(user.pk)} if authenticated else None)
        return self.get_response(request)
