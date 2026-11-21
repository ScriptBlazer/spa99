"""One-off on deploy (2026-11-19): fill a BLANK "Voicemail email to" list (System > Emails) with the site address (the address inside DEFAULT_FROM_EMAIL). A SCRIPT, never a migration.
The new column starts blank on an existing database (db_default, for safe rollback); new installs get the site address by default. Fills only a blank, so a list someone already edited is
never touched. Run it once, before anyone clears the list on purpose (a cleared list is blank again, and a second run would refill it).

    manage.py set_voicemail_recipients --dry-run     then without --dry-run."""
from django.core.management.base import BaseCommand

from plans.models import SiteSettings, default_voicemail_to


class Command(BaseCommand):
    help = "Fill a blank Voicemail email to list with the site address. --dry-run writes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")

    def handle(self, *args, dry_run=False, **options):
        site = SiteSettings.load()
        address = default_voicemail_to()
        if site.voicemail_email_to.strip():
            self.stdout.write("The list already has addresses: nothing to do.")
            return
        if not address:
            self.stdout.write("DEFAULT_FROM_EMAIL has no address: nothing to fill.")
            return
        if dry_run:
            self.stdout.write(f"Would set the Voicemail email to list to {address}.")
            return
        SiteSettings.objects.filter(pk=site.pk).update(voicemail_email_to=address)
        self.stdout.write(f"Set the Voicemail email to list to {address}.")
