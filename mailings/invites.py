"""Lists and invites: read a pasted list or CSV and check it (used to save an uploaded list), follow the personal invite link, and notice the sign-up.
The one-time token (InviteImport) guards a list save against a double click.

The import never trusts the file: every row is parsed and checked here, and the server checks it again when the list is saved
(the review page is only a preview). Two levels: errors (invalid, unsafe, ambiguous rows and whole-file problems) block the import until
fixed; warnings (repeats, members, already invited, suppressed, unsubscribed, no name) are allowed and the row is skipped or merged."""
import csv
import hashlib
import io
import re
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from common.validators import normalise_email
from notifications.models import EmailSuppression
from users.models import User

from .models import EmailOptOut, Invite, InviteImport

MAX_ROWS = 2000
MAX_BYTES = 1024 * 1024
NAME_MAX = 100
SESSION_KEY = "invite_token"
TOKEN_DAYS = 7

ERROR, WARNING, OK = "error", "warning", "ok"
# status -> (level, label). Errors block the import until fixed; warnings are allowed and the row is skipped or merged as the label says.
STATUSES = {
    "ok": (OK, "Will be invited"),
    "invalid": (ERROR, "Not a valid email address"),
    "unsafe": (ERROR, "Starts with = + - or @ (a spreadsheet could run it as a formula)"),
    "ambiguous": (ERROR, "Same email with different names"),
    "duplicate": (WARNING, "Exact repeat of an earlier row (imported once)"),
    "case_duplicate": (WARNING, "Same email written differently (imported once)"),
    "member": (WARNING, "Already has an account (skipped)"),
    "invited": (WARNING, "Already invited and waiting (skipped)"),
    "suppressed": (WARNING, "On the suppression list: bounced or complained (skipped)"),
    "opted_out": (WARNING, "Unsubscribed (skipped)"),
}
STATUS_LABELS = {key: label for key, (_, label) in STATUSES.items()}
ERROR_STATUSES = tuple(k for k, (level, _) in STATUSES.items() if level == ERROR)
NO_NAME_LABEL = "No name (invited with a blank name)"
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_ANGLE = re.compile(r"^\s*(?P<name>.*?)\s*<(?P<email>[^<>]+)>\s*$")
_EMAIL_HEADS = {"email", "emailaddress", "mail", "emailaddr", "youremail", "primaryemail", "emails"}
_NAME_HEADS = {"name", "fullname", "contactname", "customername"}
_FIRST_HEADS = {"firstname", "first", "givenname", "forename"}
_LAST_HEADS = {"lastname", "last", "surname", "familyname"}


def _key(cell):
    return re.sub(r"[^a-z]", "", (cell or "").lower())


def decode(raw):
    """(text, error) from bytes: UTF-8 (BOM fine), UTF-16 with BOM, else Windows-1252 (what Excel on a PC or Mac writes). Never raises."""
    if isinstance(raw, str):
        return raw.lstrip("\ufeff"), ""
    if len(raw) > MAX_BYTES:
        return "", f"The list is larger than {MAX_BYTES // 1024 // 1024} MB."
    if raw[:4] == b"PK\x03\x04":
        return "", "That looks like an Excel file, not a CSV. In Excel choose Save As > CSV and upload that."
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16").lstrip("\ufeff"), ""
        except UnicodeDecodeError:
            return "", "The file could not be read (text encoding). Save it as CSV (UTF-8) and try again."
    if b"\x00" in raw:
        return "", "That does not look like a CSV text file. Save it as CSV (UTF-8) and try again."
    try:
        return raw.decode("utf-8-sig"), ""
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252"), ""
    except UnicodeDecodeError:
        return "", "The file could not be read (text encoding). Save it as CSV (UTF-8) and try again."


