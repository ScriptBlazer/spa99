"""Office emails from a person (docs/features/office-email-chat.md, "Who an Office email comes from"): the sender, the Reply-To name, the copy to the group, the signature, the subject, the
thread header name, and signature pictures in his mail. Mocked: mail goes to the in-memory outbox (the test settings use the locmem backend, so nothing can reach Postmark)."""
import json
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings

from common import levels, richtext
from emailchat import sender as sender_mod
from emailchat import services
from emailchat.management.commands.fill_signatures import signatures_in
from emailchat.models import Attachment, Message, StaffSender, Thread
from emailchat.tests.test_emailchat import PNG, Base, b64, inbound_post, office, payload_for
from notifications.models import EmailLog
from plans.management.commands.seed_phase1 import seed_all
from plans.tests.helpers import make_team_member
from system.models import SiteDefaults, validate_group_copy_email

DESIGN = Path(settings.BASE_DIR) / "docs" / "design"
SENDING = dict(EMAIL_SENDING_DOMAIN="staff.example.test", SITE_URL="https://site.example.test")


def staff(email, first="", last=""):
    user = make_team_member(email, levels.OFFICE, approver=True)
    type(user).objects.filter(pk=user.pk).update(first_name=first, last_name=last)
    user.refresh_from_db()
    return user


def set_copy(address):
    row = SiteDefaults.load()
    SiteDefaults.objects.filter(pk=row.pk).update(office_copy_email=address, office_copy_seeded=True)


@override_settings(**SENDING)
class SenderTests(Base):
    def post_as(self, user, html="<p>Hello</p>", subject="", thread=None):
        return office(user, "post", f"/email/{(thread or self.thread).pk}/send/", {"body_html": html, "subject": subject})

    def test_his_own_address_on_the_sending_domain_is_the_from_and_it_is_stored_and_shown(self):
        barry = staff("barry@staff.example.test", "Barry", "Lobenstein")
        self.assertEqual(self.post_as(barry).status_code, 200)
        message = Message.objects.get(direction="out")
        self.assertEqual((message.from_address, message.from_name), ("barry@staff.example.test", "Barry, Spa 99"))
        sent = mail.outbox[-1]
        self.assertEqual(sent.from_email, '"Barry, Spa 99" <barry@staff.example.test>')  # quoted: the name holds a comma
        self.assertEqual(sent.reply_to, [f'"Barry, Spa 99" <reply+{self.thread.token}@reply.example.test>'])  # a name in the Reply-To too, same display name
        data = services.message_dict(message)
        self.assertEqual((data["sent_from"], data["author_first_name"]), ('"Barry, Spa 99" <barry@staff.example.test>', "Barry"))

    def test_another_domain_uses_the_sending_address_set_in_system_else_the_site_address_and_no_name_is_just_spa_99(self):
        bml = staff("barry@bml.example.test", "Barry")
        self.post_as(bml)
        self.assertEqual(mail.outbox[-1].from_email, '"Barry, Spa 99" <from@example.test>')  # nothing set: the site address (hello@), still with his name
        StaffSender.objects.create(user=bml, sending_address="Barry.Sends@Staff.Example.Test")
        self.post_as(bml, "<p>Again</p>")
        self.assertEqual(mail.outbox[-1].from_email, '"Barry, Spa 99" <barry.sends@staff.example.test>')
        StaffSender.objects.filter(user=bml).update(sending_address="elsewhere@gmail.example")  # not on the domain: never used
        self.assertEqual(sender_mod.sender_for(bml).source, "site")
        nameless = staff("anon@staff.example.test")
        self.post_as(nameless, "<p>No name</p>")
        self.assertEqual(mail.outbox[-1].from_email, "Spa 99 <anon@staff.example.test>")
        self.assertEqual(services.message_dict(Message.objects.get(body_text="No name"))["author_first_name"], "")  # no email prefix as a name: the sheet says "Spa 99"

    def test_the_domain_check_is_exact_and_comes_from_the_setting(self):
        for bad in ("x@evilstaff.example.test", "a@b@staff.example.test", "staff.example.test", "@staff.example.test", "x@staff.example.test.evil.test", "x @staff.example.test"):
            self.assertFalse(sender_mod.on_sending_domain(bad), bad)
        self.assertTrue(sender_mod.on_sending_domain("X@Staff.Example.Test"))
        with override_settings(EMAIL_SENDING_DOMAIN=""):  # blank: the domain of the site address
            self.assertEqual(sender_mod.sending_domain(), "example.test")

    def test_the_sender_is_decided_when_queued_so_a_retry_keeps_it(self):
        barry = staff("barry@staff.example.test", "Barry")
        self.post_as(barry)
        message = Message.objects.get(direction="out")
        Message.objects.filter(pk=message.pk).update(status="failed", error_code="send_failed", claimed_at=None)
        type(barry).objects.filter(pk=barry.pk).update(email="renamed@staff.example.test", first_name="Someone")  # changed after it was queued
        self.assertEqual(office(barry, "post", f"/email/{self.thread.pk}/retry/{message.pk}/").status_code, 200)
        self.assertEqual(mail.outbox[-1].from_email, '"Barry, Spa 99" <barry@staff.example.test>')

    def test_a_hostile_first_name_cannot_break_the_header_and_an_accent_is_encoded(self):
        evil = staff("evil@staff.example.test", 'Bob <x@y>", Cc: spy@z\r\nBcc: q@r')
        self.post_as(evil)
        sent = mail.outbox[-1]
        self.assertNotIn("\n", sent.from_email)
        self.assertNotIn("<x@y>", sent.from_email)
        self.assertEqual(sent.message()["From"].count("@"), 1)  # one address only, whatever the name held
        accent = staff("zoe@staff.example.test", "Zoë")
        self.post_as(accent, "<p>accent</p>")
        self.assertIn("=?utf-8?", mail.outbox[-1].message()["From"])
        self.assertEqual(sender_mod.display_name(accent), "Zoë, Spa 99")

    def test_automatic_emails_do_not_go_from_a_person(self):
        from notifications.services import send_templated

        send_templated("welcome", ["new@example.com"], "Welcome", {"first_name": "New"})
        self.assertEqual(mail.outbox[-1].from_email, settings.DEFAULT_FROM_EMAIL)


