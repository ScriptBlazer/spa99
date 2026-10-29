"""The email builder: parts validation, rendering (HTML and text), the old body unchanged, uploaded pictures and the public image view,
the Start from template, and a send with parts. Mocked: in-memory media and outbox."""
import json
import struct
import zlib

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from mailings import blocks, images, sending
from mailings.models import Mailing, MailingImage, MailingTemplate
from mailings.tests.test_mailings import mailing, person
from notifications.services import preview_email
from plans.management.commands.seed_phase1 import seed_all
from system.models import SystemEvent
from system.tests.test_system import make_user, unlocked_client


def png(width=40, height=20, pad=0):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"") + b"\x00" * pad)


def upload(data, name="a.png"):
    return SimpleUploadedFile(name, data, content_type="image/png")


def parts(*extra):
    return [{"type": "paragraph", "text": "Hello {first_name}"}, *extra]


class ValidationTests(TestCase):
    def errors(self, raw):
        return blocks.clean(raw)[1]

    def test_the_rules(self):
        self.assertEqual(self.errors(parts()), {})
        self.assertEqual(self.errors(parts({"type": "button", "label": "Book", "url": "/account/book/"})), {})
        for url in ("javascript:alert(1)", "data:text/html,x", "//evil.example/x", "ftp://x.example/a", "https://", "/a b"):
            self.assertIn("url", self.errors(parts({"type": "button", "label": "Go", "url": url}))["1"], url)
        self.assertIn("alt", self.errors(parts({"type": "image", "image": "1f0e8d0e-0000-4000-8000-000000000000", "alt": ""}))["1"])
        self.assertIn("image", self.errors(parts({"type": "image", "image": "1f0e8d0e-0000-4000-8000-000000000000", "alt": "x"}))["1"])  # no such picture
        self.assertIn("type", self.errors(parts({"type": "video"}))["1"])
        self.assertIn("text", self.errors([{"type": "paragraph", "text": "Hi {nope}"}])["0"])
        self.assertIn("text", self.errors([{"type": "heading", "text": "x" * 121}])["0"])
        self.assertIn("_", self.errors([{"type": "divider"}]))  # nothing but dividers
        self.assertIn("_", self.errors(parts(*[{"type": "divider"}] * 30)))  # 31 parts
        self.assertIn("_", self.errors("not json"))

    def test_error_text_and_the_cleaned_list(self):
        cleaned, errors = blocks.clean(json.dumps(parts({"type": "button", "label": " Go ", "url": "x", "extra": 1})))
        self.assertEqual(blocks.flat_errors(errors)[0][:7], "Part 2:")
        self.assertEqual(cleaned[1], {"type": "button", "link": "url", "label": "Go", "url": "x"})


class RenderTests(TestCase):
    def setUp(self):
        seed_all()

    def render(self, *items, name="James"):
        cleaned, errors = blocks.clean(list(items))
        self.assertEqual(errors, {})
        return blocks.render(cleaned, {"first_name": name})

    def test_each_part_in_html_and_text_with_escaping(self):
        image = images.save_upload(upload(png(40, 20)))
        html, text, pre = self.render(
            {"type": "heading", "text": "Hello <b>{first_name}</b>"},
            {"type": "paragraph", "text": "Welcome, {first_name}.\n\nSecond <i>paragraph</i> here, with enough words to be a preview line."},
            {"type": "button", "label": "Book <now>", "url": "/account/book/"},
            {"type": "image", "image": str(image.pk), "alt": 'A "room"', "url": "https://example.com/x?a=1&b=2"},
            {"type": "divider"}, {"type": "small_print", "text": "Fine <print>"}, name="<b>Sam</b>")
        self.assertNotIn("<b>", html)
        self.assertIn("<h2", html)
        self.assertIn("&lt;b&gt;Sam&lt;/b&gt;", html)
        self.assertIn('href="http://localhost:8000/account/book/"', html)
        self.assertIn(f'src="http://localhost:8000/email-image/{image.pk}.png" width="40" height="20" alt="A &quot;room&quot;"', html)
        self.assertIn('href="https://example.com/x?a=1&amp;b=2"', html)
        self.assertIn("e-hair", html)
        self.assertIn('class="e-muted"', html)
        self.assertIn("Book &lt;now&gt;", html)
        self.assertIn("Book <now>:\nhttp://localhost:8000/account/book/", text)
        self.assertIn("[Image: A \"room\"]\nhttps://example.com/x?a=1&b=2", text)
        self.assertIn("----", text)
        self.assertNotIn("http", pre)
        self.assertTrue(pre.startswith("Welcome, <b>Sam</b>."))  # plain text; the layout escapes it

    def test_first_name_falls_back_to_there(self):
        from notifications import emailbody

        values = emailbody.values_for(emailbody.SPECS["mailing"], {"first_name": " "})
        self.assertIn("Hello there", blocks.render([{"type": "paragraph", "text": "Hello {first_name}"}], values)[1])

    def test_a_mailing_without_parts_renders_from_the_body_as_before(self):
        old = preview_email("mailing", "S", "Hi {first_name}\n\nSoon.")
        self.assertIn("Hi James", old["text"])
        self.assertEqual(old, preview_email("mailing", "S", "Hi {first_name}\n\nSoon.", blocks=[]))
        self.assertIn("<h2", preview_email("mailing", "S", "", blocks=[{"type": "heading", "text": "Hi"}])["html"])

    def test_thirty_parts_stay_under_the_gmail_clip(self):
        items = [{"type": "paragraph", "text": "A paragraph of ordinary length. " * 30}] * 10 + [
            {"type": "button", "label": "Book your first visit", "url": "https://example.com/some/long/path"}] * 10 + [
            {"type": "heading", "text": "Heading"}, {"type": "divider"}, {"type": "small_print", "text": "Small " * 20}] * 3 + [
            {"type": "divider"}]
        self.assertEqual(len(items), 30)
        html = preview_email("mailing", "S", "", blocks=blocks.clean(items)[0])["html"]
        self.assertLess(len(html.encode()), 102 * 1024)


