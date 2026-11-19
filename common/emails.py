"""One cleaner for email addresses. Phones (WhatsApp, contacts, right-to-left keyboards) paste invisible Unicode format
characters (U+200F, U+202C and friends) onto an address. Django's EmailValidator accepts them after the domain, `.strip()`
does not remove them, and the SMTP/IDNA step then fails at send time. Every place that takes or compares an address uses this."""
import unicodedata


def strip_hidden(value):
    """Remove every Unicode format character (category Cf: zero-width, direction marks, BOM...) and surrounding whitespace.
    Real characters are untouched (no NFKC). Case is not changed."""
    if not isinstance(value, str):
        return ""
    return "".join(ch for ch in value if unicodedata.category(ch) != "Cf").strip()


def clean_email(value):
    """The address as stored and compared: hidden characters and surrounding whitespace removed, lower case."""
    return strip_hidden(value).lower()


def has_hidden(value):
    return isinstance(value, str) and any(unicodedata.category(ch) == "Cf" for ch in value)
