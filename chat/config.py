"""Read the assistant's settings once per request (System > Assistant). Callers read a value where it is used, so a change applies at once."""
from django.conf import settings

from .models import AssistantSettings

_ATTR = "_assistant_settings"


def get(request=None):
    if request is None:
        return AssistantSettings.load()
    cached = getattr(request, _ATTR, None)
    if cached is None:
        cached = AssistantSettings.load()
        setattr(request, _ATTR, cached)
    return cached


def forget(request):
    if hasattr(request, _ATTR):
        delattr(request, _ATTR)


def is_on(request=None):
    """The chat works: an API key is set and the System switch is on. (The switch is read only when there is a key.)"""
    return bool(settings.ANTHROPIC_API_KEY) and get(request).enabled
