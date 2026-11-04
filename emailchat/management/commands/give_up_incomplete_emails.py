from django.core.management.base import BaseCommand

from emailchat import services


class Command(BaseCommand):
    help = "Inbound emails still incomplete after a day stop saying they are loading and say their files could not be saved (also runs hourly as a scheduled job). --dry-run only counts."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count them, change nothing.")

    def handle(self, *args, **options):
        count = services.give_up_incomplete(dry_run=options["dry_run"])
        self.stdout.write(f"{'Would give up on' if options['dry_run'] else 'Gave up on'} {count} incomplete email(s).")
