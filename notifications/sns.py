"""Amazon SNS messages for SES bounce and complaint feedback.

Flow: SES publishes to the SNS topic, SNS POSTs to /ses/notifications/. We trust a message only when
  1. its TopicArn is exactly settings.SES_SNS_TOPIC_ARN, and
  2. its signature verifies against a certificate downloaded from https://sns.<region>.amazonaws.com/ (any other host is refused).
Then a permanent bounce or a complaint puts each address on the suppression list (notifications.suppression); the central
sender (notifications.services.send_templated) never emails a suppressed address. Transient bounces are not stored."""
import base64
import datetime
import json
import logging
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache

from . import suppression
from .models import EmailSuppression

logger = logging.getLogger("spa99.email")

SNS_HOST = re.compile(r"^sns\.(?P<region>[a-z]{2}(?:-gov)?-[a-z]+-\d)\.amazonaws\.com$")  # region-shaped only: not sns.s3.amazonaws.com
MAX_AGE = datetime.timedelta(hours=1)  # older messages are refused (replay after an address was removed)
MAX_FUTURE = datetime.timedelta(minutes=5)
MAX_BODY_BYTES = 256 * 1024  # SNS's own limit
CERT_CACHE_SECONDS = 24 * 3600

NOTIFICATION_FIELDS = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]  # Subject only when present
SUBSCRIPTION_FIELDS = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]


class Rejected(Exception):
    """The message is not acceptable; the text is for the log only."""


class Malformed(Rejected):
    """The body is not a usable SNS envelope at all (answered 400; other refusals are 403)."""


def topic_region():
    parts = (settings.SES_SNS_TOPIC_ARN or "").split(":")
    return parts[3] if len(parts) > 3 else ""


def trusted_sns_url(url, region=None):
    """True only for an https URL on sns.<region>.amazonaws.com (exact host, default port, no credentials), where the
    region is the one in our topic ARN (`region` overrides, for tests)."""
    try:
        parts = urlsplit(url or "")
        match = SNS_HOST.match(parts.hostname or "")
        return (parts.scheme == "https" and parts.username is None and parts.port in (None, 443) and bool(match)
                and match.group("region") == (region or topic_region()))
    except ValueError:
        return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _fetch(url, limit=64 * 1024):
    """GET an already-validated SNS url: no redirects, short timeout, size capped."""
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "spa99-sns"}), timeout=5) as response:
        return response.read(limit)


def signing_certificate(url):
    """The PEM bytes of the signing certificate (cached a day). Refuses a URL that is not an SNS https .pem."""
    if not trusted_sns_url(url) or not urlsplit(url).path.endswith(".pem"):
        raise Rejected("signing certificate URL is not an SNS https address")
    key = "sns-cert:" + url
    pem = cache.get(key)
    if pem is None:
        try:
            pem = _fetch(url)
        except (urllib.error.URLError, OSError) as error:
            raise Rejected(f"could not download the signing certificate ({type(error).__name__})")
        cache.set(key, pem, CERT_CACHE_SECONDS)
    return pem


def string_to_sign(message):
    kind = message.get("Type")
    if kind == "Notification":
        fields = [f for f in NOTIFICATION_FIELDS if f != "Subject" or "Subject" in message]
    elif kind in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        fields = SUBSCRIPTION_FIELDS
    else:
        raise Rejected("unknown message type")
    try:
        return "".join(f"{name}\n{message[name]}\n" for name in fields).encode()
    except KeyError as error:
        raise Rejected(f"missing field {error}")


def verify_signature(message):
    """Raise Rejected unless Amazon signed this message (SignatureVersion 1 = SHA1, 2 = SHA256)."""
    version = message.get("SignatureVersion")
    if version not in ("1", "2"):
        raise Rejected("unsupported SignatureVersion")
    pem = signing_certificate(message.get("SigningCertURL", ""))  # refuses any host but SNS before anything is downloaded
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    algorithm = hashes.SHA256 if version == "2" else hashes.SHA1  # SNS version 1 is SHA1; we only verify with it
    try:
        public_key = x509.load_pem_x509_certificate(pem).public_key()
        signature = base64.b64decode(message.get("Signature", ""), validate=True)
        public_key.verify(signature, string_to_sign(message), padding.PKCS1v15(), algorithm())
    except InvalidSignature:
        raise Rejected("signature does not match")
    except (ValueError, TypeError) as error:
        raise Rejected(f"signature could not be checked ({type(error).__name__})")


