"""The audit log engine: the hash chain (seal, verify, prune) and security events (log_event).

Chain: every SystemChange and SystemEvent gets the next `seq` (one count across both tables), `prev_hash` (the hash of the
row before it) and `hash` = sha256(prev_hash + canonical JSON of its fields). The newest hash lives on the one AuditHead
row, which is locked while a row is added, so two writers can never take the same place. Edit a row and its hash no longer
matches; delete a row and the numbers jump; delete the newest and the head no longer matches. `verify_audit_log` walks it.

Pruning (retention) removes a whole oldest prefix and moves the anchor to the last removed row. Verification then starts
from the anchor: the first kept row must continue it. Older history is gone by design and cannot be verified any more."""
import hashlib
import heapq
import json
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from common.audit import client_ip
from common.jobs import tracked

from . import changes
from .models import AuditHead, SystemChange, SystemEvent

logger = logging.getLogger("spa99.audit")

# kind -> (category for the filter, section, outcome). Categories: security, failure, undo.
KINDS = {
    SystemEvent.SIGN_IN: ("security", "security", "ok"), SystemEvent.SIGN_IN_FAILED: ("failure", "security", "failed"),
    SystemEvent.UNLOCK: ("security", "security", "ok"), SystemEvent.UNLOCK_FAILED: ("failure", "security", "failed"),
    SystemEvent.UNLOCK_RATE_LIMITED: ("failure", "security", "blocked"), SystemEvent.LOCK_MANUAL: ("security", "security", "ok"),
    SystemEvent.LOCK_IDLE: ("security", "security", "ok"), SystemEvent.SIGN_OUT: ("security", "security", "ok"),
    SystemEvent.SESSION_EXPIRED: ("security", "security", "ok"), SystemEvent.ACCESS_DENIED: ("failure", "security", "blocked"),
    SystemEvent.ROLE_CHANGED: ("security", "team", "ok"), SystemEvent.USER_DEACTIVATED: ("security", "team", "ok"),
    SystemEvent.USER_REACTIVATED: ("security", "team", "ok"), SystemEvent.UNDO: ("undo", "changes", "ok"),
    SystemEvent.UNDO_ALL: ("undo", "changes", "ok"), SystemEvent.EXPORT: ("security", "changes", "ok"),
    SystemEvent.AUDIT_PRUNED: ("security", "changes", "ok"), SystemEvent.AUDIT_CHECK: ("security", "changes", "ok"), SystemEvent.JOB_RUN: ("security", "security", "ok"),
}
CATEGORIES = [("change", "Changes"), ("security", "Security"), ("undo", "Undos"), ("failure", "Failures")]
EVENT_SECTION_LABELS = {"security": "Security", "changes": "Change log"}


def kinds_in(category):
    return [kind for kind, (cat, _s, _o) in KINDS.items() if cat == category]


def category_of_event(kind):
    return KINDS.get(kind, ("security",))[0]


# ---------- the hash chain ----------

def _plain(value):
    if isinstance(value, datetime):
        return value.astimezone(dt_timezone.utc).isoformat()
    return str(value)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_plain)


def digest(prev_hash, payload):
    return hashlib.sha256((prev_hash + canonical(payload)).encode()).hexdigest()


def seal(row):
    """Give a new row its place in the chain. Called inside the row's save(), in its transaction, with the head locked."""
    head = AuditHead.lock()
    row.seq = head.last_seq + 1
    row.prev_hash = head.last_hash
    row.hash = digest(row.prev_hash, row.hash_payload())
    AuditHead.objects.filter(pk=1).update(last_seq=row.seq, last_hash=row.hash)


def _walk(limit):
    """Rows with seq up to `limit` (the head as read at the start), so a row written while we walk is not 'unexpected'."""
    streams = [SystemChange.objects.filter(seq__isnull=False, seq__lte=limit).order_by("seq").iterator(),
               SystemEvent.objects.filter(seq__isnull=False, seq__lte=limit).order_by("seq").iterator()]
    return heapq.merge(*streams, key=lambda row: row.seq)


