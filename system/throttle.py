"""Wrong-try feedback with an escalating wait, for the System sign-in and the unlock (and the undo code check).

Rules: 5 wrong tries in a row lock for 1 minute; once the wait is over each further wrong try (no success between) locks
again for one minute more (2, 3, 4 ...), at most 60. Success clears the keys; 24 hours without an attempt forgets them.
While waiting nothing is checked and blocked hits are not counted. All timing is the server's (`time.time`).

Counted BEFORE the secret is checked, atomically (`reserve`): a row per key (`system.WrongTries`) is bumped with an F()
update, so parallel requests get distinct numbers and at most the tries left are verified. Whoever reaches the limit takes
the wait with a conditional UPDATE (`locked_until <= now`), which only one request can win; the others are refused without
being verified. Works the same on SQLite and Postgres. Keys are hashed; no email or IP is stored in clear.
"""
import hashlib
import ipaddress
import math
import time
import unicodedata
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F

from common.audit import client_ip

from .models import WrongTries

FREE_TRIES = 6  # Moishe 2026-10-29: the first wrong try says "5 more tries"
MAX_WAIT_MINUTES = 60
QUIET_SECONDS = 24 * 3600


@dataclass(frozen=True)
class Bucket:
    scope: str
    identifier: str
    limit: int = FREE_TRIES  # tries in a row before the first wait

    @property
    def key(self):
        return hashlib.sha256(f"{self.scope}|{self.identifier}".encode()).hexdigest()[:64]


def network_of(address):
    """The IP as a bucket key: IPv4 as is, IPv6 as its /64 (one home or phone gets a whole /64, so a new address inside it
    must not reset the count)."""
    try:
        ip = ipaddress.ip_address((address or "").strip())
    except ValueError:
        return address or "unknown"
    if ip.version == 6:
        ip = ip.ipv4_mapped or ip
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def email_key(email):
    return unicodedata.normalize("NFKC", email or "").strip().casefold()[:254] or "-"


def sign_in_buckets(request, email):
    ip, who = network_of(client_ip(request)), email_key(email)
    return [Bucket("signin", f"{who}|{ip}"), Bucket("signin-ip", ip, limit=2 * FREE_TRIES), Bucket("signin-email", who, limit=50)]


def sign_in_success_buckets(buckets):
    """A good sign-in clears the email+IP and per-email counters, not the per-IP one (a spray must not be undone by one login)."""
    return [b for b in buckets if b.scope != "signin-ip"]


def unlock_buckets(request):
    ip, pk = network_of(client_ip(request)), str(request.user.pk)
    return [Bucket("unlock", f"{pk}|{ip}"), Bucket("unlock-person", pk, limit=2 * FREE_TRIES)]  # the person cap holds whatever the address


@dataclass(frozen=True)
class Reservation:
    allowed: bool  # True: verify the secret now. False: waiting, verify nothing
    wait: int  # seconds to wait (0 = none)
    left: int  # tries left after this one (if it is wrong)
    started: bool  # this try began a wait (log it once)


def _rows(buckets, now):
    return {r.key: r for r in WrongTries.objects.filter(key__in=[b.key for b in buckets])
            if now - r.last_at <= QUIET_SECONDS}  # a quiet day: the old count no longer counts


def wait_seconds(buckets, now=None):
    """Whole seconds left of the longest wait on these buckets (0 = free to try)."""
    now = time.time() if now is None else now
    left = max((r.locked_until - now for r in _rows(buckets, now).values()), default=0)
    return math.ceil(left) if left > 0 else 0  # a wait that has ended is 0 (never rounded up from a negative)


def reserve(buckets, now=None):
    """Count one try on every bucket, atomically, before the secret is checked."""
    now = time.time() if now is None else now
    waiting = wait_seconds(buckets, now)
    if waiting:
        return Reservation(False, waiting, 0, False)
    WrongTries.objects.filter(last_at__lt=now - QUIET_SECONDS).delete()
    started, refused, left = False, False, FREE_TRIES
    with transaction.atomic():
        for b in buckets:
            row, _ = WrongTries.objects.get_or_create(key=b.key)
            if now - row.last_at > QUIET_SECONDS:
                WrongTries.objects.filter(key=b.key).update(count=0, locked_until=0)
            WrongTries.objects.filter(key=b.key).update(count=F("count") + 1, last_at=now)
            number = WrongTries.objects.values_list("count", flat=True).get(key=b.key)
            left = min(left, max(b.limit - number, 0))
            if number >= b.limit:
                minutes = min(number - b.limit + 1, MAX_WAIT_MINUTES)
                # one winner: only a request that still sees the old (expired) wait can set the new one
                won = WrongTries.objects.filter(key=b.key, locked_until__lte=now).update(locked_until=now + minutes * 60)
                started = started or bool(won)
                refused = refused or not won
    if refused:
        return Reservation(False, wait_seconds(buckets, now) or 1, 0, False)
    return Reservation(True, wait_seconds(buckets, now), left, started)


def refund(buckets):
    """Give back this request's own count (a good sign-in must not use up the per-IP allowance, nor erase the wrong tries)."""
    for b in buckets:
        WrongTries.objects.filter(key=b.key, count__gt=0).update(count=F("count") - 1)


def clear(buckets):
    WrongTries.objects.filter(key__in=[b.key for b in buckets]).delete()


def clock(seconds):
    """1:05 style text for a countdown."""
    return f"{seconds // 60}:{seconds % 60:02d}"


def spoken(seconds):
    minutes, rest = divmod(seconds, 60)
    parts = ([f"{minutes} minute{'s' if minutes != 1 else ''}"] if minutes else []) + ([f"{rest} second{'s' if rest != 1 else ''}"] if rest else [])
    return " ".join(parts) or "0 seconds"


def tries_text(left):
    return f"{left} more tr{'y' if left == 1 else 'ies'}"


def lock_context(seconds):
    """Template context for the locked state (server-rendered; the script only ticks it)."""
    return {"locked_seconds": seconds, "locked_clock": clock(seconds), "locked_spoken": spoken(seconds)} if seconds else {}
