"""Privacy notice and Terms of use (docs/features/legal.md): the real text renders from content rows, the contact email
comes from Site settings, fill-later values are marked on dev only, and the backfill is idempotent and never overwrites
an edited row."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from content import legal, legal_render
from content.models import Page, Section
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings

ICO_TODO = "[ICO registration number — to add before launch]"


class LegalPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        site = SiteSettings.load()
        site.contact_email = "desk@example.com"
        site.save()

    def test_both_pages_render_the_company_and_the_contact_email_from_site_settings(self):
        for path in ("/privacy/", "/terms/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, "BML SPA 99 LIMITED")
                self.assertContains(response, "16930909")
                self.assertContains(response, "40 Wellington Avenue, London N15 6AS")
                self.assertContains(response, 'href="mailto:desk@example.com"')
                self.assertContains(response, "Last updated 23 October 2026")
                self.assertNotContains(response, "To be supplied")
                self.assertNotContains(response, "{contact}")

    def test_contents_list_links_to_every_part(self):
        response = self.client.get("/privacy/")
        for anchor in ("who-we-are", "cookies", "your-rights", "complaints", "contact"):
            self.assertContains(response, f'href="#{anchor}"')
            self.assertContains(response, f'id="{anchor}"')

    def test_privacy_lists_the_real_cookies_and_shows_the_version(self):
        response = self.client.get("/privacy/")
        for cookie in ("csrftoken", "sessionid", "messages", "spa99_journey"):
            self.assertContains(response, cookie)
        self.assertContains(response, f"Version {legal.PRIVACY_VERSION}")
        self.assertEqual(SiteSettings.load().privacy_version, legal.PRIVACY_VERSION)

    def test_terms_link_to_the_privacy_notice_and_fill_the_opening(self):
        response = self.client.get("/terms/")
        self.assertContains(response, 'href="/privacy/"')
        self.assertNotContains(response, "{opening}")

    @override_settings(DEBUG=True)
    def test_dev_marks_the_missing_ico_number_and_hosting_provider(self):
        response = self.client.get("/privacy/")
        self.assertContains(response, ICO_TODO)
        self.assertContains(response, 'data-legal-todo="hosting"')

    def test_live_never_shows_a_placeholder(self):
        html = self.client.get("/privacy/").content.decode()
        self.assertNotIn("to add before launch", html)
        self.assertNotIn("Our registration number is", html)  # the line is dropped until the number exists
        self.assertIn("Website hosting: the servers", html)  # "({hosting})" is dropped

    def test_filled_values_show_everywhere(self):
        Section.objects.filter(page__key="privacy", key="ico").update(body="ZB123456")
        Section.objects.filter(page__key="privacy", key="hosting").update(body="Example Cloud Ltd")
        response = self.client.get("/privacy/")
        self.assertContains(response, "Our registration number is ZB123456.")
        self.assertContains(response, "Website hosting (Example Cloud Ltd)")


class LegalRenderTests(TestCase):
    def test_blocks_links_and_escaping(self):
        html = legal_render.render(
            "Intro <b>bold</b>\n### Small heading\n- one\n- two [x](/privacy/)\nAfter [bad](javascript:alert(1))",
            contact="a@b.com")
        self.assertIn("<p>Intro &lt;b&gt;bold&lt;/b&gt;</p>", html)
        self.assertIn("<h3>Small heading</h3>", html)
        self.assertIn('<ul><li>one</li><li>two <a href="/privacy/">x</a></li></ul>', html)
        self.assertNotIn('href="javascript', html)

    def test_placeholder_rules(self):
        text = "Number {ico}.\nHost ({hosting}) here."
        self.assertEqual(legal_render.render(text), "<p>Host here.</p>")
        self.assertIn("legal-todo", legal_render.render(text, show_placeholders=True))
        self.assertIn("<p>Number 1&lt;2.</p>", legal_render.render(text, values={"ico": "1<2"}))


class LegalBackfillTests(TestCase):
    def _old_install(self):
        """The legal rows as seeded before 2026-10-23."""
        privacy = Page.objects.create(key="privacy", title="Privacy notice", meta_description="How Spa 99 uses your information.")
        for order, (key, heading, body) in enumerate([
                ("body", "Privacy notice.", ""), ("draft_note", "Draft.", legal.OLD_DRAFT_NOTE),
                ("part_1", "What we collect", "To be supplied."), ("part_2", "How we use it", "Edited by hand."),
                ("contact", "Contact", "Write to us at")], start=1):
            Section.objects.create(page=privacy, key=key, heading=heading, body=body, order=order)
        Page.objects.create(key="terms", title="Terms", meta_description="Spa 99 terms.")
        site = SiteSettings.load()
        site.privacy_version = "draft-1"
        site.save()

    def test_replaces_placeholders_only_and_runs_twice_safely(self):
        self._old_install()
        call_command("backfill_site_data", "--dry-run", stdout=StringIO())
        self.assertEqual(Section.objects.get(page__key="privacy", key="part_1").body, "To be supplied.")
        call_command("backfill_site_data", stdout=StringIO())
        rows = {s.key: s for s in Section.objects.filter(page__key="privacy")}
        self.assertEqual(rows["part_1"].heading, "Who we are")
        self.assertEqual(rows["part_2"].body, "Edited by hand.")  # edited in Control: left alone
        self.assertIn("{contact}", rows["contact"].body)
        self.assertFalse(rows["draft_note"].visible)
        self.assertIn("part_11", rows)
        self.assertEqual(Page.objects.get(key="terms").title, "Terms of use")
        self.assertEqual(SiteSettings.load().privacy_version, legal.PRIVACY_VERSION)
        out = StringIO()
        call_command("backfill_site_data", stdout=out)
        self.assertNotIn("legal", out.getvalue())

    def test_a_chosen_privacy_version_is_kept(self):
        site = SiteSettings.load()
        site.privacy_version = "2027-01-01"
        site.save()
        call_command("backfill_site_data", stdout=StringIO())
        self.assertEqual(SiteSettings.load().privacy_version, "2027-01-01")
