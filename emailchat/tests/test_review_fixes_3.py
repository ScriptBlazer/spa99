"""Final review fixes for the email chat. Mocked: nothing real is sent, the queue runs inline."""
import os
import time
from datetime import timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from common import richtext
from emailchat import services
from emailchat.models import Message, Thread
from emailchat.tests.test_emailchat import Base, inbound_post, office, payload_for
from office.tests.test_leads import lead
from users import services as user_services
from users.tests.test_register import cleaned


def _fill(unit, size=1_000_000):
    return (unit * (size // len(unit) + 1))[:size]


def _attributes(count, template="a%d", tag="div"):
    return f"<{tag} " + " ".join(template % i for i in range(count)) + ">"


CAP = richtext.MAX_HTML
SHAPES = {
    # attribute floods: nh3 is quadratic in the different attributes on one tag, and a quoted `>` hides them from any count of `<` or `>`
    "1 MB of attributes": _attributes(200_000), "1 MB of quoted > attributes": _attributes(110_000, 'a%d=">"'), "1 MB of attributes, never closed": _attributes(200_000)[:-1],
    "attributes just under the size cap": _attributes((CAP - 12) // 7), "quoted > attributes just under the cap": _attributes((CAP - 12) // 12, 'a%d=">"'),
    "x-tag attributes just under the cap": _attributes((CAP - 12) // 7, tag="x-a"), "many tags with 5000 attributes": "".join(_attributes(5_000) for _ in range(CAP // 40_000)),
    "just under the cap, many tags": _fill("<span><div></span></div>", CAP), "just under the cap, a newsletter": _fill("<table><tr><td><div><p>x</p></div></td></tr></table>", CAP),
    "div/": _fill("<div/>"), "div <>": _fill("<div <>"), 'div a="<"': _fill('<div a="<">'), "x-a x-b": _fill("<x-a></x-b>"),
    "span div misnest": _fill("<span><div></span></div>"), "deep": "<div>" * 200_000, "wide": _fill("<p>a</p>"), "comments": _fill("<!-- a -->"),
    "entities": _fill("&amp;&lt;&#x41;"), "unclosed": _fill("<a"), "unclosed with a late >": _fill("<a<") + ">",
    "misnest at the budget": "<span><div></span></div>" * 12_000 + "x" * 700_000,
}


class HostileHtmlBudgetTests(Base):
    def test_every_one_megabyte_shape_goes_through_the_webhook_quickly_and_keeps_its_text(self):
        times = {}
        for number, (name, html) in enumerate(SHAPES.items()):
            payload = {**payload_for(self.thread, text="", message_id=f"pm-shape-{number}"), "HtmlBody": html}
            started = time.monotonic()
            self.assertEqual(inbound_post(payload).status_code, 200, name)
            times[name] = time.monotonic() - started
            message = Message.objects.get(provider_id=f"pm-shape-{number}")
            if message.body_html == "" and richtext.too_complex(html):  # refused: the text is kept and the note says so
                self.assertEqual(message.note, services.TOO_COMPLEX, name)
        if os.environ.get("SHOW_TIMES"):
            for name, took in sorted(times.items(), key=lambda item: -item[1]):
                print(f"{took:6.2f}s  {name}")
        self.assertLess(max(times.values()), 2.5, times)

    def test_the_size_cap_refuses_big_html_and_a_normal_newsletter_still_passes(self):
        newsletter = "<table><tr><td><div><p>x</p></div></td></tr></table>" * 1_800  # 18,000 `<`, about 100 KB
        self.assertEqual(newsletter.count("<"), 18_000)
        self.assertFalse(richtext.too_complex(newsletter))
        self.assertNotEqual(richtext.clean_incoming(newsletter), "")
        self.assertTrue(richtext.too_complex("x" * (richtext.MAX_HTML + 1)))
        self.assertFalse(richtext.too_complex("x" * richtext.MAX_HTML))
        payload = {**payload_for(self.thread, text="", message_id="pm-big"), "HtmlBody": "<p>kept words</p>" + "x" * richtext.MAX_HTML}
        self.assertEqual(inbound_post(payload).status_code, 200)
        message = Message.objects.get(provider_id="pm-big")
        self.assertEqual((message.body_html, message.note), ("", services.TOO_COMPLEX))
        self.assertIn("kept words", message.body_text)

    def test_the_budget_refuses_by_tag_count_and_lets_real_mail_through(self):
        from common import richtext

        self.assertTrue(richtext.too_complex("<div/>" * 500))  # a slash does not close anything
        self.assertTrue(richtext.too_complex("<span><div></span></div>" * 13_000))  # shallow by the depth count, over the budget
        self.assertFalse(richtext.too_complex("<table><tr><td><div><p>x</p></div></td></tr></table>" * 2_000))  # a long newsletter


class StaffStartedEmailOnUnverifiedPersonTests(Base):
    def test_the_thread_is_linked_to_the_person_staff_chose_and_the_stranger_rule_still_holds(self):
        lead("victim@example.com")
        _, leads_thread = services.create_thread("victim@example.com", "For the lead", self.approver)
        stranger = user_services.register_interest(cleaned(email="victim@example.com")).user
        created = office(self.approver, "post", "/email/new/", {"person": f"person:{stranger.pk}", "subject": "From his page", "body_html": "<p>Hello</p>"}, HTTP_ACCEPT="application/json")
        self.assertEqual(created.status_code, 200)
        thread = Thread.objects.get(subject="From his page")
        self.assertEqual(thread.user_id, stranger.pk)
        chat = office(self.reader, "get", f"/people/{stranger.pk}/").context["email_chat"]
        self.assertEqual((chat["state"], chat["thread_count"]), ("open", 1))  # his own thread, not the lead's on the same address
        found = services.threads_for_person(stranger, {"victim@example.com"})
        self.assertEqual(list(found), [thread])
        self.assertEqual(services.erase_person(stranger, {"victim@example.com"})["email_threads"], 1)
        self.assertTrue(Thread.objects.filter(pk=leads_thread.pk).exists())  # the lead's thread was never his to erase
        self.assertFalse(Thread.objects.filter(pk=thread.pk).exists())


class UnverifiedAccountWhatsAppTests(Base):
    def test_an_unverified_account_does_not_pick_up_a_gold_applicants_chat_on_its_address(self):
        from gold import services as gold_services
        from gold.tests.test_gold import application_data
        from office import profile
        from whatsapp import services as whatsapp
        from whatsapp.models import Contact

        application, _ = gold_services.submit_application(application_data(email="victim@example.com"))
        chat = Contact.objects.create(phone="+447700900123", application=application)
        stranger = user_services.register_interest(cleaned(email="victim@example.com")).user
        self.assertEqual(profile._contacts(user=stranger), [])  # the profile timeline
        self.assertEqual(list(whatsapp.contacts_for_person(stranger, {"victim@example.com"})), [])  # and the export and erase path, with the addresses passed anyway
        self.assertEqual(list(whatsapp.contacts_for_person(None, {"victim@example.com"})), [chat])  # the lead or applicant's own view still finds it


class InboundNotesAndGiveUpTests(Base):
    def stuck_inbound(self, message_id="pm-x", files=True, **extra):
        attachments = [{"Name": "a.png", "Content": "AAAA", "ContentType": "image/png"}] if files else []
        payload = payload_for(self.thread, Attachments=attachments, message_id=message_id)
        with mock.patch("emailchat.services.enqueue", side_effect=RuntimeError("queue")):
            inbound_post(payload)
        message = Message.objects.get(provider_id=message_id)
        old = timezone.now() - timedelta(days=2)
        Message.objects.filter(pk=message.pk).update(created_at=old, **{"claimed_at": old, **extra})
        return payload, message

    def test_a_retry_after_a_failed_queue_rebuilds_the_note_instead_of_doubling_it(self):
        too_big = [{"Name": "huge.bin", "Content": "A" * 400, "ContentType": "application/octet-stream"}]
        payload = payload_for(self.thread, Attachments=too_big, message_id="pm-note")
        with mock.patch("emailchat.services.enqueue", side_effect=RuntimeError("queue")), self.settings(EMAILCHAT_MAX_ATTACHMENT_BYTES=100):
            inbound_post(payload)
            message = Message.objects.get(provider_id="pm-note")
            first = message.note
            self.assertIn("too big", first)
            Message.objects.filter(pk=message.pk).update(claimed_at=timezone.now() - timedelta(minutes=3))
            inbound_post(payload)  # Postmark's retry: the queue fails again
        message.refresh_from_db()
        self.assertEqual(message.note, first)

    def test_give_up_leaves_a_live_claim_uses_fitting_words_and_pushes_once(self):
        _, claimed = self.stuck_inbound("pm-live", claimed_at=timezone.now())
        self.assertEqual(services.give_up_incomplete(), 0)  # a worker is on it
        _, bare = self.stuck_inbound("pm-bare", files=False)
        with mock.patch("whatsapp.push.notify_payload", return_value=1) as push:
            self.assertEqual(services.give_up_incomplete(), 1)
            self.assertEqual(services.give_up_incomplete(), 0)
        bare.refresh_from_db()
        claimed.refresh_from_db()
        self.assertTrue(claimed.incomplete)
        self.assertFalse(bare.incomplete)
        self.assertEqual(bare.note, services.GAVE_UP_NO_FILES)
        self.assertNotIn("Some files", bare.note)
        self.assertIsNotNone(bare.notified_at)
        self.assertEqual(push.call_count, 1)


class FeedbackAndCursorTests(Base):
    def test_a_blank_recipient_does_not_bounce_a_row_with_a_blank_to_address(self):
        message = Message.objects.create(thread=self.thread, direction="out", subject="s", body_text="b", status="sent", to_address="")
        for record in ({"RecordType": "Bounce", "Type": "HardBounce", "Recipient": "", "Metadata": {"chat": str(message.pk)}},
                       {"RecordType": "Bounce", "Type": "HardBounce", "Email": "  ", "Metadata": {"chat": str(message.pk)}}):
            self.assertFalse(services.apply_feedback(record))
        message.refresh_from_db()
        self.assertEqual(message.status, "sent")

    def test_an_absurd_cursor_is_a_bad_cursor_not_a_500(self):
        from whatsapp.models import Contact

        contact = Contact.objects.create(phone="+447700900555")
        for url in (f"/email/{self.thread.pk}/poll/", f"/whatsapp/{contact.pk}/poll/"):
            for since in ("0001-01-01", "0001-01-01T00:00:00+00:00", "9999-12-31T23:59:59+00:00", "nonsense"):
                response = office(self.reader, "get", url, {"after": 0, "since": since})
                self.assertEqual(response.status_code, 200, (url, since))
