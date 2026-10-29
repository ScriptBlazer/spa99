"""Uploaded lists (save, merge, flag, never send), group sends to a list, the Invitation sent to a list with per-person tracking, and
GDPR. Mocked: in-memory outbox, queue stepped inline."""
import datetime

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.utils import timezone

from mailings import invites, lists, segments, sending
from mailings.models import ContactList, ContactListMember, EmailOptOut, Invite, InviteImport, Mailing, MailingRecipient
from mailings.tests.test_mailings import person
from notifications import suppression
from notifications.models import EmailSuppression
from plans.management.commands.seed_phase1 import seed_all
from users import services as user_services

User = get_user_model()
CSV = ("name,email\nAl Smith,al@example.com\nAl Smith,al@example.com\nAl Smith,AL@Example.com\nBo Jones,bo@example.com\n"
       "Mem Ber,member@example.com\nBounced,bounced@example.com\nQuiet,quiet@example.com\nWaiting,waiting@example.com\nNo Consent,noconsent@example.com")


def make_list(admin, text=CSV, name="Gym", category="Fitness"):
    row = invites.find_token(invites.issue_token(admin, text), admin, text)
    return lists.save_new(name, category, text, admin, row)


class ListFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.admin = User.objects.create_user("dev@example.com", "a-long-test-password-1")
        person("member@example.com", consent=True)
        person("noconsent@example.com", consent=False)
        suppression.add("bounced@example.com", EmailSuppression.HARD_BOUNCE)
        EmailOptOut.objects.create(email="quiet@example.com")
        Invite.objects.create(name="W", email="waiting@example.com", batch_id="00000000-0000-0000-0000-000000000001", status=Invite.SENT)


class ListSaveTests(ListFixtures):
    def test_a_list_saves_with_merges_and_flags_and_sends_nothing(self):
        report = lists.review(CSV)
        self.assertTrue(report["can_save"])
        self.assertEqual((report["ok"], report["flagged"], report["counts"]["duplicate"], report["counts"]["case_duplicate"]), (7, 5, 1, 1))  # al, bo and five flagged (two have accounts)
        lst, saved = make_list(self.admin)
        self.assertEqual(sorted(lst.members.values_list("email", flat=True)),
                         ["al@example.com", "bo@example.com", "bounced@example.com", "member@example.com", "noconsent@example.com", "quiet@example.com", "waiting@example.com"])
        self.assertEqual((lst.name, lst.category, lst.created_by), ("Gym", "Fitness", self.admin))
        self.assertEqual(lst.members.get(email="al@example.com").source_row, 2)
        self.assertEqual(len(mail.outbox), 0)  # saving sends nothing
        self.assertFalse(MailingRecipient.objects.exists())

    def test_errors_block_saving_and_the_name_must_be_new(self):
        bad = "name,email\nAl,al@example.com\nBad,not-an-email\n=cmd|x,evil@example.com\nA,dup@example.com\nB,DUP@example.com"
        self.assertFalse(lists.review(bad)["can_save"])
        with self.assertRaises(lists.ListError):
            lists.save_new("Bad", "", bad, self.admin)
        self.assertFalse(ContactList.objects.exists())
        make_list(self.admin, "Al,al@example.com")
        with self.assertRaises(lists.ListError) as clash:
            lists.save_new("gym", "", "Bo,bo@example.com", self.admin)  # the same name in another case
        self.assertIn("name", clash.exception.errors)
        self.assertEqual(ContactList.objects.count(), 1)

    def test_phone_columns_are_ignored_and_the_token_saves_once(self):
        text = "name,email,phone\nAl,al@example.com,+447912345678"
        row = invites.find_token(invites.issue_token(self.admin, text), self.admin, text)
        stale = InviteImport.objects.get(pk=row.pk)  # what a racing second request loaded
        first, _ = lists.save_new("Phones", "", text, self.admin, row)
        again, report = lists.save_new("Phones 2", "", text, self.admin, stale)
        self.assertEqual((again, report.get("existing")), (first, True))
        self.assertEqual((ContactList.objects.count(), ContactListMember.objects.count()), (1, 1))

    def test_add_more_merges_new_addresses_and_leaves_existing_ones_alone(self):
        lst, _ = make_list(self.admin, "Al Smith,al@example.com")
        ContactListMember.objects.filter(email="al@example.com").update(name="Kept Name")
        added, report = lists.add_more(lst, "Al Other,al@example.com\nCy,cy@example.com", self.admin)
        self.assertEqual((added, report["exists"]), (1, 1))
        self.assertEqual(lst.members.get(email="al@example.com").name, "Kept Name")
        self.assertEqual(lst.members.count(), 2)
        with self.assertRaises(lists.ListError):
            lists.add_more(lst, "cy@example.com", self.admin)  # nobody new

    def test_remove_rename_category_and_delete_are_audited(self):
        from system.models import SystemEvent

        lst, _ = make_list(self.admin, "Al,al@example.com\nBo,bo@example.com")
        member = lst.members.get(email="al@example.com")
        self.assertTrue(lists.remove_member(lst, member.pk, self.admin))
        lists.edit(lst, self.admin, name="Gym 2", category="Sport")
        lists.delete(lst, self.admin)
        kinds = list(SystemEvent.objects.order_by("created_at").values_list("kind", flat=True))
        self.assertEqual(kinds, ["list_created", "list_changed", "list_changed", "list_deleted"])
        self.assertFalse(any("al@example.com" in e.sentence for e in SystemEvent.objects.all()))  # no address in the audit line
        self.assertEqual((ContactList.objects.count(), ContactListMember.objects.count()), (0, 0))


