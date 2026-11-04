"""Email chat (docs/features/office-email-chat.md). Mocked: no Postmark call is ever made (mail goes to the in-memory outbox), the queue runs inline and files
are in memory."""
import base64
import json
from datetime import timedelta
from io import StringIO
from urllib.parse import quote
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone

from common import levels, richtext
from emailchat import services
from emailchat.models import Attachment, Message, Thread
from gold import services as gold_services
from gold.models import ApplicationEvent, GoldApplication
from gold.tests.test_gold import application_data
from notifications import suppression
from notifications.models import EmailSuppression
from office.tests.test_leads import lead, verify
from office.tests.test_office import OfficeTestCase
from outreach.models import PersonMessage
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.tests.test_register import cleaned
from whatsapp.models import PushSubscription

User = get_user_model()
OFFICE = "office.localhost"
PUBLIC = "localhost"
DOMAIN = "reply.example.test"
CONFIG = dict(SITE_URL="https://spa99.uk", EMAIL_INBOUND_DOMAIN=DOMAIN, EMAIL_INBOUND_USER="inb", EMAIL_INBOUND_PASSWORD="secret-pw",
              VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", VAPID_SUBJECT="mailto:hello@example.test")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
AUTH = "Basic " + base64.b64encode(b"inb:secret-pw").decode()


def office(user, method, path, data=None, **extra):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return getattr(client, method)(path, data or {}, **extra)


def b64(data):
    return base64.b64encode(data).decode()


def inbound_post(payload, auth=AUTH):
    headers = {"HTTP_AUTHORIZATION": auth} if auth else {}
    return Client(HTTP_HOST=PUBLIC).post("/postmark/inbound/", json.dumps(payload), content_type="application/json", **headers)


def payload_for(thread, text="Thanks, that works.", message_id="pm-1", **extra):
    return {"MailboxHash": thread.token, "From": "him@example.com", "FromFull": {"Email": "Him@Example.com", "Name": "Him"}, "Subject": "Re: Hello", "MessageID": message_id,
            "TextBody": text, "Headers": [{"Name": "Message-ID", "Value": "<abc@mail.example.com>"}], "Attachments": [], **extra}


@override_settings(**CONFIG)
class Base(OfficeTestCase):
    def setUp(self):
        self.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        self.reader = make_team_member("reader@example.test", levels.OFFICE)
        self.thread = Thread.objects.create(email="him@example.com", subject="Hello", name="Him")

    def send(self, html="<p>Hello <b>there</b></p>", subject="", thread=None, **extra):
        return office(self.approver, "post", f"/email/{(thread or self.thread).pk}/send/", {"body_html": html, "subject": subject, **extra})


class RichTextTests(Base):
    def test_outgoing_html_keeps_the_allow_list_and_drops_the_rest(self):
        dirty = ('<p style="color:red;position:fixed">hi <a href="javascript:alert(1)">x</a><a href="https://ok.example/">ok</a><script>bad()</script>'
                 '<img src="https://t/x.gif"><b onclick="x()">b</b><iframe src="https://e"></iframe></p><span style="background-color:url(http://x)">z</span>')
        clean = richtext.clean_outgoing(dirty)
        for bad in ("script", "javascript", "onclick", "<img", "iframe", "position", "url("):
            self.assertNotIn(bad, clean)
        self.assertIn('href="https://ok.example/"', clean)
        self.assertIn('rel="noopener noreferrer nofollow"', clean)
        self.assertIn("color: red", clean)

    def test_incoming_html_allows_pictures_but_never_data_or_scripts_and_counts_outside_ones(self):
        clean = richtext.clean_incoming('<table><tr><td><img src="https://t/p.gif"><img src="cid:logo"><img src="data:image/png;base64,AAAA"></td></tr></table><form><input></form><script>x</script>')
        self.assertNotIn("data:", clean)
        self.assertNotIn("<form", clean)
        self.assertNotIn("script", clean)
        self.assertEqual((richtext.remote_image_count(clean), richtext.cid_names(clean)), (1, {"logo"}))

    def test_plain_text_copy_keeps_lists_and_link_addresses(self):
        text = richtext.html_to_text('<p>Hello <b>you</b></p><ul><li>a</li></ul><a href="https://x.example/">link</a>')
        self.assertIn("Hello you", text)
        self.assertIn("- a", text)
        self.assertIn("https://x.example/", text)


class SendingTests(Base):
    def test_send_goes_by_the_worker_with_reply_to_threading_headers_html_and_text(self):
        Message.objects.create(thread=self.thread, direction="in", subject="Hello", body_text="Earlier", rfc_message_id="<first@mail.example.com>", references="<root@mail.example.com>", status="received")
        response = self.send("<p>Hello <b>there</b></p>")
        self.assertEqual(response.status_code, 200)
        message = Message.objects.get(direction="out")
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.subject, "Re: Hello")  # no subject typed: Re: and the thread's subject
        sent = mail.outbox[-1]
        self.assertEqual(sent.to, ["him@example.com"])
        self.assertEqual(sent.reply_to, [f"Spa 99 <reply+{self.thread.token}@{DOMAIN}>"])  # a display name, so mail apps show one
        self.assertEqual(sent.extra_headers["In-Reply-To"], "<first@mail.example.com>")
        self.assertEqual(sent.extra_headers["References"], "<root@mail.example.com> <first@mail.example.com>")
        self.assertEqual(sent.extra_headers["X-PM-Metadata-chat"], str(message.pk))
        self.assertIn("<b>there</b>", sent.alternatives[0][0])
        self.assertIn("Hello there", sent.body)

    @override_settings(EMAIL_INBOUND_DOMAIN="")
    def test_blank_inbound_domain_keeps_reply_to_the_mailbox_and_says_so(self):
        self.send()
        self.assertNotIn("reply+", ",".join(mail.outbox[-1].reply_to))
        self.assertTrue(services.replies_to_mailbox())
        self.assertTrue(office(self.reader, "get", f"/email/{self.thread.pk}/").context["replies_to_mailbox"])

    def test_a_suppressed_address_shows_failed_with_a_plain_reason_and_no_retry(self):
        suppression.add("him@example.com", EmailSuppression.HARD_BOUNCE)
        self.assertEqual(self.send().status_code, 200)
        data = services.message_dict(Message.objects.get())  # the worker has run: the poll shows its outcome
        self.assertEqual(data["status"], "failed")
        self.assertIn("nothing more can be sent", data["error"]["reason"])
        self.assertFalse(data["error"]["can_retry"])
        self.assertEqual(len(mail.outbox), 0)

    def test_duplicate_within_ten_seconds_is_refused_and_a_retry_sends_once(self):
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(self.send().json()["error"], "duplicate")
        failing = Message.objects.create(thread=self.thread, direction="out", subject="x", body_text="x", body_html="<p>x</p>", status="failed", error_code="send_failed")
        first = office(self.approver, "post", f"/email/{self.thread.pk}/retry/{failing.pk}/")
        second = office(self.approver, "post", f"/email/{self.thread.pk}/retry/{failing.pk}/")
        self.assertEqual((first.status_code, second.status_code), (200, 409))
        self.assertEqual(len(mail.outbox), 2)

    def test_files_are_attached_a_dangerous_type_is_refused_and_a_reader_cannot_send(self):
        ok = self.send(files=SimpleUploadedFile("note.pdf", b"%PDF-1.4 x", "application/pdf"))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(mail.outbox[-1].attachments[0][0], "note.pdf")
        self.assertEqual(self.send(files=SimpleUploadedFile("run.exe", b"MZ", "application/octet-stream")).json()["error"], "bad_file")
        self.assertEqual(office(self.reader, "post", f"/email/{self.thread.pk}/send/", {"body_html": "<p>x</p>"}).status_code, 403)

    def test_send_from_a_gold_thread_marks_contacted_once(self):
        application, _ = gold_services.submit_application(application_data(email="gold@example.com"))
        thread = Thread.objects.create(email="gold@example.com", subject="Gold", application=application)
        self.send(thread=thread, gold=str(application.pk))
        self.send("<p>Another</p>", thread=thread, gold=str(application.pk))
        application.refresh_from_db()
        self.assertEqual(application.status, GoldApplication.CONTACTED)
        events = application.events.filter(action=ApplicationEvent.RESPONDED)
        self.assertEqual((events.count(), events.first().meta), (1, {"email": True}))


