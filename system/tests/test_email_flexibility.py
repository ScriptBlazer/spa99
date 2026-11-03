"""System > Emails: the Footer tab and the per-email footer, sender, heading and button text (office-outreach.md, Email flexibility)."""
from django.core import mail
from django.test import TestCase, override_settings

from notifications.models import NotificationTemplate
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings
from system.models import SystemChange
from system.tests.test_system import make_user, unlocked_client

SAVE = "/emails/automatic/verify/save/"
BASE = {"subject": "Confirm", "body": ""}


@override_settings(DEFAULT_FROM_EMAIL="Spa 99 <hello@spa99.test>")
class EmailFlexibilityViewTests(TestCase):
    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())

    def test_footer_tab_saves_lines_is_logged_and_checks_placeholders(self):
        page = self.client.get("/emails/footer/")
        self.assertContains(page, 'data-tab="footer"')
        self.assertEqual(page.context["form"].initial["footer_brand_line"], "Beyond Luxury")
        bad = self.client.post("/emails/footer/", {"footer_brand_line": "x", "footer_address_line": "{nope}", "footer_contact_line": ""})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("footer_address_line", bad.context["form"].errors)
        self.client.post("/emails/footer/", {"footer_brand_line": "Quiet", "footer_address_line": "{address}", "footer_contact_line": ""})
        row = SiteSettings.load()
        self.assertEqual((row.footer_brand_line, row.footer_address_line, row.footer_contact_line), ("Quiet", "{address}", ""))  # blank is kept: left out
        fields = SystemChange.objects.filter(model_label="plans.sitesettings", section="emails").values_list("field", flat=True)
        self.assertEqual(sorted(fields), ["footer_address_line", "footer_brand_line", "footer_contact_line"])

    def test_footer_preview_follows_what_is_typed_and_keeps_the_unsubscribe_line(self):
        data = {"footer_brand_line": "Typed brand", "footer_address_line": "", "footer_contact_line": "Ring us"}
        good = self.client.post("/emails/footer/preview/", data).json()
        self.assertTrue(good["ok"])
        self.assertIn("Typed brand", good["html"])
        self.assertIn("Unsubscribe", good["html"])
        self.assertEqual(SiteSettings.load().footer_brand_line, "Beyond Luxury")  # a preview saves nothing
        bad = self.client.post("/emails/footer/preview/", {**data, "footer_contact_line": "{zzz}"}).json()
        self.assertEqual((bad["ok"], list(bad["errors"])), (False, ["footer_contact_line"]))

    def test_per_email_settings_save_default_values_as_blank_and_reset_restores_all(self):
        page = self.client.get("/emails/automatic/verify/")
        self.assertEqual((page.context["form"].initial["footer_mode"], page.context["form"].initial["sender"]), ("shared", "site"))
        self.client.post(SAVE, {**BASE, "footer_mode": "custom", "footer_brand_line": "B", "footer_address_line": "A", "footer_contact_line": "",
                                "sender": "person", "heading": "Hello {first_name}", "button_text": "Confirm now"})
        row = NotificationTemplate.objects.get(key="verify")
        self.assertEqual((row.footer_mode, row.sender, row.heading, row.button_text, row.footer_brand_line), ("custom", "person", "Hello {first_name}", "Confirm now", "B"))
        self.assertTrue({"footer_mode", "sender", "heading", "button_text"} <= set(SystemChange.objects.filter(model_label="notifications.notificationtemplate").values_list("field", flat=True)))
        self.assertNotIn("Reset to default", self.client.get("/emails/automatic/welcome/").content.decode())
        self.assertContains(self.client.get("/emails/automatic/verify/"), "Reset to default")
        self.client.post(SAVE, {**BASE, "footer_mode": "shared", "sender": "site"})  # the defaults again: stored blank
        row.refresh_from_db()
        self.assertEqual((row.footer_mode, row.sender), ("", ""))
        self.client.post(SAVE, {**BASE, "footer_mode": "no_contact", "sender": "person", "heading": "H", "button_text": "B"})
        self.client.post("/emails/automatic/verify/reset/")
        row.refresh_from_db()
        self.assertEqual((row.footer_mode, row.sender, row.heading, row.button_text, row.footer_contact_line), ("", "", "", "", "Questions? Reply to this email or write to {contact_email}."))
        self.assertNotContains(self.client.get("/emails/automatic/verify/"), "Reset to default")

    def test_bad_settings_are_field_errors_and_the_next_morning_default_is_shown(self):
        bad = self.client.post(SAVE, {**BASE, "heading": "Hi {nope}", "button_text": "a{b}", "footer_mode": "custom", "footer_contact_line": "{zz}"})
        self.assertEqual(bad.status_code, 400)
        self.assertTrue({"heading", "button_text", "footer_contact_line"} <= set(bad.context["form"].errors))
        page = self.client.get("/emails/automatic/lead_next_morning/")
        self.assertEqual((page.context["form"].initial["footer_mode"], page.context["form"].initial["sender"]), ("no_contact", "person"))
        self.assertFalse(page.context["footer"]["person_sender"])  # the screen says the person sender has no address yet
        self.assertContains(page, "data-se-person-missing")

    def test_preview_and_test_send_use_the_typed_settings(self):
        SiteSettings.objects.update(auto_email_from_name="Barry", auto_email_from_address="barry@spa99.test")
        typed = {**BASE, "footer_mode": "custom", "footer_brand_line": "Typed brand", "footer_address_line": "", "footer_contact_line": "",
                 "sender": "person", "heading": "Typed heading", "button_text": "Typed button"}
        preview = self.client.post("/emails/automatic/verify/preview/", typed).json()
        self.assertTrue(preview["ok"])
        for text in ("Typed brand", "Typed heading", "Typed button"):
            self.assertIn(text, preview["html"])
        self.assertEqual(preview["from"], "Barry <barry@spa99.test>")
        self.assertEqual(NotificationTemplate.objects.get(key="verify").heading, "")  # nothing saved
        self.client.post("/emails/automatic/verify/test/", typed, HTTP_ACCEPT="application/json")
        sent = mail.outbox[-1]
        self.assertEqual((sent.from_email, sent.reply_to, sent.to), ("Barry <barry@spa99.test>", ["barry@spa99.test"], ["dev@example.com"]))
        self.assertIn("Typed heading", sent.alternatives[0][0])
        self.assertIn("Typed button", sent.body)
        bad = self.client.post("/emails/automatic/verify/preview/", {**typed, "heading": "{nope}"}).json()
        self.assertEqual((bad["ok"], "heading" in bad["errors"]), (False, True))
