"""2026-10-29: WhatsApp as proper buttons (footer on every page, one calm button per public page), the Gold wording, and the backfill
(number from the old link, Gold copy by exact old wording). No network."""
import re
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase

from chat.models import FaqItem
from content.models import Page, Section
from plans.management.commands import backfill_site_data as backfill
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan, SiteSettings
from plans.tests.helpers import open_memberships

BUTTON = "btn btn-secondary btn-whatsapp"


def run_backfill(*args):
    out = StringIO()
    call_command("backfill_site_data", *args, stdout=out)
    return out.getvalue()


class ButtonPlacementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        open_memberships()

    def set_number(self, number="447441919990"):
        SiteSettings.load()
        SiteSettings.objects.update(whatsapp_number=number)

    def test_the_footer_button_shows_on_public_pages_and_hides_without_a_number(self):
        self.set_number()
        for path in ("/", "/the-spa/", "/memberships/", "/gold-card/", "/visit/", "/book/", "/privacy/"):
            html = self.client.get(path).content.decode()
            self.assertIn('href="/whatsapp/?from=footer"', html, path)
            self.assertIn("footer-whatsapp", html, path)
        self.set_number("")
        for path in ("/", "/gold-card/", "/visit/"):
            html = self.client.get(path).content.decode()
            self.assertNotIn("/whatsapp/", html, path)
            self.assertNotIn(BUTTON, html, path)

    def test_each_page_has_one_in_page_button_with_its_own_source_plus_the_footer(self):
        self.set_number()
        for path, source in (("/gold-card/", "gold_card"), ("/book/", "book"), ("/visit/", "visit"),
                             ("/memberships/", "memberships"), ("/tour/", "tour")):
            html = self.client.get(path).content.decode()
            self.assertEqual(len(re.findall(rf'href="/whatsapp/\?from={source}(?:&amp;msg=rates)?"', html)), 1, path)
            self.assertLessEqual(html.count(BUTTON), 2, path)  # one in the page and the footer, never a second in-page button
            self.assertNotIn("position: fixed", html)

    def test_home_and_the_spa_have_only_the_footer_button(self):
        self.set_number()
        for path in ("/", "/the-spa/"):
            html = self.client.get(path).content.decode()
            self.assertEqual(len(re.findall(r'href="/whatsapp/\?from=(?!chat)[a-z_]+', html)), 1, path)
            self.assertIn("/whatsapp/?from=footer", html)

    def test_the_whatsapp_icon_is_in_the_sprite(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("common/img/icons.svg")) as sprite:
            self.assertIn('id="whatsapp-logo"', sprite.read())


class GoldWordingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        open_memberships()

    def test_the_gold_card_is_for_bml_clients_everywhere_it_is_described(self):
        said = "a free membership"
        self.assertIn("A free membership* for BML clients, past, present and future, by approval.", Client().get("/gold-card/").content.decode())
        self.assertIn("A free membership* for BML clients, past, present and future, by approval.", Client().get("/").content.decode())
        self.assertIn("The Gold Card: a free membership* for BML clients, past, present and future, by approval.", Client().get("/memberships/").content.decode())
        self.assertIn("for BML clients", Section.objects.get(page__key="memberships", key="gold_line").body)
        self.assertIn("Every application is reviewed personally. Not a BML client yet? You&#x27;re still welcome to apply.", Client().get("/gold-card/").content.decode())
        self.assertIn("for BML clients, past, present and future, by approval", Page.objects.get(key="gold").meta_description)
        self.assertIn(said.lower(), Plan.objects.get(slug="gold").short_description.lower())
        self.assertIn(said.lower(), Section.objects.get(page__key="journey", key="gold_panel").body.lower())
        self.assertIn(said.lower(), Section.objects.get(page__key="journey", key="gold_line").body.lower())
        self.assertIn(said.lower(), FaqItem.objects.get(question="What is the Gold Card?").answer.lower())


class BackfillTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_the_number_is_copied_from_the_old_link_and_never_overwritten(self):
        SiteSettings.load()
        SiteSettings.objects.update(discount_contact_url="https://wa.me/447441919990", whatsapp_number="")
        self.assertIn("Would change 1 x plans.SiteSettings (WhatsApp number", run_backfill("--dry-run"))
        self.assertEqual(SiteSettings.load().whatsapp_number, "")
        run_backfill()
        self.assertEqual(SiteSettings.load().whatsapp_number, "447441919990")
        SiteSettings.objects.update(whatsapp_number="447000000000")
        run_backfill()
        self.assertEqual(SiteSettings.load().whatsapp_number, "447000000000")

    def test_an_old_link_that_is_not_a_plain_wa_me_link_is_left_alone(self):
        SiteSettings.load()
        for url in ("https://api.whatsapp.com/send?phone=447441919990", "https://wa.me/447441919990?text=Hi", ""):
            SiteSettings.objects.update(discount_contact_url=url, whatsapp_number="")
            run_backfill()
            self.assertEqual(SiteSettings.load().whatsapp_number, "", url)

    def test_the_gold_copy_is_updated_on_exact_old_wording_only_and_once(self):
        for page_key, key, field, olds, new in backfill.OLD_GOLD_SECTIONS:
            Section.objects.filter(page__key=page_key, key=key).update(**{field: olds[0]})  # the original live wording
        Page.objects.filter(key="gold").update(meta_description=backfill.OLD_GOLD_META[1][0])
        Plan.objects.filter(slug="gold").update(short_description=backfill.OLD_GOLD_PLAN[0][0])
        FaqItem.objects.filter(question="What is the Gold Card?").update(answer=backfill.OLD_GOLD_FAQ[0][0])
        Section.objects.filter(page__key="gold", key="who_note").update(body="Not in property? You're still welcome (edited by hand).")  # edited: kept
        text = run_backfill()
        self.assertIn("content.Section (Gold: for BML clients)", text)
        for page_key, key, field, olds, new in backfill.OLD_GOLD_SECTIONS:
            expected = "Not in property? You're still welcome (edited by hand)." if key == "who_note" else new
            self.assertEqual(getattr(Section.objects.get(page__key=page_key, key=key), field), expected, key)
        self.assertEqual(Page.objects.get(key="gold").meta_description, backfill.OLD_GOLD_META[2])
        self.assertEqual(Plan.objects.get(slug="gold").short_description, backfill.OLD_GOLD_PLAN[1])
        self.assertEqual(FaqItem.objects.get(question="What is the Gold Card?").answer, backfill.OLD_GOLD_FAQ[1])
        self.assertNotIn("Gold: for BML clients", run_backfill())  # a second run changes nothing

    def test_an_edited_faq_and_edited_copy_are_not_touched(self):
        FaqItem.objects.filter(question="What is the Gold Card?").update(answer="Our own words.")
        Section.objects.filter(page__key="home", key="gold_teaser").update(body="Something I wrote.")
        run_backfill()
        self.assertEqual(FaqItem.objects.get(question="What is the Gold Card?").answer, "Our own words.")
        self.assertEqual(Section.objects.get(page__key="home", key="gold_teaser").body, "Something I wrote.")


class RateMessageTests(TestCase):
    """The "better prices" message (msg=rates) is its own editable text; only the better-rate spots use it."""

    @classmethod
    def setUpTestData(cls):
        seed_all()
        open_memberships()

    def setUp(self):
        SiteSettings.load()
        SiteSettings.objects.update(whatsapp_number="447441919990")
        self.client = Client(HTTP_USER_AGENT="Mozilla/5.0 (iPhone) Safari/604.1")

    def test_the_default_and_the_encoded_saved_text(self):
        self.assertEqual(SiteSettings.load().whatsapp_rate_message, "Hi, I'd like to discuss better prices for Spa 99.")
        self.assertEqual(self.client.get("/whatsapp/?from=register&msg=rates")["Location"],
                         "https://wa.me/447441919990?text=Hi%2C%20I%27d%20like%20to%20discuss%20better%20prices%20for%20Spa%2099.")
        SiteSettings.objects.update(whatsapp_rate_message="Rates & offers? 50%")
        self.assertEqual(self.client.get("/whatsapp/?msg=rates")["Location"], "https://wa.me/447441919990?text=Rates%20%26%20offers%3F%2050%25")
        self.assertIn("Gold%20Card", self.client.get("/whatsapp/?msg=gold_business")["Location"])  # its own text is untouched
        SiteSettings.objects.update(whatsapp_rate_message="")  # empty: the general message
        self.assertIn("find%20out%20more", self.client.get("/whatsapp/?msg=rates")["Location"])

    def test_every_better_rate_button_uses_rates_and_the_others_do_not(self):
        page = lambda path: self.client.get(path).content.decode()
        for path, source in (("/register/", "register"), ("/memberships/", "memberships")):
            self.assertIn(f'href="/whatsapp/?from={source}&amp;msg=rates"', page(path), path)
        self.assertIn("/whatsapp/?from=journey&msg=rates", self.client.get("/journey/").content.decode().replace("\\u0026", "&"))
        for path, source in (("/visit/", "visit"), ("/gold-card/", "gold_card"), ("/book/", "book")):
            html = page(path)
            self.assertIn(f'href="/whatsapp/?from={source}"', html)
            self.assertNotIn("msg=rates", html, path)

    def test_the_chat_hand_off_and_the_assistant_link_use_rates(self):
        from chat import knowledge, services

        self.assertEqual(services.handoff_links("asked")["whatsapp_url"], "/whatsapp/?from=chat&msg=rates")
        from django.template.loader import render_to_string

        html = render_to_string("chat/_chat.html", {"chat_gate": {"consent": "", "privacy_label": ""}, "chat_handoff": services.handoff_links("asked"), "chat_suggested": []})
        self.assertIn("/whatsapp/?from=chat&amp;msg=rates", html)
        self.assertIn("/whatsapp/?from=chat&msg=rates", "\n".join(knowledge._about(SiteSettings.load())))
