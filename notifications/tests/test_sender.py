"""Who an Office email comes from and what goes under it (notifications/sender.py), the signature allow-list, fill_signatures and System > Team > Email. Mocked: nothing is sent."""
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase, override_settings

from common import levels, richtext
from notifications import sender as sender_mod
from notifications.management.commands.fill_signatures import signatures_in
from notifications.models import StaffSender
from plans.tests.helpers import make_team_member

DESIGN = Path(settings.BASE_DIR) / "docs" / "design"
SENDING = dict(EMAIL_SENDING_DOMAIN="staff.example.test", SITE_URL="https://site.example.test")


def staff(email, first="", last=""):
    user = make_team_member(email, levels.OFFICE, approver=True)
    type(user).objects.filter(pk=user.pk).update(first_name=first, last_name=last)
    user.refresh_from_db()
    return user


@override_settings(**SENDING)
class SenderTests(TestCase):
    def test_his_own_address_on_the_sending_domain_else_the_address_set_in_system_else_the_site_address(self):
        own = sender_mod.sender_for(staff("barry@staff.example.test", "Barry"))
        self.assertEqual((own.address, own.name, own.source), ("barry@staff.example.test", "Barry, Spa 99", "own"))
        self.assertEqual(sender_mod.format_address(own.address, own.name), '"Barry, Spa 99" <barry@staff.example.test>')  # quoted: the name holds a comma
        bml = staff("barry@bml.example.test", "Barry")
        self.assertEqual(sender_mod.sender_for(bml).source, "site")  # nothing set: the site address, still with his name
        StaffSender.objects.create(user=bml, sending_address="Barry.Sends@Staff.Example.Test")
        self.assertEqual(sender_mod.sender_for(bml).address, "barry.sends@staff.example.test")
        StaffSender.objects.filter(user=bml).update(sending_address="elsewhere@gmail.example")  # not on the domain: never used
        self.assertEqual(sender_mod.sender_for(bml).source, "site")
        self.assertEqual(sender_mod.display_name(staff("anon@staff.example.test")), "Spa 99")  # no first name: no email prefix as a name

    def test_the_domain_check_is_exact_and_blank_means_the_site_address_domain(self):
        for bad in ("x@evilstaff.example.test", "a@b@staff.example.test", "staff.example.test", "@staff.example.test", "x@staff.example.test.evil.test", "x @staff.example.test"):
            self.assertFalse(sender_mod.on_sending_domain(bad), bad)
        self.assertTrue(sender_mod.on_sending_domain("X@Staff.Example.Test"))
        with override_settings(EMAIL_SENDING_DOMAIN=""):
            self.assertEqual(sender_mod.sending_domain(), "example.test")

    def test_a_hostile_first_name_cannot_break_the_header_and_an_accent_is_encoded(self):
        evil = staff("evil@staff.example.test", 'Bob <x@y>", Cc: spy@z\r\nBcc: q@r')
        header = sender_mod.format_address(*sender_mod.sender_for(evil)[:2])
        self.assertNotIn("\n", header)
        self.assertNotIn("<x@y>", header)
        self.assertEqual(header.count("@"), 1)  # one address only, whatever the name held
        self.assertEqual(sender_mod.display_name(staff("zoe@staff.example.test", "Zoë")), "Zoë, Spa 99")

    def test_nobody_can_send_as_another_person(self):
        barry, other = staff("barry@staff.example.test"), staff("other@bml.example.test")
        StaffSender.objects.create(user=other, sending_address="shared@staff.example.test")
        self.assertTrue(sender_mod.belongs_to_someone_else("barry@staff.example.test", other))  # his login
        self.assertTrue(sender_mod.belongs_to_someone_else("shared@staff.example.test", barry))  # his sending address
        self.assertFalse(sender_mod.belongs_to_someone_else("shared@staff.example.test", other))