def parse(body):
    """The SNS envelope as a dict, or Rejected."""
    if len(body) > MAX_BODY_BYTES:
        raise Rejected("body too large")
    try:
        message = json.loads(body)
    except (ValueError, RecursionError):
        raise Malformed("body is not JSON")
    if not isinstance(message, dict):
        raise Malformed("body is not an object")
    return message


def check_fresh(message, now=None):
    """Refuse a message whose Timestamp is more than an hour old (or in the future): a captured one cannot be replayed."""
    try:
        sent = datetime.datetime.fromisoformat(str(message.get("Timestamp", "")))
    except ValueError:
        raise Rejected("Timestamp is not valid")
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now - sent > MAX_AGE or sent - now > MAX_FUTURE:
        raise Rejected("message is too old or from the future")


def confirm_subscription(message):
    url = message.get("SubscribeURL", "")
    if not trusted_sns_url(url):
        raise Rejected("SubscribeURL is not an SNS https address")
    try:
        _fetch(url)
    except (urllib.error.URLError, OSError) as error:
        raise Rejected(f"could not confirm the subscription ({type(error).__name__})")
    logger.info("SES feedback: SNS subscription confirmed for %s", message.get("TopicArn"))


def _addresses(entries):
    return [entry.get("emailAddress", "") for entry in entries or [] if isinstance(entry, dict)]


def apply_feedback(ses):
    """Act on one SES notification (the parsed Message). Returns how many addresses were newly suppressed or updated."""
    kind = ses.get("notificationType") or ses.get("eventType")
    mail_id = str((ses.get("mail") or {}).get("messageId", ""))
    if kind == "Bounce":
        bounce = ses.get("bounce") or {}
        if bounce.get("bounceType") != "Permanent":
            logger.debug("SES feedback: transient bounce ignored")
            return 0
        feedback_id = str(bounce.get("feedbackId") or mail_id)
        detail = f"{bounce.get('bounceSubType', '')} {_diagnostic(bounce)}".strip()
        return sum(suppression.add(a, EmailSuppression.HARD_BOUNCE, feedback_id, detail) for a in _addresses(bounce.get("bouncedRecipients")))
    if kind == "Complaint":
        complaint = ses.get("complaint") or {}
        feedback_id = str(complaint.get("feedbackId") or mail_id)
        detail = complaint.get("complaintFeedbackType") or complaint.get("complaintSubType") or ""
        return sum(suppression.add(a, EmailSuppression.COMPLAINT, feedback_id, detail) for a in _addresses(complaint.get("complainedRecipients")))
    logger.debug("SES feedback: %s ignored", kind)
    return 0


def _diagnostic(bounce):
    for entry in bounce.get("bouncedRecipients") or []:
        if isinstance(entry, dict) and entry.get("diagnosticCode"):
            return entry["diagnosticCode"]
    return ""


def handle(body):
    """Process one POST body. Raises Rejected for anything untrusted; returns a short word for the log."""
    message = parse(body)
    if message.get("TopicArn") != settings.SES_SNS_TOPIC_ARN:
        raise Rejected("wrong topic")
    check_fresh(message)
    verify_signature(message)
    kind = message["Type"]
    if kind == "SubscriptionConfirmation":
        confirm_subscription(message)
        return "confirmed"
    if kind == "Notification":
        try:
            ses = json.loads(message.get("Message", ""))
        except (ValueError, RecursionError):
            raise Rejected("Message is not JSON")
        if not isinstance(ses, dict):
            raise Rejected("Message is not an object")
        count = apply_feedback(ses)
        logger.info("SES feedback: %s handled, %d address(es) recorded", ses.get("notificationType"), count)
        return "handled"
    return "ignored"  # UnsubscribeConfirmation
