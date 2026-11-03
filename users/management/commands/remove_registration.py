"""Remove one person's registration (a test or a mistake). The account stays. Dry run first:
    manage.py remove_registration --email barry@spa99.uk --plan tier-2 --dry-run
Refuses anything with a payment or a kept sale price on it, and the stored figures move with it."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from insights import metrics
from users.models import InterestRegistration


class Command(BaseCommand):
    help = "Remove one registration by email and plan (the account stays). Use --dry-run first."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--plan", required=True, help="The plan slug it must be on, e.g. tier-2 (a safety check).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, email, plan, dry_run, **options):
        with transaction.atomic():
            interest = (InterestRegistration.objects.select_for_update(of=("self",)).select_related("user", "plan")
                        .filter(user__email__iexact=email.strip()).first())
            if interest is None:
                raise CommandError(f"{email} has no registration.")
            slug = interest.plan.slug if interest.plan_id else ""
            if slug != plan:
                raise CommandError(f"{email} is on {slug or 'no plan'}, not {plan}. Nothing changed.")
            if interest.paid_at or interest.payment_source or interest.sale_locked_at:
                raise CommandError(f"{email} has a payment or a kept sale price on this registration. Nothing changed.")
            line = f"{interest.user.email}: {slug}, source {interest.source}, registered {interest.created_at:%Y-%m-%d %H:%M}"
            if dry_run:
                self.stdout.write(f"WOULD REMOVE {line}")
                return
            metrics.registered(slug, interest.source, interest.created_at, marketing=interest.user.marketing_consent, amount=-1)
            interest.delete()
            self.stdout.write(f"REMOVED {line}. The account stays.")
