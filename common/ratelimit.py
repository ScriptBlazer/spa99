"""Small fixed-window rate limiter on Django's cache. No extra packages.

The cache is the database cache (config.settings.base CACHES), so every gunicorn worker shares the count. If the cache
cannot be reached (for example the table was never created) the limiter lets the request through and logs it: a broken
cache must not lock everyone out of sign-in.
"""
import hashlib
import logging
import time
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse

from .audit import client_ip

logger = logging.getLogger("spa99.ratelimit")


def hit(scope, identifier, limit, window_seconds, sliding=False):
    """Count one hit. Returns True if the caller is still within `limit` per `window_seconds`.

    Two modes. Default: a fixed window (cheap and friendly: people search, chat, JSON endpoints). sliding=True: for sign-in, password reset, registration, token and code
    guessing, where a fixed window lets a burst of up to twice the limit through at a window edge and lets a non-stop bot get `limit` more every window.

    A fixed window: the key carries the window number, and every write sets the expiry to the end of that window. (Django's `cache.incr` cannot take a timeout and the database
    cache resets the expiry to its default, 300 seconds, on every increment, so a count would live five quiet minutes and refused hits would extend it.) Refused hits write
    nothing. Get then set is not atomic, so a burst of parallel requests can slip a few extra through: fine for a limit like this."""
    digest = hashlib.sha256(str(identifier).encode()).hexdigest()[:32]
    if sliding:
        return _sliding(f"rl:{scope}:{digest}", limit, window_seconds)
    moment = time.time()
    window = int(moment // window_seconds)
    key = f"rl:{scope}:{digest}:{window}"
    expires_in = max(int(window_seconds - (moment % window_seconds)) + 1, 1)
    try:
        if cache.add(key, 1, expires_in):
            return limit >= 1
        count = cache.get(key)
        if count is None:  # expired between add and get
            cache.add(key, 1, expires_in)
            return limit >= 1
        if count >= limit:
            return False
        cache.set(key, count + 1, expires_in)
        return True
    except Exception:  # noqa: BLE001 - fail open, loudly
        logger.exception("Rate limit cache unavailable for %s", scope)
        return True


def _sliding(key, limit, window_seconds):
    """Every hit, allowed or refused, counts and moves the expiry to `window_seconds` from now. Someone who keeps trying while blocked stays blocked until they stop for a
    whole window (what the database cache's incr did before, but with the caller's own window instead of its 300 s default). No window edge exists to slip through."""
    try:
        count = (cache.get(key) or 0) + 1
        cache.set(key, count, window_seconds)
        return count <= limit
    except Exception:  # noqa: BLE001 - fail open, loudly
        logger.exception("Rate limit cache unavailable for %s", key)
        return True


def too_many_response(window_seconds):
    response = JsonResponse({"error": "Too many requests. Please wait a moment."}, status=429)
    response["Retry-After"] = str(window_seconds)
    return response


def rate_limited_json(scope, limit, window_seconds, sliding=False):
    """View decorator: per-IP limit, answers 429 JSON when exceeded."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not hit(scope, client_ip(request) or "unknown", limit, window_seconds, sliding):
                return too_many_response(window_seconds)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
