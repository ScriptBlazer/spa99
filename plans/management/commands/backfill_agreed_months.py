"""Store how long an agreed price lasts on subscriptions set up before `Subscription.agreed_months` existed, and report what a person should look at. A SCRIPT, never a migration.
Safe to run twice. It prints counts and internal ids only.

It fills an active subscription only when its agreed price is exactly a sale price: the member's kept sale, else a sale that was live and covered the plan when it was set up. That is the
sale's months. Nothing else is guessed, so two lists are printed for a person to check, and neither is changed:
- an agreed price below the plan's price with no months stored (Revenue counts it for the whole year);
- someone who registered during a sale, on a plan it covered, with no sale price stored, who counts in Revenue at the full price. He may have moved plan since.

    manage.py backfill_agreed_months --dry-run     then without --dry-run."""
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from office.counts import DECLINED, with_review
from plans import payments, sales
from plans.models import PaymentWindow, Plan, Sale, Subscription
from users.models import InterestRegistration


def months_for(sub):
    reg = sub.registration
    if payments.holds_sale_price(reg, sub.plan, sub.agreed_price_ex_vat):
        return reg.sale_months or 1
    live = sales.live_sale(sub.created_at)
    if sales.covers(live, sub.plan) and sales.sale_price(sub.plan, live) == sub.agreed_price_ex_vat:
        return live.months_at_price or 1
    return None


class Command(BaseCommand):
    help = "Fill agreed_months where the agreed price is a sale price, and list what a person should check. --dry-run writes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change; write nothing.")

    def handle(self, *args, dry_run=False, **options):
        filled, unclear = 0, []
        rows = Subscription.objects.filter(status=Subscription.ACTIVE, agreed_price_ex_vat__isnull=False, agreed_months__isnull=True).select_related("registration__sale", "plan")
        for sub in rows:
            months = months_for(sub)
            if months is None:
                if sub.agreed_price_ex_vat < sub.plan.price_ex_vat:
                    unclear.append(sub.pk)
                continue
            filled += 1
            self.stdout.write(f"{'WOULD SET' if dry_run else 'SET'}  subscription {sub.pk}: {months} months")
            if not dry_run:
                sub.agreed_months = months
                sub._change_reason = "backfill_agreed_months"
                sub.save(update_fields=["agreed_months", "updated_at"])
        self.stdout.write(f"Subscriptions {'to fill' if dry_run else 'filled'}: {filled}")
        self.stdout.write(f"Agreed price below the plan's price with no months stored: {len(unclear)}")
        for pk in unclear:
            self.stdout.write(f"  LOOK AT  subscription {pk}")

        missing = self.registered_without_a_sale_price()
        self.stdout.write(f"Registered during a sale with no sale price stored: {len(missing)}")
        for public_id in sorted(missing):
            self.stdout.write(f"  LOOK AT  {public_id}")

    @staticmethod
    def registered_without_a_sale_price():
        opened = PaymentWindow.objects.filter(opened_at__isnull=False).order_by("opened_at").values_list("opened_at", flat=True).first()
        active = Subscription.objects.filter(registration=OuterRef("pk"), status=Subscription.ACTIVE)
        ended = Subscription.objects.filter(registration=OuterRef("pk"), status=Subscription.CANCELLED)
        agreed = active.filter(agreed_price_ex_vat__isnull=False)
        counted = (with_review(InterestRegistration.objects.filter(sale_percent_off__isnull=True, plan__kind=Plan.MONTHLY, user__is_staff=False))
                   .annotate(has_active=Exists(active), has_cancelled=Exists(ended), has_agreed=Exists(agreed)).exclude(review_status=DECLINED).exclude(has_agreed=True).exclude(has_cancelled=True, has_active=False))
        missing = set()
        for sale in Sale.objects.prefetch_related("plans"):
            end = min(sale.ends_at, sale.ended_early_at) if sale.ended_early_at else sale.ends_at
            if opened:  # after payments open a sale is pay now: nothing is stored on the registration
                end = min(end, opened)
            missing.update(counted.filter(created_at__gte=sale.starts_at, created_at__lt=end, plan__in=sale.plans.all()).values_list("user__public_id", flat=True))
        return missing
