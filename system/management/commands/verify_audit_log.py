"""Walk the audit hash chain and report OK or the first broken row. Exit code 1 when broken."""
from django.core.management.base import BaseCommand, CommandError

from system import audit


class Command(BaseCommand):
    help = "Verify the System audit log hash chain (changes and security events)."

    def handle(self, *args, **options):
        result = audit.check_and_store()
        if not result["ok"]:
            raise CommandError(result["message"])
        self.stdout.write(result["message"])
