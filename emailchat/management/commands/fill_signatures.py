"""Fill the Office email signatures of existing staff from the design files (docs/design/spa99-signature-*.html), the same ones CodeTwo uses for Microsoft mail.

Matches by email: each file says whose it is in its first comment ("Senders = name@domain"), and the staff account with that email gets it. Only an EMPTY signature is filled; one that
was typed or edited in System is never touched. Safe to run twice. The pictures in the files are pointed at our own static copies (/static/common/img/email/, made absolute from SITE_URL
when an email is sent). The files are the source: no name, number or address is in this code. `--dry-run` writes nothing. `docs/` is not in the live image, so on the server copy the
files somewhere and give `--source`."""
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from common import richtext

PICTURES = {"spa99-signature-logo.png": "signature-logo.png", "spa99-signature-banner.jpg": "signature-banner.jpg"}  # file name in the design folder -> our static file
SENDER = re.compile(r"Senders\s*=\s*([^\s,;)]+@[^\s,;)]+)", re.I)
LEADING_COMMENT = re.compile(r"^\s*(?:<!--.*?-->\s*)+", re.S)


def signatures_in(folder):
    """{email: signature html (pictures pointed at /static/common/img/email/)} from the design files, and [problems]."""
    found, problems = {}, []
    for path in sorted(Path(folder).glob("spa99-signature-*.html")):
        raw = path.read_text(encoding="utf-8")
        match = SENDER.search(raw)
        if not match:
            problems.append(f"{path.name}: no 'Senders = <email>' in its first comment, skipped")
            continue
        html = LEADING_COMMENT.sub("", raw).strip()
        for name, ours in PICTURES.items():
            html = html.replace(f'src="{name}"', f'src="{richtext.OWN_IMAGES}{ours}"')
        found[match.group(1).strip().lower()] = html
    return found, problems


class Command(BaseCommand):
    help = "Fill empty Office email signatures of existing staff from docs/design/spa99-signature-*.html (matched by email). --dry-run writes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be filled; write nothing.")
        parser.add_argument("--source", default=str(Path(settings.BASE_DIR) / "docs" / "design"), help="Folder holding the spa99-signature-*.html files (default docs/design).")

    def handle(self, *args, **options):
        from emailchat.models import StaffSender
        from system import team

        folder = Path(options["source"])
        if not folder.is_dir():
            raise CommandError(f"No such folder: {folder}")
        dry = options["dry_run"]
        files, problems = signatures_in(folder)
        for problem in problems:
            self.stdout.write(problem)
        if not files:
            raise CommandError(f"No spa99-signature-*.html files with a Senders line in {folder}")
        staff = {u.email.lower(): u for u in team.team_queryset()}
        for row in StaffSender.objects.filter(user__in=team.team_queryset()).exclude(sending_address="").select_related("user"):
            staff.setdefault(row.sending_address.lower(), row.user)  # a BML login: its signature file names its @spa99.uk sending address
        filled = 0
        with transaction.atomic():
            for email, html in files.items():
                user = staff.get(email)
                if user is None:
                    self.stdout.write(f"{email}: no staff account with this email, skipped")
                    continue
                clean = richtext.clean_signature(html)
                if not clean:
                    self.stdout.write(f"{email}: the file did not clean to a usable signature, skipped")
                    continue
                row = StaffSender.objects.filter(user=user).first()
                if row is not None and row.signature_html.strip():
                    self.stdout.write(f"{email}: already has a signature, left as it is")
                    continue
                self.stdout.write(f"{email}: {'would fill' if dry else 'filled'} the signature ({len(clean)} characters)")
                filled += 1
                if not dry:
                    row = row or StaffSender(user=user)
                    row.signature_html, row.updated_at = clean, timezone.now()
                    row.save()
        self.stdout.write(f"{'Dry run: nothing was saved. Would fill' if dry else 'Filled'} {filled} signature(s).")
