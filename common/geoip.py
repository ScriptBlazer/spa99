"""Country from an IP address, with the free DB-IP "IP to Country Lite" file (CC BY 4.0) read by `maxminddb`.
The IP is looked up and dropped: nothing here stores it. A missing or unreadable file (or no maxminddb library) means every
country is 'unknown'; nothing breaks, so local runs and CI work without the file. Path: settings.GEOIP_DB_PATH."""
import logging
import os

from django.conf import settings

logger = logging.getLogger("spa99.geoip")

UNKNOWN = "unknown"
_state = {"loaded": False, "reader": None}


def database_path():
    return getattr(settings, "GEOIP_DB_PATH", "") or ""


def is_available():
    """True when the database file exists (for the startup line); does not open it."""
    path = database_path()
    return bool(path) and os.path.isfile(path)


def _reader():
    """The cached reader, opened on first use (one try only: a file added later is picked up after a restart)."""
    if _state["loaded"]:
        return _state["reader"]
    _state["loaded"] = True
    if not is_available():
        return None
    try:
        import maxminddb

        _state["reader"] = maxminddb.open_database(database_path())
    except Exception:  # noqa: BLE001 - a broken file must not break a page
        logger.warning("Could not open the GeoIP file %s: countries will show as unknown", database_path(), exc_info=True)
    return _state["reader"]


def reset():
    """Forget the cached reader (tests, and after the file is replaced)."""
    reader = _state["reader"]
    _state.update(loaded=False, reader=None)
    try:
        if reader is not None:
            reader.close()
    except Exception:  # noqa: BLE001
        pass


def country_code(ip):
    """Lower-case two-letter country code ('gb'), or 'unknown'. Never raises."""
    if not ip:
        return UNKNOWN
    try:
        reader = _reader()
        found = reader.get(ip) if reader is not None else None
        code = ((found or {}).get("country") or {}).get("iso_code") or ""
    except Exception:  # noqa: BLE001 - a bad address, a closed file
        return UNKNOWN
    code = str(code).strip().lower()
    return code if len(code) == 2 and code.isalpha() else UNKNOWN
