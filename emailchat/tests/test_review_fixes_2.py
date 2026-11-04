"""Review round 2 of the email chat. Mocked: nothing real is sent, the queue runs inline, files are in memory."""
import time
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib import admin as django_admin
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from emailchat import services
from emailchat.admin import AttachmentAdmin
from emailchat.models import Attachment, Message, Thread
from emailchat.tests.test_emailchat import PNG, Base, b64, inbound_post, office, payload_for
from gold import services as gold_services
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from office.tests.test_leads import lead, verify
from outreach import services as outreach
from users import services as user_services
from users.tests.test_register import cleaned


class HostileInboundTests(Base):
    def test_deeply_nested_html_only_mail_is_stored_quickly_as_text(self):
        payload = {**payload_for(self.thread, text="", message_id="pm-deep"), "HtmlBody": "<blockquote>" * 2000 + "the real words"}
        start = time.monotonic()
        self.assertEqual(inbound_post(payload).status_code, 200)
        self.assertLess(time.monotonic() - start, 10)  # it took 32 seconds before, and Postmark retries
        message = Message.objects.get(provider_id="pm-deep")
        self.assertEqual((message.body_html, message.incomplete), ("", False))
        self.assertIn("the real words", message.body_text)
        self.assertIn("too complicated", message.note)


class StrangerTests(Base):
    """An unverified account on a lead's address must not see the lead's thread."""

    def test_unverified_person_page_shows_no_thread_of_the_lead(self):
        lead("victim@example.com")
        _, thread = services.create_thread("victim@example.com", "For Victim", self.approver)
        services.send(thread, self.approver, "For Victim", "<p>Private</p>")
        stranger = user_services.register_interest(cleaned(email="victim@example.com")).user
        page = office(self.reader, "get", f"/people/{stranger.pk}/")
        chat = page.context["email_chat"]
        self.assertEqual((chat["has_thread"], chat["thread_count"], chat["state"]), (False, 0, "start"))
        self.assertNotIn("For Victim", page.content.decode())
        button = office(self.reader, "get", reverse("office_person_email_chat", args=[stranger.pk], urlconf="config.urls_office"))
        self.assertEqual(button.status_code, 302)
        self.assertNotIn(str(thread.pk), button["Location"])  # it starts a new email, it does not open his thread
        self.assertEqual(services.threads_for_person(stranger, {"victim@example.com"}).count(), 0)  # nor in his staff export or erasure
        verify(stranger)
        self.assertEqual(office(self.reader, "get", f"/people/{stranger.pk}/").context["email_chat"]["state"], "open")  # once verified it is his


class MoveAddressTests(Base):
    def test_lead_threads_move_but_a_gold_linked_thread_account_or_application_only_threads_stay(self):
        application, _ = gold_services.submit_application(application_data(email="old@example.com"))
        _, gold_thread = services.create_thread("old@example.com", "Gold chat", self.approver)
        self.assertEqual(gold_thread.application_id, application.pk)
        Thread.objects.filter(pk=gold_thread.pk).update(lead_email="old@example.com")
        application_only = Thread.objects.create(email="old@example.com", subject="Application only", application=application)
        plain = Thread.objects.create(email="old@example.com", subject="Lead only", lead_email="old@example.com")
        owned = Thread.objects.create(email="x@example.com", subject="Owned", user=self.approver, lead_email="old@example.com")
        services.move_address("old@example.com", "new@example.com")
        for row in (gold_thread, application_only, plain, owned):
            row.refresh_from_db()
        self.assertEqual((gold_thread.email, gold_thread.lead_email), ("old@example.com", "old@example.com"))  # stays: the application is unchanged, replies must not go to another address
        self.assertEqual((application_only.email, application_only.lead_email), ("old@example.com", ""))
        self.assertEqual((plain.email, plain.lead_email), ("new@example.com", "new@example.com"))
        self.assertEqual(owned.lead_email, "old@example.com")
        self.assertNotIn(gold_thread, services.threads_for(["new@example.com"]))
        self.assertIn(gold_thread, services.threads_for(["old@example.com"]))  # the applicant's address still finds it


class DeliveryProofTests(Base):
    def queued(self, minutes=11):
        then = timezone.now() - timedelta(minutes=minutes)
        return Message.objects.create(thread=self.thread, direction="out", subject="s", body_text="b", body_html="<p>b</p>", status="queued", claimed_at=then, updated_at=then)

    def test_a_delivery_webhook_corrects_a_claimed_queued_message_so_try_again_cannot_double_send(self):
        message = self.queued()
        self.assertTrue(services.can_retry(message))
        record = {"RecordType": "Delivery", "Recipient": self.thread.email, "MessageID": "pmid", "Metadata": {"chat": str(message.pk)}}
        self.assertTrue(services.apply_feedback(record))
        message.refresh_from_db()
        self.assertEqual(message.status, "delivered")
        self.assertIsNotNone(message.sent_at)
        sent = len(mail.outbox)
        self.assertFalse(services.can_retry(message))
        self.assertEqual(services.retry(message)[0], services.NOT_RETRYABLE)
        self.assertEqual(len(mail.outbox), sent)