class ListSendTests(ListFixtures):
    def setUp(self):
        self.lst, _ = make_list(self.admin)
        self.params = {"list_id": str(self.lst.pk)}

    def mailing(self, kind=Mailing.NEWS, **over):
        return Mailing.objects.create(name="Hello", subject="Hi {first_name}", body="Hello {first_name}\n\nNews.", kind=kind, group="list", params=self.params, **over)

    def test_news_to_a_list_counts_and_sends_only_to_people_who_may_be_emailed(self):
        # al, bo: fine. bounced, quiet: never. member: has an account with news on. noconsent: account with news off. waiting: fine for news.
        self.assertEqual(segments.count("list", self.params, Mailing.NEWS), 4)
        self.assertEqual(segments.skipped_summary("list", self.params, Mailing.NEWS), (3, "unsubscribed, bounced or complained or news switched off"))
        m = sending.start(self.mailing(), self.admin)
        self.assertEqual(sorted(msg.to[0] for msg in mail.outbox), ["al@example.com", "bo@example.com", "member@example.com", "waiting@example.com"])
        self.assertEqual((m.status, m.total_count), (Mailing.SENT, 4))
        first = next(msg for msg in mail.outbox if msg.to == ["al@example.com"])
        self.assertIn("List-Unsubscribe", first.extra_headers)
        self.assertEqual(first.subject, "Hi Al")

    def test_someone_who_unsubscribes_after_the_snapshot_is_skipped(self):
        from unittest import mock

        with mock.patch("mailings.sending.enqueue"):
            m = sending.start(self.mailing(), self.admin)
        EmailOptOut.objects.create(email="bo@example.com")
        sending.run_mailing(m.pk)
        self.assertNotIn("bo@example.com", [msg.to[0] for msg in mail.outbox])
        self.assertEqual(MailingRecipient.objects.get(mailing=m, email="bo@example.com").status, "skipped")

    def test_a_service_message_to_a_list_is_refused_everywhere(self):
        m = self.mailing(kind=Mailing.SERVICE)
        self.assertEqual(segments.count("list", self.params, Mailing.SERVICE), 0)
        self.assertIn("group", sending.check_mailing(m))
        with self.assertRaises(sending.MailingError):
            sending.start(m, self.admin)
        self.assertEqual(len(mail.outbox), 0)
        plain = self.mailing(kind=Mailing.INVITATION)  # an invitation needs the Invitation email, not the plain composer
        from system.emails import MailingForm
        form = MailingForm({"name": "x", "subject": "s", "kind": "invitation", "group": "list", "body": "Hi", **self.params})
        self.assertIn("kind", form.errors)
        self.assertTrue(plain.pk)


