"""Unsubscribe links: an opaque random key per address (UnsubscribeKey), no login, no expiry (an old email must still be able to
stop the mail), and no address in the URL. The key can only switch that address's marketing off."""
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse

from .models import UnsubscribeKey


def make_unsubscribe_token(email):
    email = (email or "").strip().lower()
    row = UnsubscribeKey.objects.filter(email=email).first()
    if row is None:
        try:
            with transaction.atomic():
                row = UnsubscribeKey.objects.create(email=email)
        except IntegrityError:  # two sends at once
            row = UnsubscribeKey.objects.get(email=email)
    return row.token


def read_unsubscribe_token(token):
    """The address behind a key, else None."""
    row = UnsubscribeKey.objects.filter(token=token or "").first()
    return row.email if row else None


def unsubscribe_url(email):
    # the public site's routes, whichever host is serving this request (a System page previews and tests mailings)
    return f"{settings.SITE_URL}{reverse('unsubscribe', args=[make_unsubscribe_token(email)], urlconf='config.urls')}"


def list_unsubscribe_headers(url):
    """The headers mail clients use for their own Unsubscribe button (RFC 8058 one-click)."""
    return {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