class StuckReachesAnOpenPageTests(Base):
    def poll(self, after, since, later):
        with mock.patch("django.utils.timezone.now", return_value=later):
            return office(self.reader, "get", f"/email/{self.thread.pk}/poll/", {"after": after, "since": since.isoformat()}).json()

    def test_a_message_that_turns_stuck_is_sent_once_and_never_again(self):
        message = Message.objects.create(thread=self.thread, direction="out", subject="s", body_text="b", body_html="<p>b</p>", status="queued", claimed_at=timezone.now())
        start = timezone.now()
        first = self.poll(message.pk, start, start + timedelta(minutes=11))
        self.assertEqual([u["id"] for u in first["updates"]], [message.pk])
        self.assertIn("may not have been sent", first["updates"][0]["error"]["reason"])
        again = self.poll(message.pk, timezone.datetime.fromisoformat(first["cursor"]), start + timedelta(minutes=12))
        self.assertEqual(again["updates"], [])  # not reread on every poll: the cost does not grow


class IncompleteTests(Base):
    def half_stored(self, message_id="pm-half"):
        two = [{"Name": "a.png", "Content": b64(PNG), "ContentType": "image/png"}, {"Name": "b.png", "Content": b64(PNG), "ContentType": "image/png"}]
        payload = payload_for(self.thread, Attachments=two, message_id=message_id)
        with mock.patch("emailchat.services.enqueue", side_effect=RuntimeError("queue")):
            inbound_post(payload)
        return payload, Message.objects.get(provider_id=message_id)

    def test_incomplete_is_marked_and_files_landing_bump_updated_at(self):
        payload, message = self.half_stored()
        self.assertTrue(message.incomplete)
        self.assertTrue(services.message_dict(message)["incomplete"])
        before = message.updated_at
        Message.objects.filter(pk=message.pk).update(claimed_at=timezone.now() - timedelta(minutes=3))
        self.assertEqual(inbound_post(payload).status_code, 200)  # Postmark's retry finishes it
        message.refresh_from_db()
        self.assertFalse(message.incomplete)
        self.assertGreater(message.updated_at, before)
        self.assertFalse(services.message_dict(message)["incomplete"])

    def test_the_sweep_gives_up_after_a_day_and_dry_run_changes_nothing(self):
        _, message = self.half_stored()
        self.assertEqual(services.give_up_incomplete(), 0)  # not yet a day
        Message.objects.filter(pk=message.pk).update(created_at=timezone.now() - timedelta(days=2), claimed_at=timezone.now() - timedelta(days=2))
        out = StringIO()
        call_command("give_up_incomplete_emails", "--dry-run", stdout=out)
        self.assertIn("Would give up on 1", out.getvalue())
        message.refresh_from_db()
        self.assertTrue(message.incomplete)
        call_command("give_up_incomplete_emails", stdout=out)
        message.refresh_from_db()
        self.assertFalse(message.incomplete)
        self.assertIn("could not be saved", services.message_dict(message)["note"])

    def test_erasure_still_covers_an_incomplete_message_and_its_files(self):
        message, _ = services.record_inbound(payload_for(self.thread, message_id="pm-erase"), self.thread)
        key = default_storage.save("emailchat/x/y", ContentFile(b"1"))
        Attachment.objects.create(message=message, key=key, filename="y", size=1)
        services.erase_threads([self.thread])
        self.assertFalse(Message.objects.filter(pk=message.pk).exists())
        self.assertFalse(default_storage.exists(key))


class SmallFixTests(Base):
    def test_to_address_is_kept_when_the_lead_address_is_corrected(self):
        session = lead("old@example.com")
        _, thread = services.create_thread("old@example.com", "Hello", self.approver)
        _, message = services.send(thread, self.approver, "Hello", "<p>Hi</p>")
        outreach.correct_lead_email("old@example.com", "new@example.com", self.approver)
        message.refresh_from_db()
        thread.refresh_from_db()
        self.assertEqual((thread.email, message.to_address, services.message_dict(message)["to_address"]), ("new@example.com", "old@example.com", "old@example.com"))
        self.assertTrue(services.apply_feedback({"RecordType": "Bounce", "Type": "HardBounce", "Email": "old@example.com", "Metadata": {"chat": str(message.pk)}}))  # a bounce names the old address
        self.assertEqual(JourneySession.objects.get(pk=session.pk).lead_email, "new@example.com")

    def test_admin_delete_of_the_last_file_clears_the_thread_paperclip(self):
        message = Message.objects.create(thread=self.thread, direction="in", status="received", body_text="b")
        key = default_storage.save("emailchat/x/1", ContentFile(b"1"))
        item = Attachment.objects.create(message=message, key=key, filename="1", size=1)
        Thread.objects.filter(pk=self.thread.pk).update(has_attachment=True)
        AttachmentAdmin(Attachment, django_admin.site).delete_queryset(None, Attachment.objects.filter(pk=item.pk))
        self.thread.refresh_from_db()
        self.assertFalse(self.thread.has_attachment)
