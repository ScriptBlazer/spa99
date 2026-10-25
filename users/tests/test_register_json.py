"""The register form is sent with fetch: errors come back as JSON (a list the page shows in one dialog), never a reload."""
from unittest import mock

from django.test import TestCase

from plans.management.commands.seed_phase1 import seed_all
from users.models import User
from users.tests.test_register import signup_data

JSON = {"HTTP_X_REQUESTED_WITH": "fetch", "HTTP_ACCEPT": "application/json"}


class RegisterJsonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def post(self, **over):
        return self.client.post("/register/", signup_data(**over), **JSON)

    def test_a_missing_plan_is_listed_first_with_label_and_message(self):
        response = self.post(plan="", password="short")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["errors"][0], {"field": "plan", "label": "Membership", "message": "Choose a membership to continue."})
        self.assertIn("password", [e["field"] for e in data["errors"]])
        for error in data["errors"]:
            self.assertEqual(set(error), {"field", "label", "message"})
        self.assertFalse(User.objects.filter(email="hugo@example.com").exists())

    def test_a_duplicate_mobile_keeps_the_pages_wording(self):
        self.assertTrue(self.post().json()["ok"])
        data = self.post(email="other@example.com").json()
        self.assertEqual(data["errors"], [{"field": "mobile", "label": "Mobile", "message": "That mobile number is already registered."}])

    def test_success_returns_the_redirect_and_remembers_the_email(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "redirect": "/register/sent/"})
        self.assertEqual(self.client.session["pending_verification_email"], "hugo@example.com")

    def test_the_honeypot_looks_like_success_and_creates_nothing(self):
        response = self.post(website="http://spam.example")
        self.assertEqual(response.json(), {"ok": True, "redirect": "/register/sent/"})
        self.assertEqual(User.objects.count(), 0)

    def test_rate_limit_answers_429_json_with_a_calm_message(self):
        with mock.patch("users.views._throttled", return_value=True):
            response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["errors"], [{"field": "__all__", "label": "", "message": "Too many attempts. Please try again later."}])
        self.assertEqual(User.objects.count(), 0)

    def test_the_plain_post_is_unchanged(self):
        response = self.client.post("/register/", signup_data(plan=""))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Choose a membership to continue.", status_code=400)
        self.assertTemplateUsed(response, "users/register.html")
        ok = self.client.post("/register/", signup_data())
        self.assertRedirects(ok, "/register/sent/")
