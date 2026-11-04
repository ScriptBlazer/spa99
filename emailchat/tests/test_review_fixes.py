"""Regression tests for the review of the email chat and WhatsApp round 2 work (docs/features/office-email-chat.md, "Review fixes"). Mocked: nothing real is sent."""
import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from common import levels, richtext
from emailchat import services
from emailchat.models import Attachment, Message, Thread
from emailchat.tests.test_emailchat import PNG, Base, b64, inbound_post, office, payload_for
from office.tests.test_leads import lead, verify
from outreach import services as outreach
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.tests.test_register import cleaned
from whatsapp.models import PushSubscription


class CorrectedAddressTests(Base):
    """Item 1: a lead whose address is corrected keeps his email threads (UK GDPR: export and erase must still find them)."""

    def test_thread_moves_with_the_corrected_address_and_a_late_reply_still_lands(self):
        session = lead("wrong@example.com")
        _, thread = services.create_thread("wrong@example.com", "Hello", self.approver, lead_email="wrong@example.com")  # started from his lead page
        services.send(thread, self.approver, "Hello", "<p>Hi</p>")
        token = thread.token
        self.assertEqual(outreach.correct_lead_email("wrong@example.com", "right@example.com", self.approver)[0], outreach.DONE)
        thread.refresh_from_db()
        self.assertEqual((thread.email, thread.lead_email, thread.token), ("right@example.com", "right@example.com", token))
        page = office(self.reader, "get", f"/leads/{session.pk}/").context["email_chat"]
        self.assertEqual(page["state"], "open")
        self.assertEqual(inbound_post(payload_for(thread, message_id="late-1")).status_code, 200)  # a reply to the old Reply-To lands in the same thread
        self.assertEqual(Message.objects.filter(thread=thread, direction="in").count(), 1)
        admin = make_team_member("admin@example.test", levels.ADMIN)
        exported = json.loads(office(admin, "get", f"/leads/{session.pk}/export/").content)["email_threads"]
        self.assertEqual(len(exported), 1)
        self.assertEqual(len(exported[0]["messages"]), 2)
        keys = list(Attachment.objects.filter(message__thread=thread).values_list("key", flat=True))
        office(admin, "post", f"/leads/{session.pk}/delete/")
        self.assertFalse(Thread.objects.filter(pk=thread.pk).exists())
        self.assertEqual(Message.objects.filter(thread_id=thread.pk).count(), 0)
        self.assertEqual(keys, [])

    def test_a_thread_owned_by_an_account_is_not_moved(self):
        lead("wrong@example.com")
        owned = Thread.objects.create(email="wrong@example.com", subject="His", user=self.approver)
        services.move_address("wrong@example.com", "right@example.com")
        owned.refresh_from_db()
        self.assertEqual(owned.email, "wrong@example.com")


class HtmlEscapingTests(Base):
    """Item 2: a message with text only (old copied ones) is shown as escaped paragraphs."""

    def test_text_only_message_is_escaped_in_the_page_html(self):
        message = Message.objects.create(thread=self.thread, direction="out", subject="x", body_text='<img src=x onerror=alert(1)>\nsecond & line', body_html="", status="sent")
        html = services.message_dict(message)["body_html"]
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn("<br>", html)
        self.assertIn("&amp;", html)


class UnverifiedAccountTests(Base):
    """Item 3: an unverified account (anyone can register any address) never takes a lead's thread, owner link, name, export or erasure."""

    def setUp(self):
        super().setUp()
        lead("victim@example.com")
        self.stranger = user_services.register_interest(cleaned(email="victim@example.com")).user
        _, self.thread_v = services.create_thread("victim@example.com", "For Victim", self.approver, lead_email="victim@example.com")  # started from his lead page
        services.send(self.thread_v, self.approver, "For Victim", "<p>Private</p>")

    def test_unverified_account_does_not_take_the_thread(self):
        self.thread_v.refresh_from_db()
        self.assertIsNone(self.thread_v.user_id)
        self.assertEqual(self.thread_v.lead_email, "victim@example.com")
        self.assertNotEqual(self.thread_v.name, self.stranger.get_full_name())

    def test_staff_export_and_erase_of_the_unverified_account_leave_the_lead_thread_alone(self):
        self.assertEqual(user_services.export_user_data(self.stranger, include_chats=True)["email_threads"], [])
        user_services.delete_user_data(self.stranger, include_chats=True)
        self.assertTrue(Thread.objects.filter(pk=self.thread_v.pk).exists())
        self.assertEqual(Message.objects.filter(thread=self.thread_v).count(), 1)

    def test_a_verified_account_is_linked_and_covered(self):
        verify(self.stranger)
        self.thread_v.refresh_from_db()
        self.assertEqual(self.thread_v.user_id, self.stranger.pk)
        self.stranger.refresh_from_db()
        self.assertEqual(len(user_services.export_user_data(self.stranger, include_chats=True)["email_threads"]), 1)


