"""One-off: copy the old CONTACT_EMAIL, GOLD_APPROVER_EMAILS and GOLD_APPROVER_CC environment values into the database
(System > Emails now owns them). Never a migration. Only fills fields that are still blank, so running it twice (or
after someone edited them in System) changes nothing.

  manage.py import_email_settings_from_env --dry-run   # show what would be copied
  manage.py import_email_settings_from_env             # copy it
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from plans.models import SiteSettings

# env var -> SiteSettings field
MAPPING = {
    "GOLD_APPROVER_EMAILS": "gold_approver_emails",
    "GOLD_APPROVER_CC": "gold_approver_cc",
    "CONTACT_EMAIL": "contact_email",
}


class Command(BaseCommand):
    help = "Copy CONTACT_EMAIL / GOLD_APPROVER_EMAILS / GOLD_APPROVER_CC from the environment into System (blank fields only)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be copied; change nothing.")

    def handle(self, *args, **options):
        site = SiteSettings.load()
        found = getattr(settings, "ENV", None)
        changed = []
        for var, field in MAPPING.items():
            value = (found.get(var) if found is not None else "") or ""
            value = ", ".join(part.strip() for part in value.split(",") if part.strip())
            if not value:
                self.stdout.write(f"{var}: not set in the environment, skipped.")
            elif getattr(site, field):
                self.stdout.write(f"{var}: System already has a value, left alone.")
            else:
                try:
                    SiteSettings._meta.get_field(field).run_validators(value)
                except ValidationError as error:
                    self.stdout.write(f"{var}: not copied ({' '.join(error.messages)})")
                    continue
                setattr(site, field, value)
                changed.append(field)
                self.stdout.write(f"{var}: {'would copy' if options['dry_run'] else 'copied'} {value}")
        if changed and not options["dry_run"]:
            site.save(update_fields=changed + ["updated_at"])
        if options["dry_run"]:
            self.stdout.write("Dry run: nothing was saved.")