@override_settings(**SENDING)
class SignatureTests(TestCase):
    def design(self):
        found, problems = signatures_in(DESIGN)
        self.assertEqual(problems, [])
        return found

    def test_the_design_signature_survives_the_allow_list_and_nothing_unsafe_does(self):
        clean = richtext.clean_signature(next(iter(self.design().values())))
        for keep in ("<table", "border-left: 2px solid #E5AC6E", "<img", "mailto:", "tel:"):
            self.assertIn(keep, clean)
        evil = ('<table style="position:fixed;color:red;margin:-9px;background:url(http://x/a.png)"><tr><td onclick="x()"><script>bad()</script><a href="javascript:x()">a</a>'
                '<img src="javascript:1"><img src="data:image/png;base64,AA"><iframe src="https://e"></iframe><form><input></form></td></tr></table>')
        out = richtext.clean_signature(evil)
        for bad in ("position", "url(", "-9px", "onclick", "script", "javascript", "data:", "iframe", "<form", "<input"):
            self.assertNotIn(bad, out)
        self.assertEqual(richtext.clean_signature("x" * (richtext.MAX_SIGNATURE + 1)), "")

    def test_the_pictures_are_in_a_plain_unhashed_static_path_and_made_absolute_when_sent(self):
        for name in ("signature-logo.png", "signature-banner.jpg"):
            self.assertTrue(finders.find(f"common/img/email/{name}"), name)
        html = richtext.absolute_images(richtext.clean_signature('<img src="/static/common/img/email/signature-logo.png" alt="x">'), "https://site.example.test/")
        self.assertIn('src="https://site.example.test/static/common/img/email/signature-logo.png"', html)

    def test_sign_off_is_his_signature_or_a_plain_kind_regards_with_his_name(self):
        barry = staff("barry@staff.example.test", "Barry", "Lobenstein")
        html, text = sender_mod.sign_off(barry)
        self.assertIn("Kind regards,<br>Barry Lobenstein", html)
        self.assertEqual(text, "Kind regards,\nBarry Lobenstein")
        StaffSender.objects.create(user=barry, signature_html="<p>Sig <b>here</b></p>")
        self.assertIn("<b>here</b>", sender_mod.sign_off(barry)[0])

    def test_fill_signatures_by_email_or_sending_address_only_empty_ones_and_a_dry_run_writes_nothing(self):
        emails = list(self.design())
        owner, other = staff(emails[0]), staff(emails[1])
        bml = staff("owner@bml.example.test")
        StaffSender.objects.create(user=other, signature_html="<p>Typed by hand</p>")
        out = StringIO()
        call_command("fill_signatures", "--dry-run", stdout=out)
        self.assertIn("Dry run", out.getvalue())
        self.assertFalse(StaffSender.objects.filter(user=owner).exists())
        call_command("fill_signatures", stdout=StringIO())
        self.assertIn(emails[0], StaffSender.objects.get(user=owner).signature_html)
        self.assertEqual(StaffSender.objects.get(user=other).signature_html, "<p>Typed by hand</p>")  # never overwritten
        self.assertFalse(StaffSender.objects.filter(user=bml).exists())

    def test_system_edits_the_sender_and_signature_at_the_right_level_and_cleans_on_save(self):
        from system.tests.test_system import unlocked_client
        from system.tests.test_team import at

        dev, admin = at("developer", "dev@example.com"), at("admin", "admin@example.com")
        client = unlocked_client(dev)
        url = f"/team/{admin.pk}/email/"
        page = client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Inbox address")
        bad = client.post(url, {"sending_address": "x@gmail.example", "signature": "<p>ok</p>"})
        self.assertContains(bad, "must end in @staff.example.test", status_code=400)
        self.assertFalse(StaffSender.objects.filter(user=admin).exists())
        ok = client.post(url, {"sending_address": "Admin@Staff.Example.Test", "signature": '<table><tr><td>Hi<script>x()</script></td></tr></table>'})
        self.assertEqual(ok.status_code, 302)
        row = StaffSender.objects.get(user=admin)
        self.assertEqual(row.sending_address, "admin@staff.example.test")
        self.assertNotIn("script", row.signature_html)
        taken = client.post(f"/team/{at('developer', 'dev2@example.com').pk}/email/", {"sending_address": "admin@staff.example.test", "signature": ""})
        self.assertEqual(taken.status_code, 302)  # same level: refused, nothing saved
        self.assertEqual(StaffSender.objects.count(), 1)
        preview = client.post(url, {"sending_address": "", "signature": "<p>Preview <b>me</b></p><script>bad()</script>", "preview": "1"})
        self.assertContains(preview, "srcdoc=")
        self.assertEqual(StaffSender.objects.get(user=admin).signature_html, row.signature_html)  # a preview saves nothing