def canonical(text):
    """The list as the server reads it: one newline style. The import token is tied to the hash of this (browsers change line ends)."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def content_hash(text, scope=""):
    """Hash of the list as the server reads it. `scope` ties it to what it is for (the id of the list being added to), so a token for one
    target cannot save into another."""
    return hashlib.sha256(f"{scope}\0{canonical(text)}".encode("utf-8")).hexdigest()


def _delimiter(sample):
    sample = re.sub(r'"[^"]*"', "", sample)
    counts = {d: sample.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _clean_name(value):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", value or "")).strip(' "')


def _split_row(cells):
    """(name, raw email text) from one row with no header: the cell holding an @ is the address, the other cells are the name."""
    cells = [c.strip() for c in cells if c and c.strip()]
    for index, cell in enumerate(cells):
        if "@" in cell:
            match = _ANGLE.match(cell)
            if match:  # Name <a@b.c>
                name = " ".join(filter(None, [match.group("name").strip(' "'), *cells[:index], *cells[index + 1:]]))
                return name.strip(), match.group("email").strip()
            return " ".join(cells[:index] + cells[index + 1:]).strip(), cell
    if len(cells) > 1:  # no @ anywhere: the last cell is the (invalid) address, shown to the person as typed
        return " ".join(cells[:-1]).strip(), cells[-1]
    return "", cells[0] if cells else ""


def _columns(cells):
    """The header's column plan {email, name, first, last} (cell indexes), or None when this row is not a header."""
    keys = [_key(c) for c in cells]
    plan = {"email": None, "name": [], "first": [], "last": []}
    for index, key in enumerate(keys):
        if key in _EMAIL_HEADS and plan["email"] is None:
            plan["email"] = index
        elif key in _NAME_HEADS:
            plan["name"].append(index)
        elif key in _FIRST_HEADS:
            plan["first"].append(index)
        elif key in _LAST_HEADS:
            plan["last"].append(index)
    known = plan["email"] is not None or plan["name"] or plan["first"] or plan["last"]
    return plan if known else None


def _from_plan(cells, plan):
    cell = lambda i: cells[i].strip() if i < len(cells) else ""  # noqa: E731
    email = cell(plan["email"])
    match = _ANGLE.match(email)
    extra = ""
    if match:
        email, extra = match.group("email").strip(), match.group("name").strip(' "')
    parts = [cell(i) for i in plan["first"] + plan["name"] + plan["last"]]
    return " ".join(filter(None, [*parts, extra])), email


def parse(raw):
    """(rows, file_errors). rows: [{"line", "name", "email" (as typed), "unsafe"}]. `line` is the row number in the file (header = 1).
    Whole-file errors: unreadable, empty, over 1 MB or 2000 rows, no email column. Reads , ; or tab, quotes (also across lines), a BOM, a header
    in many spellings (Email, E-mail, Email Address; Name, or First name + Last name) or no header."""
    text, error = decode(raw)
    if error:
        return [], [error]
    text = canonical(text)
    if len(text.encode("utf-8")) > MAX_BYTES:
        return [], [f"The list is larger than {MAX_BYTES // 1024 // 1024} MB."]
    first_line = next((line for line in text.split("\n") if line.strip()), "")
    if not first_line:
        return [], ["The list is empty."]
    reader = csv.reader(io.StringIO(text), delimiter=_delimiter(first_line), skipinitialspace=True)
    rows, plan, seen_first, last_line = [], None, False, 0
    try:
        for cells in reader:
            number, last_line = last_line + 1, reader.line_num
            if not any(c.strip() for c in cells):
                continue
            if not seen_first:
                seen_first = True
                if not any("@" in c for c in cells):
                    plan = _columns(cells)
                    if plan is not None:
                        if plan["email"] is None:
                            return [], ["There is no email column. The first row should say Email (or Email Address) above the addresses."]
                        continue
            name, email = _from_plan(cells, plan) if plan else _split_row(cells)
            used = cells if plan is None else [cells[i] for i in [plan["email"], *plan["first"], *plan["name"], *plan["last"]] if i < len(cells)]
            unsafe = any(c.strip().startswith(FORMULA_START) for c in used)  # extra columns (a phone like +44...) are ignored
            rows.append({"line": number, "name": _clean_name(name)[:NAME_MAX * 3], "email": email.strip(), "unsafe": unsafe})
            if len(rows) > MAX_ROWS:
                return [], [f"The list has more than {MAX_ROWS} rows. Split it into smaller lists."]
    except csv.Error:
        return [], ["The file could not be read as a CSV (a quote or a very long cell is broken). Check it and try again."]
    if not rows:
        return [], ["No email addresses were found."]
    return rows, []


def _chunks(items, size=500):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _existing(model, field, emails, **filters):
    found = set()
    for chunk in _chunks(emails):
        found |= {e.lower() for e in model.objects.filter(**{f"{field}__in": chunk}, **filters).values_list(field, flat=True)}
    return found


def _same_name(a, b):
    return a.casefold() == b.casefold()


def _lines(numbers, limit=20):
    shown = ", ".join(str(n) for n in numbers[:limit])
    return shown + (f" and {len(numbers) - limit} more" if len(numbers) > limit else "")


def _empty(errors):
    return {"rows": [], "counts": {}, "errors": errors, "ok": 0, "total": 0, "problems": 0, "warnings": 0, "blocked": True, "can_import": False,
            "groups": [], "summary": "", "skipped": 0, "merged": 0}