class InviteToListTests(ListFixtures):
    def setUp(self):
        self.lst, _ = make_list(self.admin)
        self.mailing = Mailing.objects.create(name="Invitation to register", subject="You are invited", kind=Mailing.INVITATION, automatic_key="invite",
                                              group="list", params={"list_id": str(self.lst.pk)}, created_by=self.admin)

    def test_an_invitation_skips_members_and_people_already_invited_and_tracks_each_person(self):
        self.assertEqual(segments.count("list", self.mailing.params, Mailing.INVITATION), 2)  # al, bo
        self.assertEqual(segments.skipped_summary("list", self.mailing.params, Mailing.INVITATION)[0], 5)
        m = sending.start(self.mailing, self.admin)
        self.assertEqual((m.status, sorted(msg.to[0] for msg in mail.outbox)), (Mailing.SENT, ["al@example.com", "bo@example.com"]))
        invite = Invite.objects.get(batch_id=m.pk, email="al@example.com")
        self.assertEqual((invite.status, invite.name, invite.created_by), (Invite.SENT, "Al Smith", self.admin))
        message = next(msg for msg in mail.outbox if msg.to == ["al@example.com"])
        self.assertIn(f"/invite/{invite.token}/", message.body)
        self.assertIn("Hello Al,", message.body)
        self.assertIn("List-Unsubscribe", message.extra_headers)
        self.assertEqual(Invite.objects.filter(batch_id=m.pk).count(), 2)  # one per person, none for the people left out
        sending.run_mailing(m.pk)  # a second run sends nothing more
        self.assertEqual(len(mail.outbox), 2)

    def test_the_personal_link_marks_opened_and_registering_marks_registered(self):
        sending.start(self.mailing, self.admin)
        invite = Invite.objects.get(email="al@example.com")
        client = Client()
        self.assertRedirects(client.get(f"/invite/{invite.token}/"), "/register/", fetch_redirect_response=False)
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.SENT)  # a link scanner does not count as opened
        page = client.get("/register/")
        self.assertContains(page, 'value="al@example.com"')
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.OPENED)
        user = user_services.register_interest({
            "first_name": "Al", "last_name": "Smith", "email": "al@example.com", "password": "a-long-test-password-1", "mobile": "+447912345678",
            "date_of_birth": datetime.date(1990, 1, 1), "plan": "tier-2"}).user
        invite.refresh_from_db()
        self.assertEqual((invite.status, invite.registered_user), (Invite.REGISTERED, user))
        # he is a member now: another invitation to the list leaves him out, and the old pending invite for bo still blocks bo
        self.assertEqual(segments.count("list", self.mailing.params, Mailing.INVITATION), 0)

    def test_cancelling_before_sending_leaves_no_waiting_invites(self):
        from unittest import mock

        with mock.patch("mailings.sending.enqueue"):
            m = sending.start(self.mailing, self.admin)
        self.assertEqual(Invite.objects.filter(batch_id=m.pk, status=Invite.QUEUED).count(), 2)
        sending.cancel(m, self.admin)
        self.assertFalse(Invite.objects.filter(batch_id=m.pk, status=Invite.QUEUED).exists())
        self.assertEqual(len(mail.outbox), 0)


