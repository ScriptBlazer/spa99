"""The cursor of a short-polling endpoint (?since=...)."""
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone


def parse_cursor(value):
    """An aware datetime from the `since` query value, or None when it is missing or not a usable cursor (not a date, or absurd: `0001-01-01` overflows when the poll
    subtracts its look-back windows). A bad cursor is treated like no cursor: the page just gets the new messages."""
    if not value:
        return None
    try:
        since = datetime.fromisoformat(value)
        if timezone.is_naive(since):
            since = timezone.make_aware(since)
        if not 2000 <= since.astimezone(dt_timezone.utc).year <= 2100:
            return None
        return since
    except (ValueError, OverflowError):
        return None