@override_settings(**SENDING)
class SubjectAndLayoutTests(Base):
    def test_a_new_email_goes_out_with_the_subject_as_typed_and_a_reply_gets_re(self):
        """The owner's first New email "Spa Email test" seemed to go out as "Re: ...". Not reproducible: the first email keeps the typed subject, only a reply with the subject box left alone gets Re:."""
        response = office(self.approver, "post", "/email/new/", {"to": "dan@example.com", "subject": "Spa Email test", "body_html": "<p>First</p>"}, headers={"X-Requested-With": "fetch"})
        self.assertEqual(response.status_code, 200, response.content)
        thread = Thread.objects.get(email="dan@example.com")
        first = Message.objects.get(thread=thread)
        self.assertEqual((first.subject, thread.subject, first.shows_subject, mail.outbox[-1].subject), ("Spa Email test", "Spa Email test", True, "Spa Email test"))
        self.assertEqual(services.reply_subject(thread), "Re: Spa Email test")
        office(self.approver, "post", f"/email/{thread.pk}/send/", {"body_html": "<p>Second</p>"})
        second = Message.objects.filter(thread=thread).order_by("-id").first()
        self.assertEqual((second.subject, second.shows_subject, mail.outbox[-1].subject), ("Re: Spa Email test", False, "Re: Spa Email test"))

    def test_an_office_email_has_no_heading_repeating_the_subject_and_no_contact_line(self):
        office(self.approver, "post", "/email/new/", {"to": "dan@example.com", "subject": "Spa Email test", "body_html": "<p>Words here</p>"}, headers={"X-Requested-With": "fetch"})
        html = mail.outbox[-1].alternatives[0][0]
        self.assertNotIn("<h1", html)
        self.assertEqual(html.count("Spa Email test"), 1)  # the title tag only
        self.assertNotIn("Questions? Reply to this email", html)
        self.assertNotIn("Questions? Reply to this email", mail.outbox[-1].body)
        self.assertIn("Spa 99, ", html)  # the layout's own footer stays


