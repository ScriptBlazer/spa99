"""Type checks for JSON typed into a form (perks, plan points, conditions), run BEFORE a value is used as a set member or a
dict key (a list or an object there would raise TypeError and become a 500). Each check returns the value or raises a
ValidationError with the message given. System's rule forms use these; the code view reuses them."""
import re

from django.core.exceptions import ValidationError

WHOLE_NUMBER = re.compile(r"-?[0-9]+")  # ASCII digits only: int() also accepts digits such as Arabic-Indic ones


def is_text(value):
    return isinstance(value, str)


def is_whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def has_non_ascii_digit(text):
    return isinstance(text, str) and any(ch.isdigit() and not ch.isascii() for ch in text)


def parse_whole(raw):
    """'12' or '-5' as an int; anything else (including '--5' and superscript or Arabic-Indic digits) comes back unchanged."""
    return int(raw) if isinstance(raw, str) and WHOLE_NUMBER.fullmatch(raw) else raw


def no_nul(value, message="Remove the hidden character (\\u0000)."):
    """Postgres refuses the NUL character inside JSON text; refuse it here so it is a field error, not a 500."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str) and "\x00" in item:
            raise ValidationError(message)
        if isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return value


def need_list(value, message):
    if not isinstance(value, list):
        raise ValidationError(message)
    return value


def need_dict(value, message):
    if not isinstance(value, dict):
        raise ValidationError(message)
    return value


def need_text(value, message, blank=False):
    if not is_text(value) or (not blank and not value.strip()):
        raise ValidationError(message)
    return value


def need_text_list(value, message, empty=True):
    need_list(value, message)
    if (not empty and not value) or not all(is_text(item) for item in value):
        raise ValidationError(message)
    return value


def need_whole_in(value, low, high, message):
    if not is_whole(value) or not low <= value <= high:
        raise ValidationError(message)
    return value
