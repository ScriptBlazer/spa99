"""Email verification and password reset tokens.

Verification: a signed token (24h, settings.EMAIL_VERIFY_MAX_AGE). Single use because the person's
`email_verified_at` is checked: a replayed link never signs anyone in again.
Password reset: Django's token generator (1h, settings.PASSWORD_RESET_TIMEOUT). Single use because the
token is built from the current password hash, which changes when the password is reset.
"""
import uuid

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User

VERIFY_SALT = "spa99.users.verify-email"
VERIFIED, ALREADY, EXPIRED, INVALID = "verified", "already", "expired", "invalid"


def make_verify_token(user):
    # The email is inside the token: if the address changes later, old links stop working.
    return signing.dumps({"u": str(user.pk), "e": user.email}, salt=VERIFY_SALT)


def read_verify_token(token):
    """(status, user). status is EXPIRED / INVALID with user None, or 'ok' with the user."""
    try:
        payload = signing.loads(token, salt=VERIFY_SALT, max_age=settings.EMAIL_VERIFY_MAX_AGE)
    except signing.SignatureExpired:
        return EXPIRED, None
    except signing.BadSignature:
        return INVALID, None
    user = User.objects.filter(pk=payload.get("u"), email__iexact=payload.get("e", "")).first()
    return ("ok", user) if user else (INVALID, None)


def make_reset_link_parts(user):
    return urlsafe_base64_encode(force_bytes(str(user.pk))), default_token_generator.make_token(user)


def read_reset_token(uidb64, token):
    """The user if the link is valid and still unused and unexpired, else None."""
    try:
        pk = uuid.UUID(urlsafe_base64_decode(uidb64).decode())
    except (ValueError, TypeError, OverflowError, UnicodeDecodeError):
        return None
    user = User.objects.filter(pk=pk, is_active=True).first()
    return user if user and default_token_generator.check_token(user, token) else None