class InboundResumeTests(Base):
    """Item 4: a death after the message was stored must not lose its files or its push; Postmark's retry finishes it, once."""

    def setUp(self):
        super().setUp()
        PushSubscription.objects.create(user=self.approver, endpoint="https://push.example/1", p256dh="k", auth="a")
        self.files = [{"Name": "a.png", "Content": b64(PNG), "ContentType": "image/png"}]

    def stored_then_died(self):
        """The first attempt stored the message (incomplete) and died before its files or its task: claimed long ago."""
        payload = payload_for(self.thread, Attachments=self.files)
        message, created = services.record_inbound(payload, self.thread)
        self.assertTrue(created and message.incomplete)
        Message.objects.filter(pk=message.pk).update(claimed_at=timezone.now() - timedelta(minutes=5))
        return payload, message

    def test_retry_after_a_death_stores_the_files_and_pushes_once(self):
        payload, message = self.stored_then_died()
        with mock.patch("whatsapp.push.webpush") as sent:
            self.assertEqual(inbound_post(payload).status_code, 200)
            self.assertEqual(inbound_post(payload).status_code, 200)  # Postmark sends it once more: nothing is doubled
        message.refresh_from_db()
        self.assertFalse(message.incomplete)
        self.assertEqual((Message.objects.count(), Attachment.objects.count(), sent.call_count), (1, 1, 1))

    def test_a_retry_while_another_attempt_is_still_working_is_turned_away(self):
        payload, message = self.stored_then_died()
        Message.objects.filter(pk=message.pk).update(claimed_at=timezone.now())
        self.assertEqual(inbound_post(payload).status_code, 500)
        self.assertEqual(Attachment.objects.count(), 0)

    def test_a_queue_that_is_down_leaves_it_incomplete_and_the_retry_does_not_double_the_files(self):
        payload = payload_for(self.thread, Attachments=self.files)
        with mock.patch("emailchat.services.enqueue", side_effect=OSError("queue down")):
            self.assertEqual(inbound_post(payload).status_code, 500)
        message = Message.objects.get()
        self.assertTrue(message.incomplete)
        self.assertEqual(Attachment.objects.count(), 1)
        Message.objects.filter(pk=message.pk).update(claimed_at=timezone.now() - timedelta(minutes=5))
        with mock.patch("whatsapp.push.webpush") as sent:
            self.assertEqual(inbound_post(payload).status_code, 200)
        self.assertEqual((Attachment.objects.count(), sent.call_count, Message.objects.get().incomplete), (1, 1, False))
        self.assertEqual(len(list(Attachment.objects.values_list("key", flat=True))), 1)


class NewEmailTests(Base):
    """Item 5: a failed first send leaves no empty thread, and an empty thread is never "Open email thread"."""

    def test_failed_send_checks_leave_no_thread(self):
        before = Thread.objects.count()
        response = office(self.approver, "post", "/email/new/", {"to": "new@example.com", "subject": "Hi", "body_html": "<p> </p>", "files": []}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["error"], "empty")
        with mock.patch("emailchat.services.send", side_effect=OSError("storage down")):
            with self.assertRaises(OSError):
                office(self.approver, "post", "/email/new/", {"to": "new@example.com", "subject": "Hi", "body_html": "<p>x</p>"}, HTTP_ACCEPT="application/json")
        self.assertEqual(Thread.objects.count(), before)

    def test_latest_thread_ignores_threads_with_nothing_in_them(self):
        _, empty = services.create_thread("quiet@example.com", "Nothing sent", self.approver)
        self.assertIsNone(services.latest_thread(["quiet@example.com"]))
        services.send(empty, self.approver, "Nothing sent", "<p>Now</p>")
        self.assertEqual(services.latest_thread(["quiet@example.com"]).pk, empty.pk)


class MessageIdTests(Base):
    """Item 6: a Message-ID with a newline must never make a later reply fail with BadHeaderError."""

    def test_stored_clean_and_a_dirty_old_row_is_cleaned_on_read(self):
        dirty = {"Name": "Message-ID", "Value": "<abc\r\n  def@mail.example.com>"}
        inbound_post({**payload_for(self.thread), "Headers": [dirty, {"Name": "References", "Value": "<r1@x>\n <r2@x>"}]})
        stored = Message.objects.get()
        self.assertEqual((stored.rfc_message_id, stored.references), ("<abcdef@mail.example.com>", "<r1@x> <r2@x>"))
        Message.objects.filter(pk=stored.pk).update(rfc_message_id="<abc\r\ndef@mail.example.com>", references="<r1@x>\r\n<r2@x>")  # a row stored before the fix
        response = office(self.approver, "post", f"/email/{self.thread.pk}/send/", {"body_html": "<p>Reply</p>"})
        self.assertEqual(response.status_code, 200)
        out = Message.objects.get(direction="out")
        self.assertEqual(out.status, "sent")
        sent = mail.outbox[-1]
        self.assertEqual(sent.extra_headers["In-Reply-To"], "<abcdef@mail.example.com>")
        self.assertNotIn("\n", sent.extra_headers["References"])


