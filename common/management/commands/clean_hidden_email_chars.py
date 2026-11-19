"""Remove invisible Unicode characters (U+200F, U+202C, zero-width marks...) from stored email addresses. Never part of a migration.
Usage:  manage.py clean_hidden_email_chars            (dry run, writes nothing)
        manage.py clean_hidden_email_chars --apply    (one transaction)
Prints `table . id . field: before -> after` with the hidden characters shown as <U+202C> and the local part masked (ids, not
addresses). A change that would make two rows the same address where the column or a constraint must be unique is a CONFLICT line and is
skipped: nothing is merged or overwritten. Email log and history (audit) rows get only the hidden characters removed (case kept), so
erasure and the lead timeline still find them. Works on SQLite and Postgres."""
import unicodedata

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import UniqueConstraint

from common.emails import clean_email, has_hidden, strip_hidden

# (app_label.Model, field): the stored address fields. Their history tables (if any) and the email log are added by targets().
FIELDS = [
    ("users.User", "email"),
    ("journey.JourneySession", "lead_email"),
    ("chat.Conversation", "lead_email"),
    ("gold.GoldApplication", "email"),
    ("gold.ApproverDelivery", "other_email"),
    ("mailings.Invite", "email"),
    ("mailings.MailingRecipient", "email"),
    ("mailings.ContactListMember", "email"),
    ("mailings.EmailOptOut", "email"),
    ("mailings.UnsubscribeKey", "email"),
    ("notifications.EmailSuppression", "email"),
    ("notifications.EmailBounce", "email"),
    ("outreach.StickyNote", "email"),
    ("outreach.OutreachEntry", "lead_email"),
    ("outreach.PersonMessage", "email"),
    ("outreach.PersonEdit", "email"),
    ("outreach.ArchivedLead", "email"),
    ("outreach.GenuineLead", "email"),
    ("outreach.LeadArchiveEvent", "email"),
    ("outreach.NextMorningEmail", "email"),
]


# Log fields: hidden characters removed, nothing else changed (decided 2026-11-16, PROJECT.md).
LOG_FIELDS = [("notifications.EmailLog", "to"), ("notifications.EmailLog", "cc"), ("notifications.EmailLog", "subject_email")]


def targets():
    """(model, field, is_log) for every column to scan: the address fields, their simple-history tables, then the email log."""
    out = []
    for label, field in FIELDS:
        model = apps.get_model(label)
        out.append((model, field, False))
        history = getattr(model, "history", None)
        if history is not None and hasattr(history, "model"):
            out.append((history.model, field, True))
    out += [(apps.get_model(label), field, True) for label, field in LOG_FIELDS]
    return out


def show(value):
    """Hidden characters made visible: <U+202C>."""
    return "".join(f"<U+{ord(ch):04X}>" if unicodedata.category(ch) == "Cf" else ch for ch in value)


def mask(value):
    """n***@gmail.com : first character of the local part, then stars; the hidden characters stay visible."""
    visible = show(value)
    local, at, domain = visible.partition("@")
    return (local[:1] + "***" + at + domain) if at else (visible[:1] + "***")


def _unique_specs(model, field):
    """Every uniqueness rule that names `field`: a list of (other_fields, condition). [] means the address may repeat.
    Covers a unique column, UniqueConstraint (several fields, a case-insensitive Lower(field), or a condition) and unique_together."""
    meta = model._meta
    specs = []
    if meta.get_field(field).unique:
        specs.append(([], None))
    for c in meta.constraints:
        if not isinstance(c, UniqueConstraint):
            continue
        names = list(c.fields)
        names += [getattr(getattr(e, "source_expressions", [None])[0], "name", None) for e in c.expressions]
        if field in names:
            specs.append(([n for n in c.fields if n != field], c.condition))
    for group in meta.unique_together:
        if field in group:
            specs.append(([n for n in group if n != field], None))
    return specs


def _conflict_keys(model, field, pk, cleaned):
    """(querysets of other rows that would hold the same address, keys for this run's own claims). Other fields of the rule must match
    exactly; the address is compared case-insensitively (the cleaner lower-cases)."""
    querysets, keys = [], []
    row = model._default_manager.filter(pk=pk).values().first() or {}
    for others, condition in _unique_specs(model, field):
        if condition is not None and not model._default_manager.filter(pk=pk).filter(condition).exists():
            continue  # this row is outside a conditional rule (a finished approach-list row cannot clash)
        match = {name: row.get(model._meta.get_field(name).attname) for name in others}
        qs = model._default_manager.exclude(pk=pk).filter(**match, **{f"{field}__iexact": cleaned})
        querysets.append(qs.filter(condition) if condition is not None else qs)
        keys.append((model._meta.label, field, cleaned, tuple(sorted(match.items(), key=lambda kv: kv[0]))))
    return querysets, keys


class Command(BaseCommand):
    help = "Find and remove hidden Unicode characters from stored email addresses. Dry run unless --apply."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write the changes (one transaction). Without it nothing is written.")
        parser.add_argument("--dry-run", action="store_true", help="The default: list what would change, write nothing.")

    def handle(self, *args, apply=False, dry_run=False, **options):
        apply = apply and not dry_run
        changes, conflicts = [], 0
        claimed = set()  # rule keys already taken by an earlier row in this run
        for model, field, is_log in targets():
            table = model._meta.db_table
            for pk, value in model._default_manager.order_by("pk").values_list("pk", field):
                if not has_hidden(value):
                    continue
                keep_case = is_log or field == "other_email"  # logs and other_email keep the case as stored
                cleaned = strip_hidden(value) if keep_case else clean_email(value)
                line = f"{table} . {pk} . {field}: {mask(value)} -> {mask(cleaned)}"
                querysets, keys = ([], []) if is_log else _conflict_keys(model, field, pk, cleaned)
                if any(qs.exists() for qs in querysets) or any(k in claimed for k in keys):
                    conflicts += 1
                    self.stdout.write(f"CONFLICT (skipped) {line}")
                    continue
                claimed.update(keys)
                changes.append((model, pk, field, cleaned))
                self.stdout.write(line if apply else f"WOULD CHANGE {line}")
        if apply and changes:
            with transaction.atomic():
                for model, pk, field, cleaned in changes:
                    model._default_manager.filter(pk=pk).update(**{field: cleaned})  # update(): no save() side effects, no history row
        if not changes and not conflicts:
            self.stdout.write("Nothing to change.")
            return
        verb = "changed" if apply else "would change"
        self.stdout.write(f"{len(changes)} value(s) {verb}; {conflicts} conflict(s) skipped." + ("" if apply else " Dry run: nothing written. Use --apply."))
