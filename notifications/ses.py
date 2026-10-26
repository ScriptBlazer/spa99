"""The SES production gate. Group sends and invites only start when Amazon SES has production access (a sandbox account can
only write to verified addresses, so a real send would bounce and hurt the sender reputation).

`ses_status()` reads the account once an hour (boto3 sesv2 get_account), caches it and never raises. In development (DEBUG or a
console/in-memory mail backend) the mode is "dev": allowed, the emails are printed or kept in memory."""
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("spa99.email")

CACHE_KEY = "notifications:ses-status"
CACHE_SECONDS = 3600
UNKNOWN_CACHE_SECONDS = 120  # a failed read is retried soon, not hammered
PRODUCTION, SANDBOX, DEV, UNKNOWN = "production", "sandbox", "dev", "unknown"
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
    return bool(settings.DEBUG) or settings.EMAIL_BACKEND in DEV_BACKENDS


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
    if is_dev():
        status = _blank(DEV)
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
    status["allowed"] = status["mode"] in (PRODUCTION, DEV)
    status["message"] = "" if status["allowed"] else MESSAGES[status["mode"]]
    return status


def require_sending_allowed():
    """Raise SendingRefused (with the plain message) unless SES is in production (or this is development). Returns the status."""
    status = ses_status()
    if not status["allowed"]:
        raise SendingRefused(status["message"])
    return status
