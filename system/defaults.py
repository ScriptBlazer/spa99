"""Read the editable defaults (System > Defaults). `get(request)` loads the one row once per request (kept on the request);
without a request it is one small read by key. Callers read a value where it is used, so a change applies at once."""
from .models import SiteDefaults

_ATTR = "_site_defaults"


def get(request=None):
    if request is None:
        return SiteDefaults.load()
    cached = getattr(request, _ATTR, None)
    if cached is None:
        cached = SiteDefaults.load()
        setattr(request, _ATTR, cached)
    return cached


def forget(request):
    """Drop the per-request copy (after the row was saved in this same request)."""
    if hasattr(request, _ATTR):
        delattr(request, _ATTR)