class InboundTests(Base):
    def test_webhook_is_404_until_configured_and_401_for_bad_credentials(self):
        with override_settings(EMAIL_INBOUND_PASSWORD=""):
            self.assertEqual(inbound_post(payload_for(self.thread)).status_code, 404)
        self.assertEqual(inbound_post(payload_for(self.thread), auth="Basic " + b64(b"inb:wrong")).status_code, 401)
        self.assertEqual(inbound_post(payload_for(self.thread), auth=None).status_code, 401)
        self.assertEqual(Message.objects.count(), 0)

    def test_stores_once_prefers_the_stripped_reply_and_moves_the_thread(self):
        body = payload_for(self.thread, text="Thanks!\n\nOn Monday you wrote:\n> old", StrippedTextReply="Thanks!", HtmlBody="<p>Thanks!</p><blockquote>old</blockquote>")
        self.assertEqual((inbound_post(body).status_code, inbound_post(body).status_code), (200, 200))  # Postmark retries: same MessageID
        message = Message.objects.get()
        self.assertEqual((message.body_text, message.from_address, message.status), ("Thanks!", "him@example.com", "received"))
        self.assertIn("old", message.body_full)
        self.assertIn("<blockquote>", message.body_html)
        self.thread.refresh_from_db()
        self.assertEqual((self.thread.last_preview, self.thread.last_direction), ("Thanks!", "in"))

    def test_text_falls_back_to_html_stripped_and_unknown_tokens_store_nothing(self):
        only_html = {"MailboxHash": self.thread.token, "From": "him@example.com", "Subject": "Hi", "MessageID": "pm-2", "HtmlBody": "<p>Only <i>html</i> here</p><script>x()</script>"}
        inbound_post(only_html)
        self.assertEqual(Message.objects.get().body_text, "Only html here")
        for hash_ in ("", "nonsense", "0" * 24):
            self.assertEqual(inbound_post({**payload_for(self.thread, message_id=f"x{hash_}"), "MailboxHash": hash_}).status_code, 200)
        self.assertEqual(Message.objects.count(), 1)

    def test_a_different_sender_is_stored_and_exposed(self):
        inbound_post({**payload_for(self.thread), "FromFull": {"Email": "assistant@other.example", "Name": "PA"}})
        data = services.message_dict(Message.objects.get())
        self.assertEqual((data["from_address"], data["from_other"]), ("assistant@other.example", True))

    def test_spam_is_stored_flagged_never_pushed_or_unread(self):
        PushSubscription.objects.create(user=self.approver, endpoint="https://push.example/1", p256dh="k", auth="a")
        with mock.patch("whatsapp.push.webpush") as sent:
            inbound_post({**payload_for(self.thread, message_id="spam1"), "Headers": [{"Name": "X-Spam-Status", "Value": "Yes, score=9"}]})
            self.assertEqual(sent.call_count, 0)
            inbound_post(payload_for(self.thread, message_id="ham1"))
            self.assertEqual(sent.call_count, 1)
            title = json.loads(sent.call_args.kwargs["data"])["title"]
        self.assertTrue(title.startswith("Email from"))
        self.assertTrue(Message.objects.get(provider_id="spam1").spam)
        self.assertEqual(services.unread_total(self.approver), 1)
        self.assertEqual(services.unread_counts(self.approver, [self.thread.pk]), {self.thread.pk: 1})

    def test_files_are_kept_big_ones_dropped_with_a_note_and_only_real_images_open_inline(self):
        files = [{"Name": "photo.png", "Content": b64(PNG), "ContentType": "image/png", "ContentLength": len(PNG)},
                 {"Name": "fake.png", "Content": b64(b"<html>not a png"), "ContentType": "image/png", "ContentLength": 15},
                 {"Name": "run.exe", "Content": b64(b"MZ"), "ContentType": "application/x-msdownload", "ContentLength": 2},
                 {"Name": "huge.pdf", "Content": b64(b"%PDF" + b"0" * 2048), "ContentType": "application/pdf", "ContentLength": 2052}]
        with override_settings(EMAILCHAT_MAX_ATTACHMENT_BYTES=1024):
            inbound_post(payload_for(self.thread, Attachments=files))
        message = Message.objects.get()
        by_name = {a.filename: a for a in message.attachments.all()}
        self.assertEqual(set(by_name), {"photo.png", "fake.png", "run.exe"})
        self.assertIn("huge.pdf was too big", message.note)
        self.assertEqual([(n, a.inline_ok) for n, a in sorted(by_name.items())], [("fake.png", False), ("photo.png", True), ("run.exe", False)])
        shown = office(self.reader, "get", f"/email/file/{by_name['photo.png'].pk}/")
        self.assertEqual((shown["Content-Type"], "attachment" in shown.get("Content-Disposition", "")), ("image/png", False))
        downloaded = office(self.reader, "get", f"/email/file/{by_name['fake.png'].pk}/")
        self.assertIn("attachment", downloaded["Content-Disposition"])
        self.assertEqual(downloaded["Content-Type"], "application/octet-stream")

    def test_a_storage_failure_answers_500_and_leaves_nothing_so_the_retry_stores_it_whole(self):
        files = [{"Name": "a.png", "Content": b64(PNG), "ContentType": "image/png"}]
        with mock.patch("emailchat.services._store_file", side_effect=OSError("down")):
            self.assertEqual(inbound_post(payload_for(self.thread, Attachments=files)).status_code, 500)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(inbound_post(payload_for(self.thread, Attachments=files)).status_code, 200)
        self.assertEqual(Attachment.objects.count(), 1)

    def test_oversized_body_is_dropped_with_200_so_postmark_does_not_retry(self):
        with override_settings(EMAILCHAT_MAX_INBOUND_BYTES=50):
            self.assertEqual(inbound_post(payload_for(self.thread)).status_code, 200)
        self.assertEqual(Message.objects.count(), 0)


