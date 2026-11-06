"""Office 2, server side: Barry's membership approval, the counts and Revenue, Leads and the approach list, the Registered lists, the wa.me button. Mocked: sync queue, in-memory mail."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from common import levels
from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from journey.models import JourneySession
from office import approvals, counts
from office.models import MembershipReview, MembershipReviewEvent
from office.tests.test_leads import lead, verify
from office.tests.test_office import OFFICE, OfficeTestCase
from outreach import services as outreach
from outreach.models import ArchivedLead, OutreachEntry
from plans import payments
from plans.models import Plan, Sale, Subscription
from plans.sales import sale_price
from plans.tests.helpers import make_team_member
from users import services as user_services
from users.models import InterestRegistration
from users.tests.test_register import cleaned


def call(user, method, path, data=None, **extra):
    client = Client(HTTP_HOST=OFFICE)
    client.force_login(user)
    return getattr(client, method)(path, data or {}, **extra)


class Base(OfficeTestCase):
    def setUp(self):
        self.approver = make_team_member("approver@example.test", levels.OFFICE, approver=True)
        self.reader = make_team_member("reader@example.test", levels.OFFICE)
        self.admin = make_team_member("admin@example.test", levels.ADMIN)

    mobiles = 0

    def member(self, email, plan="tier-2"):
        """A registered person. The Gold plan cannot be registered for (it is by application), so a Gold-plan member is made as an approved invite makes him."""
        type(self).mobiles += 1
        mobile = f"0791112{type(self).mobiles:04d}"
        if plan == "gold":
            from users.models import User

            user = User.objects.create_user(email, "x-Pass-123456")
            InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug="gold"))
            return user
        return user_services.register_interest(cleaned(email=email, plan=plan, mobile=mobile)).user

    def figures(self):
        counts.refresh_approvals()
        return counts.read()


class ApprovalTests(Base):
    def test_everyone_starts_waiting_with_no_row_and_a_decision_is_audited_and_changes_nothing_for_him(self):
        user = self.member("hugo@example.com")
        reg = user.interest
        self.assertFalse(MembershipReview.objects.exists())  # no row means waiting: no backfill needed
        self.assertEqual(self.figures()["memberships"], {"total": 1, "waiting": 1, "approved": 0, "declined": 0})
        before = (reg.plan_id, reg.payment_status, reg.sale_percent_off)
        mail.outbox.clear()
        response = call(self.approver, "post", f"/approvals/{user.pk}/approve/", HTTP_X_REQUESTED_WITH="fetch")
        body = response.json()
        self.assertEqual((body["ok"], body["status"], body["counts"]["approved"], body["counts"]["waiting"]), (True, "approved", 1, 0))
        reg.refresh_from_db()
        self.assertEqual((reg.plan_id, reg.payment_status, reg.sale_percent_off), before)  # his membership is untouched
        self.assertEqual(mail.outbox, [])  # nothing is sent to him
        event = MembershipReviewEvent.objects.get()
        self.assertEqual((event.from_status, event.to_status, event.by_label), ("waiting", "approved", "approver@example.test"))
        call(self.approver, "post", f"/approvals/{user.pk}/decline/")
        call(self.approver, "post", f"/approvals/{user.pk}/undo/")
        self.assertEqual(MembershipReview.objects.get().status, "waiting")
        self.assertEqual(MembershipReviewEvent.objects.count(), 3)
        self.assertEqual(call(self.approver, "post", f"/approvals/{user.pk}/undo/", HTTP_X_REQUESTED_WITH="fetch").json()["result"], "unchanged")

    def test_only_an_approver_or_admin_sees_or_decides_and_gold_members_are_not_in_the_list(self):
        user, gold = self.member("a@example.com"), self.member("g@example.com", plan="gold")
        for who, code in ((self.reader, 403), (self.approver, 200), (self.admin, 200)):
            self.assertEqual(call(who, "get", "/approvals/").status_code, code)
            self.assertEqual(call(who, "get", "/revenue/").status_code, code)
        self.assertEqual(call(self.reader, "post", f"/approvals/{user.pk}/approve/").status_code, 403)
        self.assertEqual(call(self.approver, "get", f"/approvals/{user.pk}/approve/").status_code, 405)  # a decision is a POST
        self.assertEqual(call(self.approver, "post", f"/approvals/{gold.pk}/approve/").status_code, 404)  # a Gold-plan member is approved through Gold
        self.figures()
        context = call(self.approver, "get", "/approvals/?status=waiting").context
        self.assertEqual([r["email"] for r in context["rows"]], ["a@example.com"])
        self.assertEqual({t["status"]: t["count"] for t in context["tabs"]}, {"waiting": 1, "approved": 0, "declined": 0})
        self.assertIn("Nothing here changes anything for the member", context["note"])
        self.assertIsNotNone(call(self.admin, "get", "/").context["cards"])
        self.assertIsNone(call(self.reader, "get", "/").context["cards"])  # the Home cards are Barry's view too

    def test_the_review_is_in_the_staff_export_and_goes_with_the_person(self):
        user = self.member("hugo@example.com")
        approvals.decide(user.pk, "approved", self.approver)
        exported = call(self.admin, "get", f"/people/{user.pk}/export/").json()["membership_review"]
        self.assertEqual((exported["status"], exported["decided_by"], len(exported["changes"])), ("approved", "approver@example.test", 1))
        user_services.delete_user_data(user)
        self.assertFalse(MembershipReview.objects.exists() or MembershipReviewEvent.objects.exists())

    def test_the_member_facing_apps_never_import_the_review(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        for app in ("users", "plans", "pages", "journey", "gold", "mailings", "notifications", "chat"):
            for path in (root / app).rglob("*.py"):
                if "/tests/" in str(path) or "/migrations/" in str(path):
                    continue
                self.assertNotIn("MembershipReview", path.read_text(encoding="utf-8"), str(path))


class RevenueTests(Base):
    def test_revenue_counts_each_members_own_price_gold_from_the_plan_fee_and_keeps_waiting_apart(self):
        from plans.tests.test_payments import make_sale

        tier2 = Plan.objects.get(slug="tier-2")  # £399 ex VAT a month in the seed
        plain = self.member("plain@example.com")
        make_sale(start=-1, end=100)
        sale = self.member("sale@example.com", plan="tier-2")
        self.assertTrue(sale.interest.sale_percent_off)  # holds a kept sale price
        waiting = self.member("waiting@example.com", plan="tier-1")
        for user in (plain, sale):
            approvals.decide(user.pk, "approved", self.approver)
        applicant, _ = gold_services.submit_application(application_data(email="gold@example.com"))
        GoldApplication.objects.filter(pk=applicant.pk).update(status="approved")
        data = self.figures()["revenue"]
        approved = {r["slug"]: r for r in data["approved"]["by_plan"]}
        kept = int((Decimal(tier2.price_ex_vat) * (100 - sale.interest.sale_percent_off) / 100 * 100).quantize(Decimal(1)))
        self.assertEqual(approved["tier-2"]["count"], 2)
        months = sale.interest.sale_months
        full = int(tier2.price_ex_vat * 100)
        self.assertEqual(approved["tier-2"]["year_pence"], full * 12 + kept * months + full * (12 - months))  # his own price: the kept sale price for the sale's months only
        self.assertEqual((approved["gold"]["count"], approved["gold"]["year_pence"]), (1, int(Plan.objects.get(slug="gold").annual_fee * 100)))  # the fee comes from the plan
        self.assertEqual(data["waiting"]["by_plan"][0]["count"] + sum(r["count"] for r in data["waiting"]["by_plan"][1:]), 1)  # only the one waiting person
        self.assertEqual(data["approved"]["year_pence"], sum(r["year_pence"] for r in data["approved"]["by_plan"]))  # the total is the sum of exact pence, never of rounded figures
        view = counts.revenue_view(data, 20)
        self.assertEqual(view["approved"]["year_inc"], Decimal(data["approved"]["year_pence"]) * Decimal("1.2"))
        plans = Plan.objects.get(slug="gold")
        plans.annual_fee = Decimal("250.00")
        plans.save()
        self.assertEqual(self.figures()["revenue"]["gold_fee_pence"], 25000)  # change the fee and the figure follows
        page = call(self.approver, "get", "/revenue/")
        self.assertEqual((page.status_code, page.context["empty"]), (200, False))
        self.assertContains(page, "Not money received")
        del waiting

    def test_a_tier_member_with_a_gold_application_counts_once_at_his_tier_and_declined_counts_nowhere(self):
        user = self.member("both@example.com")
        applicant, _ = gold_services.submit_application(application_data(email="both@example.com"))
        GoldApplication.objects.filter(pk=applicant.pk).update(status="approved", user=user)
        approvals.decide(user.pk, "approved", self.approver)
        stored = self.figures()
        self.assertEqual((stored["gold"]["approved"], stored["memberships"]["approved"]), (1, 1))  # both rings count him
        revenue = stored["revenue"]["approved"]
        self.assertEqual([r["count"] for r in revenue["by_plan"] if r["slug"] in ("tier-2", "gold")], [1, 0])  # but the money counts one plan
        approvals.decide(user.pk, "declined", self.approver)  # a declined Tier counts nowhere: his approved Gold application now counts, as Gold
        self.assertEqual([r["count"] for r in self.figures()["revenue"]["approved"]["by_plan"] if r["slug"] in ("tier-2", "gold")], [0, 1])

    def test_an_agreed_price_on_an_active_subscription_is_his_price(self):
        from datetime import date

        user = self.member("agreed@example.com")
        Subscription.objects.create(registration=user.interest, plan=user.interest.plan, start_date=date(2026, 12, 1), agreed_price_ex_vat=Decimal("350.00"))
        approvals.decide(user.pk, "approved", self.approver)
        row = next(r for r in self.figures()["revenue"]["approved"]["by_plan"] if r["slug"] == "tier-2")
        self.assertEqual(row["year_pence"], 35000 * 12)
        self.assertEqual(approvals.row(InterestRegistration.objects.get(user=user))["month_pence"], 35000)  # the Approvals row uses the same price rule

    def test_cancelled_subscriptions_and_staff_registrations_are_left_out_of_revenue(self):
        from datetime import date

        cancelled, staff, kept = self.member("cancelled@example.com"), self.member("staffer@example.com"), self.member("kept@example.com")
        Subscription.objects.create(registration=cancelled.interest, plan=cancelled.interest.plan, start_date=date(2026, 12, 1), agreed_price_ex_vat=Decimal("50.00"), status=Subscription.CANCELLED)
        type(staff).objects.filter(pk=staff.pk).update(is_staff=True)
        for person in (cancelled, staff, kept):
            approvals.decide(person.pk, "approved", self.approver)
        pending, _ = gold_services.submit_application(application_data(email="staffer@example.com"))
        GoldApplication.objects.filter(pk=pending.pk).update(status="approved", user=staff)  # a staff member's own Gold application is not revenue either
        other, _ = gold_services.submit_application(application_data(email="STAFFER@example.com"))
        GoldApplication.objects.filter(pk=other.pk).update(status="approved", user=None)  # no account link, but his (staff) address
        row = next(r for r in self.figures()["revenue"]["approved"]["by_plan"] if r["slug"] == "tier-2")
        self.assertEqual(row["count"], 1)
        self.assertEqual(row["year_pence"], counts.to_pence(Plan.objects.get(slug="tier-2").price_ex_vat) * 12)
        self.assertEqual(next(r for r in self.figures()["revenue"]["approved"]["by_plan"] if r["slug"] == "gold")["count"], 0)


class RevenueSaleMonthsTests(Base):
    """A kept sale price counts only for the sale's months, then the plan's price (John: 20% off for 6 months is 6 at the sale price and 6 at the full price)."""

    def john(self, percent=20, months=6):
        user = self.member("john@example.com", plan="tier-2")
        InterestRegistration.objects.filter(user=user).update(sale_percent_off=percent, sale_months=months, sale_name="Launch")
        return InterestRegistration.objects.select_related("plan").get(user=user)

    def test_six_months_at_the_sale_price_then_six_at_the_full_price(self):
        reg = self.john()
        full = int(reg.plan.price_ex_vat * 100)
        sale = int((Decimal(reg.plan.price_ex_vat) * 80).quantize(Decimal(1)))
        self.assertEqual(counts.year_pence(reg), sale * 6 + full * 6)

    def test_a_sale_of_twelve_months_or_more_is_twelve_at_the_sale_price(self):
        reg = self.john(months=24)
        self.assertEqual(counts.year_pence(reg), counts.month_pence(reg)[0] * 12)

    def test_no_months_on_the_snapshot_reads_as_one(self):
        reg = self.john(months=None)
        self.assertEqual(counts.year_pence(reg), counts.month_pence(reg)[0] + int(reg.plan.price_ex_vat * 100) * 11)

    def test_an_expired_sale_is_the_full_price_all_year(self):
        reg = self.john()
        reg.sale_expired_at = timezone.now()
        self.assertEqual(counts.year_pence(reg), int(reg.plan.price_ex_vat * 100) * 12)

    def test_an_agreed_price_is_that_price_all_year(self):
        reg = self.john()
        Subscription.objects.create(registration=reg, plan=reg.plan, source=Subscription.MANUAL, start_date=timezone.localdate(), agreed_price_ex_vat=Decimal("100.00"))
        self.assertEqual(counts.year_pence(reg), 10000 * 12)


class RegisteredAndLeadsTests(Base):
    def test_registered_lists_approved_people_with_membership_and_gold_apart_and_the_gold_column_only_while_pending(self):
        a, b, gold = self.member("a@example.com"), self.member("b@example.com"), self.member("g@example.com", plan="gold")
        approvals.decide(a.pk, "approved", self.approver)
        pending, _ = gold_services.submit_application(application_data(email="a@example.com"))
        GoldApplication.objects.filter(pk=pending.pk).update(user=a)
        context = call(self.admin, "get", "/people/").context
        tables = {t["key"]: t for t in context["tables"]}
        self.assertEqual([r["email"] for r in tables["membership"]["rows"]], ["a@example.com"])  # b has not been approved: he waits in Approvals
        self.assertEqual([r["email"] for r in tables["gold"]["rows"]], ["g@example.com"])
        self.assertEqual(tables["membership"]["rows"][0]["gold_application_id"], str(pending.pk))  # an application still in play
        GoldApplication.objects.filter(pk=pending.pk).update(status="approved")
        self.assertEqual(call(self.admin, "get", "/people/?table=membership").context["rows"][0]["gold_application_id"], "")  # approved: no Gold column
        self.assertEqual(call(self.admin, "get", "/people/?table=gold").context["table"], "gold")
        self.assertEqual(call(self.approver, "get", "/people/").context["approvals_line"]["text"], "1 approved, 1 left to approve")  # a decision refreshed the stored counts
        self.assertIsNone(call(self.reader, "get", "/people/").context["approvals_line"])  # Barry's level only
        del b, gold

    def test_adding_to_the_list_takes_a_lead_out_of_leads_and_back_to_leads_or_archive_brings_it_back_from_the_list(self):
        session = lead("a@example.com")
        listed = lambda: [r["email"] for r in call(self.reader, "get", "/leads/").context["rows"]]
        self.assertEqual(listed(), ["a@example.com"])
        outreach.add_to_list(self.admin, lead_email="a@example.com", reason="rang him")
        self.assertEqual(listed(), [])  # on the list = gone from Leads
        entry = OutreachEntry.objects.get()
        rows = call(self.reader, "get", "/outreach/").context["rows"]
        self.assertEqual((rows[0]["is_lead"], bool(rows[0]["to_leads_url"])), (True, True))
        self.assertEqual(call(self.reader, "post", rows[0]["to_leads_url"]).status_code, 403)
        done = call(self.approver, "post", f"/outreach/{entry.pk}/to-leads/", HTTP_X_REQUESTED_WITH="fetch").json()
        self.assertEqual((done["ok"], done["undo"]["email"], listed()), (True, "a@example.com", ["a@example.com"]))
        call(self.approver, "post", done["undo"]["url"], {k: v for k, v in done["undo"].items() if k != "url"})  # Undo: back on the list
        self.assertEqual((listed(), OutreachEntry.objects.count()), ([], 1))
        archived = call(self.approver, "post", f"/outreach/{OutreachEntry.objects.get().pk}/archive/", {"reason": "not a fit"}, HTTP_X_REQUESTED_WITH="fetch").json()
        self.assertEqual((archived["ok"], archived["undo"]["archived"], ArchivedLead.objects.get().reason, OutreachEntry.objects.count()), (True, True, "not a fit", 0))
        del session

    def test_registering_takes_him_off_the_list_by_lookup_only_and_the_tiles_are_true_totals(self):
        lead("a@example.com"), lead("b@example.com")
        outreach.add_to_list(self.admin, lead_email="a@example.com")
        user = user_services.register_interest(cleaned(email="a@example.com")).user
        verify(user)
        self.assertEqual(call(self.admin, "get", "/outreach/").context["counts"], {"open": 0, "done": 0})
        self.assertEqual(OutreachEntry.objects.count(), 1)  # no row was rewritten or deleted
        counts.refresh_approvals()
        tiles = call(self.admin, "get", "/leads/").context["tiles"]
        self.assertEqual(tiles, {"leads_total": 1, "registered_total": 1})  # one lead left (b), one registered (a); "went on to register" is gone

    def test_back_to_leads_removes_older_done_entries_and_adding_again_revives_an_entry_hidden_by_registering(self):
        lead("a@example.com")
        outreach.add_to_list(self.admin, lead_email="a@example.com")
        outreach.mark_done(OutreachEntry.objects.get(), self.admin)
        outreach.add_to_list(self.admin, lead_email="a@example.com")  # a second, open entry beside the done one
        result = outreach.entry_to_leads(OutreachEntry.objects.get(done_at__isnull=True))
        self.assertEqual((result[0], OutreachEntry.objects.count()), (outreach.DONE, 0))
        self.assertEqual([r["email"] for r in call(self.reader, "get", "/leads/").context["rows"]], ["a@example.com"])  # really back in Leads
        outreach.add_to_list(self.admin, lead_email="a@example.com")  # Archive from the list does the same: an older Done entry must not keep him out of Leads
        outreach.mark_done(OutreachEntry.objects.get(), self.admin)
        outreach.add_to_list(self.admin, lead_email="a@example.com")
        outreach.entry_archive(OutreachEntry.objects.get(done_at__isnull=True), self.admin)
        outreach.unarchive_lead("a@example.com", self.admin)
        self.assertEqual(([r["email"] for r in call(self.reader, "get", "/leads/").context["rows"]], OutreachEntry.objects.count()), (["a@example.com"], 0))
        user = user_services.register_interest(cleaned(email="b@example.com")).user
        outreach.add_to_list(self.admin, user=user, reason="first")
        verify(user)  # registering takes him off the list (the row stays, hidden)
        self.assertEqual(call(self.admin, "get", "/outreach/").context["counts"]["open"], 0)
        result, entry = outreach.add_to_list(self.admin, user=user, reason="again")
        self.assertEqual((result, OutreachEntry.objects.count(), entry.reason), (outreach.DONE, 1, "again"))
        self.assertEqual(call(self.admin, "get", "/outreach/").context["counts"]["open"], 1)  # visible again
        self.assertEqual(outreach.add_to_list(self.admin, user=user)[0], outreach.ALREADY)

    def test_the_emailed_tag_and_filters_follow_a_person_or_group_send_and_a_bounce_replaces_it_with_possible_fake(self):
        from mailings.models import Mailing, MailingRecipient
        from outreach.models import PersonMessage

        lead("a@example.com"), lead("b@example.com"), lead("c@example.com")
        PersonMessage.objects.create(email="a@example.com", text="hello", status="sent")
        mailing = Mailing.objects.create(name="m", subject="s", group="leads", kind="news")
        MailingRecipient.objects.create(mailing=mailing, email="b@example.com", status="sent", sent_at=timezone.now())
        rows = {r["email"]: r for r in call(self.reader, "get", "/leads/").context["rows"]}
        self.assertEqual((bool(rows["a@example.com"]["emailed_at"]), bool(rows["b@example.com"]["emailed_at"]), bool(rows["c@example.com"]["emailed_at"])), (True, True, False))
        self.assertEqual(sorted(r["email"] for r in call(self.reader, "get", "/leads/?emailed=1").context["rows"]), ["a@example.com", "b@example.com"])
        from notifications import suppression
        from notifications.models import EmailSuppression

        suppression.add("a@example.com", EmailSuppression.HARD_BOUNCE)
        rows = {r["email"]: r for r in call(self.reader, "get", "/leads/").context["rows"]}
        self.assertEqual((rows["a@example.com"]["bounced"], rows["a@example.com"]["emailed_at"]), (True, ""))
        outreach.add_to_list(self.admin, lead_email="b@example.com")
        self.assertEqual([r["email"] for r in call(self.reader, "get", "/outreach/?emailed=1").context["rows"]], ["b@example.com"])


class WhatsAppButtonTests(Base):
    def test_the_button_is_a_wa_me_link_with_a_mobile_and_gold_respond_and_mark_contacted_follow_it(self):
        session = lead("a@example.com")
        JourneySession.objects.filter(pk=session.pk).update(lead_mobile="+447700900123")
        page = call(self.approver, "get", f"/leads/{session.pk}/")
        self.assertEqual((page.context["whatsapp"]["state"], page.context["whatsapp"]["wa_link"]), ("mobile", "https://wa.me/447700900123"))
        self.assertContains(page, 'href="https://wa.me/447700900123"')
        none = call(self.approver, "get", f"/leads/{lead('b@example.com').pk}/")
        self.assertEqual((none.context["whatsapp"]["state"], none.context["whatsapp"]["wa_link"]), ("none", ""))
        application, _ = gold_services.submit_application(application_data(email="g@example.com"))
        mail.outbox.clear()
        self.assertTrue(call(self.approver, "get", f"/gold/{application.pk}/respond/")["Location"].startswith("https://wa.me/"))
        application.refresh_from_db()
        self.assertEqual(application.status, "new")  # a wa.me click proves nothing, so Respond marks nothing
        self.assertEqual(call(self.reader, "post", f"/gold/{application.pk}/contacted/").status_code, 403)
        call(self.approver, "post", f"/gold/{application.pk}/contacted/")
        application.refresh_from_db()
        self.assertEqual(application.status, "contacted")


class InstallableAppTests(Base):
    def test_the_office_stays_installable_with_a_service_worker_that_does_nothing_else(self):
        manifest = Client(HTTP_HOST=OFFICE).get("/manifest.webmanifest")
        self.assertEqual((manifest.status_code, manifest.json()["display"]), (200, "standalone"))
        worker = Client(HTTP_HOST=OFFICE).get("/sw.js")
        self.assertEqual((worker.status_code, worker["Service-Worker-Allowed"]), (200, "/"))
        self.assertNotIn(b"showNotification", worker.content)  # no push, and no fetch handler: it never holds a page or staff data
        self.assertNotIn(b"addEventListener('fetch'", worker.content)
        self.assertEqual(Client().get("/sw.js").status_code, 404)  # the public site does not serve it


class RevenueAgreedMonthsTests(Base):
    """A reduced price lasts its own months however it was recorded, and those months are stored on the subscription."""

    def john(self, percent=20, months=6):
        user = self.member("john.months@example.com", plan="tier-2")
        InterestRegistration.objects.filter(user=user).update(sale_percent_off=percent, sale_months=months, sale_name="Launch")
        return InterestRegistration.objects.select_related("plan", "user").get(user=user)

    def setup(self, reg, price, months=None):
        return payments.set_up_manually(reg, self.admin, reg.plan, timezone.localdate(), price, "", months)

    def test_the_sale_price_as_the_agreed_price_stores_the_sales_months_and_revenue_uses_them(self):
        reg = self.john()
        price = sale_price(reg.plan, 20)
        sub = self.setup(reg, price)
        self.assertEqual(Subscription.objects.get(pk=sub.pk).agreed_months, 6)
        full = int(reg.plan.price_ex_vat * 100)
        self.assertEqual(counts.year_pence(InterestRegistration.objects.select_related("plan").get(pk=reg.pk)), int(price * 100) * 6 + full * 6)

    def test_the_months_typed_win_and_another_agreed_price_has_no_end(self):
        reg = self.john()
        self.assertEqual(self.setup(reg, sale_price(reg.plan, 20), 3).agreed_months, 3)
        other = InterestRegistration.objects.select_related("plan").get(user=self.member("other.months@example.com", plan="tier-2"))
        self.assertIsNone(self.setup(other, Decimal("100.00")).agreed_months)
        self.assertEqual(counts.year_pence(InterestRegistration.objects.select_related("plan").get(pk=other.pk)), 120000)

    def test_a_sale_live_at_set_up_gives_its_months_when_nothing_is_kept(self):
        reg = InterestRegistration.objects.select_related("plan").get(user=self.member("live.months@example.com", plan="tier-2"))
        now = timezone.now()
        sale = Sale.objects.create(name="Spring", percent_off=50, months_at_price=3, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1))
        sale.plans.add(reg.plan)
        self.assertEqual(self.setup(reg, sale_price(reg.plan, 50)).agreed_months, 3)

    def test_the_stored_total_matches_and_editing_the_sale_later_changes_nothing(self):
        reg = self.john()
        price = sale_price(reg.plan, 20)
        self.setup(reg, price)
        before = counts.year_pence(InterestRegistration.objects.select_related("plan").get(pk=reg.pk))
        Sale.objects.all().delete()
        self.assertEqual(counts.year_pence(InterestRegistration.objects.select_related("plan").get(pk=reg.pk)), before)
        row = next(r for r in counts.revenue()["waiting"]["by_plan"] if r["slug"] == "tier-2")
        self.assertEqual(row["year_pence"], before)

    def test_the_rest_of_the_year_is_at_the_plan_on_the_subscription(self):
        reg = self.john()
        tier3 = Plan.objects.get(slug="tier-3")
        payments.set_up_manually(reg, self.admin, tier3, timezone.localdate(), Decimal("100.00"), "", 6)
        fresh = InterestRegistration.objects.select_related("plan").get(pk=reg.pk)
        expected = 10000 * 6 + int(tier3.price_ex_vat * 100) * 6
        self.assertEqual(counts.year_pence(fresh), expected)
        self.assertEqual(next(r for r in counts.revenue()["waiting"]["by_plan"] if r["slug"] == "tier-2")["year_pence"], expected)

    def test_editing_only_the_note_leaves_the_months_and_empty_clears_them(self):
        reg = self.john()
        price = sale_price(reg.plan, 20)
        sub = self.setup(reg, price, 3)
        payments.edit_manual(sub, self.admin, reg.plan, sub.start_date, price, "a note", 3)
        self.assertEqual(Subscription.objects.get(pk=sub.pk).agreed_months, 3)
        payments.edit_manual(sub, self.admin, reg.plan, sub.start_date, price, "a note", None)
        self.assertIsNone(Subscription.objects.get(pk=sub.pk).agreed_months)

    def test_a_sale_going_live_later_does_not_touch_an_edit_of_the_note(self):
        reg = InterestRegistration.objects.select_related("plan").get(user=self.member("later.months@example.com", plan="tier-2"))
        price = sale_price(reg.plan, 50)
        sub = self.setup(reg, price)
        now = timezone.now()
        sale = Sale.objects.create(name="Later", percent_off=50, months_at_price=3, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1))
        sale.plans.add(reg.plan)
        payments.edit_manual(sub, self.admin, reg.plan, sub.start_date, price, "a note", None)
        self.assertIsNone(Subscription.objects.get(pk=sub.pk).agreed_months)

    def test_changing_the_price_on_an_edit_works_the_months_out_again(self):
        reg = self.john()
        sub = self.setup(reg, Decimal("100.00"))
        self.assertIsNone(sub.agreed_months)
        payments.edit_manual(sub, self.admin, reg.plan, sub.start_date, sale_price(reg.plan, 20), "", None)
        self.assertEqual(Subscription.objects.get(pk=sub.pk).agreed_months, 6)

    def test_months_without_a_price_are_not_stored(self):
        self.assertIsNone(self.setup(self.john(), None, 6).agreed_months)

    def test_a_kept_sale_that_does_not_cover_the_plan_gives_no_months(self):
        reg = self.john()
        now = timezone.now()
        sale = Sale.objects.create(name="Tier 2 only", percent_off=20, months_at_price=6, starts_at=now - timedelta(days=9), ends_at=now - timedelta(days=8))
        sale.plans.add(reg.plan)
        InterestRegistration.objects.filter(pk=reg.pk).update(sale=sale)
        reg = InterestRegistration.objects.select_related("plan", "sale").get(pk=reg.pk)
        tier3 = Plan.objects.get(slug="tier-3")
        sub = payments.set_up_manually(reg, self.admin, tier3, timezone.localdate(), sale_price(tier3, 20), "")
        self.assertIsNone(sub.agreed_months)

    def test_the_backfill_uses_a_sale_live_at_set_up_and_lists_a_reduced_price_it_cannot_read(self):
        now = timezone.now()
        reg = InterestRegistration.objects.select_related("plan").get(user=self.member("window.months@example.com", plan="tier-2"))
        sale = Sale.objects.create(name="Past", percent_off=50, months_at_price=3, starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=4))
        sale.plans.add(reg.plan)
        sub = Subscription.objects.create(registration=reg, plan=reg.plan, start_date=timezone.localdate(), agreed_price_ex_vat=sale_price(reg.plan, 50))
        Subscription.objects.filter(pk=sub.pk).update(created_at=now - timedelta(days=4, hours=12))
        odd = InterestRegistration.objects.select_related("plan").get(user=self.member("odd.months@example.com", plan="tier-2"))
        unclear = Subscription.objects.create(registration=odd, plan=odd.plan, start_date=timezone.localdate(), agreed_price_ex_vat=Decimal("1.00"))
        out = StringIO()
        call_command("backfill_agreed_months", stdout=out)
        self.assertEqual(Subscription.objects.get(pk=sub.pk).agreed_months, 3)
        self.assertIn(f"LOOK AT  subscription {unclear.pk}", out.getvalue())

    def test_the_report_leaves_out_people_revenue_does_not_count(self):
        now = timezone.now()
        declined = self.member("declined.months@example.com", plan="tier-2")
        cancelled = self.member("cancelled.months@example.com", plan="tier-2")
        paying = self.member("paying.months@example.com", plan="tier-2")
        counted = self.member("counted.months@example.com", plan="tier-2")
        sale = Sale.objects.create(name="Report", percent_off=10, months_at_price=2, starts_at=now - timedelta(days=2), ends_at=now - timedelta(hours=1))
        sale.plans.add(counted.interest.plan)
        InterestRegistration.objects.filter(user__in=[declined, cancelled, paying, counted]).update(created_at=now - timedelta(days=1))
        MembershipReview.objects.create(registration=declined.interest, status=counts.DECLINED)
        Subscription.objects.create(registration=cancelled.interest, plan=cancelled.interest.plan, start_date=timezone.localdate(), status=Subscription.CANCELLED)
        Subscription.objects.create(registration=paying.interest, plan=paying.interest.plan, start_date=timezone.localdate(), agreed_price_ex_vat=Decimal("100.00"))
        out = StringIO()
        call_command("backfill_agreed_months", dry_run=True, stdout=out)
        self.assertIn("no sale price stored: 1", out.getvalue())
        self.assertIn(counted.public_id, out.getvalue())

    def test_the_backfill_dry_run_writes_nothing_then_fills_only_the_sale_price(self):
        reg = self.john()
        sub = Subscription.objects.create(registration=reg, plan=reg.plan, start_date=timezone.localdate(), agreed_price_ex_vat=sale_price(reg.plan, 20))
        other = InterestRegistration.objects.get(user=self.member("left.months@example.com", plan="tier-2"))
        InterestRegistration.objects.filter(pk=other.pk).update(sale_percent_off=20, sale_months=6)
        left = Subscription.objects.create(registration=other, plan=other.plan, start_date=timezone.localdate(), agreed_price_ex_vat=Decimal("1.00"))
        out = StringIO()
        call_command("backfill_agreed_months", dry_run=True, stdout=out)
        self.assertIn("to fill: 1", out.getvalue())
        self.assertIsNone(Subscription.objects.get(pk=sub.pk).agreed_months)
        call_command("backfill_agreed_months", stdout=StringIO())
        self.assertEqual(Subscription.objects.get(pk=sub.pk).agreed_months, 6)
        self.assertIsNone(Subscription.objects.get(pk=left.pk).agreed_months)

    def test_the_backfill_reports_a_sale_registration_with_nothing_stored(self):
        now = timezone.now()
        user = self.member("gap.months@example.com", plan="tier-2")
        sale = Sale.objects.create(name="Gap", percent_off=10, months_at_price=2, starts_at=now - timedelta(days=2), ends_at=now - timedelta(hours=1))
        sale.plans.add(user.interest.plan)
        InterestRegistration.objects.filter(user=user).update(created_at=now - timedelta(days=1))
        out = StringIO()
        call_command("backfill_agreed_months", dry_run=True, stdout=out)
        self.assertIn("no sale price stored: 1", out.getvalue())
        self.assertIn(user.public_id, out.getvalue())
