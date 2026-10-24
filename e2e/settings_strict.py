"""Settings for the SECOND end-to-end server (scripts/e2e.sh starts it next to the normal one). Same throwaway database, media and
mail folder as e2e.settings (so it keeps the same safety guard), with two deliberate differences:

- real rate limits (an in-memory cache instead of the dummy one), so the sign-in, forgot-password and System unlock limits can be
  proven; only the walk-throughs that need that use this server, so the other walk-throughs never trip a limit;
- tiny Control Library limits: audio files over 1 MB are refused and the whole Library holds about 2 KB, so the refusals can be
  proven with a small upload, without changing the normal server (the first Library walk-through still uploads a normal file there).
"""
from e2e.settings import *  # noqa: F401,F403 (the guard in e2e.settings runs first)

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "e2e-strict"}}
CONTROL_MAX_AUDIO_MB = 1
CONTROL_LIBRARY_MAX_GB = 0.000002  # about 2,147 bytes
