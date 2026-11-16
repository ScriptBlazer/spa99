"""A System save checks only the fields it changes (plus the model's own rules); errors never crash a page. Mocked."""
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from plans.models import SiteSettings
from system import services
from system.tests.test_system import make_user, unlocked_client

NEW_SENDER = "Spa 99 <hello@new.example>"


class NarrowSaveTests(TestCase):
    def setUp(self):
        self.dev = make_user()
        self.client = unlocked_client(self.dev)

    def _stale_site(self):
        site = SiteSettings.load()
        SiteSettings.objects.filter(pk=site.pk).update(auto_email_from_address="old@old.example")  # stored before the sending domain moved
        return SiteSettings.load()

    @override_settings(DEFAULT_FROM_EMAIL=NEW_SENDER)
    def test_saving_a_form_ignores_a_stored_value_on_a_field_that_is_not_on_it(self):
        self._stale_site()
        response = self.client.post("/emails/", {"contact_email": "front@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SiteSettings.load().contact_email, "front@example.com")

    @override_settings(DEFAULT_FROM_EMAIL=NEW_SENDER)
    def test_a_full_check_still_rejects_the_invalid_stored_field(self):
        site = self._stale_site()
        with self.assertRaises(ValidationError) as caught:
            services.save_logged(site, self.dev)  # fields=None: new rows and other callers get the whole row checked
        self.assertIn("auto_email_from_address", caught.exception.message_dict)
        site.contact_email = "front@example.com"
        with self.assertRaises(ValidationError):
            services.save_logged(site, self.dev, fields=["contact_email", "auto_email_from_address"])  # asked to save it: checked

    def test_a_model_error_on_a_field_not_in_the_form_is_a_form_error_not_a_500(self):
        error = ValidationError({"auto_email_from_address": ["Wrong domain."], "contact_email": ["Bad address."], "__all__": ["Whole row."]})
        with mock.patch("system.views.services.save_form", side_effect=error):
            response = self.client.post("/emails/", {"contact_email": "front@example.com"})
        self.assertEqual(response.status_code, 400)
        form = response.context["form"]
        self.assertEqual(form.errors["contact_email"], ["Bad address."])
        self.assertIn("Automatic emails sender address: Wrong domain.", form.non_field_errors())
        self.assertIn("Whole row.", form.non_field_errors())
