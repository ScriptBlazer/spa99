"""Uploaded lists (System > Emails > Groups): check a CSV with the strict invite checks, save it as a named list, add more, remove people,
rename, delete. Nothing here sends anything.

`review()` wraps `invites.check()` (unchanged: errors block, warnings are allowed, repeats merge, ambiguous and formula rows block) and
re-words it for a list. A row for someone who already has an account, is waiting on an invite, is suppressed or unsubscribed is still
SAVED, flagged: he stays on the list (the list is a record of who was uploaded), and every send leaves him out (mailings.segments reads
the suppression list, opt-outs and accounts when the send is made, so a later bounce or unsubscribe is honoured too).
Members are personal data: erased with the person (mailings.erasure) and exported with their data (users.services)."""
import csv
import io
import json
import uuid
from collections import Counter

from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from . import invites
from .models import ContactList, ContactListMember, InviteImport

NAME_MAX = 120
CATEGORY_MAX = 60
PAGE = 50
EXISTS = "exists"
# Rows with these statuses are saved (the last four flagged). Everything else is only in the report (repeats) or blocks.
SAVED = ("ok", "member", "invited", "suppressed", "opted_out")
FLAGGED = ("member", "invited", "suppressed", "opted_out")
LABELS = {
    "ok": "Will be saved",
    "invalid": invites.STATUS_LABELS["invalid"],
    "unsafe": invites.STATUS_LABELS["unsafe"],
    "ambiguous": invites.STATUS_LABELS["ambiguous"],
    "duplicate": "Exact repeat of an earlier row (saved once)",
    "case_duplicate": "Same email written differently (saved once)",
    "member": "Already has an account (saved; invitations skip him)",
    "invited": "Already invited and waiting (saved; invitations skip him)",
    "suppressed": "On the suppression list: bounced or complained (saved; never emailed)",
    "opted_out": "Unsubscribed (saved; never emailed)",
    EXISTS: "Already on this list (left alone)",
}
NO_NAME_LABEL = "No name (saved with a blank name)"