class FrameTests(Base):
    def make(self, html, **kw):
        return Message.objects.create(thread=self.thread, direction="in", subject="x", body_text="x", body_html=html, status="received", provider_id=kw.pop("pid", "f1"), **kw)

    def test_his_html_is_served_in_a_locked_down_document_and_never_in_the_page(self):
        message = self.make(richtext.clean_incoming('<p>Hi</p><img src="https://track.example/p.gif"><script>x()</script>'), has_remote_images=True)
        page = office(self.reader, "get", f"/email/{self.thread.pk}/")
        data = page.context["chat_messages"][0]
        self.assertEqual((data["body_html"], data["frame_url"], data["has_remote_images"]), ("", f"/email/message/{message.pk}/frame/", True))
        self.assertNotIn("track.example", page.content.decode())
        blocked = office(self.reader, "get", data["frame_url"])
        self.assertNotIn("track.example", blocked.content.decode())
        self.assertEqual((blocked["X-Frame-Options"], blocked["X-Blocked-Images"]), ("SAMEORIGIN", "1"))
        csp = blocked["Content-Security-Policy"]
        for part in ("default-src 'none'", "form-action 'none'", "img-src data:", "sandbox"):
            self.assertIn(part, csp)
        self.assertNotIn("script-src", csp)
        shown = office(self.reader, "get", data["frame_url"] + "?images=1")
        self.assertIn("track.example", shown.content.decode())
        self.assertIn("https:", shown["Content-Security-Policy"])

    def test_cid_pictures_come_from_the_stored_files(self):
        message = self.make('<img src="cid:logo1"><img src="cid:missing">')
        key = default_storage.save("emailchat/t/logo", ContentFile(PNG))
        Attachment.objects.create(message=message, key=key, filename="logo.png", content_type="image/png", declared_type="image/png", size=len(PNG), content_id="logo1", inline_ok=True, checked=True)
        body = office(self.reader, "get", f"/email/message/{message.pk}/frame/").content.decode()
        self.assertIn("data:image/png;base64,", body)
        self.assertNotIn("cid:", body)