@override_settings(**SENDING)
class SignatureTests(Base):
    def setUp(self):
        super().setUp()
        self.barry = staff("barry@staff.example.test", "Barry", "Lobenstein")

    def design(self):
        found, problems = signatures_in(DESIGN)
        self.assertEqual(problems, [])
        return found

    def test_the_design_signature_survives_the_allow_list_and_nothing_unsafe_does(self):
        raw = next(iter(self.design().values()))
        clean = richtext.clean_signature(raw)
        for keep in ("<table", "border-left: 2px solid #E5AC6E", "<img", "mailto:", "tel:", "font-family", "text-transform: uppercase"):
            self.assertIn(keep, clean)
        evil = ('<table style="position:fixed;color:red;margin:-9px;background:url(http://x/a.png)"><tr><td onclick="x()"><script>bad()</script><a href="javascript:x()">a</a>'
                '<img src="javascript:1"><img src="data:image/png;base64,AA"><iframe src="https://e"></iframe><form><input></form></td></tr></table>')
        out = richtext.clean_signature(evil)
        for bad in ("position", "url(", "-9px", "onclick", "script", "javascript", "data:", "iframe", "<form", "<input"):
            self.assertNotIn(bad, out)
        self.assertIn("color: red", out)
        self.assertEqual(richtext.clean_signature("x" * (richtext.MAX_SIGNATURE + 1)), "")

    def test_the_pictures_are_in_a_plain_unhashed_static_path_so_old_emails_keep_working(self):
        for name in ("signature-logo.png", "signature-banner.jpg"):
            self.assertTrue(finders.find(f"common/img/email/{name}"), name)
        design = DESIGN / "spa99-signature-logo.png"
        self.assertEqual(Path(finders.find("common/img/email/signature-logo.png")).read_bytes(), design.read_bytes())
        html = richtext.absolute_images(richtext.clean_signature('<img src="/static/common/img/email/signature-logo.png" alt="x">'), "https://site.example.test/")
        self.assertIn('src="https://site.example.test/static/common/img/email/signature-logo.png"', html)

    def test_fill_signatures_by_email_only_empty_ones_and_a_dry_run_writes_nothing(self):
        emails = list(self.design())
        owner, other = staff(emails[0]), staff(emails[1])
        StaffSender.objects.create(user=other, signature_html="<p>Typed by hand</p>")
        out = StringIO()
        call_command("fill_signatures", "--dry-run", stdout=out)
        self.assertIn("would fill", out.getvalue())
        self.assertIn("Dry run", out.getvalue())
        self.assertFalse(StaffSender.objects.filter(user=owner).exists())
        call_command("fill_signatures", stdout=StringIO())
        filled = StaffSender.objects.get(user=owner)
        self.assertIn("/static/common/img/email/signature-logo.png", filled.signature_html)
        self.assertIn(emails[0], filled.signature_html)
        self.assertEqual(StaffSender.objects.get(user=other).signature_html, "<p>Typed by hand</p>")  # never overwritten
        before = StaffSender.objects.get(user=owner).updated_at
        call_command("fill_signatures", stdout=StringIO())
        self.assertEqual(StaffSender.objects.get(user=owner).updated_at, before)  # second run: nothing

    def test_the_email_has_the_signature_with_absolute_pictures_a_plain_text_sign_off_and_it_is_stored_as_sent(self):
        StaffSender.objects.create(user=self.barry, signature_html=richtext.clean_signature(next(iter(self.design().values()))))
        office(self.barry, "post", f"/email/{self.thread.pk}/send/", {"body_html": "<p>Hello Him</p>"})
        message = Message.objects.get(direction="out")
        html, text = mail.outbox[-1].alternatives[0][0], mail.outbox[-1].body
        self.assertIn('src="https://site.example.test/static/common/img/email/signature-logo.png"', html)
        self.assertIn('src="https://site.example.test/static/common/img/email/signature-banner.jpg"', html)
        self.assertIn('class="e-sig"', html)
        self.assertLess(html.index("Hello Him"), html.index('class="e-sig"'))
        self.assertNotIn("<script", html)
        self.assertIn("Barry Lobenstein\nSpa 99\nhttps://site.example.test", text)
        self.assertEqual(message.body_text, "Hello Him")  # his words only: the list preview and a reply's quote never carry the signature
        self.assertEqual(self.thread.messages.get(pk=message.pk).body_html, "<p>Hello Him</p>")
        self.assertIn("signature-logo.png", message.signature_html)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.last_preview, "Hello Him")
        data = services.message_dict(message)
        self.assertIn("<table", data["signature_html"])
        StaffSender.objects.filter(user=self.barry).update(signature_html="<p>Changed later</p>")
        self.assertIn("signature-logo.png", services.message_dict(Message.objects.get(pk=message.pk))["signature_html"])  # as sent, not as it is now

    def test_no_signature_is_a_plain_sign_off_with_his_name_and_the_composer_says_so(self):
        office(self.barry, "post", f"/email/{self.thread.pk}/send/", {"body_html": "<p>Hello Him</p>"})
        html, text = mail.outbox[-1].alternatives[0][0], mail.outbox[-1].body
        self.assertIn("Kind regards,<br>Barry Lobenstein", html)
        self.assertIn("Hello Him\n\nKind regards,\nBarry Lobenstein", text)
        page = office(self.barry, "get", f"/email/{self.thread.pk}/")
        self.assertContains(page, "Barry, Spa 99 &lt;barry@staff.example.test&gt;</span>, with a plain sign-off")
        StaffSender.objects.create(user=self.barry, signature_html="<p>Sig <b>here</b></p>")
        page = office(self.barry, "get", f"/email/{self.thread.pk}/")
        self.assertContains(page, ", with your signature")
        self.assertContains(page, "<b>here</b>")
        self.assertContains(office(self.barry, "get", "/email/new/"), "with your signature")

    def test_system_edits_the_sender_and_signature_at_the_right_level_and_cleans_on_save(self):
        from system.tests.test_system import unlocked_client
        from system.tests.test_team import at

        dev = at("developer", "dev@example.com")
        admin = at("admin", "admin@example.com")
        client = unlocked_client(dev)
        url = f"/team/{admin.pk}/email/"
        self.assertEqual(client.get(url).status_code, 200)
        bad = client.post(url, {"sending_address": "x@gmail.example", "signature": "<p>ok</p>"})
        self.assertEqual(bad.status_code, 400)
        self.assertContains(bad, "must end in @staff.example.test", status_code=400)
        self.assertFalse(StaffSender.objects.filter(user=admin).exists())
        ok = client.post(url, {"sending_address": "Admin@Staff.Example.Test", "signature": '<table><tr><td>Hi<script>x()</script><a href="javascript:1">l</a></td></tr></table>'})
        self.assertEqual(ok.status_code, 302)
        row = StaffSender.objects.get(user=admin)
        self.assertEqual(row.sending_address, "admin@staff.example.test")
        self.assertNotIn("script", row.signature_html)
        self.assertNotIn("javascript", row.signature_html)
        self.assertIn("<table", row.signature_html)
        preview = client.post(url, {"sending_address": "", "signature": "<p>Preview <b>me</b></p><script>bad()</script>", "preview": "1"})
        self.assertContains(preview, "srcdoc=")
        self.assertContains(preview, "Preview &lt;b&gt;me&lt;/b&gt;")  # inside the attribute, escaped
        self.assertEqual(StaffSender.objects.get(user=admin).signature_html, row.signature_html)  # a preview saves nothing
        peer = at("developer", "dev2@example.com")
        self.assertEqual(client.post(f"/team/{peer.pk}/email/", {"sending_address": "", "signature": "<p>x</p>"}).status_code, 302)  # refused (same level): back to Team, nothing saved
        self.assertFalse(StaffSender.objects.filter(user=peer).exists())
        self.assertEqual(unlocked_client(admin).get(url).status_code, 404)  # Admin level is not System


