"""Starting templates. Creates what is missing (by key) and never overwrites an edited one. Run by `seed_phase1`."""
from . import blocks
from .models import MailingTemplate


def run(ensure):
    for key, starter in blocks.STARTERS.items():
        if not MailingTemplate.objects.filter(key=key).exists() and MailingTemplate.objects.filter(name__iexact=starter["name"]).exists():
            continue  # someone already made one with this name: do not clash with it
        ensure(MailingTemplate, {"key": key}, {"name": starter["name"], "subject": starter["subject"], "kind": starter["kind"],
                                               "group": starter["group"], "blocks": starter["blocks"]})