class FeedbackTests(Base):
    def record(self, kind, message, **extra):
        return {"RecordType": kind, "ID": 1, "Email": "him@example.com", "Type": "HardBounce", "Details": "Mailbox does not exist", "MessageID": "pm-out-1", "Metadata": {"chat": str(message.pk)}, **extra}

    def feedback(self, record):
        from notifications import postmark

        return postmark.apply(record)

    def test_a_bounce_marks_the_chat_message_and_still_suppresses_the_address(self):
        self.send()
        message = Message.objects.get(direction="out")
        self.assertEqual(self.feedback(self.record("Bounce", message)), 1)  # the existing path still records the address
        message.refresh_from_db()
        self.assertEqual((message.status, message.error_code, message.provider_id), ("bounced", "bounced", "pm-out-1"))
        self.assertTrue(suppression.is_suppressed("him@example.com"))
        self.assertIn("did not accept", services.message_dict(message)["error"]["reason"])

    def test_delivery_a_soft_transient_bounce_and_another_address_are_handled_safely(self):
        self.send()
        message = Message.objects.get(direction="out")
        self.feedback({"RecordType": "Delivery", "Recipient": "him@example.com", "MessageID": "pm-d", "Metadata": {"chat": str(message.pk)}})
        message.refresh_from_db()
        self.assertEqual(message.status, "delivered")
        self.feedback(self.record("Bounce", message, Type="Transient"))
        self.feedback(self.record("Bounce", message, Email="someone@else.example"))
        message.refresh_from_db()
        self.assertEqual(message.status, "delivered")