@override_settings(**SENDING)
class GroupCopyTests(Base):
    def reply(self, message_id="pm-1", **extra):
        return inbound_post(payload_for(self.thread, message_id=message_id, **{"Subject": "Re: Hello", "TextBody": "Friday suits me.", **extra}))

    def copies(self):
        return [m for m in mail.outbox if m.extra_headers.get("X-Spa99-Group-Copy")]

    def test_a_reply_is_copied_once_with_the_answer_in_the_office_and_no_way_back_into_the_thread(self):
        set_copy("team@example.test")
        self.assertEqual(self.reply(Attachments=[{"Name": "plan.pdf", "Content": b64(b"%PDF-1.4 x"), "ContentType": "application/pdf"}]).status_code, 200)
        self.assertEqual(self.reply().status_code, 200)  # Postmark sends the same MessageID again
        [copy] = self.copies()
        self.assertEqual(copy.to, ["team@example.test"])
        self.assertEqual(copy.reply_to, ["team@example.test"])  # "Reply" in a mail app goes to the group, never to him or into the thread
        self.assertEqual(copy.attachments, [])  # files are named, not attached
        for text in (copy.body, copy.alternatives[0][0]):
            self.assertIn("Him <him@example.com> wrote to the Office", text.replace("&lt;", "<").replace("&gt;", ">"))
            self.assertIn("Friday suits me.", text)
            self.assertIn("plan.pdf", text)
            self.assertIn("Answer in the Office", text)
            self.assertIn(f"/email/{self.thread.pk}/", text)
            self.assertNotIn("reply+", text)
        self.assertNotIn("reply+", str(copy.message()))  # not in any header either
        self.assertEqual(copy.extra_headers["Auto-Submitted"], "auto-generated")
        self.assertEqual(copy.subject, "Reply in the Office: Re: Hello")
        log = EmailLog.objects.get(template="office_group_copy")
        self.assertEqual((log.subject_email, log.status, log.to), ("him@example.com", EmailLog.SENT, "team@example.test"))
        self.assertNotIn("Questions? Reply to this email", copy.alternatives[0][0])

    def test_off_when_blank_none_for_spam_and_a_failed_copy_can_be_tried_again_but_never_twice(self):
        set_copy("")
        self.reply("pm-a")
        self.assertEqual(self.copies(), [])
        set_copy("team@example.test")
        self.reply("pm-spam", Headers=[{"Name": "X-Spam-Status", "Value": "Yes, score=9"}])
        self.assertEqual(self.copies(), [])
        message = Message.objects.get(provider_id="pm-a")
        from emailchat import tasks

        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=OSError("down")):
            self.assertIn("copy failed", tasks.process_inbound(message.pk))
        message.refresh_from_db()
        self.assertIsNone(message.group_copied_at)  # the claim is given back
        self.assertIn("copied", tasks.process_inbound(message.pk))
        self.assertIn("already copied", tasks.process_inbound(message.pk))
        self.assertEqual(len(self.copies()), 1)

    def test_a_copy_that_comes_back_is_never_stored_and_the_group_address_cannot_be_the_reply_domain(self):
        set_copy("team@example.test")
        self.reply("pm-1")
        looped = payload_for(self.thread, message_id="pm-loop", Headers=[{"Name": "X-Spa99-Group-Copy", "Value": "1"}])
        self.assertEqual(inbound_post(looped).status_code, 200)
        self.assertFalse(Message.objects.filter(provider_id="pm-loop").exists())
        for bad in ("anything@reply.example.test", "x@mail.reply.example.test"):
            with self.assertRaises(ValidationError):
                validate_group_copy_email(bad)
            set_copy(bad)
            self.assertEqual(services.group_copy_address(), "")  # also refused at send time
        validate_group_copy_email("")
        validate_group_copy_email("team@example.test")

    def test_the_setup_fills_the_group_address_once_and_never_overwrites_an_edit_or_a_clear(self):
        row = SiteDefaults.load()
        self.assertTrue(row.office_copy_seeded)  # the test base already ran the seed
        SiteDefaults.objects.filter(pk=row.pk).update(office_copy_email="", office_copy_seeded=False)
        seed_all()
        self.assertEqual(SiteDefaults.load().office_copy_email, "staff@spa99.uk")
        SiteDefaults.objects.filter(pk=row.pk).update(office_copy_email="")
        seed_all()
        self.assertEqual(SiteDefaults.load().office_copy_email, "")  # cleared on purpose: left alone


