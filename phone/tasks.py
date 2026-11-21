"""Background entry points (django-q2). They never raise and never queue anything themselves, so a failure cannot turn into a retry loop."""
from . import services


def process(pk):
    """Download and email one call's voicemail (phone.services.process)."""
    return services.process(pk)


def sweep():
    """Every 5 minutes: at most 10 waiting voicemails and 90 seconds, each capped at 8 attempts with backoff."""
    return services.sweep()