def check(raw):
    """The validation report. Nothing is written.
    {"rows": [{line, name, email, status, level, message, no_name}], "counts": {status: n, "no_name": n}, "errors": [file-level], "ok": n,
    "total": n, "problems": rows to fix, "warnings": rows with a heads-up, "blocked": True while anything must be fixed, "can_import",
    "groups": [{key, label, level, count, lines}] for every category that has rows, "summary": one line}."""
    rows, errors = parse(raw)
    if errors:
        return _empty(errors)
    report, by_email = [], {}
    for row in rows:
        item = {"line": row["line"], "name": row["name"], "email": row["email"], "status": "ok", "message": "", "no_name": False, "_typed": row["email"]}
        try:
            item["email"] = normalise_email(row["email"])
        except ValidationError:
            item["status"] = "invalid"
        if row["unsafe"]:
            item["status"] = "unsafe"
        elif len(row["name"]) > NAME_MAX:
            item["status"], item["message"] = "invalid", f"The name is longer than {NAME_MAX} characters."
        if item["status"] == "ok":
            by_email.setdefault(item["email"], []).append(item)
        report.append(item)
    candidates = []
    for email, items in by_email.items():
        names = []
        for item in items:
            if item["name"] and not any(_same_name(item["name"], n) for n in names):
                names.append(item["name"])
        if len(names) > 1:  # one address, two people: we cannot know which name is right
            for item in items:
                item["status"] = "ambiguous"
                item["message"] = f"Appears on rows {_lines([i['line'] for i in items])} with different names ({', '.join(names)})."
            continue
        first = items[0]
        first["name"] = first["name"] or (names[0] if names else "")
        candidates.append(email)
        for item in items[1:]:
            exact = item["_typed"] == first["_typed"] and (not item["name"] or item["name"] == first["name"])
            item["status"] = "duplicate" if exact else "case_duplicate"
            item["message"] = f"Same as row {first['line']}."
    members = _existing(User, "email", candidates)
    # case-insensitive match on stored emails: users are saved lower case, invites too (Invite.save)
    suppressed = _existing(EmailSuppression, "email", candidates)
    opted_out = _existing(EmailOptOut, "email", candidates)
    invited = _existing(Invite, "email", candidates, status__in=Invite.PENDING, expires_at__gt=timezone.now())
    for item in report:
        if item["status"] == "ok":
            for status, group in (("member", members), ("suppressed", suppressed), ("opted_out", opted_out), ("invited", invited)):
                if item["email"] in group:
                    item["status"] = status
                    break
        item["level"] = STATUSES[item["status"]][0]
        item["message"] = item["message"] or ("" if item["status"] == "ok" else STATUS_LABELS[item["status"]])
        item["no_name"] = item["status"] == "ok" and not item["name"]
        if item["no_name"]:
            item["level"], item["message"] = WARNING, NO_NAME_LABEL
        item.pop("_typed")
    counts = {key: sum(1 for i in report if i["status"] == key) for key in STATUSES}
    counts["no_name"] = sum(1 for i in report if i["no_name"])
    groups = []
    for key, (level, label) in [*STATUSES.items(), ("no_name", (WARNING, NO_NAME_LABEL))]:
        if key != "ok" and counts[key]:
            lines = [i["line"] for i in report if (i["no_name"] if key == "no_name" else i["status"] == key)]
            groups.append({"key": key, "label": label, "level": level, "count": counts[key], "lines": _lines(lines)})
    groups.sort(key=lambda g: g["level"] != ERROR)
    problems = sum(counts[k] for k in ERROR_STATUSES)
    skipped = sum(counts[k] for k in ("member", "invited", "suppressed", "opted_out"))
    merged = counts["duplicate"] + counts["case_duplicate"]
    parts = [f"{counts['ok']} will be invited"]
    if skipped:
        parts.append(f"{skipped} skipped")
    if merged:
        parts.append(f"{merged} repeated {'row' if merged == 1 else 'rows'} merged")
    if problems:
        parts.append(f"{problems} need{'s' if problems == 1 else ''} fixing")
    return {"rows": report, "counts": counts, "errors": [], "ok": counts["ok"], "total": len(report), "problems": problems,
            "warnings": sum(1 for i in report if i["level"] == WARNING), "blocked": bool(problems), "can_import": bool(counts["ok"]) and not problems,
            "groups": groups, "summary": " · ".join(parts), "skipped": skipped, "merged": merged}


def problem_rows(report):
    """[(row, level, name, email, what is wrong)] for the download: every row that is not simply ready, errors first."""
    rows = [(i["line"], i["level"], i["name"], i["email"], i["message"]) for i in report["rows"] if i["level"] != OK]
    return sorted(rows, key=lambda r: (r[1] != ERROR, r[0]))