class ListError(Exception):
    """A plain-words reason a list could not be saved: {field: [messages]}."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, dict) else {"_": [str(errors)]}
        super().__init__(" ".join(m for ms in self.errors.values() for m in ms))


def categories():
    """Categories already used, for the suggestions on the form."""
    return sorted(set(ContactList.objects.exclude(category="").values_list("category", flat=True)), key=str.casefold)


def clean_name(name, exclude=None):
    name = " ".join((name or "").split())
    if not name:
        raise ListError({"name": ["Give the list a name."]})
    if len(name) > NAME_MAX:
        raise ListError({"name": [f"The name is longer than {NAME_MAX} characters."]})
    taken = ContactList.objects.filter(name__iexact=name)
    if exclude is not None:
        taken = taken.exclude(pk=exclude.pk)
    if taken.exists():
        raise ListError({"name": ["A list with this name already exists."]})
    return name


def clean_category(category):
    category = " ".join((category or "").split())
    if len(category) > CATEGORY_MAX:
        raise ListError({"category": [f"The category is longer than {CATEGORY_MAX} characters."]})
    return category


def review(raw, target=None):
    """The invite report, re-worded for a list. Adds: `ok` (people who will be saved), `flagged` (saved but never emailed / skipped by
    invitations), `exists` (already on `target`, left alone), `can_save`, a new `summary`, `groups` and `labels`. Writes nothing."""
    report = invites.check(raw)
    report["labels"] = LABELS
    if report["errors"]:
        report.update(can_save=False, flagged=0, exists=0)
        return report
    have = set(target.members.values_list("email", flat=True)) if target is not None else set()
    for item in report["rows"]:
        if item["email"] in have and item["status"] in SAVED:
            item["status"], item["level"], item["no_name"] = EXISTS, invites.WARNING, False
        if item["status"] in LABELS and not item["message"].startswith(("Appears on rows", "Same as row", "The name is longer")):
            item["message"] = "" if item["status"] == "ok" else LABELS[item["status"]]
        if item["status"] in FLAGGED:
            item["level"] = invites.WARNING
        if item["no_name"]:
            item["message"] = NO_NAME_LABEL
    choices = {}
    for item in report["rows"]:  # one address on rows with different names: the names to pick from
        if item["status"] == "ambiguous" and item["name"] and not any(item["name"].casefold() == n.casefold() for n in choices.setdefault(item["email"], [])):
            choices[item["email"]].append(item["name"])
    for item in report["rows"]:
        item["choices"] = choices.get(item["email"], []) if item["status"] == "ambiguous" else []
    counts = Counter(i["status"] for i in report["rows"])
    counts = {key: counts.get(key, 0) for key in LABELS}
    counts["no_name"] = sum(1 for i in report["rows"] if i["no_name"])
    saved = counts["ok"] + sum(counts[k] for k in FLAGGED)
    flagged = sum(counts[k] for k in FLAGGED)
    merged = counts["duplicate"] + counts["case_duplicate"]
    problems = report["problems"]
    groups = []
    for key, label in [*LABELS.items(), ("no_name", NO_NAME_LABEL)]:
        if key != "ok" and counts[key]:
            level = invites.ERROR if key in invites.ERROR_STATUSES else invites.WARNING
            lines = [i["line"] for i in report["rows"] if (i["no_name"] if key == "no_name" else i["status"] == key)]
            groups.append({"key": key, "label": label, "level": level, "count": counts[key], "lines": invites._lines(lines)})
    groups.sort(key=lambda g: g["level"] != invites.ERROR)
    parts = [f"{saved} will be saved"]
    if flagged:
        parts.append(f"{flagged} flagged (never emailed or skipped by invitations)")
    if counts[EXISTS]:
        parts.append(f"{counts[EXISTS]} already on the list")
    if merged:
        parts.append(f"{merged} repeated {'row' if merged == 1 else 'rows'} merged")
    if problems:
        parts.append(f"{problems} need{'s' if problems == 1 else ''} fixing")
    report.update(counts=counts, groups=groups, ok=saved, flagged=flagged, exists=counts[EXISTS], summary=" · ".join(parts),
                  warnings=sum(1 for i in report["rows"] if i["level"] == invites.WARNING), can_save=bool(saved) and not problems)
    return report


def apply_edits(raw, edits):
    """The list with fixes applied: `edits` is a JSON string or list of {line, name, email}, `line` being the row number the report shows. Every
    other row stays, in the same order and on the same line number (rows are written back as `name,email`; phone columns were ignored anyway).
    A row that was blocked as a formula stays blocked until its cell is edited. Returns the new text (the old one if it cannot be read)."""
    try:
        edits = json.loads(edits) if isinstance(edits, str) else edits
    except ValueError:
        return raw
    rows, errors = invites.parse(raw)
    if errors or not isinstance(edits, list):
        return raw
    by_line = {int(e["line"]): e for e in edits[:invites.MAX_ROWS] if isinstance(e, dict) and str(e.get("line", "")).isdigit()}
    lines = [""] * max(r["line"] for r in rows)
    if min(r["line"] for r in rows) > 1:
        lines[0] = "name,email"
    for row in rows:
        name, email = row["name"], row["email"]
        edit = by_line.get(row["line"])
        if edit is not None:
            name, email = str(edit.get("name", "")).strip(), str(edit.get("email", "")).strip()
        elif row["unsafe"] and not any(c.startswith(invites.FORMULA_START) for c in (name, email)):
            name = "\t" + name  # the leading character was cleaned away when read: keep the row blocked
        out = io.StringIO()
        csv.writer(out, lineterminator="").writerow([name, email])
        lines[row["line"] - 1] = out.getvalue().replace("\n", " ").replace("\r", " ")
    return "\n".join(lines)


def problem_lines(report):
    """Plain sentences for the Go back and fix page: 'Row 7: Not a valid email address.' Errors only, then whole-file problems."""
    lines = [f"Row {i['line']}: {i['message'].rstrip('.')}." for i in report["rows"] if i["level"] == invites.ERROR]
    return [f"{e.rstrip('.')}." for e in report["errors"]] + lines


def _event(kind, user, sentence, detail, request=None):
    from system import audit

    audit.log_event(kind, request, user=user, detail=detail, sentence=sentence[:1000])


def _members(lst, report):
    return [ContactListMember(list=lst, email=i["email"], name=i["name"][:100], source_row=i["line"], added_at=timezone.now())
            for i in report["rows"] if i["status"] in SAVED]


def _claim(token_row):
    """One conditional update claims the token (a double click, lag or two tabs save once). False when someone else already did."""
    if token_row is None:
        return True
    return bool(InviteImport.objects.filter(pk=token_row.pk, batch_id__isnull=True).update(batch_id=uuid.uuid4(), used_at=timezone.now()))


def existing_for(token_row):
    """The list a used token produced (None if the list was deleted since)."""
    return InviteImport.objects.get(pk=token_row.pk).contact_list


@transaction.atomic
def save_new(name, category, raw, user, token_row=None, request=None):
    """Check again and save a new list. Returns (list, report). Raises ListError (nothing written) while anything needs fixing or the name
    is taken. With a `token_row` a second save with the same token returns the first list with `report["existing"] = True`."""
    errors = {}
    try:
        name = clean_name(name)
    except ListError as error:
        errors.update(error.errors)
    try:
        category = clean_category(category)
    except ListError as error:
        errors.update(error.errors)
    report = review(raw)
    if report["errors"] or report["blocked"]:
        errors["_"] = report["errors"] or [f"{report['problems']} row(s) need fixing before the list is saved."]
    elif not report["ok"]:
        errors["_"] = ["There is nobody to save in this list."]
    if errors:
        raise ListError(errors)
    if not _claim(token_row):  # the winner's list is the answer; nothing is written here
        return existing_for(token_row), {**report, "existing": True}
    try:
        with transaction.atomic():
            lst = ContactList(name=name, category=category, created_by=user if getattr(user, "pk", None) else None)
            lst._history_user = user
            lst.save()
    except IntegrityError:
        raise ListError({"name": ["A list with this name already exists."]}) from None
    if token_row is not None:
        InviteImport.objects.filter(pk=token_row.pk).update(contact_list=lst)
    ContactListMember.objects.bulk_create(_members(lst, report), ignore_conflicts=True)
    _event("list_created", user, f"{getattr(user, 'email', '') or 'A script'} created the list '{lst.name}' with {report['ok']} people",
           {"list": str(lst.pk), "name": lst.name, "category": lst.category, "people": report["ok"], "flagged": report["flagged"]}, request)
    return lst, report


@transaction.atomic
def add_more(lst, raw, user, token_row=None, request=None):
    """Check again and merge the new addresses into `lst`; people already on it are left alone. Returns (added, report)."""
    report = review(raw, lst)
    if report["errors"] or report["blocked"]:
        raise ListError({"_": report["errors"] or [f"{report['problems']} row(s) need fixing before the list is saved."]})
    if not report["ok"]:
        raise ListError({"_": ["Nobody new to add: everyone is already on this list."]})
    if not _claim(token_row):
        return 0, {**report, "existing": True}
    if token_row is not None:
        InviteImport.objects.filter(pk=token_row.pk).update(contact_list=lst)
    ContactListMember.objects.bulk_create(_members(lst, report), ignore_conflicts=True)
    _event("list_changed", user, f"{getattr(user, 'email', '') or 'A script'} added {report['ok']} people to the list '{lst.name}'",
           {"list": str(lst.pk), "name": lst.name, "change": "added", "people": report["ok"], "flagged": report["flagged"]}, request)
    return report["ok"], report


def members_page(lst, query="", page=1):
    qs = lst.members.all()
    query = (query or "").strip()
    if query:
        qs = qs.filter(Q(email__icontains=query) | Q(name__icontains=query))
    return Paginator(qs.order_by(Lower("email")), PAGE).get_page(page)


def remove_member(lst, member_id, user, request=None):
    """Take one person off the list. Returns True if he was on it. The audit line holds no address."""
    removed = lst.members.filter(pk=member_id).delete()[0]
    if removed:
        _event("list_changed", user, f"{user.email} removed 1 person from the list '{lst.name}'", {"list": str(lst.pk), "name": lst.name, "change": "removed", "people": 1}, request)
    return bool(removed)


def edit(lst, user, name=None, category=None, request=None):
    """Rename and/or change the category (history keeps the old values). Raises ListError."""
    old = {"name": lst.name, "category": lst.category}
    new_name = clean_name(name, exclude=lst) if name is not None else lst.name
    new_category = clean_category(category) if category is not None else lst.category
    if (new_name, new_category) == (lst.name, lst.category):
        return False
    lst.name, lst.category = new_name, new_category
    lst._history_user = user
    try:
        lst.save()
    except IntegrityError:
        raise ListError({"name": ["A list with this name already exists."]}) from None
    _event("list_changed", user, f"{user.email} changed the list '{old['name']}' (now '{lst.name}', category '{lst.category}')",
           {"list": str(lst.pk), "change": "edited", "old": old, "new": {"name": lst.name, "category": lst.category}}, request)
    return True


def delete(lst, user, request=None):
    """Delete the list and its people (not the people's accounts or anything already sent)."""
    detail = {"list": str(lst.pk), "name": lst.name, "people": lst.members.count()}
    lst._history_user = user
    lst.delete()
    _event("list_deleted", user, f"{user.email} deleted the list '{detail['name']}' ({detail['people']} people)", detail, request)
