"""Back to top control: on public marketing and content pages, never on the journey, the member area, the memberships page
(own bottom bar), the tour or the reduced layouts."""
from django.test import TestCase

from plans.management.commands.seed_phase1 import seed_all
from users.tests.test_member_dashboard import make_user, plan

MARK = "data-back-to-top"


class BackToTopTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_present_on_public_content_pages(self):
        for path in ("/", "/the-spa/", "/visit/", "/gold-card/", "/privacy/"):
            with self.subTest(path=path):
                response = self.client.get(path, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, MARK)
                self.assertContains(response, 'href="#top"')

    def test_absent_where_it_would_clash_or_does_not_belong(self):
        for path in ("/memberships/", "/tour/", "/journey/"):
            with self.subTest(path=path):
                response = self.client.get(path, follow=True)
                self.assertNotContains(response, MARK)

    def test_absent_in_the_member_area(self):
        user = make_user(plan=plan("tier-2"))
        self.client.force_login(user)
        response = self.client.get("/account/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "m-chrome")
        self.assertNotContains(response, MARK)
