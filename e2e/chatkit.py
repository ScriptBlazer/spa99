"""Helpers for the WhatsApp and email chat walk-throughs: what Twilio and Postmark would post to the site, signed the way they sign it, and a reader for what the
site would have sent to Twilio (the fake in e2e/fakes.py writes each send to twilio-calls.jsonl). Nothing here reaches a real service."""
import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .kit import SITE, WORKSPACE_DIR

TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "e2e-twilio-auth-token")
SENDER = os.environ.get("TWILIO_WHATSAPP_FROM", "+442045384999")
INBOUND_USER = os.environ.get("EMAIL_INBOUND_USER", "e2e-inbound")
INBOUND_PASSWORD = os.environ.get("EMAIL_INBOUND_PASSWORD", "e2e-inbound-password")


def twilio_sign(url, params):
    """X-Twilio-Signature: HMAC-SHA1 of the full URL plus the sorted parameters, keyed with the Auth Token, base64."""
    data = url + "".join(key + params[key] for key in sorted(params))
    return base64.b64encode(hmac.new(TWILIO_TOKEN.encode(), data.encode(), hashlib.sha1).digest()).decode()


def twilio_post(path, params):
    """POST to one of the site's Twilio webhooks (public host), signed. Returns the HTTP status."""
    url = f"{SITE}{path}"
    request = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST", headers={"X-Twilio-Signature": twilio_sign(url, params)})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def whatsapp_from_him(phone, body, sid, **extra):
    """A message from him to the Spa 99 sender, as Twilio posts it. `extra` carries things like OriginalRepliedMessageSid."""
    params = {"MessageSid": sid, "From": f"whatsapp:{phone}", "To": f"whatsapp:{SENDER}", "Body": body, "NumMedia": "0", "ProfileName": "E2E Guest", **extra}
    return twilio_post("/twilio/whatsapp/incoming/", params)


def twilio_calls():
    """Every message the site tried to send to Twilio so far (oldest first): {sid, To, From, Body, MediaUrl, ...}."""
    path = WORKSPACE_DIR / "twilio-calls.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def postmark_inbound(token, message_id, **fields):
    """An email from him, as Postmark posts it to the inbound webhook (HTTP Basic). `fields`: Subject, TextBody, StrippedTextReply, HtmlBody, FromFull ..."""
    body = {"MailboxHash": token, "MessageID": message_id, **fields}
    request = urllib.request.Request(f"{SITE}/postmark/inbound/", data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(f"{INBOUND_USER}:{INBOUND_PASSWORD}".encode()).decode()})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
