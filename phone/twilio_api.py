"""The ONLY place we talk to Twilio's API. Cost safety (docs/features/voicemail.md): GET only, nothing here can create a call, message, transcription or
anything billable. `_send` refuses any other method, and `get` refuses any path that is not on the short list below (this account's call list, one call's
recordings, one recording's MP3). Timeouts everywhere, a size cap on downloads, and no automatic retry of any kind in this module."""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

HOST = "api.twilio.com"
TIMEOUT = 20
MAX_BYTES = 30 * 1024 * 1024
MAX_REDIRECTS = 3


class TwilioError(Exception):
    pass


class Refused(TwilioError):
    """A call we will never make (not GET, not on the list)."""


def configured():
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_API_KEY_SID and settings.TWILIO_API_KEY_SECRET)


def allowed_path(path):
    sid = re.escape(settings.TWILIO_ACCOUNT_SID)
    return bool(re.fullmatch(rf"/2010-04-01/Accounts/{sid}/(Calls\.json|Calls/[A-Za-z0-9]+/Recordings\.json|Recordings/[A-Za-z0-9]+\.mp3)", path))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # we follow redirects ourselves, so the API key never goes to another host


_opener = urllib.request.build_opener(_NoRedirect)


def _open(request, timeout):
    """The single door to the network (tests replace it)."""
    try:
        return _opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        return error


def _send(method, url, headers=None):
    """One HTTP request, GET only. Returns (status, headers, body bytes)."""
    if method != "GET":
        raise Refused(f"Twilio calls are GET only (refused {method})")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise Refused("Twilio calls are https only")
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    response = _open(request, TIMEOUT)
    try:
        # One read(n) can return fewer bytes than asked (seen on Twilio's chunked JSON pages), so read until the end or the cap.
        chunks, size = [], 0
        while size <= MAX_BYTES:
            chunk = response.read(min(65536, MAX_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        body = b"".join(chunks)
    finally:
        response.close()
    if len(body) > MAX_BYTES:
        raise TwilioError("The file is too large")
    expected = response.headers.get("Content-Length")
    if expected and expected.isdigit() and int(expected) != len(body):
        # Never keep a cut-off page or MP3: fail this attempt (the capped retry takes it again later).
        raise TwilioError(f"Incomplete answer from Twilio ({len(body)} of {expected} bytes)")
    return response.status, dict(response.headers), body


def _auth():
    token = base64.b64encode(f"{settings.TWILIO_API_KEY_SID}:{settings.TWILIO_API_KEY_SECRET}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def get(path, params=None):
    """GET https://api.twilio.com<path>?params with the API key. `path` may carry its own query (a next_page_uri). Follows up to 3 redirects, the first with the key,
    the rest (a signed media link) without it, https only. Returns (status, body bytes). Raises Refused or TwilioError."""
    base, _, query = path.partition("?")
    if not allowed_path(base):
        raise Refused("That Twilio path is not allowed")
    if not configured():
        raise TwilioError("Twilio API key is not set")
    if params:
        query = urllib.parse.urlencode(params) + ("&" + query if query else "")
    url = f"https://{HOST}{base}" + (f"?{query}" if query else "")
    headers = _auth()
    for _ in range(MAX_REDIRECTS + 1):
        status, response_headers, body = _send("GET", url, headers)
        if status in (301, 302, 303, 307, 308):
            location = urllib.parse.urljoin(url, response_headers.get("Location", ""))
            if not location.startswith("https://"):
                raise TwilioError("Redirect to a non-https address refused")
            url, headers = location, {}
            continue
        if status != 200:
            raise TwilioError(f"Twilio answered {status}")
        return status, body
    raise TwilioError("Too many redirects")


def get_json(path, params=None):
    return json.loads(get(path, params)[1].decode("utf-8"))


def recording_path(recording_sid):
    return f"/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Recordings/{recording_sid}.mp3"


def download_recording(recording_sid):
    return get(recording_path(recording_sid))[1]
