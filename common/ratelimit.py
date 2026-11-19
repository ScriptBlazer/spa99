"""Small rate limiter (fixed, rolling, or rolling with a lock) on its own small table, common.RateHit. No extra packages.

Every gunicorn worker shares the count through the database. If the table cannot be reached the limiter lets the request
through and logs it: a broken store must not lock everyone out of sign-in.
"""
import hashlib
import logging
import time
from datetime import datetime, timezone as dt_timezone
from functools import wraps

from django.db import IntegrityError, transaction
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

    Each key is one small `common.RateHit` row, read and written under a row lock inside a short transaction, so parallel requests never lose a hit. (On SQLite the
    database's own write lock does the same job; select_for_update is a no-op there.) Fixed: the key carries the window number and the row expires at the end of that
    window. Rolling: the row holds the allowed hit times (at most `limit`) plus the lock time, and expires `window_seconds` after the last write. Refused hits write
    nothing, except in lock mode. If the database cannot be reached the request is let through and logged."""
    digest = hashlib.sha256(str(identifier).encode()).hexdigest()[:32]
    if rolling or lock:
        return _run(f"rl:{scope}:{digest}", lambda row, now: _rolling(row, now, limit, window_seconds, lock), scope)
    moment = time.time()
    window = int(moment // window_seconds)
    key = f"rl:{scope}:{digest}:{window}"
    expires_in = max(int(window_seconds - (moment % window_seconds)) + 1, 1)
    return _run(key, lambda row, now: _fixed(row, limit, expires_in), scope)


def _fixed(state, limit, expires_in):
    """state: {"count": n} or None. Returns (allowed, new state or None, seconds to live)."""
    count = state["count"] if state else 0
    if count >= limit:
        return False, None, expires_in
    return limit >= 1, {"count": count + 1}, expires_in


def _rolling(state, now, limit, window_seconds, lock):
    """state: {"times": [...], "locked_until": t} or None. Only allowed hits are recorded; a refusal in lock mode sets locked_until, and any attempt while locked pushes it on."""
    expires_in = int(window_seconds) + 1
    times, locked_until = (state["times"], state["locked_until"]) if state else ([], 0.0)
    if lock and locked_until > now:
        return False, {"times": times, "locked_until": now + window_seconds}, expires_in
    times = [t for t in times if t > now - window_seconds]
    if len(times) >= limit:
        if lock:
            return False, {"times": times, "locked_until": now + window_seconds}, expires_in
        return False, None, expires_in
    times.append(now)
    return True, {"times": times[-limit:], "locked_until": 0.0}, expires_in


def _run(key, decide, scope):
    """Load the row for `key` under a lock (an expired row counts as empty), let `decide` choose, and write the new state. A racing insert (two requests creating the
    same key) loses on the unique key and is retried once, when the row exists and is locked normally."""
    from .models import RateHit

    try:
        for attempt in (1, 2):
            now = time.time()
            try:
                with transaction.atomic():
                    row = RateHit.objects.select_for_update().filter(key=key).first()
                    live = row is not None and row.expires_at.timestamp() > now
                    state = (row.data if row.data is not None else {"count": row.count}) if live else None
                    allowed, new_state, expires_in = decide(state, now)
                    if new_state is not None:
                        values = {"expires_at": datetime.fromtimestamp(now + expires_in, dt_timezone.utc),
                                  "count": new_state.get("count", 0), "data": None if "count" in new_state else new_state}
                        if row is None:
                            RateHit.objects.create(key=key, **values)
                        else:
                            RateHit.objects.filter(pk=row.pk).update(**values)
                    return allowed
            except IntegrityError:
                if attempt == 2:
                    raise
    except Exception:  # noqa: BLE001 - fail open, loudly
        logger.exception("Rate limit store unavailable for %s", scope)
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
