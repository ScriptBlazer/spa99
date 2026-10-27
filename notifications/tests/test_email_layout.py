"""The shared email layout (docs/design/EMAIL-LAYOUT.md): logo, preheader, button, plain text, size, News footer."""
import re

from django.core import mail
from django.test import TestCase, override_settings

from notifications import emailbody
from notifications.services import base_context, preview_email, render_email, send_templated

SITE = "https://spa99.example"


@override_settings(SITE_URL=SITE)
class EmailLayoutTests(TestCase):
    def verify(self):
        return preview_email("verify", "[Test] Confirm your email for Spa 99", "")

    def test_logo_is_absolute_and_unhashed(self):
        self.assertEqual(base_context()["logo_url"], f"{SITE}/static/common/img/email/logo-on-dark-2x.png")
        html = self.verify()["html"]
        self.assertIn(f'src="{SITE}/static/common/img/email/logo-on-dark-2x.png"', html)
        self.assertIn('alt="Spa 99"', html)
        self.assertIn('width="120" height="89"', html)

    def test_heading_is_subject_without_test_prefix(self):
        html = self.verify()["html"]
        self.assertRegex(html, r">Confirm your email for Spa 99</h1>")
        self.assertNotIn("[Test]</h1>", html)

    def test_preheader_skips_greeting(self):
        html = self.verify()["html"]
        pre = re.search(r'mso-hide:all[^>]*>(.*?)&#847;', html, re.S).group(1)
        self.assertTrue(pre.startswith("Please confirm your email address"))
        self.assertNotIn("Hello", pre)

    def test_preview_text_rules(self):
        self.assertEqual(emailbody.preview_text("Hello James,\n\nShort body."), "Short body.")
        long = emailbody.preview_text("Hi,\n\n" + "word " * 60)
        self.assertTrue(long.endswith("…"))
        self.assertLessEqual(len(long), 101)
        self.assertEqual(emailbody.preview_text("Hello James, this is a long enough first line to count as real content."),
                         "Hello James, this is a long enough first line to count as real content.")

    def test_button_is_table_with_absolute_href_and_fallback(self):
        html = self.verify()["html"]
        self.assertRegex(html, r'<table role="presentation"[^>]*>\s*<tr><td class="e-btn"')
        self.assertIn(f'href="{SITE}/example-link/" target="_blank"', html)
        self.assertIn("If the button does not work, paste this link into your browser:", html)

    def test_plain_text_button_has_label_then_url(self):
        text = self.verify()["text"]
        self.assertIn(f"Confirm my email:\n{SITE}/example-link/", text)
        self.assertTrue(text.startswith("SPA 99\n\nHello James,"))
        self.assertIn("\n-- \n", text)
        self.assertIn("Beyond Luxury", text)

    def test_footer_has_brand_line_and_contact(self):
        html = self.verify()["html"]
        self.assertIn("Beyond Luxury", html)
        self.assertIn("mailto:", html)
        self.assertNotIn("#FFFFFF", html.upper())

    def test_gold_approver_size_and_structure(self):
        rows = [(f"Question number {i}", "A long answer with many words. " * 20) for i in range(25)]
        ctx = {**base_context(), "subject": "Gold", "name": "James Smith", "potential_label": "High", "is_repeat": True,
               "repeat_reference": "GC-1", "approve_url": f"{SITE}/a/", "decline_url": f"{SITE}/d/", "respond_url": f"{SITE}/r/",
               "view_url": f"{SITE}/v/", "sections": [{"title": "Contact", "rows": rows}, {"title": "Property", "rows": rows},
                                                       {"title": "Other", "rows": rows}]}
        html, text = render_email("gold_approver", ctx)
        self.assertLess(len(html.encode()), 80 * 1024)
        self.assertIn("Gold Card application: James Smith</h1>", html)
        self.assertIn("High potential. Review it in the Office.", html)
        self.assertEqual(html.count('class="e-btn"'), 1)  # one primary button, the rest are text links
        self.assertIn('class="e-row"', html)
        self.assertTrue(text.startswith("SPA 99\n\n"))
        self.assertIn("Questions? Reply to this email", text)

    def test_service_email_size(self):
        self.assertLess(len(self.verify()["html"].encode()), 40 * 1024)

    def test_news_email_keeps_unsubscribe(self):
        extra = {"unsubscribe_url": f"{SITE}/unsubscribe/abc/", "notice": "You are receiving this because you opted in."}
        html = preview_email("mailing", "News", "Hello {first_name},\n\nOur spa opens soon.", extra)
        self.assertIn("You are receiving this because you opted in.", html["html"])
        self.assertIn(f'href="{SITE}/unsubscribe/abc/"', html["html"])
        self.assertIn(f"Unsubscribe from these emails: {SITE}/unsubscribe/abc/", html["text"])
        mail.outbox.clear()
        log = send_templated("mailing", ["g@example.com"], "News", {**extra, "first_name": "Guy"},
                             headers={"List-Unsubscribe": f"<{SITE}/unsubscribe/abc/>"}, body="Hello {first_name},\n\nOur spa opens soon.")
        self.assertEqual(log.status, "sent")
        self.assertEqual(mail.outbox[0].extra_headers["List-Unsubscribe"], f"<{SITE}/unsubscribe/abc/>")
