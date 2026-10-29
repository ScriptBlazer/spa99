"""Review fixes: 12 hour sign-in limit, VAT range, 404 before CSRF, atomic undo all, no double undo, unlock after a POST."""
import uuid
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from plans.models import SiteSettings
from system import services
from system.models import SystemChange
from system.tests.test_extras import SETTINGS_POST
from system.tests.test_system import PASSWORD, make_user, sign_in, unlocked_client

ZERO = "00000000-0000-0000-0000-000000000000"
POST_ROUTES = ["/lock/", "/unlock/", "/unlock/ping/", "/logout/", f"/changes/{ZERO}/undo/", f"/changes/batch/{ZERO}/undo/", "/emails/", "/settings/",
               f"/team/{ZERO}/roles/", f"/team/{ZERO}/active/", "/plans/add/", f"/plans/{ZERO}/", "/hours/capacity/", "/hours/rules/add/",
               f"/hours/rules/{ZERO}/", "/hours/closures/add/", f"/hours/closures/{ZERO}/", f"/hours/closures/{ZERO}/delete/", "/gold/add/",
               f"/gold/{ZERO}/", f"/journey/questions/{ZERO}/", f"/journey/questions/{ZERO}/options/add/", f"/journey/options/{ZERO}/",
               f"/journey/suggestions/{ZERO}/"]


class SignInLimitTests(TestCase):
    def test_the_sign_in_ends_after_12_hours_however_active_the_person_is(self):
        client, _ = sign_in(make_user())
        start = client.session[services.SIGNED_IN_KEY]
        with mock.patch("system.services.time.time", return_value=start):
            client.post("/unlock/", {"password": PASSWORD})
        for minutes in range(10, 12 * 60, 10):  # busy every 10 minutes (the 15 minute idle lock never fires)
            with mock.patch("system.services.time.time", return_value=start + minutes * 60):
                self.assertEqual(client.get("/").status_code, 200, minutes)
        with mock.patch("system.services.time.time", return_value=start + 12 * 3600 + 60):
            response = client.get("/")
        self.assertEqual((response.status_code, response["Location"]), (302, "/dev-login/"))
        self.assertEqual(client.get("/").status_code, 404)  # signed out now


class VatTests(TestCase):
    def test_vat_must_be_between_0_and_100_and_is_confirmed_as_risky(self):
        site = SiteSettings.load()
        for bad in (Decimal("-5"), Decimal("999")):
            site.vat_rate = bad
            with self.assertRaises(ValidationError):
                site.full_clean()
        client = unlocked_client(make_user())
        for bad in ("-5", "999"):
            response = client.post("/settings/", SETTINGS_POST | {"vat_rate": bad})
            self.assertEqual(response.status_code, 400)
            self.assertIn("vat_rate", response.context["form"].errors)
        self.assertEqual(SiteSettings.load().vat_rate, Decimal("20.00"))
        self.assertIn("vat_rate", client.get("/settings/").context["risky_fields"])


class NotFoundBeforeCsrfTests(TestCase):
    def test_strangers_get_404_on_every_system_post_even_without_a_csrf_token(self):
        approver = make_user("approver@example.com", system=False)
        approver.groups.add(Group.objects.get_or_create(name="Approver")[0])
        staff = make_user("office@example.com", system=False)
        for who in (None, staff, approver):
            client = Client(HTTP_HOST="system.localhost", enforce_csrf_checks=True)
            if who:
                client.force_login(who)
            for path in POST_ROUTES + ["/nowhere/"]:
                self.assertEqual(client.post(path).status_code, 404, (who, path))

    def test_the_sign_in_post_still_needs_its_csrf_token_and_a_developer_is_not_blocked(self):
        user = make_user()
        anonymous = Client(HTTP_HOST="system.localhost", enforce_csrf_checks=True)
        self.assertEqual(anonymous.post("/dev-login/", {"username": user.email, "password": PASSWORD}).status_code, 403)
        client = Client(HTTP_HOST="system.localhost", enforce_csrf_checks=True)
        token = client.get("/dev-login/").cookies["csrftoken"].value
        self.assertEqual(client.post("/dev-login/", {"username": user.email, "password": PASSWORD, "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(client.post("/lock/").status_code, 403)  # a real developer without a token: the ordinary CSRF refusal


class UndoSafetyTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def test_undo_all_is_all_or_nothing_on_an_unexpected_error_and_reports_refusals(self):
        self.client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00", "opening_text": "March 2027"})
        batch = SystemChange.objects.first().batch_id
        real = services.undo_change
        calls = []

        def flaky(change, user):
            calls.append(change.pk)
            if len(calls) == 2:
                raise RuntimeError("boom")
            return real(change, user)

        with mock.patch("system.services.undo_change", flaky), self.assertRaises(RuntimeError):
            services.undo_batch(batch, self.user)
        site = SiteSettings.load()
        self.assertEqual((str(site.vat_rate), site.opening_text), ("25.00", "March 2027"))  # the first undo was rolled back too
        SiteSettings.objects.update(opening_text="Changed again")  # one entry now refused, the other still goes through
        done, refused = services.undo_batch(batch, self.user)
        self.assertEqual((done, len(refused)), (1, 1))
        self.assertEqual(str(SiteSettings.load().vat_rate), "20.00")

    def test_a_change_that_was_already_undone_cannot_be_undone_again(self):
        self.client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00"})
        change = SystemChange.objects.get(field="vat_rate")
        services.undo_change(change, self.user)
        SiteSettings.objects.update(vat_rate=Decimal("25.00"))  # the value is back to what the entry set
        with self.assertRaisesMessage(services.ChangeRefused, "already been undone"):
            services.undo_change(change, self.user)
        self.assertEqual(SiteSettings.load().vat_rate, Decimal("25.00"))


class UnlockAfterPostTests(TestCase):
    def test_a_locked_post_comes_back_to_the_referer_or_the_section_page_not_the_post_only_url(self):
        client, _ = sign_in(make_user())
        referer = client.post("/plans/add/", HTTP_REFERER="http://system.localhost/plans/?x=1")
        self.assertEqual(referer["Location"], "/unlock/?next=%2Fplans%2F%3Fx%3D1")
        foreign = client.post(f"/hours/closures/{uuid.uuid4()}/delete/", HTTP_REFERER="http://evil.example/x")
        self.assertEqual(foreign["Location"], "/unlock/?next=%2Fhours%2F")
        self.assertEqual(client.post("/lock/").status_code, 302)
        self.assertRedirects(client.post("/unlock/", {"password": PASSWORD, "next": "/plans/?x=1"}), "/plans/?x=1")
