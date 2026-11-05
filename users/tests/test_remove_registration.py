"""remove_registration: dry run changes nothing, the plan must match, payments refuse, the account stays."""
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from gold.models import GoldApplication
from office import lists
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan
from users.models import InterestRegistration, User


class RemoveRegistrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.user = User.objects.create_user("test@example.com", "a-long-password-1")
        cls.interest = InterestRegistration.objects.create(user=cls.user, plan=Plan.objects.get(slug="tier-2"))

    def run_it(self, *extra, plan="tier-2"):
        out = StringIO()
        call_command("remove_registration", "--email", "TEST@example.com", "--plan", plan, *extra, stdout=out)
        return out.getvalue()

    def test_dry_run_then_real(self):
        self.assertIn("WOULD REMOVE", self.run_it("--dry-run"))
        self.assertTrue(InterestRegistration.objects.filter(user=self.user).exists())
        self.assertIn("REMOVED", self.run_it())
        self.assertFalse(InterestRegistration.objects.filter(user=self.user).exists())
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_wrong_plan_or_a_payment_refuses(self):
        with self.assertRaises(CommandError):
            self.run_it(plan="tier-3")
        InterestRegistration.objects.filter(pk=self.interest.pk).update(payment_source="manual")
        with self.assertRaises(CommandError):
            self.run_it()
        self.assertTrue(InterestRegistration.objects.filter(pk=self.interest.pk).exists())


class GoldColumnTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_a_declined_application_leaves_the_registered_row(self):
        user = User.objects.create_user("g@example.com", "a-long-password-1")
        InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug="tier-2"))
        application = GoldApplication.objects.create(email=user.email, first_name="A", last_name="B", user=user)
        self.assertEqual(lists.person_row(user)["gold_application_id"], str(application.pk))
        GoldApplication.objects.filter(pk=application.pk).update(status=GoldApplication.DECLINED)
        fresh = User.objects.get(pk=user.pk)
        self.assertEqual(lists.person_row(fresh)["gold_application_id"], "")