class ImageTests(TestCase):
    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())

    def post(self, upload_file):
        return self.client.post("/emails/mailings/images/", {"file": upload_file})

    def test_upload_checks_the_content_not_the_name(self):
        ok = self.post(upload(png(60, 30)))
        data = ok.json()
        self.assertEqual((ok.status_code, data["width"], data["height"]), (200, 60, 30))
        image = MailingImage.objects.get(pk=data["id"])
        self.assertRegex(image.file.name, r"^mailings/images/[0-9a-f]{32}\.png$")
        self.assertEqual(data["url"], f"http://localhost:8000/email-image/{image.pk}.png")
        self.assertEqual(self.post(upload(b"just some text, not a picture", "fake.png")).status_code, 400)
        self.assertEqual(self.post(upload(b"<svg onload=alert(1)>", "x.png")).status_code, 400)
        self.assertEqual(self.post(upload(png(pad=2 * 1024 * 1024))).status_code, 400)
        self.assertEqual(MailingImage.objects.count(), 1)

    def test_the_header_readers(self):
        self.assertEqual(images.dimensions(b"GIF89a" + struct.pack("<HH", 7, 9), "image/gif"), (7, 9))
        jpeg = b"\xff\xd8\xff\xe0\x00\x04\x00\x00\xff\xc0\x00\x0b\x08" + struct.pack(">HH", 20, 30) + b"\x01\x01\x11\x00"
        self.assertEqual(images.dimensions(jpeg, "image/jpeg"), (30, 20))

    def test_the_public_view_streams_with_cache_headers(self):
        image = images.save_upload(upload(png()))
        response = Client().get(f"/email-image/{image.pk}.png")
        self.assertEqual(Client().get(f"/email-image/{image.pk}/").status_code, 200)  # the older address keeps working
        self.assertEqual((response.status_code, response["Content-Type"]), (200, "image/png"))
        self.assertIn("max-age=31536000", response["Cache-Control"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\x89PNG"))
        self.assertEqual(Client().get("/email-image/00000000-0000-4000-8000-000000000000/").status_code, 404)
        self.assertEqual(Client().post(f"/email-image/{image.pk}/").status_code, 405)


class BuilderTests(TestCase):
    def setUp(self):
        seed_all()
        self.client = unlocked_client(make_user())
        person("a@example.com", consent=True)

    def data(self, items, **over):
        return {"name": "Opening", "subject": "Hello {first_name}", "kind": "service", "group": "everyone", "blocks": json.dumps(items), **over}

    def test_save_with_parts_and_errors_by_part(self):
        bad = self.client.post("/emails/mailings/new/", self.data(parts({"type": "button", "label": "Go", "url": "javascript:x"})), HTTP_ACCEPT="application/json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("url", bad.json()["errors"]["blocks"]["1"])
        self.assertEqual(Mailing.objects.count(), 0)
        ok = self.client.post("/emails/mailings/new/", self.data(parts()), HTTP_ACCEPT="application/json")
        self.assertTrue(ok.json()["ok"])
        row = Mailing.objects.get()
        self.assertEqual((row.blocks, row.body), ([{"type": "paragraph", "text": "Hello {first_name}"}], ""))

    def test_preview_with_parts_and_an_old_draft_opens_as_paragraphs(self):
        preview = self.client.post("/emails/mailings/preview/", {"subject": "S", "blocks": json.dumps(parts())}).json()
        self.assertTrue(preview["ok"])
        self.assertIn("Hello James", preview["text"])
        errors = self.client.post("/emails/mailings/preview/", {"subject": "S", "blocks": "[]"}).json()["errors"]
        self.assertIn("_", errors["blocks"])
        old = mailing(body="One.\n\nTwo.")
        context = self.client.get(f"/emails/mailings/{old.pk}/edit/").context
        self.assertEqual([p["text"] for p in context["blocks"]], ["One.", "Two."])

    def test_the_booking_is_open_starter_prefills(self):
        context = self.client.get("/emails/mailings/new/?start=booking_open").context  # a key works as well as an id
        self.assertEqual((context["form"]["kind"].value(), context["form"]["group"].value()), ("service", "everyone"))
        self.assertEqual([p["type"] for p in context["blocks"]], ["heading", "paragraph", "button", "small_print"])
        self.assertEqual(context["blocks"][2]["url"], "/account/book/")
        self.assertEqual(self.client.get("/emails/mailings/new/").context["blocks"], [])
        self.assertEqual(blocks.clean(blocks.STARTERS["booking_open"]["blocks"])[1], {})
        row = MailingTemplate.objects.get(key="booking_open")
        self.assertEqual(context["start"], str(row.pk))
        self.assertIn("Service message to Everyone registered: a heading", [d["description"] for d in context["starter_details"]][0])
        self.assertNotIn("!", json.dumps(blocks.STARTERS["booking_open"]))

    def test_a_send_with_parts_carries_the_unsubscribe_link_or_the_notice(self):
        items = blocks.clean(parts({"type": "button", "label": "Book", "url": "/account/book/"}))[0]
        news = mailing(kind=Mailing.NEWS, body="", blocks=items)
        sending.start(news)
        message = mail.outbox[-1]
        self.assertIn("Unsubscribe", message.body)
        self.assertIn("Hello Sam", message.body)
        self.assertIn("http://localhost:8000/account/book/", message.alternatives[0][0])
        service = mailing(kind=Mailing.SERVICE, body="", blocks=items)
        sending.start(service)
        self.assertNotIn("Unsubscribe", mail.outbox[-1].body)
        self.assertIn("You are receiving this message", mail.outbox[-1].body)
        self.assertEqual(Mailing.objects.get(pk=service.pk).status, "sent")


class ReviewFixTests(TestCase):
    def test_too_long_an_email_is_refused_and_unknown_parts_do_not_shift_errors(self):
        full = {"type": "paragraph", "text": "A & B <x> " * 200}
        _, errors = blocks.clean([full] * 30)
        self.assertEqual(errors, {"_": [blocks.TOO_LONG]})
        self.assertEqual(blocks.clean([full] * 10)[1], {})
        errors = blocks.clean([{"type": "paragraph", "text": "ok"}, {"type": "video"}, {"type": "image", "image": "x", "alt": "a"}])[1]
        self.assertIn("type", errors["1"])
        self.assertIn("image", errors["2"])  # numbered by where the part sits

    def test_links_to_this_computer_are_refused_unless_debugging(self):
        with override_settings(DEBUG=False):
            self.assertIn("computer", blocks.clean_url("http://localhost:8000/x")[1])
            self.assertIn("computer", blocks.clean_url("http://127.0.0.1/x")[1])
            self.assertEqual(blocks.clean_url("https://spa99.uk/x")[1], "")
        with override_settings(DEBUG=True):
            self.assertEqual(blocks.clean_url("http://localhost:8000/x")[1], "")


class TemplateTests(TestCase):
    def setUp(self):
        seed_all()
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def save(self, **over):
        data = {"name": "Mine", "subject": "Hello", "kind": "news", "group": "", "blocks": json.dumps(parts()), **over}
        return self.client.post("/emails/mailings/templates/save/", data)

    def test_save_overwrite_rename_delete_and_the_audit(self):
        first = self.save()
        self.assertEqual((first.status_code, first.json()["created"]), (200, True))
        again = self.save(name="mine", subject="New")
        self.assertEqual((again.status_code, again.json()["exists"]), (409, True))  # no silent overwrite
        self.assertEqual(MailingTemplate.objects.get(name="Mine").subject, "Hello")
        over = self.save(name="mine", subject="New", overwrite="1")
        self.assertEqual((over.json()["created"], MailingTemplate.objects.get(pk=over.json()["id"]).subject), (False, "New"))
        bad = self.save(name="Bad", blocks=json.dumps(parts({"type": "button", "label": "x", "url": "javascript:1"})))
        self.assertIn("url", bad.json()["errors"]["blocks"]["1"])
        template = MailingTemplate.objects.get(name="mine")
        self.assertEqual(self.client.post(f"/emails/templates/{template.pk}/rename/", {"name": "booking is open"}, HTTP_ACCEPT="application/json").status_code, 409)
        self.assertTrue(self.client.post(f"/emails/templates/{template.pk}/rename/", {"name": "Renamed"}, HTTP_ACCEPT="application/json").json()["ok"])
        self.assertContains(self.client.get("/emails/templates/"), "Renamed")
        self.client.post(f"/emails/templates/{template.pk}/delete/")
        self.assertFalse(MailingTemplate.objects.filter(pk=template.pk).exists())
        kinds = set(SystemEvent.objects.values_list("kind", flat=True))
        self.assertTrue({"tpl_saved", "tpl_renamed", "tpl_deleted"} <= kinds)

    def test_save_from_a_mailing_and_the_seed_is_idempotent(self):
        old = mailing(body="One.\n\nTwo.")
        done = self.client.post("/emails/mailings/templates/save/", {"name": "From old", "mailing": str(old.pk)}).json()
        self.assertEqual([p["text"] for p in MailingTemplate.objects.get(pk=done["id"]).blocks], ["One.", "Two."])
        count = MailingTemplate.objects.count()
        seed_all()
        self.assertEqual(MailingTemplate.objects.count(), count)
        MailingTemplate.objects.filter(key="booking_open").update(name="Edited")
        seed_all()
        self.assertEqual(MailingTemplate.objects.filter(key="booking_open").get().name, "Edited")


class TestWithoutWhoTests(TestCase):
    def setUp(self):
        seed_all()
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def test_an_unsaved_mailing_with_no_group_can_be_tested(self):
        post = {"subject": "Hello {first_name}", "blocks": json.dumps(parts())}
        self.assertTrue(self.client.post("/emails/mailings/test/", post, HTTP_ACCEPT="application/json").json()["ok"])
        self.assertEqual(mail.outbox[-1].to, [self.user.email])
        self.assertIn("Unsubscribe", mail.outbox[-1].body)  # kind defaults to News
        self.client.post("/emails/mailings/test/", {**post, "kind": "service"})
        self.assertNotIn("Unsubscribe", mail.outbox[-1].body)
        bad = self.client.post("/emails/mailings/test/", {"subject": "", "blocks": "[]"}, HTTP_ACCEPT="application/json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(len(mail.outbox), 2)

    def test_a_saved_draft_still_checks_its_wording(self):
        bad = mailing(body="Hi {nope}", group="")
        self.assertEqual(self.client.post(f"/emails/mailings/{bad.pk}/test/", HTTP_ACCEPT="application/json").status_code, 400)
        self.assertEqual(len(mail.outbox), 0)


class ReviewRound3Tests(TestCase):
    def setUp(self):
        seed_all()
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def test_a_name_race_is_a_409_not_a_500_and_rename_is_recorded(self):
        from unittest import mock
        from django.db import IntegrityError
        from mailings import saved

        with mock.patch.object(MailingTemplate, "save", side_effect=IntegrityError("duplicate")):
            with self.assertRaises(saved.TemplateError) as raised:
                saved.save("Racer", "S", "news", "", parts(), self.user)
        self.assertTrue(raised.exception.exists)
        row, _ = saved.save("One", "S", "news", "", parts(), self.user)
        saved.rename(row, "Two", self.user)
        self.assertEqual(row.history.first().history_user, self.user)

    def test_a_bad_mailing_id_is_a_404_and_the_test_limit_comes_first(self):
        post = self.client.post("/emails/mailings/templates/save/", {"name": "x", "mailing": "not-a-uuid"})
        self.assertEqual(post.status_code, 404)
        with mock_limit():
            self.assertEqual(self.client.post("/emails/mailings/test/", {"subject": "", "blocks": "not json"}, HTTP_ACCEPT="application/json").status_code, 429)

    def test_the_public_image_has_no_rate_limit(self):
        image = images.save_upload(upload(png()))
        for _ in range(3):
            self.assertEqual(Client().get(f"/email-image/{image.pk}.png").status_code, 200)


def mock_limit():
    from unittest import mock

    return mock.patch("system.views_emails.hit", return_value=False)