def verify():
    """Walk the chain from the anchor. Returns a dict: ok, checked, legacy (rows older than the chain, not covered),
    message, and `broken` (model name, id, seq) for the first bad row."""
    head = AuditHead.objects.filter(pk=1).first()
    anchor_seq, anchor_hash = (head.anchor_seq, head.anchor_hash) if head else (0, "")
    legacy = SystemChange.objects.filter(seq__isnull=True).count() + SystemEvent.objects.filter(seq__isnull=True).count()
    expected_seq, prev, checked = anchor_seq + 1, anchor_hash, 0

    def bad(row, why):
        return {"ok": False, "checked": checked, "legacy": legacy, "broken": (type(row).__name__, str(row.pk), row.seq),
                "message": f"BROKEN at {type(row).__name__} {row.pk} (number {row.seq}): {why}"}

    last_seq, last_hash = (head.last_seq, head.last_hash) if head else (anchor_seq, anchor_hash)
    for row in _walk(last_seq):
        if row.seq < expected_seq:
            return bad(row, "the number appears twice or is out of order")
        if row.seq > expected_seq:
            return {"ok": False, "checked": checked, "legacy": legacy, "broken": ("missing", "", expected_seq),
                    "message": f"BROKEN: row number {expected_seq} is missing (a row was deleted); next row is {row.seq}"}
        if row.prev_hash != prev:
            return bad(row, "it does not continue the row before it")
        if digest(row.prev_hash, row.hash_payload()) != row.hash:
            return bad(row, "its content no longer matches its hash (edited)")
        prev, expected_seq, checked = row.hash, expected_seq + 1, checked + 1
    if expected_seq - 1 != last_seq or prev != last_hash:
        return {"ok": False, "checked": checked, "legacy": legacy, "broken": ("missing", "", expected_seq),
                "message": f"BROKEN: the newest row(s) are missing (chain ends at {expected_seq - 1}, the log says {last_seq})"}
    note = f" {legacy} older row(s) from before the chain are not covered." if legacy else ""
    pruned = f" History up to number {anchor_seq} was pruned (anchor)." if anchor_seq else ""
    return {"ok": True, "checked": checked, "legacy": legacy, "broken": None, "message": f"OK: {checked} row(s) verified.{pruned}{note}"}


@tracked("audit_verify")
def check_and_store():
    """Run the full verify and store the result on the head row. Returns the verify() dict. Never call this on a page load."""
    result = verify()
    broken = result["broken"] or ("", "", None)
    AuditHead.objects.get_or_create(pk=1)
    AuditHead.objects.filter(pk=1).update(
        verified_at=timezone.now(), verify_ok=result["ok"], verify_entries=result["checked"],
        verify_broken_id=broken[1] if broken[0] != "missing" else "", verify_broken_seq=broken[2], verify_message=result["message"][:300])
    return result


def scheduled():
    """django-q2 entry point (hourly, common register_schedules). Returns a status string."""
    return check_and_store()["message"]


def stored_status():
    """The last stored verification for the page ({ok, verified_at, checked_at, entries, broken_at_id, broken_seq, message}), or
    None when no check has run yet. One tiny query."""
    head = AuditHead.objects.filter(pk=1).first()
    if head is None or head.verified_at is None:
        return None
    return {"ok": bool(head.verify_ok), "verified_at": head.verified_at, "checked_at": head.verified_at, "entries": head.verify_entries,
            "broken_at_id": head.verify_broken_id, "broken_seq": head.verify_broken_seq, "message": head.verify_message}


def prune(days, dry_run=False):
    """Remove audit rows older than `days` (the oldest prefix of the chain) and move the anchor. 0 = keep forever.
    Returns {"cutoff", "changes", "events", "anchor_seq"}; nothing is touched on a dry run."""
    if not days:
        return {"cutoff": None, "changes": 0, "events": 0, "anchor_seq": None}
    cutoff = timezone.now() - timedelta(days=days)
    with transaction.atomic():
        head = AuditHead.lock()
        newer = [qs.filter(created_at__gte=cutoff, seq__isnull=False).order_by("seq").values_list("seq", flat=True).first()
                 for qs in (SystemChange.objects, SystemEvent.objects)]
        newer = [s for s in newer if s is not None]
        first_kept = min(newer) if newer else head.last_seq + 1  # everything is old: keep nothing, anchor at the head
        old_changes = SystemChange.objects.filter(seq__isnull=False, seq__lt=first_kept)
        old_events = SystemEvent.objects.filter(seq__isnull=False, seq__lt=first_kept)
        # legacy rows (no seq) that are older than the cutoff go too; they were never chained
        legacy_changes = SystemChange.objects.filter(seq__isnull=True, created_at__lt=cutoff)
        legacy_events = SystemEvent.objects.filter(seq__isnull=True, created_at__lt=cutoff)
        result = {"cutoff": cutoff, "changes": old_changes.count() + legacy_changes.count(),
                  "events": old_events.count() + legacy_events.count(), "anchor_seq": head.anchor_seq}
        if dry_run or first_kept - 1 <= head.anchor_seq:
            if not dry_run:
                legacy_changes._prune_delete()
                legacy_events._prune_delete()
            return result
        anchor_seq = first_kept - 1
        last = (SystemChange.objects.filter(seq=anchor_seq).first() or SystemEvent.objects.filter(seq=anchor_seq).first())
        anchor_hash = last.hash if last else head.anchor_hash
        # the 'undo of' link on kept rows would point at a removed row: clear it (it is not sealed)
        SystemChange.objects.filter(undo_of__in=old_changes.values("pk")).exclude(pk__in=old_changes.values("pk"))._prune_update(undo_of=None)
        old_changes._prune_delete()
        old_events._prune_delete()
        legacy_changes._prune_delete()
        legacy_events._prune_delete()
        AuditHead.objects.filter(pk=1).update(anchor_seq=anchor_seq, anchor_hash=anchor_hash)
        result["anchor_seq"] = anchor_seq
    log_event(SystemEvent.AUDIT_PRUNED, detail={"changes": result["changes"], "events": result["events"], "anchor_seq": anchor_seq,
                                                 "older_than_days": days},
              sentence=f"Removed {result['changes']} change(s) and {result['events']} event(s) older than {days} days")
    return result


