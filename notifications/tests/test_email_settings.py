"""Email flexibility (docs/features/office-outreach.md E1, E2): the shared footer, and per email the footer mode, sender, heading and
button text, used by send and preview. Defaults are checked byte-for-byte in test_footer_golden. Mocked: the in-memory outbox."""
from django.core import mail
from django.test import TestCase, override_settings

from notifications import emailsettings
from notifications.models import NotificationTemplate
from notifications.services import preview_email, send_templated
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings

UNSUB = {"unsubscribe_url": "https://spa99.uk/unsubscribe/x/", "notice": "You get this because you asked."}


def site(**fields):
    row = SiteSettings.load()
    for name, value in fields.items():
        setattr(row, name, value)
    row.save()
    return row


def template(key, **fields):
    NotificationTemplate.objects.filter(key=key).update(**fields)


@override_settings(DEFAULT_FROM_EMAIL="Spa 99 <hello@spa99.test>")
class EmailSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_shared_footer_edits_show_in_every_email_and_a_blank_line_is_left_out(self):
        site(footer_brand_line="Quiet Luxury", footer_address_line="", footer_contact_line="Write to {contact_email}, {site_name}.")
        for key in ("verify", "welcome", "gold_final"):  # gold_final has its own .txt layout
            email = preview_email(key, "S", "")
            self.assertIn("Quiet Luxury", email["html"], key)
            self.assertIn("Write to ", email["html"], key)
            self.assertIn("Quiet Luxury\n", email["text"], key)
            self.assertNotIn("Beyond Luxury", email["html"] + email["text"], key)
            self.assertNotIn("99 Vale Road", email["html"].split('class="e-foot"')[1], key)  # the address line is gone
        self.assertNotIn("Questions?", preview_email("verify", "S", "")["text"])

    def test_the_unsubscribe_link_and_notice_stay_even_with_an_empty_footer(self):
        site(footer_brand_line="", footer_address_line="", footer_contact_line="")
        template("invite", footer_mode="custom", footer_brand_line="", footer_address_line="", footer_contact_line="")
        for key in ("welcome", "invite"):
            email = preview_email(key, "S", "", UNSUB)
            for part in (email["html"], email["text"]):
                self.assertIn("https://spa99.uk/unsubscribe/x/", part, key)
                self.assertIn("You get this because you asked.", part, key)

    def test_footer_modes_and_the_next_morning_default(self):
        self.assertNotIn("Questions? Reply", preview_email("lead_next_morning", "S", "")["html"])  # default: shared without the contact line
        template("lead_next_morning", footer_mode="shared")
        self.assertIn("Questions? Reply", preview_email("lead_next_morning", "S", "")["html"])
        template("verify", footer_mode="no_contact")
        self.assertNotIn("Questions? Reply", preview_email("verify", "S", "")["text"])
        template("verify", footer_mode="custom", footer_brand_line="Mine", footer_address_line="Round the corner", footer_contact_line="")
        email = preview_email("verify", "S", "")
        self.assertIn("Round the corner", email["html"])
        self.assertIn("Mine", email["text"])
        self.assertNotIn("Beyond Luxury", email["html"])
        self.assertIn("Beyond Luxury", preview_email("welcome", "S", "")["html"])  # other emails keep the shared footer

    def test_values_are_escaped_and_bad_lines_are_rejected(self):
        site(footer_brand_line="<b>x</b> {nope}")
        self.assertIn("&lt;b&gt;x&lt;/b&gt; {nope}", preview_email("verify", "S", "")["html"])  # shown as typed, never as markup
        self.assertTrue(emailsettings.validate_line("Hi {zzz}"))
        self.assertTrue(emailsettings.validate_line("a\nb"))
        self.assertTrue(emailsettings.validate_line("x" * 301))
        self.assertEqual(emailsettings.validate_line("{site_name}, {address}"), [])

    def test_sender_site_person_and_fallback(self):
        send_templated("verify", ["a@example.com"], "S", {"first_name": "A", "url": "https://x.test/"})
        self.assertEqual((mail.outbox[-1].from_email, mail.outbox[-1].reply_to), ("Spa 99 <hello@spa99.test>", [SiteSettings.load().contact_address]))
        template("verify", sender="person")
        send_templated("verify", ["a@example.com"], "S", {"first_name": "A", "url": "https://x.test/"})
        self.assertEqual(mail.outbox[-1].from_email, "Spa 99 <hello@spa99.test>")  # no person address yet: falls back to the site sender
        site(auto_email_from_name="Barry", auto_email_from_address="barry@spa99.test")
        send_templated("verify", ["a@example.com"], "S", {"first_name": "A", "url": "https://x.test/"})
        self.assertEqual((mail.outbox[-1].from_email, mail.outbox[-1].reply_to), ("Barry <barry@spa99.test>", ["barry@spa99.test"]))
        template("lead_next_morning", sender="site")
        send_templated("lead_next_morning", ["a@example.com"], "S", {"first_name": "A"})
        self.assertEqual(mail.outbox[-1].from_email, "Spa 99 <hello@spa99.test>")
        template("lead_next_morning", sender="")  # blank = the email's default: the person
        send_templated("lead_next_morning", ["a@example.com"], "S", {"first_name": "A"})
        self.assertEqual(mail.outbox[-1].from_email, "Barry <barry@spa99.test>")

    def test_heading_and_button_text_in_send_and_preview(self):
        template("verify", heading="Welcome aboard, {first_name}", button_text="Yes, it is me")
        send_templated("verify", ["a@example.com"], "Confirm please", {"first_name": "Sam", "url": "https://x.test/c/"})
        html = mail.outbox[-1].alternatives[0][0]
        self.assertIn("Welcome aboard, Sam</h1>", html)
        self.assertIn("Yes, it is me", html)
        self.assertIn("Yes, it is me:\nhttps://x.test/c/", mail.outbox[-1].body)
        preview = preview_email("verify", "Confirm please", "")
        self.assertIn("Welcome aboard, James</h1>", preview["html"])
        typed = preview_email("verify", "Confirm please", "", posted={"heading": "", "button_text": "Typed", "sender": "person"})  # not saved yet
        self.assertIn("Confirm please</h1>", typed["html"])
        self.assertIn("Typed", typed["html"])
        self.assertNotIn("Yes, it is me", typed["html"])

    def test_validate_options(self):
        from notifications.emailbody import SPECS

        self.assertEqual(emailsettings.validate_options(SPECS["verify"], {"heading": "Hi {first_name}", "button_text": "Go"}), {})
        errors = emailsettings.validate_options(SPECS["verify"], {"heading": "Hi {nope}", "button_text": "x{y}", "sender": "zz", "footer_mode": "custom", "footer_contact_line": "{bad}"})
        self.assertEqual(set(errors), {"heading", "button_text", "sender", "footer_contact_line"})
        self.assertIn("button_text", emailsettings.validate_options(SPECS["welcome"], {"button_text": "x"}))  # welcome has no button
