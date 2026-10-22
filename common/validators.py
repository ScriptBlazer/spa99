"""Shared validation rules. The same rules are mirrored in common/static/common/js/validate.js
for live feedback; this Python side is the one that actually protects the data.
"""
from datetime import date

import phonenumbers
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

MESSAGES = {
    "email_required": "Enter your email address.",
    "email_invalid": "Enter a valid email address.",
    "mobile_invalid": "Enter a valid UK mobile number, like 07123 456789.",
    "name_required": "Enter your name.",
    "name_long": "That name is too long.",
    "dob_required": "Enter your date of birth.",
    "dob_invalid": "Enter a valid date of birth.",
    "dob_under_age": "You must be 18 or over.",
}

NAME_MAX_LENGTH = 100


def validate_person_name(value):
    """Trim and check a first or last name. Returns the clean name or raises ValidationError."""
    cleaned = " ".join((value or "").split())
    if not cleaned:
        raise ValidationError(MESSAGES["name_required"], code="required")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise ValidationError(MESSAGES["name_long"], code="max_length")
    return cleaned


def validate_adult(dob, today=None):
    """Date of birth must be a real past date and the person 18 or over (ACC-08).
    The age comes from settings.MINIMUM_AGE. Returns the date or raises ValidationError."""
    if dob is None:
        raise ValidationError(MESSAGES["dob_required"], code="required")
    today = today or date.today()
    if dob > today or dob.year < 1900:
        raise ValidationError(MESSAGES["dob_invalid"], code="invalid")
    minimum = getattr(settings, "MINIMUM_AGE", 18)
    had_birthday = (today.month, today.day) >= (dob.month, dob.day)
    age = today.year - dob.year - (0 if had_birthday else 1)
    if age < minimum:
        raise ValidationError(MESSAGES["dob_under_age"], code="under_age")
    return dob


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