class PageTests(Base):
    def test_inbox_filters_search_and_unread(self):
        Thread.objects.filter(pk=self.thread.pk).update(last_message_at=timezone.now(), last_direction="out", last_preview="Sent")
        other = Thread.objects.create(email="two@example.com", subject="Invoice", name="Two", last_message_at=timezone.now(), last_direction="in", last_preview="Paid")
        Message.objects.create(thread=other, direction="in", subject="Invoice", body_text="Paid", status="received")
        rows = lambda q="": [r["email"] for r in office(self.reader, "get", "/email/" + q).context["rows"]]
        self.assertEqual(set(rows()), {"him@example.com", "two@example.com"})
        self.assertEqual(rows("?filter=unread"), ["two@example.com"])
        self.assertEqual(rows("?filter=noreply"), ["him@example.com"])
        self.assertEqual(rows("?q=invoice"), ["two@example.com"])  # subject
        self.assertEqual(rows("?q=HIM@"), ["him@example.com"])  # address
        self.assertEqual(office(self.reader, "get", "/email/unread/").json(), {"unread_total": 1})
        office(self.reader, "post", f"/email/{other.pk}/read/")
        self.assertEqual(office(self.reader, "get", "/email/unread/").json(), {"unread_total": 0})

    def test_poll_returns_new_messages_and_status_changes(self):
        first = Message.objects.create(thread=self.thread, direction="out", subject="s", body_text="a", body_html="<p>a</p>", status="sent")
        cursor = office(self.reader, "get", f"/email/{self.thread.pk}/poll/?after=0").json()["cursor"]
        Message.objects.filter(pk=first.pk).update(status="delivered", updated_at=timezone.now() + timedelta(seconds=1))
        later = Message.objects.create(thread=self.thread, direction="in", subject="s", body_text="b", status="received")
        data = office(self.reader, "get", f"/email/{self.thread.pk}/poll/?after={first.pk}&since={quote(cursor)}").json()
        self.assertEqual(([m["id"] for m in data["messages"]], [m["status"] for m in data["updates"]], data["last_id"]), ([later.pk], ["delivered"], later.pk))

    def test_many_threads_per_address_new_email_and_the_start_or_open_button(self):
        session = lead("hugo@example.com")
        page = lambda: office(self.reader, "get", f"/leads/{session.pk}/").context["email_chat"]
        before = page()
        self.assertEqual((before["has_thread"], before["state"], before["label"]), (False, "start", "Start email"))
        self.assertIn(f"person=lead%3A{session.pk}", before["new_email_url"])
        start = office(self.reader, "get", f"/leads/{session.pk}/email-chat/")
        self.assertEqual(start.status_code, 302)
        self.assertTrue(start["Location"].startswith("/email/new/"))
        form = office(self.reader, "get", before["new_email_url"])
        self.assertEqual(form.context["recipient"]["email"], "hugo@example.com")
        self.assertEqual(office(self.reader, "post", "/email/new/", {"person": f"lead:{session.pk}", "subject": "x"}).status_code, 403)
        created = office(self.approver, "post", "/email/new/", {"person": f"lead:{session.pk}", "subject": "First", "body_html": "<p>Hello</p>"}, HTTP_ACCEPT="application/json").json()
        self.assertTrue(created["ok"])
        office(self.approver, "post", "/email/new/", {"to": "Hugo@Example.com", "subject": "Second"})
        self.assertEqual(Thread.objects.filter(email="hugo@example.com").count(), 2)  # a new thread each time
        self.assertEqual(Message.objects.filter(thread__email="hugo@example.com").count(), 1)
        after = page()
        self.assertEqual((after["has_thread"], after["state"], after["thread_count"], after["label"]), (True, "open", 2, "Open email thread"))
        self.assertEqual(office(self.reader, "get", f"/leads/{session.pk}/email-chat/")["Location"], after["latest_thread_url"])
        self.assertEqual(office(self.approver, "post", "/email/new/", {"to": "not an address", "subject": "x"}, HTTP_ACCEPT="application/json").json()["error"], "bad_address")
        self.assertEqual(office(self.approver, "post", "/email/new/", {"to": "a@example.com", "subject": ""}, HTTP_ACCEPT="application/json").json()["error"], "no_subject")

    def test_people_search_is_short_and_covers_leads_registered_and_gold(self):
        lead("hugo@example.com")
        gold_services.submit_application(application_data(email="hugh.gold@example.com"))
        user = user_services.register_interest(cleaned(email="hughie@example.com")).user
        search = lambda q: office(self.reader, "get", f"/email/people/?q={q}").json()["results"]
        self.assertEqual(search("h"), [])
        kinds = {r["email"]: r["kinds"] for r in search("hug")}
        self.assertEqual(kinds["hugo@example.com"], ["lead"])
        self.assertEqual(kinds["hugh.gold@example.com"], ["gold"])
        self.assertEqual(kinds["hughie@example.com"], ["registered"])
        self.assertTrue(all(r["person"].split(":")[0] in ("lead", "person", "gold") for r in search("hug")))
        self.assertIsNotNone(user)

    def test_timeline_lines_cover_all_threads_and_the_old_messages_are_not_doubled(self):
        session = lead("hugo@example.com")
        PersonMessage.objects.create(email="hugo@example.com", text="Old hello", author_label="Barry")
        timeline = lambda: [e["label"] for e in office(self.reader, "get", f"/leads/{session.pk}/").context["person"]["timeline"]]
        self.assertIn("Message sent by Barry", timeline())
        for subject in ("One", "Two"):
            _, thread = services.create_thread("hugo@example.com", subject, self.approver)
            services.send(thread, self.approver, subject, "<p>Hi</p>")
        labels = timeline()
        self.assertEqual(sum(1 for x in labels if x.startswith("First email sent")), 2)
        self.assertEqual(sum(1 for x in labels if x == "Email: 1 from us"), 2)
        call_command("backfill_email_threads", stdout=StringIO())
        self.assertNotIn("Message sent by Barry", timeline())  # copied into a thread: the thread shows it now

    def test_page_context_keys_exist_on_lead_and_gold_pages(self):
        application, _ = gold_services.submit_application(application_data(email="gold@example.com"))
        context = office(self.reader, "get", f"/gold/{application.pk}/").context
        self.assertEqual(set(context["email_chat"]), {"has_thread", "thread_count", "latest_thread_url", "new_email_url", "open_url", "state", "label", "email", "can_send", "can_edit",
                                                      "unread", "replies_to_mailbox", "suppressed", "reason"})