@override_settings(**SENDING)
class InlinePictureTests(Base):
    def post(self, html, attachments, message_id="pm-pic"):
        payload = payload_for(self.thread, message_id=message_id, HtmlBody=html, TextBody="See you then", Attachments=attachments)
        self.assertEqual(inbound_post(payload).status_code, 200)
        return Message.objects.get(provider_id=message_id)

    def item(self, name, cid="", size_pad=0, kind="image/png", data=PNG, **extra):
        return {"Name": name, "Content": b64(data + b"\x00" * size_pad), "ContentType": kind, "ContentID": cid, **extra}

    def test_signature_pictures_are_stored_but_not_listed_and_real_files_still_show(self):
        html = '<p>See you then</p><img src="cid:sig-logo@mail"><p>Dan</p>'
        message = self.post(html, [self.item("banner.png", "sig-logo@mail"),  # his HTML points at it
                                   self.item("image001.png", ""),  # small, named like Outlook's signature picture
                                   self.item("marked.png", "", Disposition="inline"),  # the mail itself says inline
                                   self.item("holiday.png", "f_abc123"),  # Gmail and Apple give ordinary attachments a Content-ID too: still a file
                                   self.item("plan.pdf", "", kind="application/pdf", data=b"%PDF-1.4 x")])
        self.assertEqual(Attachment.objects.filter(message=message).count(), 5)  # all stored
        self.assertEqual(sorted(Attachment.objects.filter(message=message, inline_ref=True).values_list("filename", flat=True)), ["banner.png", "image001.png", "marked.png"])
        listed = [a["filename"] for a in services.message_dict(message)["attachments"]]
        self.assertEqual(sorted(listed), ["holiday.png", "plan.pdf"])
        self.thread.refresh_from_db()
        self.assertTrue(self.thread.has_attachment)

    def test_only_signature_pictures_means_no_paperclip_no_file_list_and_they_are_still_erased(self):
        message = self.post('<p>x</p><img src="cid:a">', [self.item("a.png", "a"), self.item("logo.png", "")], "pm-sig")
        self.assertEqual(services.message_dict(message)["attachments"], [])
        self.thread.refresh_from_db()
        self.assertFalse(self.thread.has_attachment)
        self.assertEqual(self.thread.last_preview, "See you then")
        keys = list(Attachment.objects.filter(message=message).values_list("key", flat=True))
        self.assertEqual(len(keys), 2)
        services.erase_threads([self.thread])
        from django.core.files.storage import default_storage

        self.assertFalse(any(default_storage.exists(key) for key in keys))

    def test_a_big_or_oddly_named_picture_without_a_marker_is_a_file(self):
        message = self.post("<p>x</p>", [self.item("image002.png", "", size_pad=150_000), self.item("photo-of-the-house.png", "")], "pm-big")
        self.assertEqual(sorted(a["filename"] for a in services.message_dict(message)["attachments"]), ["image002.png", "photo-of-the-house.png"])
        plain = payload_for(self.thread, message_id="pm-plain", Attachments=[self.item("image001.png", "")])  # no HTML at all: a name proves nothing
        inbound_post(plain)
        self.assertEqual([a["filename"] for a in services.message_dict(Message.objects.get(provider_id="pm-plain"))["attachments"]], ["image001.png"])


