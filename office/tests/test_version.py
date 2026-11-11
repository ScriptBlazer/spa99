"""The app version in the Office's left menu: read from APP_VERSION, "dev" when it is not set. Never on a public page."""
import os
from unittest import skipIf

from django.test import Client, override_settings

from common import levels
from office.tests.test_office import OFFICE, OfficeTestCase
from plans.tests.helpers import make_team_member


class VersionTests(OfficeTestCase):
    def office_home(self):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(make_team_member("v@example.test", levels.ADMIN))
        return client.get("/")

    @skipIf(os.environ.get("APP_VERSION"), "APP_VERSION is set in this environment")
    def test_it_falls_back_to_dev(self):
        self.assertContains(self.office_home(), "Version dev")

    @override_settings(APP_VERSION="1.1.7")
    def test_the_version_shows_under_the_name_and_role(self):
        response = self.office_home()
        self.assertContains(response, "Version 1.1.7")
        self.assertContains(response, 'class="o-who-version"')
        self.assertNotContains(response, 'class="o-disc" aria-hidden="true">V</span><span class="o-who-text"')  # the rail has no circle of its own, only the one at the top right

    @override_settings(APP_VERSION="1.1.7")
    def test_it_is_not_on_a_public_page(self):
        self.assertNotContains(Client().get("/"), "1.1.7")
