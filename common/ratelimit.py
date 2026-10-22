"""Small fixed-window rate limiter on Django's cache. No extra packages.

Note: the default cache is per process (LocMem). With several gunicorn workers the real limit is
roughly workers x limit. Point CACHES at the database or Redis later if a hard global limit is needed.
"""
import hashlib
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse

from .audit import client_ip


def hit(scope, identifier, limit, window_seconds):
    """Count one hit. Returns True if the caller is still within `limit` per `window_seconds`."""
    digest = hashlib.sha256(str(identifier).encode()).hexdigest()[:32]
    key = f"rl:{scope}:{digest}"
    if cache.add(key, 1, window_seconds):
        return True
    try:
        return cache.incr(key) <= limit
    except ValueError:  # key expired between add and incr
        cache.add(key, 1, window_seconds)
        return True


def rate_limited_json(scope, limit, window_seconds):
    """View decorator: per-IP limit, answers 429 JSON when exceeded."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not hit(scope, client_ip(request) or "unknown", limit, window_seconds):
                response = JsonResponse({"error": "Too many requests. Please wait a moment."}, status=429)
                response["Retry-After"] = str(window_seconds)
                return response
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
