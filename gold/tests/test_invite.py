"""Gold approval and the account invite. Email goes through the sync test queue into the locmem outbox (nothing real)."""
import re
from datetime import timedelta

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from gold import invites, services
from gold.admin import GoldApplicationAdmin
from gold.models import GoldApplication, GoldInvite
from gold.tests.test_gold import application_data
from plans.management.commands.seed_phase1 import seed_all
from users.models import InterestRegistration

User = get_user_model()
PASSWORD = "correct horse battery staple"


def make_application(**over):
    return services.submit_application(application_data(**over))[0]


def staff(with_permission=True, email="barry@example.com"):
    user = User.objects.create_user(email, PASSWORD, is_staff=True)
    if with_permission:
        user.user_permissions.add(Permission.objects.get(codename="change_goldapplication"))
    return user


def link_in(message):
    return re.search(r"https?://\S+/gold/invite/[^/\s]+/", message.body).group(0)


def invite_mail():
    return [m for m in mail.outbox if "approved" in m.subject][-1]


class ApprovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        mail.outbox.clear()
        self.barry = staff()

    def test_approve_creates_a_14_day_invite_and_queues_the_email(self):
        application = make_application()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.INVITED)
        application.refresh_from_db()
        self.assertEqual((application.status, application.approved_by), ("approved", self.barry))
        self.assertAlmostEqual(application.approved_at, timezone.now(), delta=timedelta(seconds=5))
        invite = application.invites.get()
        self.assertAlmostEqual(invite.expires_at - invite.created_at, timedelta(days=14), delta=timedelta(seconds=5))
        self.assertIsNotNone(invite.sent_at)
        message = invite_mail()
        self.assertEqual(message.to, ["dan@example.com"])
        self.assertIn("Set up your account", message.alternatives[0][0])
        self.assertEqual(invites.read_invite(link_in(message).rstrip("/").rsplit("/", 1)[1])[0], invites.OK)

    def test_resend_makes_a_new_link_and_the_old_one_stops_working(self):
        application = make_application()
        invites.approve_and_invite(application, self.barry)
        old = link_in(invite_mail()).rstrip("/").rsplit("/", 1)[1]
        self.assertEqual(invites.resend_invite(application), invites.INVITED)
        new = link_in(invite_mail()).rstrip("/").rsplit("/", 1)[1]
        self.assertEqual(invites.read_invite(old)[0], invites.INVALID)
        self.assertEqual(invites.read_invite(new)[0], invites.OK)

    def test_declined_never_gets_an_invite(self):
        application = make_application()
        application.status = GoldApplication.DECLINED
        application.save()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.SKIPPED)
        self.assertEqual(invites.resend_invite(application), invites.SKIPPED)
        self.assertFalse(GoldInvite.objects.exists())
        self.assertFalse([m for m in mail.outbox if "approved" in m.subject])

    def test_existing_account_gets_gold_and_a_short_email_not_an_invite(self):
        member = User.objects.create_user("dan@example.com", PASSWORD, first_name="Dan")
        application = make_application()
        mail.outbox.clear()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.ACTIVATED)
        application.refresh_from_db()
        self.assertEqual(application.user, member)
        self.assertEqual(InterestRegistration.objects.get(user=member).plan.slug, "gold")
        self.assertFalse(GoldInvite.objects.exists())
        self.assertEqual([m.subject for m in mail.outbox], ["Your Spa 99 Gold Card is active"])

    def test_only_staff_with_the_change_permission_see_the_actions(self):
        model_admin = GoldApplicationAdmin(GoldApplication, admin_site)
        request = RequestFactory().get("/")
        request.user = staff(with_permission=False, email="viewer@example.com")
        self.assertNotIn("approve_and_invite", model_admin.get_actions(request))
        request.user = self.barry
        self.assertIn("approve_and_invite", model_admin.get_actions(request))


class SetupPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        mail.outbox.clear()
        self.application = make_application()
        invites.approve_and_invite(self.application, staff())
        self.url = "/" + link_in(invite_mail()).split("/", 3)[3]
        self.client = Client(enforce_csrf_checks=True)

    def post(self, **over):
        self.client.get("/login/")  # sets the CSRF cookie
        data = {"password": PASSWORD, "date_of_birth": "1985-03-04", "men_only_accepted": "on", "privacy_accepted": "on",
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value}
        data.update(over)
        return self.client.post(self.url, data)

    def test_form_is_prefilled_and_posting_creates_the_account_with_gold_from_approval(self):
        page = self.client.get(self.url)
        self.assertContains(page, 'value="Dan"')
        self.assertContains(page, 'value="dan@example.com"')
        self.assertContains(page, 'value="+447912345678"')
        response = self.post()
        self.assertRedirects(response, "/account/", fetch_redirect_response=False)
        user = User.objects.get(email="dan@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(user.mobile, "+447912345678")
        self.application.refresh_from_db()
        self.assertEqual(self.application.user, user)
        self.assertEqual(InterestRegistration.objects.get(user=user).plan.slug, "gold")
        self.assertEqual(invites.gold_since(user), self.application.approved_at)
        self.assertEqual(self.client.get("/account/").wsgi_request.user, user)  # signed in
        self.assertContains(self.client.get("/account/membership/"), "Gold member since")

    def test_a_used_link_is_refused(self):
        self.assertEqual(self.post().status_code, 302)
        response = Client().get(self.url)
        self.assertContains(response, "This link can't be used", status_code=410)
        self.assertEqual(User.objects.filter(email="dan@example.com").count(), 1)

    def test_expired_and_tampered_links_look_the_same(self):
        GoldInvite.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        expired = self.client.get(self.url)
        tampered = self.client.get(self.url[:-3] + "xx/")
        self.assertEqual(expired.status_code, tampered.status_code)
        self.assertContains(expired, "This link can't be used", status_code=410)
        self.assertEqual(self.post().status_code, 410)
        self.assertFalse(User.objects.filter(email="dan@example.com").exists())

    def test_under_18_is_refused_and_dob_is_stored(self):
        under = (timezone.now().date() - timedelta(days=365 * 17)).isoformat()
        self.assertEqual(self.post(date_of_birth=under).status_code, 400)
        self.assertFalse(User.objects.filter(email="dan@example.com").exists())
        self.assertEqual(self.post().status_code, 302)
        self.assertEqual(str(User.objects.get(email="dan@example.com").date_of_birth), "1985-03-04")

    def test_a_mobile_used_by_another_account_becomes_editable_with_the_usual_message(self):
        User.objects.create_user("other@example.com", PASSWORD, mobile="+447912345678")
        self.assertContains(self.client.get(self.url), 'name="mobile"')
        response = self.post(mobile="07912 345678")
        self.assertContains(response, "already registered", status_code=400)
        self.assertEqual(self.post(mobile="07911 111222").status_code, 302)
        self.assertEqual(User.objects.get(email="dan@example.com").mobile, "+447911111222")

    def test_an_invalid_mobile_on_the_application_asks_again_instead_of_crashing(self):
        GoldApplication.objects.update(mobile="+447700900123")  # not a valid UK mobile
        self.assertContains(self.client.get(self.url), 'name="mobile"')
        self.assertContains(self.post(), "mobile", status_code=400)  # required again, no 500
        self.assertFalse(User.objects.filter(email="dan@example.com").exists())
        self.assertEqual(self.post(mobile="07123 456789").status_code, 302)
        self.assertEqual(User.objects.get(email="dan@example.com").mobile, "+447123456789")

    def test_weak_password_and_missing_acceptance_are_refused(self):
        self.assertEqual(self.post(password="short").status_code, 400)
        self.assertEqual(self.post(privacy_accepted="").status_code, 400)
        self.assertFalse(User.objects.filter(email="dan@example.com").exists())


class ReviewFixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        mail.outbox.clear()
        self.barry = staff()

    def test_missing_gold_plan_rolls_back_and_sends_nothing(self):
        from plans.models import Plan

        member = User.objects.create_user("dan@example.com", PASSWORD)
        application = make_application()
        mail.outbox.clear()
        Plan.objects.filter(slug="gold").delete()
        self.assertEqual(invites.approve_and_invite(application, self.barry), invites.SKIPPED)
        application.refresh_from_db()
        self.assertEqual((application.status, application.approved_at, application.user), ("new", None, member))  # linked at apply time, not by approval
        self.assertFalse(InterestRegistration.objects.filter(user=member).exists())
        self.assertEqual(mail.outbox, [])

    def test_a_second_approval_of_the_same_application_is_skipped(self):
        application = make_application()
        stale = GoldApplication.objects.get(pk=application.pk)  # a second admin tab holding the old status
        invites.approve_and_invite(application, self.barry)
        self.assertEqual(invites.approve_and_invite(stale, self.barry), invites.SKIPPED)
        self.assertEqual(GoldInvite.objects.count(), 1)

    def test_erasing_a_person_removes_invite_queue_records_and_export_lists_the_dates(self):
        from django_q.models import Task

        application = make_application()
        invites.approve_and_invite(application, self.barry)
        invite = application.invites.get()
        exported = services.export_applications("dan@example.com")[0]
        self.assertIsNotNone(exported["approved_at"])
        self.assertEqual(set(exported["invites"][0]), {"created_at", "sent_at", "expires_at", "used_at", "replaced_at"})
        Task.objects.create(id="t1", name="x", func="gold.tasks.send_gold_invite_email", args=(str(invite.pk),), started=timezone.now(), stopped=timezone.now(), success=True)
        result = services.delete_applications("dan@example.com")
        self.assertGreaterEqual(result["queue_records"], 1)
        self.assertFalse(Task.objects.filter(func="gold.tasks.send_gold_invite_email").exists())
        self.assertFalse(GoldInvite.objects.exists())

    def test_setup_page_is_not_cached(self):
        application = make_application()
        invites.approve_and_invite(application, self.barry)
        link = "/" + link_in(invite_mail()).split("/", 3)[3]
        self.assertIn("no-store", Client().get(link)["Cache-Control"])
