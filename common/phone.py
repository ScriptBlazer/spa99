"""Mobile numbers, always stored as a correct E.164 number that works on WhatsApp. Two parts on every form: a country (ISO code,
default GB = +44) and the number. A leading 0 on the national number is dropped (07441... with +44 gives +447441...); a number typed
with + or 00 wins over the chosen country. Checked with the `phonenumbers` library (is_possible, is_valid, a mobile line)."""
import json
from functools import lru_cache
from pathlib import Path

import phonenumbers
from django.core.exceptions import ValidationError

MESSAGE = "That doesn't look like a valid mobile number."
DEFAULT_COUNTRY = "GB"
FIRST = ["GB", "IE", "IL", "US", "CA", "BE", "FR", "DE", "NL"]  # UK first, then the common ones; everything else A to Z
MOBILE_KINDS = (phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE)
DATA = Path(__file__).resolve().parent / "data" / "countries.json"  # made once by scripts/make_countries.py (the library's geocoder data is far too big to load at runtime)


@lru_cache(maxsize=1)
def countries():
    """[{iso, dial, name}] for the country select: UK first, then Ireland, Israel, US, Canada, Belgium, France, Germany, Netherlands,
    then all the others A to Z. `dial` is like '+44'."""
    found = {c["iso"]: c for c in json.loads(DATA.read_text(encoding="utf-8"))}
    rest = sorted((c for iso, c in found.items() if iso not in FIRST), key=lambda c: c["name"])
    return [found[iso] for iso in FIRST if iso in found] + rest


def known_country(iso):
    iso = (iso or "").strip().upper()
    return iso if iso in phonenumbers.SUPPORTED_REGIONS else DEFAULT_COUNTRY


def normalise(value, country=None):
    """'07441 919990' (country GB), '7441919990' (GB), '+33 6 12 34 56 78' (any country) -> E.164. A leading + or 00 is an international number and
    wins over the country. Raises ValidationError(MESSAGE)."""
    raw = (value or "").strip() if isinstance(value, str) else ""
    international = raw.startswith("+") or raw.startswith("00")
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    try:
        number = phonenumbers.parse(raw, None if international else known_country(country))
    except phonenumbers.NumberParseException:
        raise ValidationError(MESSAGE, code="invalid") from None
    if not (phonenumbers.is_possible_number(number) and phonenumbers.is_valid_number(number) and phonenumbers.number_type(number) in MOBILE_KINDS):
        raise ValidationError(MESSAGE, code="invalid")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def split(e164):
    """A stored number -> {country: ISO, national: '07441 919990'} to pre-fill the two parts; blanks when it cannot be read."""
    try:
        number = phonenumbers.parse(e164 or "", None)
        return {"country": phonenumbers.region_code_for_number(number) or DEFAULT_COUNTRY, "national": phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.NATIONAL)}
    except phonenumbers.NumberParseException:
        return {"country": DEFAULT_COUNTRY, "national": ""}