class PrivacyTests(Base):
    def setUp(self):
        super().setUp()
        self.user = user_services.register_interest(cleaned(email="him@example.com")).user
        _, self.mine = services.create_thread("him@example.com", "Mine", self.approver)
        _, self.other = services.create_thread("other@example.com", "Other", self.approver)
        for thread in (self.mine, self.other):
            services.send(thread, self.approver, thread.subject, "<p>Hi</p>", [SimpleUploadedFile("a.pdf", b"%PDF-1", "application/pdf")])

    def test_member_export_and_delete_only_take_the_verified_account_thread(self):
        self.assertEqual(user_services.export_user_data(self.user)["email_threads"], [])  # not verified: nothing is his yet
        verify(self.user)
        self.user.refresh_from_db()
        exported = user_services.export_user_data(self.user)["email_threads"]
        self.assertEqual({t["subject"] for t in exported}, {"Mine", "Hello"})  # every thread on his verified address, not the other person's
        self.assertEqual(next(t for t in exported if t["subject"] == "Mine")["messages"][0]["files"][0]["name"], "a.pdf")
        keys = list(Attachment.objects.filter(message__thread=self.mine).values_list("key", flat=True))
        user_services.delete_user_data(self.user)
        self.assertFalse(Thread.objects.filter(pk=self.mine.pk).exists())
        self.assertTrue(Thread.objects.filter(pk=self.other.pk).exists())
        self.assertFalse(default_storage.exists(keys[0]))

    def test_staff_export_and_erase_include_every_thread_and_file(self):
        verify(self.user)
        self.user.refresh_from_db()
        _, second = services.create_thread("him@example.com", "Second", self.approver)
        admin = make_team_member("admin@example.test", levels.ADMIN)
        data = json.loads(office(admin, "get", f"/people/{self.user.pk}/export/").content)
        self.assertEqual({t["subject"] for t in data["email_threads"]}, {"Hello", "Mine", "Second"})
        keys = list(Attachment.objects.filter(message__thread=self.mine).values_list("key", flat=True))
        office(admin, "post", f"/people/{self.user.pk}/delete/")
        self.assertEqual(Thread.objects.filter(email="him@example.com").count(), 0)
        self.assertFalse(default_storage.exists(keys[0]))
        self.assertTrue(Thread.objects.filter(pk=self.other.pk).exists())
        self.assertIsNotNone(second)


class BackfillTests(Base):
    def test_dry_run_changes_nothing_and_the_real_run_is_idempotent(self):
        PersonMessage.objects.create(email="old@example.com", text="One", author_label="Barry")
        PersonMessage.objects.create(email="old@example.com", text="Two", author_label="Barry")
        out = StringIO()
        call_command("backfill_email_threads", "--dry-run", stdout=out)
        self.assertIn("2 old message(s)", out.getvalue())
        self.assertEqual(Message.objects.count(), 0)
        call_command("backfill_email_threads", stdout=StringIO())
        call_command("backfill_email_threads", stdout=StringIO())
        self.assertEqual((Thread.objects.filter(email="old@example.com").count(), Message.objects.filter(thread__email="old@example.com").count()), (1, 2))
        self.assertEqual(PersonMessage.objects.count(), 2)  # the old rows stay
