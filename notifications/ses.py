"""The SES production gate. Group sends and invites only start when Amazon SES has production access (a sandbox account can
only write to verified addresses, so a real send would bounce and hurt the sender reputation).

`ses_status()` reads the account once an hour (boto3 sesv2 get_account), caches it and never raises.

The gate follows EMAIL_BACKEND, not DEBUG: only notifications.backends.SesBackend is gated on SES. A console/in-memory/file backend is
mode "dev" (allowed; printed or kept). Any other backend (SMTP through Postmark, say) is mode "provider": allowed, emails really go out
through EMAIL_HOST, and no Amazon numbers are read or shown."""
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("spa99.email")

CACHE_KEY = "notifications:ses-status"
CACHE_SECONDS = 3600
UNKNOWN_CACHE_SECONDS = 120  # a failed read is retried soon, not hammered
PRODUCTION, SANDBOX, DEV, UNKNOWN, PROVIDER = "production", "sandbox", "dev", "unknown", "provider"
SES_BACKEND = "notifications.backends.SesBackend"
DEV_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend", "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend", "django.core.mail.backends.dummy.EmailBackend",
}
MESSAGES = {
    SANDBOX: "Amazon SES is still in sandbox, so group sends and invites stay off until AWS approves production access.",
    UNKNOWN: "Could not read the Amazon SES account state, so group sends and invites stay off until it can be read. Try again in a minute.",
}


class SendingRefused(Exception):
    """Group sends and invites may not start (the message says why, in plain words)."""


def is_dev():
    return settings.EMAIL_BACKEND in DEV_BACKENDS


def is_ses():
    return settings.EMAIL_BACKEND == SES_BACKEND


def backend_problem():
    """'' when EMAIL_BACKEND is the SES backend, a dev backend, or a real importable other backend (SMTP). Otherwise plain words: a path
    that mentions SES but is not the SES backend is a typo (counting it as "another provider" would skip the SES gate), and a path that
    cannot be imported would fail on every send. Both refuse group sends (mode unknown) until fixed."""
    backend = settings.EMAIL_BACKEND
    if backend == SES_BACKEND or backend in DEV_BACKENDS:
        return ""
    if "ses" in backend.lower():
        return f"EMAIL_BACKEND looks like a mistyped Amazon SES path. It should be {SES_BACKEND}, so group sends and invites stay off."
    from django.utils.module_loading import import_string

    try:
        import_string(backend)
    except ImportError:
        return "EMAIL_BACKEND cannot be loaded, so group sends and invites stay off until it is fixed."
    return ""


def provider_warning():
    host = (getattr(settings, "EMAIL_HOST", "") or "").strip().lower()
    if host in ("", "localhost", "127.0.0.1"):
        return "Email settings look incomplete: EMAIL_HOST is not set to your provider's server."
    return ""


def provider_name():
    """Postmark when the SMTP host is Postmark's, else the host itself (never the user name or password)."""
    host = (getattr(settings, "EMAIL_HOST", "") or "").strip()
    if "postmarkapp" in host.lower():
        return "Postmark"
    return host or "another provider"


def provider_message():
    """The small, calm line when a provider other than SES sends: 'Sending through Postmark ✓' (or the host)."""
    return f"Sending through {provider_name()} \u2713"


def through_label():
    """Who delivers the mail, for the send pop-up: Postmark, the host, Amazon SES, or the development printout."""
    if is_ses():
        return "Amazon SES"
    if is_dev():
        return "Development (printed in the server log, not sent)"
    return provider_name()


def _blank(mode):
    return {"mode": mode, "max_24h": None, "sent_24h": None, "max_rate": None}


def _read():
    import boto3

    client = boto3.client("sesv2", region_name=getattr(settings, "AWS_SES_REGION_NAME", "eu-west-2"))
    account = client.get_account()
    quota = account.get("SendQuota") or {}
    return {
        "mode": PRODUCTION if account.get("ProductionAccessEnabled") else SANDBOX,
        "max_24h": quota.get("Max24HourSend"), "sent_24h": quota.get("SentLast24Hours"), "max_rate": quota.get("MaxSendRate"),
    }


def ses_status(refresh=False):
    """{mode: production|sandbox|dev|unknown, max_24h, sent_24h, max_rate, allowed, message}. Cached an hour; `refresh=True` reads again."""
    problem = backend_problem()
    if problem:
        status = _blank(UNKNOWN)
    elif is_dev():
        status = _blank(DEV)
    elif not is_ses():
        status = _blank(PROVIDER)
    else:
        status = None
        if not refresh:
            try:
                status = cache.get(CACHE_KEY)
            except Exception:  # noqa: BLE001 - a broken cache must not break the page
                status = None
        if status is None:
            try:
                status = _read()
                seconds = CACHE_SECONDS
            except Exception as error:  # noqa: BLE001 - never raise: unknown means "do not send"
                logger.error("Could not read the SES account state (%s)", type(error).__name__)
                status, seconds = _blank(UNKNOWN), UNKNOWN_CACHE_SECONDS
            try:
                cache.set(CACHE_KEY, status, seconds)
            except Exception:  # noqa: BLE001
                pass
    status = dict(status)
    status["allowed"] = status["mode"] in (PRODUCTION, DEV, PROVIDER)
    status["message"] = "" if status["allowed"] else (problem or MESSAGES[status["mode"]])
    status["problem"] = problem
    status["provider"] = provider_message() if status["mode"] == PROVIDER else ""
    status["warning"] = provider_warning() if status["mode"] == PROVIDER else ""
    return status


def require_sending_allowed():
    """Raise SendingRefused (with the plain message) unless SES is in production (or this is development). Returns the status."""
    status = ses_status()
    if not status["allowed"]:
        raise SendingRefused(status["message"])
    return status
