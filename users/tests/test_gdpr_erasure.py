"""Deleting a person must leave nothing behind: email log rows (including Barry's email about them) and the
django-q task records, which used to keep a pickled EmailLog."""
from django.core import mail
from django.test import TestCase
from django_q.models import OrmQ, Task
from django_q.signing import SignedPackage

from common.tasks import erase_task_records
from gold import services as gold_services
from gold.models import GoldApplication
from notifications.models import EmailLog
from plans.management.commands.seed_phase1 import seed_all
from users import services
from users.forms import SignUpForm
from users.models import User

EMAIL = "gone@example.com"


def sign_up():
    form = SignUpForm({
        "first_name": "Gus", "last_name": "Gold", "email": EMAIL, "mobile": "07912 345678",
        "password": "correct horse battery staple", "date_of_birth": "1990-05-01", "men_only_accepted": "on",
        "privacy_accepted": "on", "plan": "tier-2",
    })
    assert form.is_valid(), form.errors
    return services.register_interest(form.cleaned_data).user


def apply_for_gold():
    return gold_services.submit_application({
        "first_name": "Gus", "last_name": "Gold", "email": EMAIL, "mobile": "+447912345678",
        "industry": "property", "property_link": "owner_investor", "size_range": "10_49", "privacy_accepted": True,
    })[0]


class ErasureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_email_tasks_return_a_status_not_the_email_log(self):
        sign_up()
        apply_for_gold()
        results = {t.func: t.result for t in Task.objects.all()}
        self.assertEqual(results["users.tasks.send_verification_email"], "sent")
        self.assertEqual(results["gold.tasks.send_gold_emails"], "sent")  # nothing pickled, so no address in the queue tables

    def test_delete_removes_emails_about_the_person_and_their_queue_records(self):
        user = sign_up()
        application = apply_for_gold()
        barry_log = EmailLog.objects.get(template="gold_approver")
        self.assertNotIn(EMAIL, barry_log.to)  # it went to Barry, so only the subject link can find it
        self.assertEqual(barry_log.subject_email, EMAIL)
        self.assertTrue(Task.objects.filter(func__startswith="gold.tasks.").exists())
        other = User.objects.create_user("stays@example.com", "correct horse battery staple")
        EmailLog.objects.create(to="stays@example.com", subject="Keep me", template="verify", status="sent", subject_email="stays@example.com")
        keep_task = Task.objects.create(id="keep", name="keep", func="users.tasks.send_welcome_email", args=(str(other.pk),), started="2026-10-22T10:00Z", stopped="2026-10-22T10:00Z", success=True)

        export = services.export_user_data(user)
        self.assertIn("gold_approver", [e["template"] for e in export["emails"]])  # the export finds Barry's email too

        result = services.delete_user_data(user)

        self.assertFalse(EmailLog.objects.filter(to__icontains=EMAIL).exists())
        self.assertFalse(EmailLog.objects.filter(subject_email=EMAIL).exists())
        self.assertFalse(EmailLog.objects.filter(subject__icontains="Gus").exists())
        self.assertFalse(GoldApplication.objects.filter(pk=application.pk).exists())
        self.assertFalse(Task.objects.filter(func__startswith="gold.tasks.").exists())
        self.assertFalse(Task.objects.filter(func__startswith="users.tasks.").exclude(pk=keep_task.pk).exists())
        self.assertEqual(result["queue_records"], 2)  # the sign-up email task and the Gold email task
        self.assertTrue(EmailLog.objects.filter(subject="Keep me").exists())  # someone else's rows are untouched
        self.assertEqual(len(mail.outbox), 3)  # (nothing was sent again by deleting)

    def test_erase_task_records_also_clears_waiting_jobs_and_ignores_other_functions(self):
        waiting = SignedPackage.dumps({"id": "w", "func": "users.tasks.send_verification_email", "args": ("abc-123",), "kwargs": {}})
        unrelated = SignedPackage.dumps({"id": "u", "func": "users.tasks.send_verification_email", "args": ("zzz",), "kwargs": {}})
        OrmQ.objects.create(key="spa99", payload=waiting)
        OrmQ.objects.create(key="spa99", payload=unrelated)
        Task.objects.create(id="t1", name="t1", func="common.tasks.heartbeat", args=("abc-123",), started="2026-10-22T10:00Z", stopped="2026-10-22T10:00Z", success=True)
        self.assertEqual(erase_task_records(["abc-123"], ["users.tasks."]), 1)
        self.assertEqual(OrmQ.objects.count(), 1)
        self.assertEqual(Task.objects.count(), 1)  # another function, never touched
