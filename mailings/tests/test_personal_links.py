"""The email builder's personal-link button: validation, {first_name}, a send that gives each person their own tracked link, the skip rules,
refusal for account groups, the full path to registered, and preview/test with sample values. Mocked: in-memory outbox, queue inline."""
import datetime
import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from mailings import blocks, invites, lists, segments, sending
from mailings.models import ContactList, ContactListMember, EmailOptOut, Invite, Mailing, MailingRecipient
from mailings.tests.test_mailings import lead, person
from notifications.services import preview_email
from plans.management.commands.seed_phase1 import seed_all
from users import services as user_services

User = get_user_model()


def button(link="personal_journey", label="Find {first_name} a plan", url=""):
    return {"type": "button", "label": label, "link": link, "url": url}


def parts(*extra):
    return [{"type": "paragraph", "text": "Hi {first_name},\n\nQuick note."}, *extra]


class BlockTests(TestCase):
    def test_link_choices_are_validated_and_a_personal_link_needs_no_url(self):
        cleaned, errors = blocks.clean(parts(button("personal_register", url="https://ignored.example.com")))
        self.assertFalse(errors)
        self.assertEqual(cleaned[1], {"type": "button", "link": "personal_register", "label": "Find {first_name} a plan", "url": ""})
        self.assertTrue(blocks.has_personal(cleaned))
        self.assertIn("link", blocks.clean(parts(button("nonsense")))[1]["1"])
        self.assertIn("url", blocks.clean(parts(button("url")))[1]["1"])  # a web address is still required for a web button
        self.assertFalse(blocks.has_personal(blocks.clean(parts({"type": "button", "label": "Go", "url": "/memberships/"}))[0]))  # old parts: web address
        self.assertIn("label", blocks.clean(parts(button(label="Hi {nope}")))[1]["1"])

    def test_first_name_is_filled_in_text_and_label_with_a_fallback(self):
        links = {"journey": "https://x.test/invite/t/?to=journey", "register": ""}
        values = {"first_name": "Sam", "personal_links": links}
        html, text, _ = blocks.render(parts(button()), values)
        self.assertIn("Hi Sam,", text)
        self.assertIn("Find Sam a plan:\nhttps://x.test/invite/t/?to=journey", text)
        text = blocks.render(parts(button()), {"first_name": " ", "personal_links": links})[1]
        self.assertIn("Hi there,", text)
        self.assertIn("Find there a plan", text)


class PersonalBase(TestCase):
    """Shared data and helpers (no tests of its own, so subclasses don't run each other's tests)."""
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.admin = User.objects.create_user("dev@example.com", "a-long-test-password-1")
        person("member@example.com")
        EmailOptOut.objects.create(email="quiet@example.com")
        Invite.objects.create(name="W", email="waiting@example.com", batch_id="00000000-0000-0000-0000-000000000001", status=Invite.SENT)
        csv = "name,email\nAl Smith,al@example.com\nBo,bo@example.com\nMem,member@example.com\nWait,waiting@example.com\nQuiet,quiet@example.com"
        cls.contacts, _ = lists.save_new("Gym", "Fitness", csv, cls.admin, invites.find_token(invites.issue_token(cls.admin, csv), cls.admin, csv))

    def make(self, kind=Mailing.NEWS, group="list", params=None, blocks_=None):
        params = params if params is not None else {"list_id": str(self.contacts.pk)}
        return Mailing.objects.create(name="Personal", subject="Hello {first_name}", kind=kind, group=group, params=params, created_by=self.admin,
                                      blocks=blocks_ or parts(button("personal_journey"), button("personal_register", label="Register")))


