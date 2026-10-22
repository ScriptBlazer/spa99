"""Shared validation rules. The same rules are mirrored in common/static/common/js/validate.js
for live feedback; this Python side is the one that actually protects the data.
"""
import phonenumbers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

MESSAGES = {
    "email_required": "Enter your email address.",
    "email_invalid": "Enter a valid email address.",
    "mobile_invalid": "Enter a valid UK mobile number, like 07123 456789.",
}


def normalise_email(value):
    """Trim and lowercase, then check the format. Returns the clean address or raises ValidationError."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        raise ValidationError(MESSAGES["email_required"], code="required")
    try:
        validate_email(cleaned)
    except ValidationError:
        raise ValidationError(MESSAGES["email_invalid"], code="invalid") from None
    return cleaned


def normalise_uk_mobile(value):
    """'07123 456789' or '+44 7123 456789' -> '+447123456789' (E.164). Raises ValidationError if not a UK mobile."""
    raw = (value or "").strip()
    try:
        number = phonenumbers.parse(raw, "GB")
    except phonenumbers.NumberParseException:
        raise ValidationError(MESSAGES["mobile_invalid"], code="invalid") from None
    is_uk_mobile = (
        number.country_code == 44
        and phonenumbers.is_valid_number(number)
        and phonenumbers.number_type(number)
        in (phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE)
    )
    if not is_uk_mobile:
        raise ValidationError(MESSAGES["mobile_invalid"], code="invalid")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def validate_uk_mobile(value):
    """Model/form validator wrapper."""
    normalise_uk_mobile(value)


def password_problems(password, email="", first_name="", last_name=""):
    """List of plain-English problems with a password (empty list = fine). Uses AUTH_PASSWORD_VALIDATORS:
    at least 10 characters, not common, not all numbers, not similar to name or email."""
    person = get_user_model()(email=email, first_name=first_name, last_name=last_name)  # unsaved
    try:
        validate_password(password, user=person)
    except ValidationError as error:
        return list(error.messages)
    return []
