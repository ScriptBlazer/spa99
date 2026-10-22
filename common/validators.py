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
    "dob_under_age": "You must be {minimum} or over.",
    # Wording for fields left empty (the JS shows these before the server is asked).
    "required": "This field is required.",
    "mobile_required": "Enter your mobile number.",
    "password_required": "Choose a password.",
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
        raise ValidationError(MESSAGES["dob_under_age"].format(minimum=minimum), code="under_age")
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


# ---------- what the browser needs to give the same answers ----------

def _password_messages():
    """The wording of the active password validators, taken from the validators themselves (so the browser shows
    exactly what the server would say). Keys are left out for validators that are switched off."""
    from django.contrib.auth.password_validation import (
        CommonPasswordValidator, MinimumLengthValidator, NumericPasswordValidator, UserAttributeSimilarityValidator,
        get_default_password_validators,
    )

    probes = {
        MinimumLengthValidator: ("password_short", lambda v: v.validate("a")),
        CommonPasswordValidator: ("password_common", lambda v: v.validate("password")),
        NumericPasswordValidator: ("password_numeric", lambda v: v.validate("12345678901")),
        UserAttributeSimilarityValidator: (
            "password_similar", lambda v: v.validate("probename", get_user_model()(first_name="probename")),
        ),
    }
    messages, minimum_length = {}, None
    for validator in get_default_password_validators():
        entry = probes.get(type(validator))
        if entry is None:
            continue
        key, run = entry
        if isinstance(validator, MinimumLengthValidator):
            minimum_length = validator.min_length
        try:
            run(validator)
        except ValidationError as error:
            first = error.error_list[0]
            text = first.message % first.params if first.params else first.message
            if key == "password_similar":  # "...similar to the first name." -> a {what} slot for the browser to fill
                text = text.replace("first name", "{what}")
            messages[key] = text
    return messages, minimum_length


def client_config(urls=None):
    """Everything validate.js needs from the server, so the wording and limits live in Python only:
    {messages, minimum_age, password_min_length, name_max_length, urls}."""
    minimum = getattr(settings, "MINIMUM_AGE", 18)
    password_messages, min_length = _password_messages()
    messages = {**MESSAGES, **password_messages}
    messages["dob_under_age"] = messages["dob_under_age"].format(minimum=minimum)
    return {
        "messages": messages, "minimum_age": minimum, "password_min_length": min_length,
        "name_max_length": NAME_MAX_LENGTH, "urls": urls or {},
    }
