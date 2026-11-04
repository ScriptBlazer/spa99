"""The link rule of common.ownership (who may set a chat's links), through the real views. Mocked: nothing is sent, the queue runs inline.
Public forms (journey gate, Register, Gold apply) never move a chat; a GET never writes; staff link, start and delete by POST."""
import json

from django.contrib.messages import get_messages
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client
from django.utils import timezone
from django_q.models import Task

from common import levels
from common.tests.test_ownership import Base, VICTIM
from emailchat.models import Thread
from emailchat.tests.test_emailchat import office
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from mailings.models import ContactList, ContactListMember
from office.tests.test_leads import lead, verify
from outreach import services as outreach
from outreach.models import ArchivedLead, OutreachEntry, StickyNote
from plans.tests.helpers import make_team_member
from system.models import SystemEvent
from users.models import User
from whatsapp.models import Contact, Message

PHONE = "+447400123790"


class LinkBase(Base):
    def setUp(self):
        super().setUp()
        self.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        self.reader = make_team_member("reader@example.test", levels.OFFICE)

    def chat(self, phone=PHONE, words="private words", **fields):
        contact = Contact.objects.create(phone=phone, **fields)
        Message.objects.create(contact=contact, direction="in", kind="text", body=words, status="received")
        return contact

    def victim_lead(self, mobile="07400 123790"):
        session = lead(VICTIM)
        outreach.set_lead_contact(VICTIM, self.approver, first_name="Leo", mobile=mobile)
        return session

    def gate(self, email, mobile, first_name="Stranger"):
        client = Client(HTTP_HOST="localhost")
        client.get("/journey/state/")
        response = client.post("/journey/lead/", json.dumps({"first_name": first_name, "email": email, "mobile_country": "GB", "mobile": mobile, "consent": True}), content_type="application/json")
        self.assertEqual(response.status_code, 200, response.content)
        return JourneySession.objects.filter(lead_email=email).latest("created_at")

    def state(self, chat):
        chat.refresh_from_db()
        return chat.user_id, chat.lead_email, chat.application_id, chat.name


class PublicFormsNeverMoveAChatTests(LinkBase):
    def test_the_journey_gate_with_the_victims_number_leaves_his_chat_on_his_lead(self):
        victim = self.victim_lead()
        chat = self.chat(lead_email=VICTIM, name="Leo")
        stranger = self.gate("stranger@example.com", "07400 123790")  # the victim's number, typed by a stranger
        self.assertEqual(self.state(chat), (None, VICTIM, None, "Leo"))
        self.assertIn("private words", office(self.admin, "get", f"/leads/{victim.pk}/export/").content.decode())  # still on the victim's export
        self.assertNotIn("private words", office(self.admin, "get", f"/leads/{stranger.pk}/export/").content.decode())
        office(self.admin, "post", f"/leads/{stranger.pk}/delete/")  # staff delete the stranger's lead
        self.assertTrue(Contact.objects.filter(pk=chat.pk).exists())
        member = self.register("stranger@example.com", mobile="07400 123790")  # and Register with the number too
        verify(member)
        self.assertEqual(self.state(chat), (None, VICTIM, None, "Leo"))
        self.assertNotIn("private words", self.export(member))

    def test_gold_apply_with_the_members_number_never_reaches_his_chat(self):
        member = self.register("acc@example.com", mobile="07400 123790")
        verify(member)
        owned = self.chat(user=member)
        free = self.chat("+447400123791", "free words")
        application = self.apply(self.public_client(), email="stranger@example.com", mobile=PHONE)
        self.apply(self.public_client(), email="other@example.com", mobile="+447400123791")
        self.assertEqual(self.state(owned)[0:3], (member.pk, "", None))
        self.assertEqual(self.state(free)[0:3], (None, "", None))
        self.assertEqual(list(whatsapp_contacts(None, {"stranger@example.com"}, application)), [])  # staff export and delete by the stranger's application find nothing
        self.assertIn("private words", self.export(member))
        office(self.admin, "post", f"/gold/{application.pk}/delete/")
        self.assertTrue(Contact.objects.filter(pk=owned.pk).exists())
        self.assertTrue(Contact.objects.filter(pk=free.pk).exists())


def whatsapp_contacts(user, addresses, application):
    from whatsapp import services

    return services.contacts_for_person(user, addresses, application)


