"""Office 2 email work: the Sender dropdown, the group send to leads (who moves to Archived, and who comes back), Barry's starter and the add-your-number link.
Mocked: the mail outbox is in memory, the queue is stepped by hand, no real service is called."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from journey.models import JourneySession
from mailings import addnumber, sending
from mailings.models import Mailing, MailingRecipient
from notifications import sender as sender_mod, suppression
from notifications.models import EmailLog, EmailSuppression, NotificationTemplate
from office.tests.test_leads import lead
from outreach import nextmorning, services
from outreach.models import ArchivedLead, NextMorningEmail, OutreachEntry, PersonEdit
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings

User = get_user_model()


def staff(email, first="Barry", **extra):
    return User.objects.create_user(email, "x-Pass-123456", first_name=first, last_name="Lobenstein", is_staff=True, **extra)


def with_mobile(email, number="+447911123456"):
    JourneySession.objects.filter(lead_email=email).update(lead_mobile=number)


@override_settings(DEFAULT_FROM_EMAIL="Spa 99 <hello@spa99.test>", EMAIL_SENDING_DOMAIN="spa99.test")
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def send(self, **over):
        fields = {"name": "Barry", "subject": "A word from Barry", "kind": Mailing.NEWS, "group": "leads",
                  "body": "Hello {first_name}\n\nPlease WhatsApp me on {whatsapp_number}. {add_number_link}", **over}
        m = Mailing.objects.create(**fields)
        with mock.patch("mailings.sending.enqueue"):
            sending.start(m, None)
        sending.run_mailing(m.pk)
        return m


class SenderTests(Base):
    def test_the_select_lists_hello_first_then_staff_on_the_sending_domain_and_a_person_who_left_falls_back_to_hello(self):
        barry, outsider = staff("barry@spa99.test"), staff("someone@gmail.test", first="Out")
        leaver = staff("leaver@spa99.test", first="Lee")
        choices = sender_mod.sender_choices()
        self.assertEqual(choices[0], ("", "Spa 99 <hello@spa99.test>"))
        self.assertEqual([v for v, _ in choices[1:]], [str(barry.pk), str(leaver.pk)])  # not the one with an outside address
        self.assertIn("Barry Lobenstein <barry@spa99.test>", dict(choices).values())
        self.assertEqual(sender_mod.from_and_reply(barry.pk), ('"Barry, Spa 99" <barry@spa99.test>', ["barry@spa99.test"]))  # Reply-To follows him
        self.assertEqual(sender_mod.from_and_reply(""), (None, None))  # hello@ keeps the contact address as Reply-To
        leaver.is_active = False
        leaver.save()
        self.assertEqual(sender_mod.from_and_reply(leaver.pk), (None, None))  # safe: hello@
        self.assertIn("has no @spa99.test address now", sender_mod.gone_note(leaver.pk))
        del outsider

    def test_a_group_send_goes_out_as_the_chosen_person_and_falls_back_to_hello_when_he_has_left(self):
        barry = staff("barry@spa99.test")
        lead("a@example.com")
        m = self.send(sender_user=barry)
        self.assertEqual((mail.outbox[0].from_email, mail.outbox[0].reply_to), ('"Barry, Spa 99" <barry@spa99.test>', ["barry@spa99.test"]))
        self.assertEqual(MailingRecipient.objects.get(mailing=m).status, "sent")
        barry.is_active = False
        barry.save()
        mail.outbox.clear()
        lead("b@example.com")
        m2 = self.send(sender_user=barry, name="Second")
        self.assertEqual(MailingRecipient.objects.filter(mailing=m2, status="sent").count(), 2)  # nothing failed or stopped because he left
        self.assertTrue(all(message.from_email == "Spa 99 <hello@spa99.test>" for message in mail.outbox))

    def test_the_next_morning_email_still_goes_with_no_sender_address_and_is_signed_by_the_chosen_person(self):
        site = SiteSettings.load()
        site.lead_next_morning_on, site.auto_email_from_address = True, ""  # no person sender address set any more
        site.save()
        session = lead("new@example.com")
        JourneySession.objects.filter(pk=session.pk).update(lead_at=timezone.now() + timedelta(hours=1))  # after the switch was turned on
        nextmorning.run(timezone.now() + timedelta(hours=30))
        self.assertEqual(NextMorningEmail.objects.get().skipped_at, None)
        self.assertEqual(mail.outbox[0].to, ["new@example.com"])
        self.assertEqual(mail.outbox[0].from_email, "Spa 99 <hello@spa99.test>")
        barry = staff("barry@spa99.test")
        NotificationTemplate.objects.filter(key="lead_next_morning").update(sender_user=barry)
        mail.outbox.clear()
        NextMorningEmail.objects.all().delete()
        nextmorning.run(timezone.now() + timedelta(hours=30))
        self.assertEqual((mail.outbox[0].from_email, mail.outbox[0].reply_to), ('"Barry, Spa 99" <barry@spa99.test>', ["barry@spa99.test"]))
        self.assertIn("Barry", mail.outbox[0].body.rsplit("Best wishes,", 1)[1])

    def test_the_old_person_sender_keeps_working_until_the_script_moves_it_and_the_script_has_a_dry_run(self):
        from django.core.management import call_command
        from io import StringIO

        barry = staff("barry@spa99.test")
        SiteSettings.objects.update(auto_email_from_address="barry@spa99.test", auto_email_from_name="Barry")
        from notifications import emailsettings

        options = emailsettings.options_for("lead_next_morning")  # default sender: the person
        self.assertEqual(emailsettings.sender_for(options, SiteSettings.load())[1], ["barry@spa99.test"])  # still works before the script
        out = StringIO()
        call_command("migrate_person_sender", "--dry-run", stdout=out)
        self.assertIn("WOULD SET", out.getvalue())
        self.assertFalse(NotificationTemplate.objects.filter(sender_user__isnull=False).exists())  # a dry run writes nothing
        call_command("migrate_person_sender", stdout=StringIO())
        row = NotificationTemplate.objects.get(key="lead_next_morning")
        self.assertEqual((row.sender_user, row.sender), (barry, ""))
        out = StringIO()
        call_command("migrate_person_sender", stdout=out)
        self.assertIn("0 email(s) moved", out.getvalue())  # safe to run twice


class GroupSendToLeadsTests(Base):
    def test_barrys_starter_and_the_confirm_say_who_will_move_and_the_placeholders_are_filled_per_lead(self):
        from mailings import blocks
        from system.tests.test_system import make_user, unlocked_client

        SiteSettings.objects.update(whatsapp_number="447441919990")
        lead("has@example.com"), lead("none@example.com")
        with_mobile("has@example.com")
        starter = blocks.STARTERS["barry_invitation"]
        self.assertEqual((starter["subject"], starter["kind"], starter["group"], starter["archive_no_number"]), ("A word from Barry at Spa 99", "news", "leads", True))
        self.assertEqual(blocks.clean(starter["blocks"])[1], {})
        m = Mailing.objects.create(name="B", subject="S", kind="news", group="leads", blocks=blocks.clean(starter["blocks"])[0], archive_no_number=True)
        client = unlocked_client(make_user())
        confirm = client.get(f"/emails/mailings/{m.pk}/confirm/").json()
        self.assertEqual((confirm["count"], confirm["moves"]["stay"], confirm["moves"]["archive"]), (2, 1, 1))
        self.assertIn("bounces stays in Leads", confirm["moves"]["bounced"])
        with mock.patch("mailings.sending.enqueue"):
            sending.start(m, None)
        sending.run_mailing(m.pk)
        message = next(x for x in mail.outbox if x.to == ["has@example.com"])
        self.assertIn("+44 7441 919990", message.body)
        link = next(line for line in message.body.splitlines() if "/add-number/" in line)
        self.assertEqual(addnumber.read_token(link.rsplit("/add-number/", 1)[1].strip("/")), "has@example.com")  # his own link

    def test_after_the_send_only_a_lead_with_no_mobile_moves_a_failure_moves_nobody_and_a_resend_sends_nothing_twice(self):
        lead("has@example.com"), lead("none@example.com"), lead("fails@example.com")
        with_mobile("has@example.com")
        with mock.patch("notifications.services.EmailMultiAlternatives.send", side_effect=[None, Exception("smtp down"), None]):  # one per recipient, in address order: fails@, has@, none@
            m = self.send(archive_no_number=True)
        statuses = dict(MailingRecipient.objects.filter(mailing=m).values_list("email", "status"))
        self.assertEqual(statuses, {"fails@example.com": "sent", "has@example.com": "failed", "none@example.com": "sent"})
        archived = {a.email: a for a in ArchivedLead.objects.all()}
        self.assertEqual(sorted(archived), ["fails@example.com", "none@example.com"])  # sent and no mobile: archived. has@ failed: he has a mobile anyway
        self.assertEqual((archived["none@example.com"].reason, archived["none@example.com"].archived_by_label), ("Emailed, no number", "Group email"))
        lead("late@example.com")
        with mock.patch("notifications.services.EmailMultiAlternatives.send", side_effect=Exception("down")):
            self.send(archive_no_number=True, name="Again")
        self.assertFalse(ArchivedLead.objects.filter(email="late@example.com").exists())  # not sent: he stays
        before = len(mail.outbox)
        sending.run_mailing(m.pk)  # a finished mailing is run again: nobody is emailed twice
        self.assertEqual(len(mail.outbox), before)

    def test_a_mailing_without_the_switch_moves_nobody_and_a_later_bounce_brings_back_only_the_group_archived(self):
        lead("none@example.com")
        self.send()
        self.assertFalse(ArchivedLead.objects.exists())  # the switch is per send
        self.send(archive_no_number=True, name="Barry")
        self.assertEqual(ArchivedLead.objects.get().reason, "Emailed, no number")
        lead("manual@example.com")
        services.archive_lead("manual@example.com", None, "Emailed, no number")  # a person typed the same words: still not the group's row
        suppression.add("none@example.com", EmailSuppression.HARD_BOUNCE)
        suppression.add("manual@example.com", EmailSuppression.HARD_BOUNCE)
        self.assertEqual(list(ArchivedLead.objects.values_list("email", flat=True)), ["manual@example.com"])
        from office import leads as lead_lists

        rows = [r for r in lead_lists.build_rows(list(lead_lists.lead_queryset("all")))]
        self.assertEqual([(r["email"], r["bounced"]) for r in rows], [("none@example.com", True)])  # back in Leads, shown as Possible fake


class AddNumberTests(Base):
    def url(self, email):
        return addnumber.link_for(email).replace("http://testserver", "")

    def setUp(self):
        self.client = Client()
        self.session = lead("a@example.com")
        JourneySession.objects.filter(pk=self.session.pk).update(lead_mobile="")

    def post(self, email="a@example.com", **data):
        return self.client.post(self.url(email), {"mobile_country": "GB", "mobile": "07911 123456", "consent": "on", **data})

    def test_the_page_shows_his_address_read_only_and_saves_the_number_audits_it_unarchives_and_adds_him_to_the_list(self):
        services.archive_lead("a@example.com", None, "Emailed, no number")
        page = self.client.get(self.url("a@example.com"))
        self.assertContains(page, "a@example.com")
        self.assertEqual(page["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(self.post(), "Barry will be in touch on WhatsApp")
        self.assertEqual(JourneySession.objects.get(pk=self.session.pk).lead_mobile, "+447911123456")
        edit = PersonEdit.objects.get()
        self.assertEqual((edit.what, edit.after, edit.by_label), ("mobile", "+447911123456", "His own link"))
        self.assertFalse(ArchivedLead.objects.exists())
        entry = OutreachEntry.objects.get()
        self.assertEqual((entry.lead_email, entry.added_by_label), ("a@example.com", "His own link"))
        self.assertContains(self.post(mobile="07911 123457"), "already with us")  # used link: nothing changes
        self.assertEqual(PersonEdit.objects.count(), 1)

    def test_a_tampered_or_expired_link_is_refused_in_the_same_words_and_a_taken_number_does_not_say_whose(self):
        good = addnumber.make_token("a@example.com")
        for token in (good[:-3] + "xyz", "garbage", signing.dumps({"e": "a@example.com"}, salt="other")):
            response = self.client.get(f"/add-number/{token}/")
            self.assertContains(response, "This link has ended", status_code=400)
            self.assertNotContains(response, "a@example.com", status_code=400)
        with mock.patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + (addnumber.LINK_DAYS + 1) * 86400):
            self.assertContains(self.client.get(f"/add-number/{good}/"), "This link has ended", status_code=400)
        other = lead("other@example.com")
        JourneySession.objects.filter(pk=other.pk).update(lead_mobile="+447911123456")
        response = self.post()
        self.assertContains(response, "That number is already with us", status_code=400)
        self.assertNotContains(response, "other@example.com", status_code=400)
        self.assertFalse(PersonEdit.objects.exists())
        self.assertContains(self.post(mobile="12"), "does not look right", status_code=400)
        self.assertContains(self.post(consent=""), "Please tick this", status_code=400)

    def test_someone_who_registered_meanwhile_is_thanked_and_nothing_changes_and_the_page_is_rate_limited(self):
        from office.tests.test_leads import verify
        from users import services as user_services
        from users.tests.test_register import cleaned

        verify(user_services.register_interest(cleaned(email="a@example.com")).user)
        self.assertContains(self.post(), "already with us")
        self.assertEqual((JourneySession.objects.get(pk=self.session.pk).lead_mobile, PersonEdit.objects.count(), OutreachEntry.objects.count()), ("", 0, 0))
        from django.core.cache import cache

        with override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "add-number"}}):
            cache.clear()
            statuses = {self.client.get(self.url("a@example.com")).status_code for _ in range(32)}
        self.assertIn(429, statuses)


class StaffAddsTheNumberTests(Base):
    def test_a_number_added_by_staff_moves_a_group_archived_lead_to_the_approach_list_and_leaves_others_alone(self):
        from common import levels
        from plans.tests.helpers import make_team_member

        admin = make_team_member("admin@example.test", levels.ADMIN)
        lead("gone@example.com"), lead("kept@example.com")
        self.send(archive_no_number=True)
        self.assertEqual(ArchivedLead.objects.count(), 2)
        services.archive_lead("kept@example.com", admin, "not a fit")  # archived by a person: replace the group's row
        ArchivedLead.objects.filter(email="kept@example.com").update(reason="not a fit", archived_by_label="admin@example.test")
        self.assertEqual(services.set_lead_contact("gone@example.com", admin, mobile="07911123456")[0], services.DONE)
        self.assertEqual(services.set_lead_contact("kept@example.com", admin, mobile="07911123457")[0], services.DONE)
        self.assertEqual(list(ArchivedLead.objects.values_list("email", flat=True)), ["kept@example.com"])
        self.assertEqual(list(OutreachEntry.objects.values_list("lead_email", flat=True)), ["gone@example.com"])
