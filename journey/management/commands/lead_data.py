"""UK GDPR for leads who never registered: print what is held for an email as JSON, and optionally erase it.
`--dry-run` with `--erase` only says what would be cleared. The answers stay anonymously (see journey.services.erase_lead)."""
import json

from django.core.management.base import BaseCommand, CommandError

from journey import services


class Command(BaseCommand):
    help = "Export (and with --erase, erase) the journey data held for a lead's email address."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--erase", action="store_true", help="Clear the address from its sessions after exporting.")
        parser.add_argument("--dry-run", action="store_true", help="With --erase: say what would be cleared; change nothing.")

    def handle(self, *args, **options):
        email = options["email"].strip()
        if not email:
            raise CommandError("--email is empty.")
        rows = services.export_lead(email)
        self.stdout.write(json.dumps({"email": email, "sessions": rows}, indent=2))
        if not options["erase"]:
            return
        if options["dry_run"]:
            self.stderr.write(f"Dry run: would clear the address from {len(rows)} session(s). Nothing changed.")
            return
        self.stderr.write(f"Cleared the address from {services.erase_lead(email)} session(s).")
