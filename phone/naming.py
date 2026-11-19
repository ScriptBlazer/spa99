"""Readable storage keys: voicemails/YYYY/MM/YYYY-MM-DD_HH-MM_<caller>.mp3 in London time. The caller is the national digits of a UK number
(07368912320), 00 plus the digits of a foreign number, or "unknown" (withheld, masked or unreadable). A clash gets _2, _3. No SIDs, no random strings.
The folder sits at the top of the private media storage like the other apps' (control/, gold/, mailings/); S3 adds the dev/ or prod/ prefix."""
import phonenumbers
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

FOLDER = "voicemails"
UNKNOWN = "unknown"
MAX_TRIES = 500


def caller_digits(number):
    try:
        parsed = phonenumbers.parse(number or "", None)
    except phonenumbers.NumberParseException:
        return UNKNOWN
    if "*" in (number or "") or not phonenumbers.is_valid_number(parsed):
        return UNKNOWN
    if phonenumbers.region_code_for_number(parsed) == "GB":
        digits = "".join(ch for ch in phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL) if ch.isdigit())
        return digits if digits.startswith("0") else "0" + digits
    return "00" + str(parsed.country_code) + str(parsed.national_number)


def base_key(received_at, from_number):
    local = timezone.localtime(received_at)
    return f"{FOLDER}/{local:%Y}/{local:%m}/{local:%Y-%m-%d_%H-%M}_{caller_digits(from_number)}"


def candidate_keys(received_at, from_number):
    """base.mp3, base_2.mp3, base_3.mp3 ..."""
    base = base_key(received_at, from_number)
    for n in range(1, MAX_TRIES):
        yield f"{base}.mp3" if n == 1 else f"{base}_{n}.mp3"
    raise RuntimeError("Too many voicemails in the same minute from one number")


def free_key(received_at, from_number, storage=None):
    """The first key not taken in the storage."""
    storage = storage or default_storage
    return next(key for key in candidate_keys(received_at, from_number) if not storage.exists(key))


def store(data, received_at, from_number, storage=None):
    """Save the bytes under the first free tidy key and return the name. If two saves race and the storage answers with a different name (S3 and disk add random text
    when a key is taken), that stray copy is removed and the next suffix is tried, so names stay tidy."""
    storage = storage or default_storage
    for key in candidate_keys(received_at, from_number):
        if storage.exists(key):
            continue
        name = storage.save(key, ContentFile(data))
        if name == key:
            return name
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 - a stray copy is harmless; the next key is tried regardless
            pass


def friendly_number(number):
    """07368 912320 for a UK number, the E.164 text as given for anything else."""
    try:
        parsed = phonenumbers.parse(number or "", None)
        if phonenumbers.is_valid_number(parsed) and phonenumbers.region_code_for_number(parsed) == "GB":
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    except phonenumbers.NumberParseException:
        pass
    return number or "withheld number"
