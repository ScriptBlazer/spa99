"""The payment window: open once, send once, remind once, close, keep the snapshot, manual set-up, staff warnings. Mocked: the local
mail outbox only, no real sending, no Stripe."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone

from notifications.models import NotificationTemplate
from plans import payments
from plans.management.commands.seed_phase1 import seed_all
from plans.models import PaymentMark, PaymentNotice, PaymentStaffAlert, PaymentWindow, Plan, Subscription
from plans.tests.test_sales import make_sale
from system.models import SiteDefaults, SystemEvent
from users import services
from users.models import InterestRegistration, User
from users.tests.test_register import cleaned

DAY = timedelta(days=1)


class PaymentCase(TestCase):
    def setUp(self):
        seed_all()
        SiteDefaults.objects.update(staff_alert_emails="")  # the seed's starting address is not part of these tests
        self.n = 0
        self.dev = User.objects.create_user("dev@example.com", "x", is_staff=True)

    def member(self, plan="tier-2", verified=True):
        self.n += 1
        user = services.register_interest(cleaned(email=f"m{self.n}@example.com", mobile=f"0791234567{self.n}", plan=plan)).user
        if verified:
            user.email_verified_at = timezone.now()
            user.save()
        return user.interest

    def mails(self, subject_part="membership"):
        return [m for m in mail.outbox if subject_part in m.subject.lower()]


class OpenAndSendTests(PaymentCase):
    def test_opening_twice_emails_each_member_once_and_makes_one_window(self):
        a, b = self.member(), self.member()
        self.member(verified=False)  # not emailed until the address is confirmed
        gold = self.member()  # Gold members go through the same window
        InterestRegistration.objects.filter(pk=gold.pk).update(plan=Plan.objects.get(slug="gold"))
        _, first = payments.open_now(self.dev)
        _, second = payments.open_now(self.dev)
        self.assertEqual((first, second), (True, False))
        self.assertEqual(PaymentWindow.objects.count(), 1)
        self.assertEqual(len(self.mails()), 3)  # a, b and the Gold member
        self.assertEqual(PaymentNotice.objects.filter(status="sent").count(), 3)
        payments.send_slice(str(PaymentWindow.objects.get().pk))  # a worker running again sends nothing more
        self.assertEqual(len(self.mails()), 3)
        self.assertEqual(payments.counts()["registered"], 3)  # Gold is counted
        a.refresh_from_db()
        self.assertEqual((a.payment_status, a.payment_invite_sent_at is not None), ("invited", True))
        window = PaymentWindow.objects.get()
        self.assertEqual(timezone.localtime(window.closes_at).date(), timezone.localdate() + 14 * DAY)

    def test_the_database_refuses_a_second_active_window_and_a_second_notice(self):
        window, _ = payments.open_now(self.dev)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentWindow.objects.create(status="scheduled")
        reg = self.member()
        PaymentNotice.objects.create(window=window, registration=reg, kind="invite")
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentNotice.objects.create(window=window, registration=reg, kind="invite")

    def test_wording_is_editable_and_the_sale_line_is_only_for_sale_holders(self):
        make_sale(start=-1, end=100)
        holder = self.member("tier-2")
        InterestRegistration.objects.filter(plan__slug="tier-1").count()
        plain = self.member("tier-1")  # not covered by the sale? make_sale covers tier-2 and tier-3
        row = NotificationTemplate.objects.get(key="payment_window_open")
        row.body = "Hi {first_name}, until {closes_on}.\n\n{sale_line}\n\n{button}"
        row.save()
        payments.open_now(self.dev)
        by = {m.to[0]: m for m in self.mails()}
        self.assertIn("20% off", by[holder.user.email].body)
        self.assertIn("until", by[holder.user.email].body)
        self.assertNotIn("launch price", by[plain.user.email].body)
        self.assertIn("/account/membership/", by[plain.user.email].body)

    def test_a_scheduled_opening_holds_back_when_more_members_than_confirmed_and_opens_with_fewer(self):
        from system.models import SystemEvent

        self.member()
        self.member()
        when = timezone.now() + timedelta(hours=2)
        payments.schedule(self.dev, when, confirmed=2)
        self.member()  # a third registers before the time comes
        payments.tick(now=when + timedelta(minutes=1))
        window = PaymentWindow.objects.get()
        self.assertEqual(window.status, "cancelled")
        self.assertIn("3 members now, 2 confirmed", window.note)
        self.assertEqual(len(self.mails()), 0)
        self.assertTrue(SystemEvent.objects.filter(kind="payments_cancelled", detail__confirmed=2).exists())
        payments.schedule(self.dev, when + timedelta(days=1), confirmed=5)  # fewer than confirmed is fine
        payments.tick(now=when + timedelta(days=1, minutes=1))
        self.assertEqual(PaymentWindow.objects.get(status="open").confirmed_count, 5)
        self.assertEqual(len(self.mails()), 3)

    def test_scheduled_opening_happens_through_the_job_not_before(self):
        self.member()
        when = timezone.now() + timedelta(hours=2)
        payments.schedule(self.dev, when)
        with self.assertRaises(ValidationError):
            payments.schedule(self.dev, timezone.now())  # too soon
        self.assertIn("no window", payments.tick())  # nothing has opened yet; only the opening waits
        self.assertEqual(len(self.mails()), 0)
        payments.tick(now=when + timedelta(minutes=1))
        self.assertEqual(PaymentWindow.objects.get().status, "open")
        self.assertEqual(len(self.mails()), 1)
        self.assertTrue(payments.cancel_schedule(self.dev) is False)


class ReminderAndCloseTests(PaymentCase):
    def test_one_reminder_at_the_right_day_and_never_to_paid_members(self):
        waiting, done = self.member(), self.member()
        window, _ = payments.open_now(self.dev)
        payments.mark_paid(done, "stripe", key="evt_1")
        due = window.closes_at - 3 * DAY
        payments.tick(now=due - timedelta(hours=1))
        self.assertEqual(len(self.mails("gentle reminder")), 0)
        payments.tick(now=due + timedelta(hours=1))
        payments.tick(now=due + timedelta(hours=2))
        reminders = self.mails("gentle reminder")
        self.assertEqual([m.to[0] for m in reminders], [waiting.user.email])
        self.assertIsNotNone(PaymentWindow.objects.get().reminder_sent_at)

    def test_closing_ends_unpaid_sale_prices_but_keeps_snapshot_account_and_paid_members(self):
        make_sale(start=-1, end=100)
        unpaid, paid, plain = self.member("tier-2"), self.member("tier-2"), self.member("tier-1")
        payments.open_now(self.dev)
        payments.mark_paid(paid, "stripe", key="evt_2")
        window = PaymentWindow.objects.get()
        counts = payments.tick(now=window.closes_at + timedelta(minutes=1))
        self.assertIn("closed", counts)
        for row in (unpaid, paid, plain):
            row.refresh_from_db()
        self.assertEqual((unpaid.payment_status, unpaid.sale_percent_off, unpaid.sale_name), ("lapsed", 20, "Christmas sale"))
        self.assertIsNotNone(unpaid.sale_expired_at)
        self.assertTrue(User.objects.filter(pk=unpaid.user_id, is_active=True).exists())
        self.assertEqual((paid.payment_status, paid.sale_expired_at), ("paid", None))
        self.assertEqual((plain.payment_status, plain.sale_expired_at), ("lapsed", None))
        self.assertIsNone(payments.close())  # closing twice does nothing
        self.assertEqual(PaymentWindow.objects.get().status, "closed")

    def test_mark_paid_is_idempotent_on_its_key(self):
        reg = self.member()
        self.assertTrue(payments.mark_paid(reg, "stripe", key="evt_9"))
        self.assertFalse(payments.mark_paid(reg, "stripe", key="evt_9"))
        self.assertEqual(PaymentMark.objects.count(), 1)


class LateRestoreGoldTests(PaymentCase):
    def test_a_registrant_after_payments_open_gets_the_email_no_window_no_lapse_no_reminder_and_no_sale_snapshot(self):
        make_sale(start=-1, end=1000)
        before = self.member("tier-2")
        window, _ = payments.open_now(self.dev)
        self.assertEqual(before.refresh_from_db() or before.sale_percent_off, 20)  # before opening the price is kept for the window
        late = self.member("tier-2")  # the sale still runs, but payments are open: no snapshot
        self.assertIsNone(late.sale_percent_off)
        payments.tick(now=window.opened_at + 6 * DAY)
        late.refresh_from_db()
        self.assertEqual((late.payment_status, late.payment_due_at), ("invited", None))
        sent = [m for m in self.mails("can now be set up") if m.to == [late.user.email]]
        self.assertEqual(len(sent), 1)
        self.assertNotIn("You have until", sent[0].body)
        payments.tick(now=window.closes_at + timedelta(minutes=1))  # the window closes: the first lapses, the late one is not touched
        payments.tick(now=window.closes_at + 30 * DAY)
        late.refresh_from_db(), before.refresh_from_db()
        self.assertEqual((before.payment_status, late.payment_status), ("lapsed", "invited"))
        self.assertEqual(len(self.mails("gentle reminder")), 0)
        after_close = self.member("tier-1")  # registered after it closed: still the email, still no timer
        payments.tick(now=window.closes_at + 31 * DAY)
        after_close.refresh_from_db()
        self.assertEqual((after_close.payment_status, after_close.payment_due_at, after_close.sale_percent_off), ("invited", None, None))

    def test_a_sale_holder_who_confirms_after_the_window_closed_gets_their_own_due_date(self):
        make_sale(start=-1, end=1000)
        slow, plain = self.member("tier-2", verified=False), self.member("tier-1", verified=False)  # registered before opening, not confirmed
        window, _ = payments.open_now(self.dev)
        after = window.closes_at + 5 * DAY
        for reg in (slow, plain):
            User.objects.filter(pk=reg.user_id).update(email_verified_at=after)
        payments.tick(now=after)
        slow.refresh_from_db(), plain.refresh_from_db()
        self.assertEqual(timezone.localtime(slow.payment_due_at).date(), timezone.localtime(after).date() + 14 * DAY)
        self.assertIsNone(plain.payment_due_at)
        self.assertIn("You have until", [m for m in self.mails("can now be set up") if m.to == [slow.user.email]][0].body)
        payments.tick(now=slow.payment_due_at + timedelta(minutes=1))
        slow.refresh_from_db()
        self.assertEqual(slow.payment_status, "lapsed")
        self.assertIsNotNone(slow.sale_expired_at)

    def test_restoring_a_lapsed_sale_price_needs_a_reason_and_is_audited(self):
        make_sale(start=-1, end=1000)
        reg = self.member("tier-2")
        window, _ = payments.open_now(self.dev)
        payments.close(now=window.closes_at + timedelta(minutes=1))
        reg.refresh_from_db()
        self.assertIsNotNone(reg.sale_expired_at)
        for bad in ("", "  ", "x"):
            with self.assertRaises(ValidationError):
                payments.restore_sale(reg, self.dev, bad)
        payments.restore_sale(reg, self.dev, "Was on holiday")
        reg.refresh_from_db()
        self.assertEqual((reg.sale_expired_at, reg.payment_status, reg.sale_percent_off), (None, "invited", 20))
        self.assertGreater(reg.payment_due_at, timezone.now() + 13 * DAY)
        event = SystemEvent.objects.get(kind="sale_restored")
        self.assertNotIn("reason", event.detail)  # the reason lives on the member's own record, not in the audit log
        self.assertEqual(reg.sale_restore_reason, "Was on holiday")
        self.assertIn("dev@example.com", event.sentence)
        with self.assertRaises(ValidationError):
            payments.restore_sale(reg, self.dev, "Again")  # nothing left to restore

    def test_gold_members_are_in_the_alerts_and_a_sale_price_is_never_granted_to_a_non_sale_registrant(self):
        gold = self.member("tier-2")
        InterestRegistration.objects.filter(pk=gold.pk).update(plan=Plan.objects.get(slug="gold"), sale_name="Old", sale_percent_off=10, sale_months=1,
                                                               sale_locked_at=timezone.now())
        window, _ = payments.open_now(self.dev)
        warning = payments.staff_warning(window.closes_at - 5 * DAY)
        self.assertEqual(warning["count"], 1)
        outsider = self.member("tier-2")  # registered with no sale running: nothing granted
        self.assertIsNone(outsider.sale_percent_off)


class ReviewFixTests(PaymentCase):
    def test_cancelling_a_manual_setup_restores_the_right_due_date(self):
        make_sale(start=-1, end=1000)
        early = self.member("tier-2")
        window, _ = payments.open_now(self.dev)
        late = self.member("tier-2")
        payments.tick(now=window.opened_at + DAY)
        plan = Plan.objects.get(slug="tier-2")
        for reg in (early, late):
            sub = payments.set_up_manually(reg, self.dev, plan, date(2026, 12, 1))
            payments.cancel_manual(sub, self.dev)
            reg.refresh_from_db()
            self.assertEqual(reg.payment_status, "invited")
        self.assertEqual(early.payment_due_at, window.closes_at)  # not a fresh 14 days
        self.assertIsNone(late.payment_due_at)
        payments.close(now=window.closes_at + timedelta(minutes=1))
        gone = self.member("tier-2")  # sale holder, confirmed after close: own date, cannot last forever
        InterestRegistration.objects.filter(pk=early.pk).update(payment_status="paid")
        sub = payments.set_up_manually(early, self.dev, plan, date(2026, 12, 1))
        early.refresh_from_db()
        InterestRegistration.objects.filter(pk=early.pk).update(sale_expired_at=None, sale_percent_off=20, sale_months=3)
        early.refresh_from_db()
        payments.cancel_manual(sub, self.dev)
        early.refresh_from_db()
        self.assertEqual(early.payment_status, "invited")
        self.assertGreater(early.payment_due_at, timezone.now() + 13 * DAY)

    def test_edits_are_audited_and_the_log_has_no_emails_or_reasons(self):
        make_sale(start=-1, end=1000)
        reg = self.member("tier-2")
        plan = Plan.objects.get(slug="tier-2")
        payments.open_now(self.dev)
        sub = payments.set_up_manually(reg, self.dev, plan, date(2026, 12, 1), Decimal("300"), "note")
        payments.edit_manual(sub, self.dev, plan, date(2026, 12, 9), Decimal("320"), "new note")
        payments.cancel_manual(sub, self.dev)
        event = SystemEvent.objects.get(kind="setup_edited")
        self.assertEqual((event.detail["old"]["start_date"], event.detail["new"]["agreed_price_ex_vat"]), ("2026-12-01", "320"))
        payments.close(early=True)
        payments.restore_sale(reg, self.dev, "Secret private reason")
        text = " ".join(f"{e.sentence} {e.detail}" for e in SystemEvent.objects.filter(kind__in=["setup_manual", "setup_edited", "sale_restored"]))
        self.assertNotIn(reg.user.email, text)
        self.assertNotIn("Secret private reason", text)
        self.assertIn(reg.user.public_id, text)
        reg.refresh_from_db()
        self.assertEqual(reg.sale_restore_reason, "Secret private reason")

    def test_job_keeps_working_while_the_next_window_is_scheduled_and_alerts_wait_for_nine(self):
        make_sale(start=-1, end=1000)
        self.member("tier-2")
        window, _ = payments.open_now(self.dev)
        payments.close(early=False, now=window.closes_at + timedelta(minutes=1))
        payments.schedule(self.dev, timezone.now() + 30 * DAY)
        late = self.member("tier-1")
        payments.tick()
        late.refresh_from_db()
        self.assertEqual(late.payment_status, "invited")  # the late invite still went out
        SiteDefaults.objects.update(staff_alert_emails="a@example.com")
        reg = self.member("tier-2")
        InterestRegistration.objects.filter(pk=reg.pk).update(payment_status="invited", payment_due_at=timezone.now() + 3 * DAY, sale_percent_off=20, sale_months=1)
        early_morning = timezone.make_aware(__import__("datetime").datetime.combine(timezone.localdate(), __import__("datetime").time(8, 0)))
        self.assertIsNone(payments.run_staff_alert(early_morning))
        SiteDefaults.objects.update(payment_staff_alert_hour=10)  # the hour is a System default
        self.assertIsNone(payments.run_staff_alert(early_morning.replace(hour=9, minute=5)))
        SiteDefaults.objects.update(payment_staff_alert_hour=9)
        self.assertIsNotNone(payments.run_staff_alert(early_morning.replace(hour=9, minute=5)))

    def test_member_page_copy_for_set_up_members_and_before_stripe(self):
        from django.test import Client
        from plans.models import SiteSettings

        reg = self.member("tier-2")
        payments.open_now(self.dev)
        client = Client(HTTP_HOST="localhost")
        client.force_login(reg.user)
        page = client.get("/account/membership/")
        self.assertContains(page, "be in touch to set up your membership")
        payments.mark_paid(reg, "manual", key="k1")
        self.assertContains(client.get("/account/membership/"), "Your membership is set up.")
        self.assertContains(self.dev_page(), "Card payments are not live yet")

    def dev_page(self):
        from system.tests.test_system import make_user, unlocked_client

        return unlocked_client(make_user("sys@example.com")).get("/payments/")


class ManualSetupTests(PaymentCase):
    def test_manual_setup_keeps_the_price_is_single_and_can_be_cancelled(self):
        make_sale(start=-1, end=100)
        reg = self.member("tier-2")
        payments.open_now(self.dev)
        plan = Plan.objects.get(slug="tier-2")
        sub = payments.set_up_manually(reg, self.dev, plan, date(2026, 12, 1), Decimal("350.00"), "Pays by standing order")
        with self.assertRaises(ValidationError):
            payments.set_up_manually(reg, self.dev, plan, date(2026, 12, 1))  # a second click
        self.assertEqual(Subscription.objects.filter(status="active").count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subscription.objects.create(registration=reg, plan=plan, start_date=date(2026, 12, 2))  # the database says so too
        reg.refresh_from_db()
        self.assertEqual((reg.payment_status, reg.payment_source), ("paid", "manual"))
        payments.close(now=timezone.now() + 20 * DAY)
        reg.refresh_from_db()
        self.assertEqual((reg.payment_status, reg.sale_expired_at, reg.sale_percent_off), ("paid", None, 20))
        self.assertEqual(payments.counts()["set_up_manually"], 1)
        self.assertTrue(SystemEvent.objects.filter(kind="setup_manual").exists())
        payments.edit_manual(sub, self.dev, plan, date(2026, 12, 5), None, "Changed")
        sub.refresh_from_db()
        self.assertEqual(sub.start_date, date(2026, 12, 5))
        self.assertTrue(payments.cancel_manual(sub, self.dev))
        reg.refresh_from_db()
        self.assertEqual((reg.payment_status, reg.paid_at), ("invited", None))  # payments were opened before: the sale holder gets their own date
        self.assertGreater(reg.payment_due_at, timezone.now() + 13 * DAY)
        self.assertEqual(sub.history.count(), 3)


class StaffWarningTests(PaymentCase):
    def prepare(self):
        make_sale(start=-1, end=100)
        self.member("tier-2")
        window, _ = payments.open_now(self.dev)
        return window.closes_at - 6 * DAY - timedelta(hours=12)  # inside the 7 day warning period

    def test_no_address_means_no_email_but_the_notice_and_the_row_still_exist(self):
        now = self.prepare()
        before = len(mail.outbox)
        alert = payments.run_staff_alert(now)
        self.assertIsNotNone(alert)
        self.assertEqual(len(mail.outbox), before)
        self.assertEqual(payments.staff_warning(now)["count"], 1)
        self.assertTrue(payments.alert_addresses() == [])

    def test_addresses_in_defaults_are_emailed_once_a_day_and_it_stops_when_nobody_is_at_risk(self):
        now = self.prepare()
        SiteDefaults.objects.update(staff_alert_emails="one@example.com, two@example.com")
        self.assertIsNone(payments.staff_warning(now - 3 * DAY))  # not yet
        payments.run_staff_alert(now)
        self.assertIsNone(payments.run_staff_alert(now + timedelta(minutes=5)))  # the same day: nothing more
        sent = [m for m in mail.outbox if "launch price" in m.subject]
        self.assertEqual(sorted(m.to[0] for m in sent), ["one@example.com", "two@example.com"])
        self.assertIn("will lose their launch price", sent[0].body)
        payments.run_staff_alert(now + DAY)
        self.assertEqual(PaymentStaffAlert.objects.count(), 2)
        InterestRegistration.objects.update(payment_status="paid")
        self.assertIsNone(payments.run_staff_alert(now + 2 * DAY))

    def test_seed_fills_the_alert_address_only_when_empty(self):
        SiteDefaults.objects.update(staff_alert_seeded=False)
        call_command("seed_phase1", stdout=open("/dev/null", "w"))
        self.assertEqual(SiteDefaults.load().staff_alert_emails, "moishe@spa99.uk")
        SiteDefaults.objects.update(staff_alert_emails="someone@else.example")
        call_command("seed_phase1", stdout=open("/dev/null", "w"))
        self.assertEqual(SiteDefaults.load().staff_alert_emails, "someone@else.example")
        SiteDefaults.objects.update(staff_alert_emails="")  # cleared on purpose: the seed does not refill it
        call_command("seed_phase1", stdout=open("/dev/null", "w"))
        self.assertEqual(SiteDefaults.load().staff_alert_emails, "")
        SiteDefaults.objects.update(staff_alert_emails="a@example.com", staff_alert_emails_on=False)
        self.assertEqual(payments.alert_addresses(), [])  # the switch stops the emails, the field stays

    def test_the_defaults_field_takes_at_most_five_valid_addresses(self):
        from system.models import validate_staff_alert_emails

        validate_staff_alert_emails("a@x.com,b@x.com")
        for bad in ("nope", ",".join(f"a{i}@x.com" for i in range(6))):
            with self.assertRaises(ValidationError):
                validate_staff_alert_emails(bad)


class ScreenTests(PaymentCase):
    def dev_client(self):
        from system.tests.test_system import make_user, unlocked_client

        return unlocked_client(make_user("system@example.com"))

    def test_system_payments_page_opens_payments_once_and_is_for_unlocked_developers_only(self):
        from system.tests.test_system import make_user, sign_in

        self.member()
        self.assertEqual(sign_in(make_user("o@example.com", system=False))[0].get("/payments/").status_code, 404)
        client = self.dev_client()
        page = client.get("/payments/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-confirm-url")  # the pop-up asks the server who and how many
        self.assertEqual(client.get("/payments/confirm/").json()["count"], 1)
        client.post("/payments/open/")  # a stray POST with no confirmation sends nothing
        client.post("/payments/open/", {"confirm": "yes", "expected_count": "9"})  # a number the pop-up did not show
        self.assertEqual(len(self.mails()), 0)
        client.post("/payments/open/", {"confirm": "yes", "expected_count": "1"})
        client.post("/payments/open/", {"confirm": "yes", "expected_count": "1"})
        self.assertEqual(len(self.mails()), 1)
        self.assertEqual(client.get("/payments/").context["counts"]["invited"], 1)
        client.post("/payments/close/")
        self.assertEqual(PaymentWindow.objects.get().status, "closed")

    def test_office_shows_the_sale_holder_and_only_admins_can_set_up_manually(self):
        from common import levels
        from plans.tests.helpers import make_team_member

        make_sale(start=-1, end=100)
        holder = self.member("tier-2")
        self.member("tier-1")
        admin, office = make_team_member("ad@example.com", levels.ADMIN), make_team_member("of@example.com", levels.OFFICE)
        c = Client(HTTP_HOST="office.localhost")
        c.force_login(office)
        rows = c.get("/people/?sale=yes").context["rows"]
        self.assertEqual([r["email"] for r in rows], [holder.user.email])
        self.assertEqual(rows[0]["sale"], "20% for 3 months")
        self.assertContains(c.get(f"/people/{holder.user_id}/"), "Christmas sale")
        self.assertEqual(c.post(f"/people/{holder.user_id}/setup/", {"plan": Plan.objects.get(slug="tier-2").pk, "start_date": "2026-12-01"}).status_code, 403)
        c.force_login(admin)
        data = {"plan": Plan.objects.get(slug="tier-2").pk, "start_date": "2026-12-01", "agreed_price": "350", "billing_note": "x"}
        c.post(f"/people/{holder.user_id}/setup/", data)
        c.post(f"/people/{holder.user_id}/setup/", data)  # double click
        self.assertEqual(Subscription.objects.count(), 1)
        self.assertContains(c.get(f"/people/{holder.user_id}/"), "Set up manually")
        self.assertIn("sale_status", c.get("/people/export.csv").content.decode())

    def test_export_includes_the_payment_state(self):
        reg = self.member()
        payments.open_now(self.dev)
        data = services.export_user_data(reg.user)["interest"]["payment"]
        self.assertEqual(data["status"], "invited")
        self.assertEqual(len(data["notices"]), 1)

    def test_registration_copy_says_no_payment_now_and_hides_whatsapp_when_blank(self):
        from plans.models import SiteSettings

        page = Client(HTTP_HOST="localhost").get("/register/")
        self.assertContains(page, "No payment is taken now")
        self.assertContains(page, "2 weeks")
        self.assertNotContains(page, "WhatsApp us")
        SiteSettings.objects.update(discount_contact_url="https://wa.me/447000000000")
        self.assertContains(Client(HTTP_HOST="localhost").get("/register/"), "WhatsApp us")