class NoGetWritesTests(LinkBase):
    def test_opening_a_chat_or_a_start_link_writes_nothing_for_any_page(self):
        stranger = self.register("stranger@example.com", mobile="07400 123790")  # unverified, holding the victim's number
        chat = self.chat()
        session = self.victim_lead("07400 123888")  # a lead with a number and no chat yet
        application = self.apply(self.public_client(), email="gold@example.com", mobile="+447400123889")
        before = (Contact.objects.count(), Thread.objects.count())
        paths = [f"/people/{stranger.pk}/whatsapp/", f"/leads/{session.pk}/whatsapp/", f"/gold/{application.pk}/whatsapp/", f"/gold/{application.pk}/?do=respond",
                 f"/whatsapp/{chat.pk}/?from=person:{stranger.pk}", f"/people/{stranger.pk}/email-chat/", f"/leads/{session.pk}/email-chat/", f"/gold/{application.pk}/email-chat/",
                 f"/email/new/?person=lead:{session.pk}", f"/people/{stranger.pk}/", f"/leads/{session.pk}/", f"/gold/{application.pk}/"]
        for path in paths:
            self.assertIn(office(self.admin, "get", path, follow=True).status_code, (200,), path)
        self.assertEqual((Contact.objects.count(), Thread.objects.count()), before)
        self.assertEqual(self.state(chat), (None, "", None, ""))

    def test_the_thread_offers_the_link_after_the_chat_is_seen_and_only_to_an_editor(self):
        member = self.register("acc@example.com", mobile="07400 123790")
        verify(member)
        chat = self.chat()
        url = f"/whatsapp/{chat.pk}/?from=person:{member.pk}"
        page = office(self.approver, "get", url)
        self.assertContains(page, f"This number isn't linked to {member.get_full_name() or member.email}. Link it?")
        self.assertContains(page, chat.phone)  # the number is on the page being shown with the line
        self.assertNotContains(office(self.reader, "get", url), "Link it?")
        self.assertNotContains(office(self.approver, "get", f"/whatsapp/{chat.pk}/"), "Link it?")  # not reached from a page
        self.assertNotContains(office(self.approver, "get", f"/whatsapp/{chat.pk}/?from=lead:{lead('hugo@example.com').pk}"), "Link it?")  # not his number
        self.assertEqual(self.state(chat)[0:3], (None, "", None))


class StartAndLinkArePostsByAnEditorTests(LinkBase):
    def test_who_may_start_and_link_and_what_a_link_may_take(self):
        member = self.register("acc@example.com", mobile="07400 123790")
        verify(member)
        chat = self.chat()
        for who in (self.reader,):
            self.assertEqual(office(who, "post", f"/people/{member.pk}/whatsapp/").status_code, 403)
            self.assertEqual(office(who, "post", f"/whatsapp/{chat.pk}/link/", {"from": f"person:{member.pk}"}).status_code, 403)
        client = Client(HTTP_HOST="office.localhost", enforce_csrf_checks=True)
        client.force_login(self.approver)
        self.assertEqual(client.post(f"/people/{member.pk}/whatsapp/").status_code, 403)  # no CSRF token: refused
        self.assertEqual(client.post(f"/whatsapp/{chat.pk}/link/", {"from": f"person:{member.pk}"}).status_code, 403)
        other = lead("other@example.com")
        office(self.approver, "post", f"/whatsapp/{chat.pk}/link/", {"from": f"lead:{other.pk}"})  # not his number
        office(self.approver, "post", f"/whatsapp/{chat.pk}/link/", {"from": "nonsense"})
        self.assertEqual(self.state(chat)[0:3], (None, "", None))
        office(self.approver, "post", f"/whatsapp/{chat.pk}/link/", {"from": f"person:{member.pk}"})
        self.assertEqual(self.state(chat)[0], member.pk)
        held = self.chat("+447400123999", lead_email=VICTIM)
        session = lead("third@example.com")
        outreach.set_lead_contact("third@example.com", self.approver, mobile="07400 123999")
        office(self.approver, "post", f"/whatsapp/{held.pk}/link/", {"from": f"lead:{session.pk}"})  # a chat somebody holds is never taken
        self.assertEqual(self.state(held)[0:3], (None, VICTIM, None))

    def test_start_makes_a_new_chat_with_the_pages_links_and_opens_an_existing_one_untouched(self):
        session = self.victim_lead()
        office(self.approver, "post", f"/leads/{session.pk}/whatsapp/")
        chat = Contact.objects.get(phone=PHONE)
        self.assertEqual(self.state(chat), (None, VICTIM, None, "Leo"))
        other = self.chat("+447400123500")
        gold = self.apply(self.public_client(), email="gold@example.com", mobile="+447400123500")
        office(self.approver, "post", f"/gold/{gold.pk}/whatsapp/")  # a chat already there: opened, not linked
        self.assertEqual(self.state(other)[0:3], (None, "", None))


class GoldDeleteExclusionsTests(LinkBase):
    def test_gold_delete_spares_a_verified_members_chat_and_a_chat_tied_only_through_a_number(self):
        member = self.register("acc@example.com", mobile="07400 123790")
        verify(member)
        application = self.apply(self.public_client(), email="acc@example.com", mobile="+447400555010")
        GoldApplication.objects.filter(pk=application.pk).update(user=None)
        held = self.chat("+447400555010", user=member, application=application)
        by_address = self.chat("+447400555011", application=application, lead_email="acc@example.com")  # his verified address
        junk = self.apply(self.public_client(), email="junk@example.com", mobile="+447400555012")
        tied = self.chat("+447400555012", application=junk)  # ownerless, no lead address: tied only through a typed number
        office(self.admin, "post", f"/gold/{application.pk}/delete/")
        office(self.admin, "post", f"/gold/{junk.pk}/delete/")
        for chat in (held, by_address, tied):
            self.assertTrue(Contact.objects.filter(pk=chat.pk).exists())