@override_settings(**SENDING)
class ThreadNameTests(Base):
    def test_a_thread_with_no_name_shows_the_senders_name_from_his_latest_email_escaped(self):
        thread = Thread.objects.create(email="dan@example.com", subject="Visit")
        self.assertEqual((services.thread_dict(thread)["name"], services.thread_dict(thread)["has_name"]), ("dan@example.com", False))
        Message.objects.create(thread=thread, direction="in", status="received", from_address="dan@example.com", from_name="Dan Early", body_text="a")
        Message.objects.create(thread=thread, direction="in", status="received", from_address="dan@example.com", from_name='<script>alert(1)</script> "Dan"\r\n', body_text="b")
        Message.objects.create(thread=thread, direction="in", status="received", from_address="someone.else@example.com", from_name="Forwarder", body_text="c")  # not him
        data = services.thread_dict(thread)
        self.assertEqual((data["name"], data["has_name"]), ("<script>alert(1)</script> \"Dan\"", True))
        page = office(self.reader, "get", f"/email/{thread.pk}/").content.decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertEqual(json.loads(office(self.reader, "get", f"/email/{thread.pk}/poll/").content)["thread"]["name"], data["name"])
        Thread.objects.filter(pk=thread.pk).update(name="Resolved Name")
        thread.refresh_from_db()
        self.assertEqual(services.thread_dict(thread)["name"], "Resolved Name")  # a resolved name always wins