class PersonalSendTests(PersonalBase):
    def test_each_allowed_person_gets_an_invite_and_their_own_links(self):
        m = sending.start(self.make(), self.admin)
        self.assertEqual((m.status, sorted(msg.to[0] for msg in mail.outbox)), (Mailing.SENT, ["al@example.com", "bo@example.com"]))
        invite = Invite.objects.get(batch_id=m.pk, email="al@example.com")
        self.assertEqual((Invite.objects.filter(batch_id=m.pk).count(), invite.status, invite.name), (2, Invite.SENT, "Al Smith"))
        body = next(msg for msg in mail.outbox if msg.to == ["al@example.com"]).body
        self.assertIn(f"/invite/{invite.token}/?to=journey", body)
        self.assertIn(f"/invite/{invite.token}/?to=register", body)
        self.assertIn("Hi Al,", body)
        self.assertIn("Find Al a plan", body)
        self.assertIn("unsubscribe", body.lower())
        sending.run_mailing(m.pk)  # a second run, or building the list again, adds nothing
        sending.snapshot(m)
        self.assertEqual((len(mail.outbox), Invite.objects.filter(batch_id=m.pk).count()), (2, 2))

    def test_the_pop_up_counts_members_and_invited_people_as_skipped(self):
        m = self.make()
        details = sending.confirm_details(m)
        self.assertEqual(details["count"], 2)
        self.assertEqual(details["skipped"], 3)
        for reason in ("already members", "already invited", "unsubscribed"):
            self.assertIn(reason, details["skipped_why"])

    def test_a_person_who_registered_after_the_list_was_made_is_skipped_at_send_time(self):
        m = self.make()
        sending.snapshot(m)
        person("bo@example.com")
        Mailing.objects.filter(pk=m.pk).update(status=Mailing.SENDING)
        sending.run_mailing(m.pk)
        self.assertEqual([msg.to[0] for msg in mail.outbox], ["al@example.com"])
        self.assertEqual(MailingRecipient.objects.get(mailing=m, email="bo@example.com").status, MailingRecipient.SKIPPED)

    def test_an_invitation_kind_is_allowed_and_leads_can_get_it(self):
        self.assertFalse(sending.check_mailing(self.make(kind=Mailing.INVITATION)))
        lead("lead@example.com")
        lead("member@example.com")  # has an account: out
        m = self.make(kind=Mailing.NEWS, group="leads", params={})
        self.assertEqual(segments.count("leads", {}, Mailing.NEWS, True), 1)
        sending.start(m, self.admin)
        self.assertEqual([msg.to[0] for msg in mail.outbox], ["lead@example.com"])
        self.assertTrue(Invite.objects.filter(batch_id=m.pk, email="lead@example.com").exists())

    def test_account_groups_refuse_personal_links_with_a_clear_message(self):
        person("p@example.com", consent=True)
        for group in ("everyone", "opted_in", "gold"):
            errors = sending.check_mailing(self.make(group=group, params={}))
            self.assertEqual(errors["blocks"], [sending.PERSONAL_REFUSED], group)
        with self.assertRaises(sending.MailingError):
            sending.start(self.make(group="everyone", params={}), self.admin)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_full_path_click_questionnaire_register_ends_registered(self):
        m = sending.start(self.make(), self.admin)
        invite = Invite.objects.get(batch_id=m.pk, email="al@example.com")
        client = Client()
        response = client.get(f"/invite/{invite.token}/?to=journey")
        self.assertRedirects(response, "/journey/", fetch_redirect_response=False)
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.OPENED)
        self.assertEqual(client.get("/journey/your-time/").context["journey_config"]["inviteEmail"], "al@example.com")
        self.assertRedirects(Client().get(f"/invite/{invite.token}/?to=register"), "/register/", fetch_redirect_response=False)
        self.assertRedirects(Client().get(f"/invite/{invite.token}/?to=evil"), "/journey/", fetch_redirect_response=False)  # not allowed: the default
        user = user_services.register_interest({
            "first_name": "Al", "last_name": "Smith", "email": "al@example.com", "password": "a-long-test-password-1", "mobile": "+447912345678",
            "date_of_birth": datetime.date(1990, 1, 1), "plan": "tier-2"}).user
        invite.refresh_from_db()
        self.assertEqual((invite.status, invite.registered_user), (Invite.REGISTERED, user))

    def test_preview_and_test_use_sample_values(self):
        shown = preview_email("mailing", "Hello {first_name}", "", {}, blocks=parts(button()))
        self.assertIn("Hi James,", shown["text"])
        self.assertIn("/example-link/", shown["text"])
        self.assertNotIn("/invite/", shown["text"])


class ReviewFixTests(PersonalBase):
    def test_db_default_keeps_old_code_working(self):
        from system.models import SiteDefaults

        self.assertEqual(SiteDefaults._meta.get_field("invite_landing").db_default, "journey")

    def test_placeholders_are_refused_in_links(self):
        for url in ("https://x.example.com/{first_name}", "/memberships/{x}"):
            self.assertEqual(blocks.clean(parts({"type": "button", "label": "Go", "url": url}))[1]["1"]["url"], ["Placeholders don't work in links"])

    def test_the_edit_page_shows_the_button_text_that_will_be_sent(self):
        from notifications import emailbody
        from system.emails import spec_info
        from system.models import SiteDefaults

        self.assertEqual(spec_info(emailbody.SPECS["invite"])["button_label"], "Find my membership")
        SiteDefaults.objects.update(invite_landing="register")
        self.assertEqual(spec_info(emailbody.SPECS["invite"])["button_label"], "Register for Spa 99")

    def test_leads_are_counted_by_address_in_the_skipped_summary(self):
        lead("a@example.com")
        lead("a@example.com")  # same address twice: one person
        person("m@example.com")
        lead("m@example.com")
        self.assertEqual(segments.skipped_summary("leads", {}, Mailing.NEWS, True)[0], 1)

    def test_a_registered_invite_is_not_used_to_pre_fill_and_the_session_is_cleared_on_sign_up(self):
        m = sending.start(self.make(), self.admin)
        invite = Invite.objects.get(batch_id=m.pk, email="al@example.com")
        client = Client()
        client.get(f"/invite/{invite.token}/")
        client.post("/register/", {"first_name": "Al", "last_name": "S", "email": "al@example.com", "password": "a-long-test-password-1",
                                   "mobile": "+447912345678", "plan": "tier-2"})
        Invite.objects.filter(pk=invite.pk).update(status=Invite.REGISTERED)
        self.assertIsNone(invites.good_invite(invite.token))
        self.assertEqual(client.get("/journey/your-time/").context["journey_config"]["inviteEmail"], "")