class LostSendTests(Base):
    """Item 8: a send claimed by a worker that died shows "may not have been sent" with Try again, and Try again sends once."""

    def make(self, minutes):
        at = timezone.now() - timedelta(minutes=minutes)
        return Message.objects.create(thread=self.thread, direction="out", subject="x", body_text="x", body_html="<p>x</p>", status="queued", claimed_at=at, updated_at=at)

    def test_claimed_for_a_while_and_still_queued_offers_try_again_with_honest_words(self):
        recent, old = self.make(2), self.make(15)
        self.assertIsNone(services.message_dict(recent)["error"])  # a worker may still be on it
        error = services.message_dict(old)["error"]
        self.assertIn("may not have been sent", error["reason"])
        self.assertTrue(error["can_retry"])

    def test_try_again_sends_once_even_when_clicked_twice(self):
        old = self.make(15)
        first = office(self.approver, "post", f"/email/{self.thread.pk}/retry/{old.pk}/")
        second = office(self.approver, "post", f"/email/{self.thread.pk}/retry/{old.pk}/")
        self.assertEqual((first.status_code, second.status_code), (200, 409))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Message.objects.get(pk=old.pk).status, "sent")


class RichTextCopyTests(Base):
    """Item 14: the plain copy keeps numbers, mailto addresses and quote marks."""

    def test_plain_copy(self):
        text = richtext.html_to_text('<ol><li>one</li><li>two</li></ol><p><a href="mailto:a@b.example">email me</a></p><blockquote><p>q1</p><p>q2</p></blockquote>')
        self.assertIn("1. one\n2. two", text)
        self.assertIn("email me (a@b.example)", text)
        self.assertIn("> q1", text)
        self.assertIn("> q2", text)


class SmallFixTests(Base):
    def test_reply_subject_stays_within_the_column(self):
        Message.objects.create(thread=self.thread, direction="in", subject="x" * 300, body_text="x", status="received")
        self.assertLessEqual(len(services.reply_subject(self.thread)), 300)

    def test_blank_from_counts_as_a_different_sender_but_not_on_our_own_mail(self):
        mine = Message.objects.create(thread=self.thread, direction="out", subject="x", body_text="x", status="sent")
        blank = Message.objects.create(thread=self.thread, direction="in", subject="x", body_text="x", status="received", from_address="")
        self.assertEqual((services.message_dict(mine)["from_other"], services.message_dict(blank)["from_other"]), (False, True))

    def test_export_has_the_whole_text_the_sender_name_and_a_file_listing(self):
        message = Message.objects.create(thread=self.thread, direction="in", subject="x", body_text="new", body_full="new\n> old", from_name="Him", from_address="him@example.com", status="received")
        Attachment.objects.create(message=message, key=default_storage.save("emailchat/t/x", ContentFile(b"%PDF-1")), filename="a.pdf", content_type="application/octet-stream", declared_type="application/pdf", size=6)
        row = services.export_for([self.thread])[0]["messages"][0]
        self.assertEqual((row["full_text"], row["from_name"], row["files"]), ("new\n> old", "Him", [{"name": "a.pdf", "type": "application/pdf", "size": 6}]))
        default_storage.delete(Attachment.objects.get().key)

    def test_admin_delete_of_a_message_removes_its_files_from_storage(self):
        from django.contrib import admin as django_admin

        from emailchat.admin import MessageAdmin

        message = Message.objects.create(thread=self.thread, direction="in", subject="x", body_text="x", status="received")
        key = default_storage.save("emailchat/t/y", ContentFile(b"data"))
        Attachment.objects.create(message=message, key=key, filename="y", content_type="application/octet-stream")
        MessageAdmin(Message, django_admin.site).delete_model(None, message)
        self.assertFalse(default_storage.exists(key))
        self.assertEqual(Attachment.objects.count(), 0)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "emailchat-people-limit"}})
    def test_people_search_is_rate_limited(self):
        cache.clear()
        statuses = {office(self.reader, "get", "/email/people/?q=zz").status_code for _ in range(125)}
        self.assertIn(429, statuses)
