"""X-Twilio-Signature check (Twilio's algorithm): HMAC-SHA1 with the Auth Token over the exact public URL followed by every POST parameter sorted by
name (name then value), base64, compared in constant time. The URL is SITE_URL plus path (Caddy and Cloudflare sit in front, so the request's own host is not what Twilio signed)."""
import base64
import hashlib
import hmac

from django.conf import settings


def expected(url, pairs, token):
    data = url + "".join(f"{name}{value}" for name, value in sorted(pairs))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


def public_url(request):
    query = request.META.get("QUERY_STRING", "")
    return f"{settings.SITE_URL}{request.path}" + (f"?{query}" if query else "")


def valid(request):
    token, given = settings.TWILIO_AUTH_TOKEN, request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
    if not token or not given:
        return False
    pairs = [(name, value) for name, values in request.POST.lists() for value in sorted(values)]
    return hmac.compare_digest(expected(public_url(request), pairs, token).encode(), given.encode())
