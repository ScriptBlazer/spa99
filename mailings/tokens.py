"""Unsubscribe links: a signed token holding the address, no login, no expiry (an old email must still be able to stop the
mail). The token proves only 'this link was made by us for this address'; the only thing it can do is switch that
address's marketing off."""
from django.conf import settings
from django.core import signing
from django.urls import reverse

SALT = "spa99.mailings.unsubscribe"


def make_unsubscribe_token(email):
    return signing.dumps({"e": (email or "").strip().lower()}, salt=SALT)


def read_unsubscribe_token(token):
    """The address in a valid token, else None."""
    try:
        email = signing.loads(token, salt=SALT).get("e", "")
    except signing.BadSignature:
        return None
    return email or None


def unsubscribe_url(email):
    # the public site's routes, whichever host is serving this request (a System page previews and tests mailings)
    return f"{settings.SITE_URL}{reverse('unsubscribe', args=[make_unsubscribe_token(email)], urlconf='config.urls')}"


def list_unsubscribe_headers(url):
    """The headers mail clients use for their own Unsubscribe button (RFC 8058 one-click)."""
    return {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