class UnclaimedChatTests(LinkBase):
    def test_person_delete_and_export_name_the_chat_and_staff_can_delete_it(self):
        member = self.register("acc@example.com", mobile="07400 123790")
        verify(member)
        chat = self.chat()
        key = default_storage.save("whatsapp/x/p.png", ContentFile(b"png"))
        Message.objects.filter(contact=chat).update(media_key=key)
        message = Message.objects.filter(contact=chat).first()
        Task.objects.create(id="a" * 32, name="queued", func="whatsapp.tasks.send_message", args=(message.pk,), started=timezone.now(), stopped=timezone.now(), success=True)
        page = office(self.admin, "get", f"/people/{member.pk}/")
        self.assertContains(page, "data-unclaimed-chats")
        exported = json.loads(office(self.admin, "get", f"/people/{member.pk}/export/").content)
        self.assertEqual((exported["whatsapp"], exported["whatsapp_chats_not_included"]), ([], [{"phone": PHONE, "name": PHONE}]))
        deleted = office(self.admin, "post", f"/people/{member.pk}/delete/")
        self.assertIn(PHONE, " ".join(str(m) for m in get_messages(deleted.wsgi_request)))
        self.assertTrue(Contact.objects.filter(pk=chat.pk).exists())  # person delete does not reach it: nothing links it to him
        for who in (self.reader, self.approver):
            self.assertEqual(office(who, "post", f"/whatsapp/{chat.pk}/delete/", {"confirm": "1"}).status_code, 403)
        office(self.admin, "post", f"/whatsapp/{chat.pk}/delete/")  # no confirmation: nothing
        self.assertTrue(Contact.objects.filter(pk=chat.pk).exists())
        self.assertEqual(office(self.admin, "post", f"/whatsapp/{chat.pk}/delete/", {"confirm": "1"}).status_code, 302)
        self.assertFalse(Contact.objects.filter(pk=chat.pk).exists())
        self.assertEqual(Message.objects.filter(contact_id=chat.pk).count(), 0)
        self.assertFalse(default_storage.exists(key))
        self.assertFalse(Task.objects.filter(func="whatsapp.tasks.send_message").exists())
        event = SystemEvent.objects.get(kind=SystemEvent.CHAT_DELETED)
        self.assertEqual((event.user_label, event.detail["whatsapp_messages"]), ("admin@example.test", 1))
        self.assertNotIn("private words", f"{event.sentence} {event.detail}")  # counts only, never message text


class UnverifiedStrangerErasureTests(LinkBase):
    def victims_data(self):
        StickyNote.objects.create(email=VICTIM, text="victim note")
        OutreachEntry.objects.create(lead_email=VICTIM, reason="victim list")
        ArchivedLead.objects.create(email=VICTIM, reason="victim archive")
        ContactListMember.objects.create(list=ContactList.objects.create(name="Victim club"), email=VICTIM, name="Victor Victim")

    def survives(self):
        return (StickyNote.objects.filter(email=VICTIM).exists(), OutreachEntry.objects.filter(lead_email=VICTIM).exists(), ArchivedLead.objects.filter(email=VICTIM).exists(),
                ContactListMember.objects.filter(email=VICTIM).exists())

    def test_an_unverified_account_with_the_victims_email_neither_erases_nor_exports_his_data(self):
        self.victims_data()
        stranger = self.register(VICTIM)
        stranger.set_password("a-Long-pass-123")
        stranger.save()
        client = Client(HTTP_HOST="localhost")
        client.force_login(stranger)
        exported = client.get("/account/export/").content.decode()
        self.assertNotIn("Victim club", exported)
        self.assertNotIn("Victor Victim", exported)
        client.post("/account/delete/", {"password": "a-Long-pass-123"})
        self.assertFalse(User.objects.filter(pk=stranger.pk).exists())
        self.assertEqual(self.survives(), (True, True, True, True))

    def test_a_verified_members_own_data_still_goes(self):
        self.victims_data()
        member = self.register(VICTIM)
        verify(member)
        member.refresh_from_db()
        member.set_password("a-Long-pass-123")
        member.save()
        client = Client(HTTP_HOST="localhost")
        client.force_login(member)
        self.assertIn("Victim club", client.get("/account/export/").content.decode())
        client.post("/account/delete/", {"password": "a-Long-pass-123"})
        self.assertEqual(self.survives(), (False, False, False, False))
