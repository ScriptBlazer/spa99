"""Small rate limiter (fixed, rolling, or rolling with a lock) on Django's cache. No extra packages.

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


def hit(scope, identifier, limit, window_seconds, rolling=False, lock=False):
    """Count one hit. Returns True if the caller is still within `limit` per `window_seconds`.

    Three modes:
    - default, a fixed window: cheap and friendly (people search, chat, JSON endpoints, signed-link GETs). A burst of up to twice the limit can pass at a window edge.
    - rolling=True: never more than `limit` allowed hits in any `window_seconds` (register, forgot password, applications). Honest traffic spread out is never refused,
      because each allowed hit simply ages out `window_seconds` after it happened. Refused hits are not recorded.
    - rolling=True, lock=True: for guessing (sign-in, password change, system code). The first refusal locks the caller: every attempt after that, refused ones included,
      is refused until a whole window passes with no attempts. A non-stop bot stays out, and the right password stays refused while locked.

    Rolling: one cache key holds a list of the allowed hit times (at most `limit` of them) plus the lock time, and expires `window_seconds` after the last write. Read then
    write is not atomic: the worst case is that a burst of N parallel requests which all read before any writes lets up to N-1 extra through, once. Fine for these limits.

    Fixed: the key carries the window number and every write sets the expiry to the end of that window. (Django's `cache.incr` cannot take a timeout and the database
    cache resets the expiry to its default, 300 seconds, on every increment.) Refused hits write nothing."""
    digest = hashlib.sha256(str(identifier).encode()).hexdigest()[:32]
    if rolling or lock:
        return _rolling(f"rl:{scope}:{digest}", limit, window_seconds, lock)
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


def _rolling(key, limit, window_seconds, lock):
    """Stored value: (allowed hit times, locked_until). Only allowed hits are recorded; a refusal in lock mode sets locked_until, and any attempt while locked pushes it on."""
    now = time.time()
    expires_in = int(window_seconds) + 1
    try:
        times, locked_until = cache.get(key) or ([], 0.0)
        if lock and locked_until > now:
            cache.set(key, (times, now + window_seconds), expires_in)
            return False
        times = [t for t in times if t > now - window_seconds]
        if len(times) >= limit:
            if lock:
                cache.set(key, (times, now + window_seconds), expires_in)
            return False
        times.append(now)
        cache.set(key, (times[-limit:], 0.0), expires_in)
        return True
    except Exception:  # noqa: BLE001 - fail open, loudly
        logger.exception("Rate limit cache unavailable for %s", key)
        return True


def too_many_response(window_seconds):
    response = JsonResponse({"error": "Too many requests. Please wait a moment."}, status=429)
    response["Retry-After"] = str(window_seconds)
    return response


def rate_limited_json(scope, limit, window_seconds, rolling=False):
    """View decorator: per-IP limit, answers 429 JSON when exceeded."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not hit(scope, client_ip(request) or "unknown", limit, window_seconds, rolling):
                return too_many_response(window_seconds)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