def issue_token(user, text, scope=""):
    """A one-time import token for this person and exactly this list (its hash). Written when the review page is drawn."""
    InviteImport.objects.filter(created_at__lt=timezone.now() - timedelta(days=TOKEN_DAYS), batch_id__isnull=True).delete()
    return InviteImport.objects.create(user=user, content_hash=content_hash(text, scope), token=secrets.token_urlsafe(32)).token


class TokenRefused(Exception):
    """The token is missing, unknown, someone else's, or for a different list. The message is plain words for the page."""


def find_token(token, user, text, scope=""):
    """The InviteImport row for this person and exactly this list, else TokenRefused."""
    row = InviteImport.objects.filter(token=token or "").first() if token else None
    if row is None:
        raise TokenRefused("This check has expired. Check the list again.")
    if row.user_id != getattr(user, "pk", None):
        raise TokenRefused("This check belongs to someone else. Check the list again.")
    if row.content_hash != content_hash(text, scope):
        raise TokenRefused("The list is not the one that was checked. Check it again.")
    return row


def batch_summary(batch_id):
    from django.db.models import Count

    counts = dict(Invite.objects.filter(batch_id=batch_id).values_list("status").annotate(n=Count("pk")).order_by().values_list("status", "n"))
    return {"total": sum(counts.values()), **{status: counts.get(status, 0) for status, _ in Invite.STATUS_CHOICES}}


# ---------- the personal link ----------

def good_invite(token):
    """The Invite when the link is good (it exists, was sent and has not expired), else None. Marks nothing: a link scanner opening
    the link must not count as opened. A link that does not exist and one that expired look the same to the caller."""
    invite = Invite.objects.filter(token=token or "").first()
    if invite is None or invite.expired or invite.status not in (Invite.SENT, Invite.OPENED):  # registered, bounced, skipped, failed or unsent: not a live link
        return None
    return invite


def open_tracking_headers(invite):
    """Mail headers that make Postmark track opens of THIS email (invites only; every other email is sent without them) and say which
    invite it was, so the Open webhook can find it. Other backends (console, locmem, SES) just carry them as unused headers."""
    return {"X-PM-TrackOpens": "true", "X-PM-Tag": "invite", "X-PM-Metadata-invite": invite.token}


def mark_email_opened(token, when=None):
    """Postmark says the invite email was opened. Records the first open only; unknown or bad tokens change nothing.
    (Not the link click: that is `opened_at` / status OPENED.) Returns the number of invites changed."""
    if not isinstance(token, str) or not 8 <= len(token) <= 40:
        return 0
    when = when or timezone.now()
    return Invite.objects.filter(token=token, email_opened_at__isnull=True).update(email_opened_at=when)


def mark_opened(invite):
    """First time only; never downgrades a registered one."""
    if invite.status == Invite.SENT:
        Invite.objects.filter(pk=invite.pk, status=Invite.SENT).update(status=Invite.OPENED, opened_at=timezone.now(), updated_at=timezone.now())


def prefill(token):
    """Called when the Register page renders with the invite in the session: marks it opened too (idempotent; the link click already did) and
    returns the form's starting values {first_name, last_name, email} (empty when it is not good). Only a convenience: the person
    confirms everything, and the address is verified by the confirm link as always."""
    invite = good_invite(token) if token else None
    if invite is None:
        return {}
    mark_opened(invite)
    first, _, last = invite.name.partition(" ")
    return {"first_name": first.strip(), "last_name": last.strip(), "email": invite.email}


def on_registered(user):
    """A person registered: any waiting invite for their address is now registered, and ticking the news box on the form clears an
    earlier no-account unsubscribe. Never raises (it must not break sign-up)."""
    import logging

    try:
        now = timezone.now()
        Invite.objects.filter(email=user.email.lower(), status__in=Invite.PENDING).update(
            status=Invite.REGISTERED, registered_user=user, registered_at=now, updated_at=now)
    except Exception:  # noqa: BLE001
        logging.getLogger("spa99.email").exception("Could not mark invites registered")


def mark_bounced(email):
    """SES reported a permanent bounce or a complaint for this address: invites and mailing rows sent to it show it."""
    from .models import MailingRecipient

    email = (email or "").strip().lower()
    now = timezone.now()
    Invite.objects.filter(email=email, status__in=(Invite.SENT, Invite.OPENED)).update(status=Invite.BOUNCED, updated_at=now)
    MailingRecipient.objects.filter(email=email, status=MailingRecipient.SENT, sent_at__gte=now - timedelta(days=7)).update(
        status=MailingRecipient.BOUNCED, updated_at=now)

