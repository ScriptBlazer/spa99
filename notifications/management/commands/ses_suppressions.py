from django.core.management.base import BaseCommand, CommandError

from notifications import suppression
from notifications.models import EmailSuppression


class Command(BaseCommand):
    help = "List the email suppression list (--list) or take an address off it (--remove EMAIL). Not audit logged: prefer System."

    def add_arguments(self, parser):
        parser.add_argument("--list", action="store_true")
        parser.add_argument("--remove", metavar="EMAIL")

    def handle(self, *args, **options):
        if options["remove"]:
            if not suppression.remove(options["remove"]):
                raise CommandError("That address is not on the list.")
            self.stdout.write("Removed.")
        else:
            for row in EmailSuppression.objects.all():
                self.stdout.write(f"{row.email}\t{row.reason}\t{row.last_seen:%Y-%m-%d %H:%M}\t{row.count}")
