"""Final review fixes for the email chat. Mocked: nothing real is sent, the queue runs inline."""
import os
import time

from django.urls import reverse

from emailchat import services
from emailchat.models import Message, Thread
from emailchat.tests.test_emailchat import Base, inbound_post, office, payload_for
from office.tests.test_leads import lead
from users import services as user_services
from users.tests.test_register import cleaned


def _fill(unit, size=1_000_000):
    return (unit * (size // len(unit) + 1))[:size]


SHAPES = {
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
            if message.body_html == "":  # refused: the text is kept and the note says so
                self.assertEqual(message.note, services.TOO_COMPLEX, name)
        if os.environ.get("SHOW_TIMES"):
            for name, took in sorted(times.items(), key=lambda item: -item[1]):
                print(f"{took:6.2f}s  {name}")
        self.assertLess(max(times.values()), 2.5, times)

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