class ListGdprTests(ListFixtures):
    def test_export_and_erase_cover_list_members(self):
        lst, _ = make_list(self.admin, "Al,al@example.com\nMem,member@example.com")
        user = User.objects.get(email="member@example.com")
        exported = user_services.export_user_data(user)
        self.assertEqual([(x["list"], x["name"]) for x in exported["uploaded_lists"]], [("Gym", "Mem")])
        from mailings.erasure import erase_address

        user_services.delete_user_data(user)
        self.assertEqual(list(lst.members.values_list("email", flat=True)), ["al@example.com"])
        self.assertGreaterEqual(erase_address("al@example.com"), 1)  # the Office "remove this lead" path
        self.assertFalse(ContactListMember.objects.exists())


class ScheduledCountTests(ListFixtures):
    def setUp(self):
        self.lst, _ = make_list(self.admin)
        self.params = {"list_id": str(self.lst.pk)}

    def scheduled(self, confirmed):
        from unittest import mock

        m = Mailing.objects.create(name="N", subject="Hi", body="Hello\n\nNews.", kind=Mailing.NEWS, group="list", params=self.params, created_by=self.admin)
        with mock.patch("mailings.sending.enqueue"):
            sending.schedule(m, timezone.now() + datetime.timedelta(hours=2), self.admin, confirmed=confirmed)
        return m

    def test_more_people_than_confirmed_sends_nothing_and_goes_back_to_draft_with_a_note(self):
        from system.models import SystemEvent

        m = self.scheduled(confirmed=3)  # four can get it now
        self.assertEqual(sending.start_scheduled(str(m.pk)), "returned to draft")
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at), (Mailing.DRAFT, None))
        self.assertEqual(m.error, "Went back to draft: 4 people now, 3 confirmed. Check and send again.")
        self.assertEqual((len(mail.outbox), MailingRecipient.objects.count()), (0, 0))
        self.assertEqual(SystemEvent.objects.get(kind="mailing_returned").detail["confirmed"], 3)

    def test_fewer_or_the_same_people_still_send(self):
        m = self.scheduled(confirmed=10)
        self.assertEqual(sending.start_scheduled(str(m.pk)), "started")
        self.assertEqual(len(mail.outbox), 4)

    def test_an_invitation_needs_the_invitation_email_behind_it(self):
        m = Mailing.objects.create(name="N", subject="Hi", body="Hi", kind=Mailing.INVITATION, group="list", params=self.params)
        self.assertIn("kind", sending.check_mailing(m))


class ReviewerFixTests(ListFixtures):
    def test_a_token_for_one_list_cannot_save_into_another(self):
        a, _ = make_list(self.admin, "Al,al@example.com", name="A")
        b, _ = make_list(self.admin, "Bo,bo@example.com", name="B")
        text = "Cy,cy@example.com"
        token = invites.issue_token(self.admin, text, str(a.pk))
        with self.assertRaises(invites.TokenRefused):
            invites.find_token(token, self.admin, text, str(b.pk))
        self.assertTrue(invites.find_token(token, self.admin, text, str(a.pk)))

    def test_mark_stale_invites_dry_run_changes_nothing_and_leaves_group_send_invites(self):
        from io import StringIO

        from django.core.management import call_command

        old = Invite.objects.create(name="O", email="old@example.com", batch_id="00000000-0000-0000-0000-000000000009", status=Invite.QUEUED)
        mine = Mailing.objects.create(name="N", subject="s", group="list", params={}, kind=Mailing.INVITATION, automatic_key="invite")
        keep = Invite.objects.create(name="K", email="keep@example.com", batch_id=mine.pk, status=Invite.QUEUED)
        out = StringIO()
        call_command("mark_stale_invites", "--dry-run", stdout=out)
        self.assertIn("1 old queued", out.getvalue())
        old.refresh_from_db()
        self.assertEqual(old.status, Invite.QUEUED)
        call_command("mark_stale_invites", stdout=StringIO())
        old.refresh_from_db()
        keep.refresh_from_db()
        self.assertEqual((old.status, old.reason, keep.status), (Invite.SKIPPED, "old batch, sending retired", Invite.QUEUED))
