"""Twilio over plain HTTPS with httpx2 (already in the project through the Anthropic SDK; no Twilio SDK needed). Sending and fetching
use the API key (revocable without touching BML); the Auth Token is only for the webhook signature. Nothing here logs a secret.
Tests replace `request` / `fetch_media`; no test calls Twilio."""
import logging

import httpx2
from django.conf import settings

logger = logging.getLogger("spa99.whatsapp")

API = "https://api.twilio.com/2010-04-01"
CONTENT = "https://content.twilio.com/v1"
SENDERS = "https://messaging.twilio.com/v2/Channels/Senders"
TIMEOUT = httpx2.Timeout(20.0, connect=10.0)


class TwilioError(Exception):
    """Twilio refused or could not be reached. `code` is Twilio's error code ('' when none), `status` the HTTP status (None = no answer)."""

    def __init__(self, message, code="", status=None):
        super().__init__(message)
        self.code, self.status = str(code or ""), status


def configured():
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_API_KEY_SID and settings.TWILIO_API_KEY_SECRET
                and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM)


def missing():
    """Names (never values) of the settings still empty."""
    names = ("TWILIO_ACCOUNT_SID", "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM")
    return [n for n in names if not getattr(settings, n)]


def _auth():
    return httpx2.BasicAuth(settings.TWILIO_API_KEY_SID, settings.TWILIO_API_KEY_SECRET)


def request(method, url, **kwargs):
    """One call; returns the decoded JSON. Raises TwilioError."""
    try:
        response = httpx2.request(method, url, auth=_auth(), timeout=TIMEOUT, **kwargs)
    except httpx2.HTTPError as error:
        raise TwilioError(f"Could not reach Twilio ({type(error).__name__}).") from None
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400:
        raise TwilioError(str(data.get("message") or f"Twilio answered {response.status_code}.")[:300], code=data.get("code", ""), status=response.status_code)
    return data if isinstance(data, dict) else {}


def send_message(to_phone, body="", content_sid="", content_variables="", media_url="", status_callback=""):
    """POST a WhatsApp message. Returns Twilio's message resource (sid, status)."""
    form = {"From": f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}", "To": f"whatsapp:{to_phone}"}
    if content_sid:
        form["ContentSid"] = content_sid
        if content_variables:
            form["ContentVariables"] = content_variables
    else:
        if body:
            form["Body"] = body
        if media_url:
            form["MediaUrl"] = media_url
    if status_callback:
        form["StatusCallback"] = status_callback
    return request("POST", f"{API}/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json", data=form)


def fetch_media(url, limit):
    """His file from Twilio (needs our credentials). Returns (bytes, content_type), or None when it is bigger than `limit` bytes.
    Streams, so a huge file is never held. Raises TwilioError."""
    try:
        with httpx2.stream("GET", url, auth=_auth(), timeout=TIMEOUT, follow_redirects=True) as response:  # Twilio redirects to its CDN (no auth is sent there)
            if response.status_code >= 400:
                raise TwilioError(f"Twilio answered {response.status_code} for the file.", status=response.status_code)
            declared = response.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > limit:
                return None
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    return None
                chunks.append(chunk)
            return b"".join(chunks), response.headers.get("content-type", "").split(";")[0].strip().lower()
    except httpx2.HTTPError as error:
        raise TwilioError(f"Could not fetch the file ({type(error).__name__}).") from None


def list_contents():
    """Every Content Template with its approval status (the ContentAndApprovals endpoint, all pages)."""
    out, url = [], f"{CONTENT}/ContentAndApprovals?PageSize=100"
    for _ in range(20):  # a safety stop
        data = request("GET", url)
        out.extend(data.get("contents", []))
        url = (data.get("meta") or {}).get("next_page_url")
        if not url:
            break
    return out


def sender_status():
    """The Spa 99 sender as Twilio lists it: {found, status, name, quality?}. Reads the WhatsApp senders list."""
    data = request("GET", f"{SENDERS}?Channel=whatsapp&PageSize=50")
    wanted = f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}"
    for sender in data.get("senders", []):
        if (sender.get("sender_id") or "").replace(" ", "") == wanted:
            profile = sender.get("profile") or {}
            return {"found": True, "status": str(sender.get("status") or ""), "name": profile.get("name", ""), "quality": (sender.get("properties") or {}).get("quality_rating", "")}
    return {"found": False, "status": "", "name": "", "quality": ""}