# ---------- security events ----------

def request_info(request=None):
    """IP, browser and path of this request (or of the System request being served when none is given)."""
    if request is not None:
        return {"ip_address": (client_ip(request) or "")[:45], "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
                "path": request.path[:200], "batch_id": changes.current_batch()}
    return changes.current_info()


def default_sentence(kind, email, detail):
    who = email or "Someone"
    return {
        SystemEvent.SIGN_IN: f"{who} signed in",
        SystemEvent.SIGN_IN_FAILED: f"Sign-in failed for {email or 'an unknown email'}" + (" (too many tries, blocked)" if detail.get("rate_limited") else ""),
        SystemEvent.UNLOCK: f"{who} unlocked System",
        SystemEvent.UNLOCK_FAILED: f"{who} typed the wrong password to unlock",
        SystemEvent.UNLOCK_RATE_LIMITED: f"{who} was blocked from unlocking (too many wrong passwords)",
        SystemEvent.LOCK_MANUAL: f"{who} locked System",
        SystemEvent.LOCK_IDLE: f"System locked after {int(detail.get('idle_seconds', 0)) // 60} idle minutes ({who})",
        SystemEvent.SIGN_OUT: f"{who} signed out",
        SystemEvent.SESSION_EXPIRED: f"{who}'s sign-in ended (the {int(detail.get('max_hours', 0))} hour limit)",
        SystemEvent.ACCESS_DENIED: f"Someone without access tried {detail.get('method', 'GET')} {detail.get('path', '')}".strip(),
        SystemEvent.UNDO: f"{who} undid a change",
        SystemEvent.UNDO_ALL: f"{who} undid {detail.get('count', 0)} changes saved together",
        SystemEvent.EXPORT: f"{who} exported {detail.get('rows', 0)} audit rows to CSV",
    }.get(kind, f"{who}: {kind}")


def recent_exists(kind, ip, label, seconds):
    """Was this kind already written from this IP (and person, unless label is None) in the last `seconds`?"""
    rows = SystemEvent.objects.filter(kind=kind, ip_address=ip, created_at__gte=timezone.now() - timedelta(seconds=seconds))
    return (rows if label is None else rows.filter(user_label=label)).exists()


def log_event(kind, request=None, user=None, email="", outcome=None, detail=None, sentence="", section=None, dedupe_seconds=0, dedupe_any_person=False):
    """Write one security event. Never raises (a broken log must not lock people out); returns the row or None.
    `dedupe_seconds`: skip when the same kind from the same IP and person was already written in that window."""
    detail = dict(detail or {})
    try:
        info = request_info(request)
        user = user if user is not None and getattr(user, "pk", None) else None
        label = (getattr(user, "email", "") or email or "")[:254]
        category, default_section, default_outcome = KINDS[kind]
        if dedupe_seconds and recent_exists(kind, info["ip_address"], None if dedupe_any_person else label, dedupe_seconds):
            return None
        with transaction.atomic():
            return SystemEvent.objects.create(
                kind=kind, outcome=outcome or default_outcome, section=section or default_section, user=user, user_label=label,
                sentence=(sentence or default_sentence(kind, label, detail))[:1000], detail=detail, **info)
    except Exception:
        logger.exception("Could not write System audit event %s", kind)
        return None


def note_access_denied(request):
    """Someone who may not be on System asked for a page. One row per IP per hour, and at most 300 an hour in all, so a
    scanner cannot flood the log. Coarse on purpose: method and path, no body."""
    from common.ratelimit import hit

    ip = (client_ip(request) or "")[:45]
    if recent_exists(SystemEvent.ACCESS_DENIED, ip, None, 3600):  # first: a repeat from one IP must not spend the shared budget
        return None
    if not hit("system-denied-total", "all", 300, 3600):
        return None
    user = getattr(request, "user", None)
    return log_event(SystemEvent.ACCESS_DENIED, request, user=user if user is not None and user.is_authenticated else None,
                     detail={"method": request.method, "path": request.path[:200]})
