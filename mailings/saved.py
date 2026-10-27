"""Saved email templates (MailingTemplate): checking, saving (with explicit overwrite), renaming and deleting. Views stay short; the
System audit events are written by the views."""
from django.db import transaction
from django.db.models.functions import Lower

from notifications import emailbody

from . import blocks as mailing_blocks, segments
from .models import Mailing, MailingTemplate

NAME_MAX = 120


class TemplateError(Exception):
    """`errors` is {field: [messages]} with `blocks` as {"_": [...], "<index>": {field: [...]}}; `exists` is True when the name is taken."""

    def __init__(self, errors, exists=False):
        super().__init__("; ".join(str(m) for v in errors.values() for m in (v if isinstance(v, list) else ["parts"])))
        self.errors, self.exists = errors, exists


def find_by_name(name, exclude=None):
    qs = MailingTemplate.objects.annotate(lowered=Lower("name")).filter(lowered=(name or "").strip().lower())
    return qs.exclude(pk=exclude.pk).first() if exclude is not None else qs.first()


def clean_name(name):
    name = " ".join((name or "").split())
    if not name:
        raise TemplateError({"name": ["Give the template a name."]})
    if len(name) > NAME_MAX:
        raise TemplateError({"name": [f"The name can be at most {NAME_MAX} characters."]})
    return name


def resolve(ref):
    """A template from an id or a key (?start=...), or None."""
    import uuid

    ref = (ref or "").strip()
    if not ref:
        return None
    try:
        return MailingTemplate.objects.filter(pk=uuid.UUID(ref)).first()
    except ValueError:
        return MailingTemplate.objects.filter(key=ref).first()


def save(name, subject, kind, group, raw_blocks, user=None, overwrite=False):
    """Create the template, or replace the one with this name (only with overwrite=True). Returns (template, created).
    Subject may be empty; the parts must be valid. Raises TemplateError."""
    name = clean_name(name)
    errors = emailbody.validate(emailbody.SPECS["mailing"], subject=subject) if (subject or "").strip() else {}
    parts, block_errors = mailing_blocks.clean(raw_blocks)
    if block_errors:
        errors["blocks"] = block_errors
    if kind not in (Mailing.NEWS, Mailing.SERVICE):
        errors["kind"] = ["Choose News or Service message."]
    if group and group not in segments.GROUPS:
        errors["group"] = ["Choose a group."]
    if errors:
        raise TemplateError(errors)
    with transaction.atomic():
        existing = find_by_name(name)
        if existing is not None and not overwrite:
            raise TemplateError({"name": [f"A template called '{existing.name}' already exists."]}, exists=True)
        row = existing or MailingTemplate(created_by=user if getattr(user, "pk", None) else None)
        row.name, row.subject, row.kind, row.group, row.blocks = name, (subject or "").strip(), kind, group or "", parts
        row._history_user = user if getattr(user, "pk", None) else None
        row.save()
    return row, existing is None


def rename(template, name):
    name = clean_name(name)
    if find_by_name(name, exclude=template) is not None:
        raise TemplateError({"name": ["Another template already has this name."]}, exists=True)
    template.name = name
    template.save(update_fields=["name", "updated_at"])
    return template


def choices():
    """For Start from: [("", "Blank"), (id, name), ...]."""
    return [("", "Blank")] + [(str(pk), name) for pk, name in MailingTemplate.objects.values_list("pk", "name")]


PART_WORDS = {"heading": ("a heading", "headings"), "paragraph": ("a paragraph", "paragraphs"), "button": ("a button", "buttons"),
              "image": ("a picture", "pictures"), "divider": ("a divider", "dividers"), "small_print": ("small print", "small print")}


def describe(template):
    """A card line made from the data: 'Service message to Everyone registered: a heading, a paragraph, a button and small print.'"""
    kind = "Service message" if template.kind == Mailing.SERVICE else "News"
    group = segments.GROUPS.get(template.group)
    counts = {}
    for part in template.blocks:
        counts[part.get("type")] = counts.get(part.get("type"), 0) + 1
    words = [PART_WORDS[t][0 if n == 1 else 1] if n == 1 else f"{n} {PART_WORDS[t][1]}" for t, n in counts.items() if t in PART_WORDS]
    listing = (", ".join(words[:-1]) + " and " + words[-1]) if len(words) > 1 else "".join(words)
    return f"{kind}{' to ' + group.label if group else ''}{': ' + listing if listing else ''}."


def details():
    """For the Start from cards: id (the value to send as ?start=), name, description and the saved fields."""
    return [{"id": str(t.pk), "key": t.key or "", "name": t.name, "subject": t.subject, "kind": t.kind, "group": t.group, "parts": len(t.blocks),
             "description": describe(t)} for t in MailingTemplate.objects.all()]
