from django.test import Client, TestCase

from office.tests.test_office import OFFICE
from system.models import SystemEvent
from system.tests.test_system import PASSWORD, SYSTEM, make_user


class OfficeSignInsTests(TestCase):
    def test_an_office_sign_in_shows_in_the_audit_log(self):
        user = make_user("nochum@example.com", system=False)
        Client(HTTP_HOST=OFFICE).post("/login/", {"username": user.email, "password": PASSWORD})
        event = SystemEvent.objects.get(kind=SystemEvent.SIGN_IN)
        self.assertEqual((event.user, event.sentence, event.detail["site"]), (user, "nochum@example.com signed in to Office", "office"))

    def test_a_failed_office_try_is_logged_with_the_typed_email(self):
        Client(HTTP_HOST=OFFICE).post("/login/", {"username": "Who@Example.com", "password": "wrong"})
        event = SystemEvent.objects.get(kind=SystemEvent.SIGN_IN_FAILED)
        self.assertEqual((event.user_label, event.sentence), ("who@example.com", "Office sign-in failed for who@example.com"))

    def test_system_sign_ins_are_written_once_and_the_public_site_not_at_all(self):
        user = make_user("dev@example.com")
        Client(HTTP_HOST=SYSTEM).post("/dev-login/", {"username": user.email, "password": PASSWORD})
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.SIGN_IN).count(), 1)
        Client().post("/login/", {"username": user.email, "password": PASSWORD})
        Client().post("/login/", {"username": user.email, "password": "wrong"})
        self.assertEqual(SystemEvent.objects.filter(kind__in=[SystemEvent.SIGN_IN, SystemEvent.SIGN_IN_FAILED]).count(), 1)

    def test_repeated_wrong_tries_write_one_row_a_minute(self):
        client = Client(HTTP_HOST=OFFICE)
        for _ in range(3):
            client.post("/login/", {"username": "who@example.com", "password": "wrong"})
        self.assertEqual(SystemEvent.objects.filter(kind=SystemEvent.SIGN_IN_FAILED).count(), 1)
