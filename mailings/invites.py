"""Invites: read a pasted list or CSV, check it, write the batch, follow the personal link, and notice the sign-up.

The import never trusts the file: every row is parsed and checked here, and the server checks it again when the batch is made
(the review page is only a preview). A report row's `status` is one of ok, invalid, duplicate, member, invited, suppressed,
opted_out."""
import csv
import io
import re
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from common.validators import normalise_email
from notifications.models import EmailSuppression
from users.models import User

from .models import INVITE_DAYS, EmailOptOut, Invite

MAX_ROWS = 2000
MAX_BYTES = 1024 * 1024
NAME_MAX = 100
SESSION_KEY = "invite_token"
STATUS_LABELS = {
    "ok": "Will be invited", "invalid": "Not a valid email address", "duplicate": "Repeated in this list",
    "member": "Already has an account", "invited": "Already invited (waiting)", "suppressed": "On the suppression list (bounced or complained)",
    "opted_out": "Unsubscribed",
}
_ANGLE = re.compile(r"^\s*(?P<name>.*?)\s*<(?P<email>[^<>]+)>\s*$")


def _delimiter(sample):
    counts = {d: sample.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def _split_row(cells):
    """(name, raw email text) from one row: the cell holding an @ is the address, the other cells are the name."""
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


def parse(raw):
    """(rows, file_errors). rows: [{"line", "name", "email" (as typed), "raw"}]. A first line with no address is a header and is skipped.
    Reasons to refuse the whole file: over 1 MB, or more than 2000 rows."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            return [], [f"The list is larger than {MAX_BYTES // 1024 // 1024} MB."]
        raw = raw.decode("utf-8-sig", errors="replace")
    raw = (raw or "")
    if len(raw.encode("utf-8")) > MAX_BYTES:
        return [], [f"The list is larger than {MAX_BYTES // 1024 // 1024} MB."]
    lines = [(number, line) for number, line in enumerate(raw.splitlines(), start=1) if line.strip()]
    if not lines:
        return [], ["The list is empty."]
    delimiter = _delimiter(lines[0][1])
    rows = []
    for position, (number, line) in enumerate(lines):
        try:
            cells = next(csv.reader([line], delimiter=delimiter, skipinitialspace=True))
        except csv.Error:
            cells = [line]
        name, email = _split_row(cells)
        if position == 0 and "@" not in email:  # header row ("name,email")
            continue
        rows.append({"line": number, "name": name[:NAME_MAX * 3], "email": email})
        if len(rows) > MAX_ROWS:
            return [], [f"The list has more than {MAX_ROWS} rows. Split it into smaller lists."]
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


def check(raw):
    """The validation report: {"rows": [...], "counts": {...}, "errors": [...], "ok": n, "total": n}. Nothing is written."""
    rows, errors = parse(raw)
    if errors:
        return {"rows": [], "counts": {}, "errors": errors, "ok": 0, "total": 0}
    report, seen, candidates = [], set(), []
    for row in rows:
        item = {"line": row["line"], "name": row["name"], "email": row["email"], "status": "ok", "message": ""}
        try:
            item["email"] = normalise_email(row["email"])
        except ValidationError:
            item["status"] = "invalid"
        if len(row["name"]) > NAME_MAX:
            item["status"], item["message"] = "invalid", f"The name is longer than {NAME_MAX} characters."
        elif item["status"] == "ok":
            if item["email"] in seen:
                item["status"] = "duplicate"
            else:
                seen.add(item["email"])
                candidates.append(item["email"])
        report.append(item)
    members = _existing(User, "email", candidates)
    # case-insensitive match on stored emails: users are saved lower case, invites too (Invite.save)
    suppressed = _existing(EmailSuppression, "email", candidates)
    opted_out = _existing(EmailOptOut, "email", candidates)
    invited = _existing(Invite, "email", candidates, status__in=Invite.PENDING, expires_at__gt=timezone.now())
    for item in report:
        if item["status"] != "ok":
            continue
        for status, group in (("member", members), ("suppressed", suppressed), ("opted_out", opted_out), ("invited", invited)):
            if item["email"] in group:
                item["status"] = status
                break
    for item in report:
        item["message"] = item["message"] or ("" if item["status"] == "ok" else STATUS_LABELS[item["status"]])
    counts = {key: sum(1 for i in report if i["status"] == key) for key in STATUS_LABELS}
    return {"rows": report, "counts": counts, "errors": [], "ok": counts["ok"], "total": len(report)}


@transaction.atomic
def create_batch(raw, user):
    """Check the list again and write the batch: `queued` invites for the ok rows, `skipped` ones (with the reason) for valid addresses
    that cannot be invited (already a member, waiting, suppressed, unsubscribed). Invalid and repeated rows are only in the report.
    Returns (batch_id, report). Nothing is sent here."""
    report = check(raw)
    batch_id = uuid.uuid4()
    if report["errors"] or not report["rows"]:
        return batch_id, report
    for item in report["rows"]:
        if item["status"] in ("invalid", "duplicate"):
            continue
        Invite.objects.create(
            name=item["name"], email=item["email"], batch_id=batch_id, created_by=user if getattr(user, "pk", None) else None,
            status=Invite.QUEUED if item["status"] == "ok" else Invite.SKIPPED, reason="" if item["status"] == "ok" else item["message"])
    return batch_id, report


def batch_summary(batch_id):
    from django.db.models import Count

    counts = dict(Invite.objects.filter(batch_id=batch_id).values_list("status").annotate(n=Count("pk")).order_by().values_list("status", "n"))
    return {"total": sum(counts.values()), **{status: counts.get(status, 0) for status, _ in Invite.STATUS_CHOICES}}


# ---------- the personal link ----------

def good_invite(token):
    """The Invite when the link is good (it exists, was sent and has not expired), else None. Marks nothing: a link scanner opening
    the link must not count as opened. A link that does not exist and one that expired look the same to the caller."""
    invite = Invite.objects.filter(token=token or "").first()
    if invite is None or invite.expired or invite.status in (Invite.SKIPPED, Invite.FAILED, Invite.QUEUED, Invite.SENDING):
        return None
    return invite


def mark_opened(invite):
    """First time only; never downgrades a registered one."""
    if invite.status == Invite.SENT:
        Invite.objects.filter(pk=invite.pk, status=Invite.SENT).update(status=Invite.OPENED, opened_at=timezone.now(), updated_at=timezone.now())


def prefill(token):
    """Called when the Register page renders with the invite in the session: marks the invite opened (a person really got here) and
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


EXPIRY_DAYS = INVITE_DAYS
