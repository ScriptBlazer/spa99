"""Preview and apply for the code view. Both answer (HTTP status, JSON payload); the views only carry them.

Apply is one transaction: the stale check, the page's forms saved through `services.save_form` (every field a normal change-log
entry sharing the request's batch id), closure removals through `services.delete_logged`, and the `code_edit` audit event. Any
failure rolls everything back, the event included: a code edit is never saved without its audit row."""
import difflib
import hashlib
import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .. import audit, changes, services
from ..models import SystemEvent
from . import adapters, render
from .parse import CodeError, check_size, error, parse
from .plan import plan_changes

logger = logging.getLogger("spa99.codeview")
DIFF_CAP = 20 * 1024
TRUNCATED = "... diff truncated (20 KB limit)"
NOTHING = "Nothing to change."
RISKY_MESSAGE = "This changes values that need a second look. Review them and confirm to apply."
AUDIT_MESSAGE = "The audit log could not be written, so nothing was saved."


class Refused(Exception):
    def __init__(self, status, payload):
        super().__init__(payload.get("message", ""))
        self.status, self.payload = status, payload


def _errors(errors, status=400, **extra):
    return status, {"ok": False, "message": errors[0]["message"] if errors else "Error", "errors": errors, **extra}


def _stale(section):
    code, version = render.render(section)
    return 409, {"ok": False, "message": services.STALE_MESSAGE, "code": code, "version": version}


def unified(before, after):
    return "\n".join(difflib.unified_diff(before.splitlines(), after.splitlines(), "saved", "edited", lineterm="", n=3))


def cap_diff(text):
    """(text, truncated): the diff cut at whole lines to about 20 KB, with a marker line when cut."""
    if len(text) <= DIFF_CAP:
        return text, False
    return text[:DIFF_CAP].rsplit("\n", 1)[0] + "\n" + TRUNCATED, True


def diff_lines(text):
    """A unified diff as rows for the page: [{type: add|del|ctx|hunk, text, old, new}] (old/new are line numbers or None)."""
    rows, old, new = [], 0, 0
    for line in (text or "").splitlines():
        if line.startswith(("--- ", "+++ ")) and not rows:
            continue
        if line.startswith("@@"):
            parts = line.split()
            try:
                old, new = int(parts[1].split(",")[0].lstrip("-")), int(parts[2].split(",")[0].lstrip("+"))
            except (IndexError, ValueError):
                pass
            rows.append({"type": "hunk", "text": line, "old": None, "new": None})
        elif line.startswith("+"):
            rows.append({"type": "add", "text": line[1:], "old": None, "new": new})
            new += 1
        elif line.startswith("-"):
            rows.append({"type": "del", "text": line[1:], "old": old, "new": None})
            old += 1
        elif line.startswith(" "):
            rows.append({"type": "ctx", "text": line[1:], "old": old, "new": new})
            old, new = old + 1, new + 1
        else:  # the truncation marker
            rows.append({"type": "hunk", "text": line, "old": None, "new": None})
    return rows


def _plan(section, code):
    """(current code, plan) or raises Refused for a stale version, size, syntax or validation problem. Reads only."""
    parsed = parse(section, code)
    plan = plan_changes(section, parsed)
    if plan.stale:
        raise Refused(*_stale(section))
    plan.raise_if_errors()
    return plan


def get(section_key):
    section = adapters.get(section_key)
    code, version = render.render(section)
    return {"code": code, "version": version, "section": section.key, "title": section.title}


def preview(section_key, code, version):
    section, now = adapters.get(section_key), timezone.now()
    try:
        check_size(code)
        current, fresh = render.render(section, now)
        if version != fresh:
            return _stale(section)
        plan = _plan(section, code)
    except CodeError as exc:
        return _errors(exc.errors, exc.status)
    except Refused as exc:
        return exc.status, exc.payload
    diff = unified(current, render.swap_header(code, section, now))
    return 200, {"ok": True, "section": section.key, "changes": plan.changes, "creates": plan.creates, "deletes": plan.deletes,
                 "diff": diff, "diff_lines": diff_lines(diff), "risky": plan.risky, "count": plan.total}


def apply(request, section_key, code, version, confirm_risky=False):
    section, now, user = adapters.get(section_key), timezone.now(), request.user
    try:
        check_size(code)
        with transaction.atomic():
            before, fresh = render.render(section, now)
            if version != fresh:
                raise Refused(*_stale(section))
            plan = _plan(section, code)
            if plan.empty:
                return 200, {"ok": True, "message": NOTHING, "changed": 0, "code": before, "version": fresh}
            if plan.risky and not confirm_risky:
                raise Refused(400, {"ok": False, "message": RISKY_MESSAGE, "errors": [], "needs_confirm": True, "risky": True,
                                    "changes": plan.changes, "creates": plan.creates, "deletes": plan.deletes})
            for form, at in plan.forms:
                try:
                    services.save_form(form, user)
                except ValidationError as exc:
                    if services.STALE_MESSAGE in exc.messages:
                        raise Refused(*_stale(section)) from None
                    raise Refused(*_errors([error(at[0], at[1], " ".join(exc.messages))])) from None
            for row in plan.removals:
                services.delete_logged(row, user)
            after, after_version = render.render(section, now)
            diff, truncated = cap_diff(unified(before, after))
            noun = "change" if plan.total == 1 else "changes"
            try:
                event = audit.log_event(
                    SystemEvent.CODE_EDIT, request, user=user, section=section.key,
                    sentence=f"{user.email} edited {section.title} as code ({plan.total} {noun})",
                    detail={"section": section.key, "title": section.title, "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                            "after_sha256": hashlib.sha256(after.encode()).hexdigest(), "diff": diff, "diff_truncated": truncated,
                            "changed_fields": len(plan.changes), "changes": plan.total, "added": len(plan.creates), "removed": len(plan.deletes)})
            except Exception:  # noqa: BLE001 - whatever stops the audit row stops the save
                logger.exception("code_edit audit event failed")
                event = None
            if event is None:
                raise Refused(500, {"ok": False, "message": AUDIT_MESSAGE})
    except CodeError as exc:
        return _errors(exc.errors, exc.status)
    except Refused as exc:
        return exc.status, exc.payload
    except IntegrityError:
        return _errors([error(1, 1, "A row clashes with another one (a value that must be unique is used twice).")])
    return 200, {"ok": True, "message": f"Saved {plan.total} {noun}.", "changed": plan.total,
                 "undo_url": services.undo_url_for_batch(changes.current_batch()), "code": after, "version": after_version}
