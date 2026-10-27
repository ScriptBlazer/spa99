"""Groups, group sends, unsubscribe, invites. Mocked: the mail outbox is in memory, SES is a patched boto3, the queue runs inline
(or is replaced by a mock where the test steps the worker by hand)."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from gold.models import GoldApplication
from journey.models import JourneySession
from mailings import invites, optout, segments, sending, tokens
from mailings.models import EmailOptOut, Invite, Mailing, MailingRecipient
from notifications import suppression
from notifications.models import EmailSuppression
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan
from users import member, services as user_services
from users.models import InterestRegistration

User = get_user_model()


def person(email, plan="tier-2", consent=False, verified=True, active=True, first_name="Sam"):
    user = User.objects.create_user(email, "a-long-test-password-1", first_name=first_name, is_active=active,
                                    marketing_consent=consent, email_verified_at=timezone.now() if verified else None)
    if plan:
        InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug=plan))
    return user


def mailing(kind=Mailing.NEWS, group="everyone", params=None, body="Hello {first_name}\n\nThe spa opens soon.", **over):
    return Mailing.objects.create(name="Opening", subject="News for {first_name}", body=body, kind=kind, group=group, params=params or {}, **over)


def application(email, status=GoldApplication.NEW, consent=False):
    return GoldApplication.objects.create(first_name="Dan", last_name="Cohen", email=email, status=status, marketing_consent=consent)


class SegmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.a = person("a@example.com", "tier-1", consent=True)
        cls.b = person("b@example.com", "tier-2", consent=False)
        cls.c = person("c@example.com", "gold", consent=True, verified=False)
        cls.d = person("d@example.com", "tier-2", consent=True, active=False)
        cls.team = person("team@example.com", plan=None, consent=True)  # no registered interest: not "registered"
        application("g1@example.com", GoldApplication.APPROVED, consent=True)
        application("g2@example.com", GoldApplication.APPROVED, consent=False)
        application("g1@example.com", GoldApplication.APPROVED, consent=True)  # the same person applied twice

    def count(self, group, params=None, kind=Mailing.SERVICE):
        return segments.count(group, params or {}, kind)

    def test_each_group(self):
        self.assertEqual(self.count("everyone"), 3)  # inactive and no-interest accounts are out
        self.assertEqual(self.count("tier", {"plan": "tier-2"}), 1)
        self.assertEqual(self.count("gold"), 1)
        self.assertEqual(self.count("opted_in"), 2)
        self.assertEqual(self.count("unconfirmed"), 1)
        self.assertEqual(self.count("between", {"date_from": "2020-01-01"}), 3)
        tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.count("between", {"date_from": tomorrow}), 0)
        self.assertEqual(self.count("applicants", {"status": "approved"}), 2)  # one address once
        self.assertEqual(self.count("applicants", {"status": "new"}), 0)
        self.assertEqual(sorted(e for e, _, _ in segments.rows("everyone", {}, Mailing.SERVICE)), ["a@example.com", "b@example.com", "c@example.com"])

    def test_news_needs_consent_and_service_does_not(self):
        self.assertEqual(self.count("everyone", kind=Mailing.NEWS), 2)
        self.assertEqual(self.count("applicants", {"status": "approved"}, kind=Mailing.NEWS), 1)  # the application's own tick
        EmailOptOut.objects.create(email="g1@example.com")
        self.assertEqual(self.count("applicants", {"status": "approved"}, kind=Mailing.NEWS), 0)  # unsubscribed without an account
        self.assertEqual(self.count("applicants", {"status": "approved"}, kind=Mailing.SERVICE), 2)

    def test_suppressed_addresses_are_always_excluded(self):
        suppression.add("A@Example.com", EmailSuppression.HARD_BOUNCE)
        suppression.add("g2@example.com", EmailSuppression.COMPLAINT)
        self.assertEqual(self.count("everyone"), 2)
        self.assertEqual(self.count("everyone", kind=Mailing.NEWS), 1)
        self.assertEqual(self.count("applicants", {"status": "approved"}), 1)

    def test_params_are_checked(self):
        self.assertIn("plan", segments.clean_params("tier", {})[1])
        self.assertIn("plan", segments.clean_params("tier", {"plan": "nope"})[1])
        self.assertIn("date_to", segments.clean_params("between", {"date_from": "2026-02-01", "date_to": "2026-01-01"})[1])
        self.assertIn("group", segments.clean_params("everybody", {})[1])


def lead(email, bot=False, user=None):
    return JourneySession.objects.create(lead_email=email, lead_at=timezone.now(), is_bot=bot, user=user)


class LeadGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def emails(self, kind=Mailing.NEWS):
        return [e for e, _, _ in segments.rows("leads", {}, kind)]

    def test_only_people_without_an_account_who_can_be_emailed_once_each(self):
        lead("a@example.com")
        lead("A@Example.com")  # another browser, another case: one person
        lead("account@example.com")
        person("Account@example.com", consent=True)
        lead("staff@example.com")
        User.objects.create_user("staff@example.com", "x", is_staff=True)
        lead("out@example.com")
        EmailOptOut.objects.create(email="out@example.com")
        lead("bounced@example.com")
        suppression.add("bounced@example.com", EmailSuppression.HARD_BOUNCE)
        lead("bot@example.com", bot=True)
        lead("")  # no address
        self.assertEqual(self.emails(), ["a@example.com"])
        self.assertEqual(segments.count("leads", {}, Mailing.NEWS), 1)  # the count matches the rows
        self.assertEqual(segments.rows("leads", {}, Mailing.NEWS).__next__(), ("a@example.com", "", None))
        tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(segments.count("leads", {"date_from": tomorrow}, Mailing.NEWS), 0)

    def test_service_messages_cannot_use_the_group(self):
        lead("a@example.com")
        self.assertEqual(self.emails(Mailing.SERVICE), [])
        self.assertTrue(segments.GROUPS["leads"].news_only)
        self.assertIn("group", sending.check_mailing(mailing(kind=Mailing.SERVICE, group="leads")))
        self.assertNotIn("group", sending.check_mailing(mailing(group="leads")))

    def test_send_has_the_unsubscribe_link_and_the_link_stops_him_without_an_account(self):
        lead("a@example.com")
        m = mailing(group="leads")
        with mock.patch("mailings.sending.enqueue"):
            sending.start(m, None)
        row = MailingRecipient.objects.get()
        self.assertIsNone(row.user_id)
        sending.run_mailing(m.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, MailingRecipient.SENT)
        self.assertIn("Hello there", mail.outbox[-1].body)
        self.assertIn("/unsubscribe/", mail.outbox[-1].body)
        token = tokens.make_unsubscribe_token("a@example.com")
        self.assertContains(Client().post(f"/unsubscribe/{token}/"), "data-unsubscribe-done")
        self.assertTrue(EmailOptOut.objects.filter(email="a@example.com").exists())
        self.assertEqual(self.emails(), [])

    def test_a_lead_who_registers_with_news_ticked_is_back_and_one_who_does_not_is_out(self):
        lead("a@example.com")
        EmailOptOut.objects.create(email="a@example.com")
        user_services.register_interest({
            "first_name": "Al", "last_name": "B", "email": "a@example.com", "password": "a-long-test-password-1", "mobile": "+447912345678",
            "date_of_birth": datetime.date(1990, 1, 1), "plan": "tier-2", "marketing_opt_in": True})
        self.assertFalse(EmailOptOut.objects.exists())
        self.assertEqual(self.emails(), [])  # he has an account now: the other groups cover him


@override_settings(MAILING_RATE_PER_SECOND=2)
class MailingSendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.users = [person(f"p{i}@example.com", consent=True, first_name=f"P{i}") for i in range(3)]
        cls.admin = User.objects.create_user("dev@example.com", "a-long-test-password-1")

    def test_news_goes_once_to_each_opted_in_person_with_unsubscribe_headers(self):
        person("no@example.com", consent=False)
        m = sending.start(mailing(), self.admin)
        self.assertEqual((m.status, m.total_count, m.sent_count), (Mailing.SENT, 3, 3))
        self.assertEqual(len(mail.outbox), 3)
        first = next(msg for msg in mail.outbox if msg.to == ["p0@example.com"])
        self.assertEqual(first.subject, "News for P0")
        self.assertIn("Hello P0", first.body)
        url = tokens.unsubscribe_url("p0@example.com")
        self.assertEqual(first.extra_headers["List-Unsubscribe"], f"<{url}>")
        self.assertEqual(first.extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertIn(url, first.body)
        self.assertIn(url, first.alternatives[0][0])
        self.assertIn("opted in to news", first.body)
        # running the worker again, or building the list again, changes nothing
        self.assertEqual(sending.snapshot(m), 3)
        sending.run_mailing(m.pk)
        self.assertEqual((len(mail.outbox), MailingRecipient.objects.filter(mailing=m).count()), (3, 3))

    def test_service_message_has_no_unsubscribe_and_says_why(self):
        person("no@example.com", consent=False)
        m = sending.start(mailing(kind=Mailing.SERVICE), self.admin)
        self.assertEqual(len(mail.outbox), 4)  # everyone, consent or not
        for msg in mail.outbox:
            self.assertNotIn("List-Unsubscribe", msg.extra_headers)
            self.assertNotIn("unsubscribe", msg.body.lower())
            self.assertIn("You are receiving this message because you registered with Spa 99", msg.body)

    @mock.patch("mailings.sending.enqueue")
    def test_batches_are_paced_and_a_resume_never_sends_twice(self, enqueue):
        m = sending.start(mailing(kind=Mailing.SERVICE), self.admin)  # snapshot only: the worker is stepped by hand
        self.assertEqual(MailingRecipient.objects.filter(mailing=m, status="queued").count(), 3)
        done = MailingRecipient.objects.filter(mailing=m).order_by("email").first()
        done.status = "sent"
        done.save()  # already handled by an earlier slice
        stale = MailingRecipient.objects.filter(mailing=m, status="queued").first()
        MailingRecipient.objects.filter(pk=stale.pk).update(status="sending", updated_at=timezone.now() - datetime.timedelta(hours=1))
        sleeps = []
        with override_settings(Q_CLUSTER={"sync": False}), mock.patch.object(sending, "_sleep", sleeps.append):
            sending.run_mailing(m.pk)
            sending.run_mailing(m.pk)
        self.assertEqual(len(mail.outbox), 1)  # the 'sent' one is not repeated, the interrupted one is not retried
        self.assertEqual(MailingRecipient.objects.get(pk=stale.pk).status, "failed")
        m.refresh_from_db()
        self.assertEqual((m.status, m.sent_count, m.failed_count), (Mailing.SENT, 2, 1))
        # with a rate of 2 a second, 3 more sends need a pause
        m2 = sending.start(mailing(kind=Mailing.SERVICE), self.admin)
        mail.outbox.clear()
        with override_settings(Q_CLUSTER={"sync": False}), mock.patch.object(sending, "_sleep", sleeps.append):
            sending.run_mailing(m2.pk)
        self.assertEqual(len(mail.outbox), 3)
        self.assertTrue(sleeps)

    @mock.patch("mailings.sending.enqueue")
    def test_cancel_stops_the_queued_people(self, enqueue):
        m = sending.start(mailing(), self.admin)
        first = MailingRecipient.objects.filter(mailing=m).order_by("email").first()
        MailingRecipient.objects.filter(pk=first.pk).update(status="sent")  # one already went out
        sending.cancel(m, self.admin)
        m.refresh_from_db()
        self.assertEqual((m.status, m.sent_count, m.skipped_count), (Mailing.CANCELLED, 1, 2))
        self.assertEqual(sending.run_mailing(m.pk), "cancelled")
        self.assertEqual(len(mail.outbox), 0)
        with self.assertRaises(sending.MailingError):
            sending.cancel(m, self.admin)

    def test_people_who_unsubscribe_or_bounce_after_the_list_was_made_are_skipped(self):
        with mock.patch("mailings.sending.enqueue"):
            m = sending.start(mailing(), self.admin)
        member.set_marketing_consent(self.users[0], False)
        suppression.add("p1@example.com", EmailSuppression.HARD_BOUNCE)
        sending.run_mailing(m.pk)
        self.assertEqual([msg.to for msg in mail.outbox], [["p2@example.com"]])
        statuses = dict(MailingRecipient.objects.filter(mailing=m).values_list("email", "status"))
        self.assertEqual(statuses, {"p0@example.com": "skipped", "p1@example.com": "skipped", "p2@example.com": "sent"})

    def test_an_empty_or_invalid_mailing_does_not_start(self):
        with self.assertRaises(sending.MailingError):
            sending.start(mailing(group="tier", params={"plan": "tier-1"}), self.admin)  # nobody in Tier 1
        with self.assertRaises(sending.MailingError):
            sending.start(mailing(body="Hello {nope}"), self.admin)
        self.assertEqual(len(mail.outbox), 0)

    @mock.patch("mailings.sending.enqueue")
    def test_schedule_makes_a_one_off_job_that_starts_the_mailing(self, enqueue):
        from django_q.models import Schedule

        m = mailing()
        with self.assertRaises(sending.MailingError):
            sending.schedule(m, timezone.now() + datetime.timedelta(seconds=5), self.admin)  # too soon
        when = timezone.now() + datetime.timedelta(hours=2)
        sending.schedule(m, when, self.admin)
        m.refresh_from_db()
        job = Schedule.objects.get(name=m.schedule_name)
        self.assertEqual((m.status, job.func, job.schedule_type, job.next_run), (Mailing.SCHEDULED, "mailings.tasks.start_scheduled", Schedule.ONCE, when))
        self.assertEqual(sending.start_scheduled(str(m.pk)), "started")
        m.refresh_from_db()
        self.assertEqual((m.status, m.total_count, Schedule.objects.filter(name=m.schedule_name).count()), (Mailing.SENDING, 3, 0))
        enqueue.assert_called_with("mailings.tasks.send_mailing", str(m.pk))
        self.assertEqual(sending.start_scheduled(str(m.pk)), "not scheduled")  # a second run does nothing

    @override_settings(DEBUG=False, EMAIL_BACKEND="notifications.backends.SesBackend",
                       CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mail-gate"}})
    def test_the_ses_gate_blocks_group_sends_until_production(self):
        cache.clear()
        client = mock.Mock()
        client.get_account.return_value = {"ProductionAccessEnabled": False, "SendQuota": {}}
        with mock.patch("boto3.client", return_value=client):
            with self.assertRaisesMessage(sending.MailingError, "sandbox"):
                sending.start(mailing(), self.admin)
            with self.assertRaisesMessage(sending.MailingError, "sandbox"):
                sending.start_invites("00000000-0000-0000-0000-000000000000", self.admin)
        self.assertFalse(MailingRecipient.objects.exists())
        cache.clear()
        client.get_account.return_value = {"ProductionAccessEnabled": True, "SendQuota": {"MaxSendRate": 1.0}}
        with mock.patch("boto3.client", return_value=client), mock.patch.object(sending, "enqueue"):
            self.assertEqual(sending.start(mailing(), self.admin).total_count, 3)  # production: allowed
            self.assertEqual(sending.rate_per_second(), 1)  # never above what SES allows


class UnsubscribeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_confirm_page_changes_nothing_and_post_turns_news_off_once(self):
        user = person("u@example.com", consent=True)
        token = tokens.make_unsubscribe_token("u@example.com")
        self.assertNotIn("example", token)  # opaque: no address in the link
        self.assertEqual(token, tokens.make_unsubscribe_token("U@example.com"))  # one key per address
        url = f"/unsubscribe/{token}/"
        client = Client()
        self.assertContains(client.get(url), "data-unsubscribe-confirm")
        user.refresh_from_db()
        self.assertTrue(user.marketing_consent)
        self.assertContains(client.post(url), "data-unsubscribe-done")
        user.refresh_from_db()
        self.assertFalse(user.marketing_consent)
        self.assertEqual(User.history.filter(id=user.pk, marketing_consent=False).count(), 1)  # logged in history
        before = User.history.filter(id=user.pk).count()
        # the one-click POST a mail client sends (no CSRF token, no cookie), repeated
        self.assertEqual(Client(enforce_csrf_checks=True).post(url, "List-Unsubscribe=One-Click", content_type="application/x-www-form-urlencoded").status_code, 200)
        self.assertEqual(User.history.filter(id=user.pk).count(), before)
        self.assertEqual(segments.count("everyone", {}, Mailing.NEWS), 0)
        self.assertFalse(EmailOptOut.objects.exists())  # has an account: consent is the record

    def test_an_address_without_an_account_goes_on_the_opt_out_list_and_the_tick_can_come_back(self):
        application("g@example.com", consent=True)
        self.assertTrue(optout.unsubscribe("G@example.com")["changed"])
        self.assertFalse(optout.unsubscribe("g@example.com")["changed"])  # idempotent
        self.assertTrue(EmailOptOut.objects.filter(email="g@example.com").exists())
        self.assertFalse(GoldApplication.objects.get().marketing_consent)
        user_services.register_interest({
            "first_name": "Gil", "last_name": "B", "email": "g@example.com", "password": "a-long-test-password-1", "mobile": "+447912345678",
            "date_of_birth": datetime.date(1990, 1, 1), "plan": "tier-2", "marketing_opt_in": True})
        self.assertFalse(EmailOptOut.objects.exists())  # chose news again when registering

    def test_a_bad_token_is_refused(self):
        self.assertEqual(Client().post("/unsubscribe/not-a-token/").status_code, 400)
        self.assertEqual(Client().get("/unsubscribe/not-a-token/").status_code, 400)


class InviteImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_report_flags_invalid_repeated_members_waiting_and_suppressed(self):
        person("member@example.com")
        suppression.add("bounced@example.com", EmailSuppression.HARD_BOUNCE)
        EmailOptOut.objects.create(email="quiet@example.com")
        Invite.objects.create(name="W", email="waiting@example.com", batch_id="00000000-0000-0000-0000-000000000001", status=Invite.SENT)
        Invite.objects.create(name="D", email="done@example.com", batch_id="00000000-0000-0000-0000-000000000001", status=Invite.REGISTERED)
        report = invites.check(
            "name,email\nAl Smith,al@example.com\nBad,not-an-email\nAl Again,AL@example.com\nMem,member@example.com\n"
            "Bo,bounced@example.com\nWait,waiting@example.com\nDone,done@example.com\nQ,quiet@example.com")
        self.assertEqual([(r["email"], r["status"]) for r in report["rows"]], [
            ("al@example.com", "ok"), ("not-an-email", "invalid"), ("al@example.com", "duplicate"), ("member@example.com", "member"),
            ("bounced@example.com", "suppressed"), ("waiting@example.com", "invited"), ("done@example.com", "ok"), ("quiet@example.com", "opted_out")])
        self.assertEqual((report["ok"], report["total"], report["counts"]["invalid"], report["counts"]["duplicate"]), (2, 8, 1, 1))
        self.assertEqual(report["rows"][0]["line"], 2)  # the header row is skipped, lines count from the file

    def test_csv_and_paste_variants(self):
        for text in ("Al Smith;al@example.com\nBo Jones;bo@example.com", '"Smith, Al","al@example.com"\n"Jones, Bo","bo@example.com"',
                     "al@example.com,Al Smith\nbo@example.com,Bo Jones", "Al Smith <al@example.com>\nBo Jones <bo@example.com>",
                     "al@example.com\n\n  bo@example.com  ", "Name\tEmail\nAl\tal@example.com\nBo\tbo@example.com", "﻿name,email\r\nAl,al@example.com\r\nBo,bo@example.com\r\n"):
            report = invites.check(text.encode() if "﻿" in text else text)
            self.assertEqual([r["email"] for r in report["rows"]], ["al@example.com", "bo@example.com"], text)
            self.assertEqual(report["ok"], 2, text)
        self.assertEqual(invites.check('"Smith, Al","al@example.com"')["rows"][0]["name"], "Smith, Al")

    def test_size_and_row_caps_and_empty_lists(self):
        rows = "\n".join(f"n{i},u{i}@example.com" for i in range(invites.MAX_ROWS))
        self.assertEqual(invites.check(rows)["ok"], invites.MAX_ROWS)
        self.assertIn("more than 2000", invites.check(rows + "\nx,x@example.com")["errors"][0])
        self.assertIn("1 MB", invites.check("a@example.com\n" + "x" * invites.MAX_BYTES)["errors"][0])
        self.assertIn("1 MB", invites.check(b"a@example.com\n" + b"x" * invites.MAX_BYTES)["errors"][0])
        self.assertTrue(invites.check("")["errors"])
        self.assertTrue(invites.check("name,email\n")["errors"])


class InviteFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.admin = User.objects.create_user("dev@example.com", "a-long-test-password-1")

    def send(self, text):
        batch, report = invites.create_batch(text, self.admin)
        sending.start_invites(batch, self.admin)
        return batch

    def test_batch_sends_a_personal_link_with_unsubscribe_and_each_invite_once(self):
        member_user = person("member@example.com")
        batch = self.send("Al Smith,al@example.com\nMem,member@example.com\nbad")
        self.assertEqual(sorted(Invite.objects.filter(batch_id=batch).values_list("email", "status")),
                         [("al@example.com", "sent"), ("member@example.com", "skipped")])
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        invite = Invite.objects.get(email="al@example.com")
        self.assertIn(f"/invite/{invite.token}/", message.body)
        self.assertIn("Hello Al,", message.body)
        self.assertIn("List-Unsubscribe", message.extra_headers)
        self.assertIsNotNone(invite.sent_at)
        sending.run_invites(batch)  # a second run sends nothing
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Invite.objects.get(email="member@example.com").reason, "Already has an account")

    def test_link_marks_opened_prefills_register_and_registering_marks_registered(self):
        batch = self.send("Al Smith,al@example.com")
        invite = Invite.objects.get()
        client = Client()
        response = client.get(f"/invite/{invite.token}/")
        self.assertRedirects(response, "/register/", fetch_redirect_response=False)
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.SENT)  # a link scanner following the redirect does not count as opened
        page = client.get("/register/")
        invite.refresh_from_db()
        self.assertEqual((invite.status, invite.opened_at is not None), (Invite.OPENED, True))  # the Register page really rendered
        self.assertContains(page, 'value="Al"')
        self.assertContains(page, 'value="al@example.com"')
        user = user_services.register_interest({
            "first_name": "Al", "last_name": "Smith", "email": "al@example.com", "password": "a-long-test-password-1", "mobile": "+447912345678",
            "date_of_birth": datetime.date(1990, 1, 1), "plan": "tier-2"}).user
        invite.refresh_from_db()
        self.assertEqual((invite.status, invite.registered_user, invite.registered_at is not None), (Invite.REGISTERED, user, True))
        client.get(f"/invite/{invite.token}/")
        client.get("/register/")  # opening again never downgrades it
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.REGISTERED)

    def test_unknown_and_expired_links_just_go_to_register_and_a_bounce_is_recorded(self):
        self.send("Al Smith,al@example.com")
        invite = Invite.objects.get()
        self.assertRedirects(Client().get("/invite/nonsense/"), "/register/", fetch_redirect_response=False)
        Invite.objects.filter(pk=invite.pk).update(expires_at=timezone.now() - datetime.timedelta(minutes=1))
        client = Client()
        client.get(f"/invite/{invite.token}/")
        client.get("/register/")
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.SENT)  # expired: not marked, no prefill
        self.assertNotContains(client.get("/register/"), 'value="al@example.com"')
        Invite.objects.filter(pk=invite.pk).update(expires_at=timezone.now() + datetime.timedelta(days=1))
        suppression.add("al@example.com", EmailSuppression.HARD_BOUNCE)
        invite.refresh_from_db()
        self.assertEqual(invite.status, Invite.BOUNCED)

    def test_deleting_a_person_erases_their_group_send_rows_and_invites(self):
        user = person("gone@example.com", consent=True)
        with mock.patch("mailings.sending.enqueue"):
            sending.start(mailing(), self.admin)
        Invite.objects.create(name="G", email="gone@example.com", batch_id="00000000-0000-0000-0000-000000000002")
        self.assertEqual(len(user_services.export_user_data(user)["group_emails"]), 1)
        user_services.delete_user_data(user)
        self.assertFalse(MailingRecipient.objects.exists() or Invite.objects.exists())


SES_BACKEND = "notifications.backends.SesBackend"
LOCK_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "mail-lock"}}


class ResilienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.users = [person(f"r{i}@example.com", consent=True) for i in range(2)]
        cls.admin = User.objects.create_user("dev@example.com", "a-long-test-password-1")

    def started(self):
        with mock.patch("mailings.sending.enqueue"):
            return sending.start(mailing(kind=Mailing.SERVICE), self.admin)

    def test_a_slice_pauses_when_ses_stops_allowing_and_resume_needs_the_gate(self):
        m = self.started()
        refusing = sending.ses.SendingRefused("Amazon SES is still in sandbox")
        with mock.patch("mailings.sending.ses.require_sending_allowed", side_effect=refusing):
            self.assertEqual(sending.run_mailing(m.pk), "paused")
            m.refresh_from_db()
            self.assertEqual((m.status, "sandbox" in m.error), (Mailing.PAUSED, True))
            with self.assertRaises(sending.MailingError):
                sending.resume(m)
            with self.assertRaises(sending.MailingError):
                sending.start_invites_resume("00000000-0000-0000-0000-000000000000")
            self.assertEqual(sending.run_invites("00000000-0000-0000-0000-000000000000"), "paused")
        self.assertEqual(len(mail.outbox), 0)
        sending.resume(m)  # allowed again (dev): back to sending and finishes
        m.refresh_from_db()
        self.assertEqual((m.status, len(mail.outbox)), (Mailing.SENT, 2))

    def test_a_paused_mailing_can_be_cancelled(self):
        m = self.started()
        Mailing.objects.filter(pk=m.pk).update(status=Mailing.PAUSED)
        self.assertEqual(sending.cancel(m, self.admin).status, Mailing.CANCELLED)

    def test_ses_throttling_requeues_with_backoff_then_sends(self):
        m = self.started()
        real = sending.send_templated
        calls = []

        def flaky(*args, **kwargs):
            calls.append(args[1])
            if len(calls) == 1:
                from notifications.models import EmailLog
                return EmailLog(status=EmailLog.FAILED, error="ClientError: An error occurred (Throttling) when calling SendEmail")
            return real(*args, **kwargs)

        sleeps = []

        def sleeper(seconds):  # time "passes": the backoff is over
            sleeps.append(seconds)
            MailingRecipient.objects.update(retry_at=None)

        with mock.patch.object(sending, "send_templated", flaky), mock.patch.object(sending, "_sleep", sleeper), \
                mock.patch("mailings.sending.enqueue"):
            sending.run_mailing(m.pk)
        row = MailingRecipient.objects.get(mailing=m, email="r0@example.com")
        self.assertEqual((row.status, row.attempts), ("sent", 1))  # waited for its backoff, then went
        self.assertTrue(sleeps)  # eased off after the throttle
        self.assertEqual(MailingRecipient.objects.filter(mailing=m, status="failed").count(), 0)
        # after five throttles the row fails instead of looping for ever
        row = MailingRecipient.objects.create(mailing=m, email="x@example.com", attempts=sending.MAX_ATTEMPTS - 1)
        self.assertFalse(sending._back_off(MailingRecipient, row.pk, row.attempts))

    @override_settings(CACHES=LOCK_CACHE)
    def test_only_one_worker_runs_a_mailing_at_a_time(self):
        cache.clear()
        m = self.started()
        self.assertTrue(sending._acquire(f"mailing:{m.pk}"))  # another worker holds it
        self.assertEqual(sending.run_mailing(m.pk), "busy")
        self.assertEqual(len(mail.outbox), 0)
        sending._release(f"mailing:{m.pk}")
        with mock.patch("mailings.sending.enqueue"):
            sending.run_mailing(m.pk)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(sending._acquire(f"mailing:{m.pk}"))  # the finished slice released it
        cache.clear()

    def test_erasing_a_gold_applicant_removes_their_group_rows_and_invites(self):
        from gold import services as gold_services

        app = application("nobody@example.com", consent=True)
        m = mailing(kind=Mailing.SERVICE, group="applicants", params={"status": "new"})
        with mock.patch("mailings.sending.enqueue"):
            sending.start(m, self.admin)
        Invite.objects.create(name="N", email="nobody@example.com", batch_id="00000000-0000-0000-0000-000000000003")
        tokens.make_unsubscribe_token("nobody@example.com")
        gold_services.delete_applications("nobody@example.com")
        from mailings.models import UnsubscribeKey
        self.assertFalse(MailingRecipient.objects.filter(email="nobody@example.com").exists() or Invite.objects.exists() or UnsubscribeKey.objects.filter(email="nobody@example.com").exists())
