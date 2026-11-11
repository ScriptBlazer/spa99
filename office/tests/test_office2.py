"""Office 2, server side: Barry's membership approval, the counts and Revenue, Leads and the approach list, the Registered lists, the wa.me button. Mocked: sync queue, in-memory mail."""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from common import levels
from common.validators import validate_sensible_year
from office.templatetags.office_tags import bp_rate
from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from insights.models import OfficeSnapshot
from journey.models import JourneySession
from office import approvals, counts
from office.models import MembershipReview, MembershipReviewEvent
from office.templatetags.office_tags import pounds_compact
from office.tests.test_leads import lead, verify
from office.tests.test_office import OFFICE, OfficeTestCase
from outreach import services as outreach
from outreach.models import ArchivedLead, OutreachEntry
from plans import payments
from plans.models import Plan, Sale, SiteSettings, Subscription
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

    def test_a_decision_updates_the_membership_counts_at_once_without_a_revenue_recount_and_still_asks_for_a_refresh(self):
        first, second = self.member("a@example.com"), self.member("b@example.com")
        self.figures()
        with mock.patch.object(counts, "revenue") as revenue, mock.patch("office.snapshots.request_refresh") as ask:
            approvals.decide(first.pk, "approved", self.approver)
            self.assertEqual(counts.read()["memberships"], {"total": 2, "waiting": 1, "approved": 1, "declined": 0})
            approvals.decide(second.pk, "declined", self.approver)
            self.assertEqual(counts.read()["memberships"], {"total": 2, "waiting": 0, "approved": 1, "declined": 1})
        revenue.assert_not_called()
        ask.assert_called()
        self.assertEqual(counts.read()["memberships"], counts._by_status(counts.membership_people()))

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


class ManualSetupCardTests(Base):
    def test_a_set_up_whose_staff_member_has_gone_still_opens_the_person(self):
        """created_by empties when that staff account is deleted (SET_NULL): the page says so and never breaks."""
        user = self.member("gone.staff@example.com")
        Subscription.objects.create(registration=user.interest, plan=user.interest.plan, start_date=timezone.localdate(), created_by=None)
        page = call(self.admin, "get", f"/people/{user.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Not recorded")


class RevenueSafetyTests(Base):
    """What the review of the Revenue dates found: settings at their limits and changes from any path."""

    def approved(self, email="safe@example.com"):
        user = self.member(email)
        approvals.decide(user.pk, "approved", self.approver)
        return user

    def test_a_monthly_drop_off_of_100_percent_keeps_month_one_and_the_page_opens(self):
        self.approved()
        SiteSettings.objects.filter(pk=SiteSettings.load().pk).update(revenue_dropoff_percent=100)
        data = self.figures()["revenue"]
        price = 39900
        self.assertEqual(counts.revenue_assumptions(data)["approved"]["assumed_total_ex"], Decimal(price))
        self.assertEqual(call(self.approver, "get", "/revenue/").status_code, 200)

    def test_a_far_off_year_never_stops_the_figures_and_the_forms_refuse_it(self):
        self.assertEqual(counts.add_months(date(9999, 6, 1), 11), date.max)
        with self.assertRaises(ValidationError):
            validate_sensible_year(date(9999, 6, 1))
        self.assertEqual(validate_sensible_year(date(2027, 1, 1)), date(2027, 1, 1))

    def test_any_change_to_the_dates_or_a_set_up_asks_for_a_refresh(self):
        user = self.member("refresh@example.com")
        site = SiteSettings.load()
        with mock.patch("office.snapshots.request_refresh") as refresh:
            site.save()
            refresh.assert_not_called()  # nothing that matters changed
            site.revenue_start_date = date(2027, 3, 1)
            site.save()
            self.assertEqual(refresh.call_count, 1)
            site.opening_date = date(2027, 4, 1)
            site.save()
            self.assertEqual(refresh.call_count, 2)
            sub = Subscription.objects.create(registration=user.interest, plan=user.interest.plan, start_date=date(2027, 1, 1))
            self.assertEqual(refresh.call_count, 3)
            sub.delete()
            self.assertEqual(refresh.call_count, 4)

    def test_analytics_money_is_never_kept_by_the_browser(self):
        self.assertIn("no-store", call(self.approver, "get", "/analytics/")["Cache-Control"])
        self.assertIn("no-store", call(self.approver, "get", "/analytics/data/")["Cache-Control"])

    def test_a_half_percent_rounds_up_as_the_tooltip_does(self):
        self.assertEqual((bp_rate(1250), bp_rate(6250), bp_rate(460)), ("13%", "63%", "4.6%"))

    def test_dates_with_nothing_stored_by_date_show_the_normal_page_and_no_false_zero(self):
        self.approved()
        stored = self.figures()
        for bucket in ("approved", "waiting"):
            stored["revenue"][bucket]["detail"].pop("calendar", None)
        OfficeSnapshot.objects.filter(page=counts.PAGE, range=counts.RANGE).update(payload=stored)
        page = call(self.approver, "get", "/revenue/?from=2027-01-01&to=2027-12-31")
        self.assertEqual(page.status_code, 200)
        self.assertIsNone(page.context["range_figures"])
        self.assertNotContains(page, "Nothing falls due")


class RevenueBreakdownTests(Base):
    """The Revenue breakdown: deals plus Gold equal the stored total, and the page shows only stored figures."""

    def john(self, email, percent=20, months=6, plan="tier-2"):
        user = self.member(email, plan=plan)
        InterestRegistration.objects.filter(user=user).update(sale_percent_off=percent, sale_months=months, sale_name="Launch")
        return user

    def build(self):
        """Approved: a 6-month sale, a 24-month sale, a lapsed sale (full price), an agreed price, plain full price, one Gold. Waiting: a sale person and Gold."""
        sale, long_sale, lapsed, agreed, plain, waiting = (self.john("bd.sale@example.com"), self.john("bd.long@example.com", 40, 24, "tier-3"), self.john("bd.lapsed@example.com"),
                                                          self.member("bd.agreed@example.com"), self.member("bd.plain@example.com", plan="tier-1"), self.john("bd.waiting@example.com"))
        InterestRegistration.objects.filter(user=lapsed).update(sale_expired_at=timezone.now())
        Subscription.objects.create(registration=agreed.interest, plan=agreed.interest.plan, start_date=timezone.localdate(), agreed_price_ex_vat=Decimal("350.00"))
        for user in (sale, long_sale, lapsed, agreed, plain):
            approvals.decide(user.pk, "approved", self.approver)
        gold, _ = gold_services.submit_application(application_data(email="bd.gold@example.com"))
        GoldApplication.objects.filter(pk=gold.pk).update(status="approved")
        gold_services.submit_application(application_data(email="bd.waitgold@example.com"))
        del waiting
        return self.figures()["revenue"]

    def test_deals_plus_gold_equal_the_stored_total_for_approved_and_waiting(self):
        data = self.build()
        for bucket in ("approved", "waiting"):
            detail = data[bucket]["detail"]
            gold = next(r for r in data[bucket]["by_plan"] if r["kind"] == "gold")["year_pence"]
            self.assertEqual(sum(g["year_pence"] for g in detail["groups"]) + gold, data[bucket]["year_pence"])
            self.assertEqual(sum(detail["months"]) + gold, data[bucket]["year_pence"])  # the 12 months read the same sum
            self.assertEqual(sum(g["count"] for g in detail["groups"]), sum(r["count"] for r in data[bucket]["by_plan"] if r["kind"] == "tier"))
        view = counts.revenue_view(data, 20)["approved"]["detail"]
        self.assertEqual(view["memberships_year_pence"] + view["gold_year_pence"], data["approved"]["year_pence"])
        self.assertEqual(view["reduced_count"] + view["full_count"], sum(g["count"] for g in data["approved"]["detail"]["groups"]))

    def test_a_year_in_real_money(self):
        """Tier 2 at £399 and Tier 3 at £499, worked out by hand."""
        def year(user):
            return counts.year_pence(InterestRegistration.objects.select_related("plan").get(user=user))

        self.assertEqual(year(self.john("t.sale@example.com")), 6 * 31920 + 6 * 39900)
        self.assertEqual(year(self.john("t.long@example.com", 40, 24, "tier-3")), 12 * 29940)
        self.assertIsNone(counts.terms(InterestRegistration(plan=None)))

    def agreed(self, email, price, months, plan_slug="tier-2"):
        user = self.member(email)
        Subscription.objects.create(registration=user.interest, plan=Plan.objects.get(slug=plan_slug), start_date=timezone.localdate(), agreed_price_ex_vat=Decimal(price), agreed_months=months)
        approvals.decide(user.pk, "approved", self.approver)
        return user

    def test_an_agreed_price_with_its_months_splits_the_year_and_twelve_or_more_fills_it(self):
        self.agreed("a.three@example.com", "350.00", 3)
        self.agreed("a.twelve@example.com", "300.00", 12)
        self.agreed("a.long@example.com", "250.00", 24)
        groups = {g["rows"][0]["month_pence"]: g for g in self.figures()["revenue"]["approved"]["detail"]["groups"]}
        self.assertEqual((groups[35000]["during_pence"], groups[35000]["after_total_pence"]), (3 * 35000, 9 * 39900))
        self.assertEqual((groups[30000]["during_pence"], groups[30000]["after_total_pence"]), (12 * 30000, 0))
        self.assertEqual((groups[25000]["during_pence"], groups[25000]["after_total_pence"], groups[25000]["lasts"]), (12 * 25000, 0, 24))

    def test_the_same_agreed_price_on_two_plans_keeps_each_ones_price_afterwards(self):
        self.agreed("b.two@example.com", "350.00", 3)
        self.agreed("b.three@example.com", "350.00", 3, "tier-3")
        rows = self.figures()["revenue"]["approved"]["detail"]["groups"][0]["rows"]
        self.assertEqual(sorted((r["count"], r["after_pence"], r["after_total_pence"]) for r in rows), [(1, 39900, 9 * 39900), (1, 49900, 9 * 49900)])

    def test_the_deals_match_each_plans_row(self):
        data = self.build()
        for bucket in ("approved", "waiting"):
            for plan in (p for p in data[bucket]["by_plan"] if p["kind"] == "tier"):
                rows = [r for g in data[bucket]["detail"]["groups"] for r in g["rows"] if r["slug"] == plan["slug"]]
                self.assertEqual((sum(r["count"] for r in rows), sum(r["year_pence"] for r in rows)), (plan["count"], plan["year_pence"]))

    def test_a_sale_name_is_escaped_on_the_page(self):
        user = self.john("x.safe@example.com")
        InterestRegistration.objects.filter(user=user).update(sale_name="<script>x</script>")
        approvals.decide(user.pk, "approved", self.approver)
        self.figures()
        page = call(self.approver, "get", "/revenue/")
        self.assertNotContains(page, "<script>x</script>")
        self.assertContains(page, "&lt;script&gt;x&lt;/script&gt;")

    def test_a_sale_of_twenty_four_months_shows_twelve_inside_the_year(self):
        data = self.build()
        view = counts.revenue_view(data, 20)["approved"]["detail"]
        long_sale = next(g for g in view["groups"] if g["lasts"] == 24)
        self.assertEqual((long_sale["lasts"], long_sale["months"], long_sale["after_months"], long_sale["after_total_pence"]), (24, 12, 0, 0))
        page = call(self.approver, "get", "/revenue/")
        self.assertContains(page, "40% off for 24 months, full price from month 25.")

    def test_a_lost_sale_counts_as_full_price_and_in_lost_count(self):
        view = counts.revenue_view(self.build(), 20)["approved"]["detail"]
        full = next(g for g in view["groups"] if g["kind"] == "full")
        self.assertEqual(full["lost"], 1)
        self.assertEqual(view["lost_count"], 1)
        tier2 = next(r for r in full["rows"] if r["slug"] == "tier-2")
        self.assertEqual((tier2["count"], tier2["lost"], tier2["year_pence"]), (1, 1, tier2["month_pence"] * 12))  # full price all year, the same price each month
        self.assertContains(call(self.approver, "get", "/revenue/"), "Of those at full price, 1 let a sale price lapse.")

    def test_waiting_people_never_land_in_the_approved_detail(self):
        data = self.build()
        approved = counts.revenue_view(data, 20)["approved"]["detail"]
        self.assertEqual(sum(g["count"] for g in approved["groups"]), 5)  # the five approved Tier members only
        self.assertEqual(approved["gold_count"], 1)
        waiting = data["waiting"]["detail"]
        self.assertEqual(sum(g["count"] for g in waiting["groups"]), 1)
        page = call(self.approver, "get", "/revenue/")
        self.assertContains(page, "Not counted in any figure above.")
        self.assertContains(page, "Launch, 20% off for 6 months, 1 waiting")

    def test_an_old_stored_payload_with_no_detail_shows_no_plus_and_no_error(self):
        self.build()
        stored = counts.read()
        for bucket in ("approved", "waiting"):
            stored["revenue"][bucket].pop("detail", None)
        from insights.models import OfficeSnapshot

        OfficeSnapshot.objects.filter(page=counts.PAGE, range=counts.RANGE).update(payload=stored)
        page = call(self.approver, "get", "/revenue/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "The breakdown will be ready after the next hourly update.")
        self.assertNotContains(page, "data-wants-details")

    def test_nothing_approved_shows_the_line_and_no_plus(self):
        self.figures()
        page = call(self.approver, "get", "/revenue/")
        self.assertContains(page, "Nothing approved yet, so there is nothing to break down.")
        self.assertNotContains(page, "o-plus")

    def test_the_page_renders_for_an_approver_with_the_stored_pence_and_no_vat_or_rounding_added(self):
        data = self.build()
        for user in (self.admin, self.approver):
            page = call(user, "get", "/revenue/")
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "data-revenue-breakdown")
            self.assertContains(page, "Estimate for the year")
        view = page.context["revenue"]["approved"]["detail"]
        self.assertEqual(view["memberships_year_pence"] + view["gold_year_pence"], data["approved"]["year_pence"])  # exact pence: no VAT, no rounding
        self.assertEqual(view["groups"][0]["rows"][0]["year_pence"], data["approved"]["detail"]["groups"][0]["rows"][0]["year_pence"])
        self.assertContains(page, "Agreed price, £350 a month")

    def test_price_month_is_exact(self):
        from office.templatetags.office_tags import price_month

        self.assertEqual((price_month(35000), price_month(27930), price_month(120000), price_month(0), price_month(5), price_month(None)), ("£350", "£279.30", "£1,200", "£0", "£0.05", "£0"))


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
        rows = {r["email"]: r for r in call(self.reader, "get", "/leads/?view=fakes").context["rows"]}  # a bounced lead is in Possible fakes, not the main list
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


class RevenueCalendarTests(Base):
    """Money due by date: each member's 12 payments, Gold's one, the range sum and the page's date filter."""

    john, build = RevenueBreakdownTests.john, RevenueBreakdownTests.build  # the same setups, without re-running that class's tests

    def due(self, bucket="approved"):
        return self.figures()["revenue"][bucket]["detail"]["calendar"]

    def test_a_sale_member_owes_six_at_the_sale_price_then_six_at_full_on_the_right_dates(self):
        user = self.john("cal.sale@example.com")
        approvals.decide(user.pk, "approved", self.approver)
        calendar = self.due()
        days = ["2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01", "2027-05-01", "2027-06-01", "2027-07-01", "2027-08-01", "2027-09-01", "2027-10-01", "2027-11-01", "2027-12-01"]
        self.assertEqual(calendar["due"], {"tier-2": {day: {str(number + 1): [31920 if number < 6 else 39900, 1]} for number, day in enumerate(days)}})
        self.assertEqual((calendar["start"], calendar["assumed"], calendar["first"], calendar["last"]), ("2027-01-01", True, "2027-01-01", "2027-12-01"))

    def test_everything_due_adds_up_to_the_year_for_both_buckets_including_gold(self):
        data = self.build()
        for bucket in ("approved", "waiting"):
            due = data[bucket]["detail"]["calendar"]["due"]
            self.assertEqual(sum(cell[0] for by_day in due.values() for months in by_day.values() for cell in months.values()), data[bucket]["year_pence"])
            self.assertGreater(data[bucket]["year_pence"], 0)
        self.assertIn("gold", data["approved"]["detail"]["calendar"]["due"])
        self.assertEqual(list(data["waiting"]["detail"]["calendar"]["due"]["gold"].values()), [{"1": [data["gold_fee_pence"], 1]}])

    def test_a_31_january_start_is_clamped_to_the_end_of_each_month(self):
        from datetime import date

        self.assertEqual([counts.add_months(date(2027, 1, 31), n).isoformat() for n in (0, 1, 2, 3, 12)], ["2027-01-31", "2027-02-28", "2027-03-31", "2027-04-30", "2028-01-31"])
        self.assertEqual(counts.add_months(date(2027, 12, 15), 1).isoformat(), "2028-01-15")
        from plans.models import SiteSettings

        SiteSettings.objects.filter(singleton_key="site").update(revenue_start_date=date(2027, 1, 31))
        approvals.decide(self.member("cal.clamp@example.com").pk, "approved", self.approver)
        self.assertEqual(list(self.due()["due"]["tier-2"])[:3], ["2027-01-31", "2027-02-28", "2027-03-31"])

    def test_his_subscription_beats_the_opening_date_and_that_beats_the_assumed_date(self):
        from datetime import date

        from plans.models import SiteSettings

        user = self.member("cal.start@example.com")
        approvals.decide(user.pk, "approved", self.approver)
        self.assertEqual((self.due()["start"], self.due()["assumed"], self.due()["first"]), ("2027-01-01", True, "2027-01-01"))
        SiteSettings.objects.filter(singleton_key="site").update(opening_date=date(2027, 3, 10))
        calendar = self.due()
        self.assertEqual((calendar["start"], calendar["assumed"], calendar["first"], calendar["last"]), ("2027-03-10", False, "2027-03-10", "2028-02-10"))
        Subscription.objects.create(registration=user.interest, plan=user.interest.plan, start_date=date(2027, 5, 20))
        calendar = self.due()
        self.assertEqual((calendar["first"], calendar["last"]), ("2027-05-20", "2028-04-20"))

    def test_revenue_between_includes_both_ends_and_an_empty_range_is_zero(self):
        from datetime import date

        approvals.decide(self.john("cal.range@example.com").pk, "approved", self.approver)
        data = self.figures()["revenue"]
        got = counts.revenue_between(data, date(2027, 1, 1), date(2027, 2, 1), 20)["approved"]
        self.assertEqual((got["payments"], got["total_ex"], got["total_inc"]), (2, Decimal(63840), Decimal(63840) * Decimal("1.2")))
        row = next(r for r in got["by_plan"] if r["slug"] == "tier-2")
        self.assertEqual((row["payments"], row["total_ex"]), (2, Decimal(63840)))
        self.assertEqual([r["slug"] for r in got["by_plan"]], [r["slug"] for r in data["approved"]["by_plan"]])
        none = counts.revenue_between(data, date(2030, 1, 1), date(2030, 2, 1), 20)
        self.assertEqual((none["approved"]["payments"], none["approved"]["total_ex"], none["waiting"]["payments"]), (0, 0, 0))
        self.assertEqual(counts.revenue_between({"approved": {"count": 0, "year_pence": 0, "by_plan": []}}, date(2027, 1, 1), date(2027, 2, 1), 20)["waiting"]["payments"], 0)

    def test_the_page_reads_the_range_refuses_a_backwards_one_and_ignores_garbage(self):
        approvals.decide(self.john("cal.page@example.com").pk, "approved", self.approver)
        self.figures()
        page = call(self.approver, "get", "/revenue/?from=2027-02-01&to=2027-03-31").context
        self.assertEqual((page["date_range"]["active"], page["range_figures"]["approved"]["payments"], page["date_format"]), (True, 2, "d/m/Y"))
        self.assertEqual((page["calendar"]["first"], page["calendar"]["last"], page["calendar"]["assumed"]), ("2027-01-01", "2027-12-01", True))
        only_from = call(self.approver, "get", "/revenue/?from=2027-12-01").context
        self.assertEqual(only_from["range_figures"]["approved"]["payments"], 1)
        only_to = call(self.approver, "get", "/revenue/?to=2027-01-01").context
        self.assertEqual(only_to["range_figures"]["approved"]["payments"], 1)
        backwards = call(self.approver, "get", "/revenue/?from=2027-03-01&to=2027-02-01").context
        self.assertEqual((backwards["range_error"], backwards["date_range"]["active"], backwards["range_figures"]), ("The end date can't be before the start date.", False, None))
        for query in ("", "?from=&to=", "?from=banana&to=2027-99-99"):
            plain = call(self.approver, "get", f"/revenue/{query}").context
            self.assertEqual((plain["date_range"]["active"], plain["range_figures"], plain["range_error"]), (False, None, ""))

    def test_an_old_stored_payload_with_no_calendar_still_loads(self):
        from insights.models import OfficeSnapshot

        approvals.decide(self.john("cal.old@example.com").pk, "approved", self.approver)
        data = self.figures()
        for bucket in ("approved", "waiting"):
            data["revenue"][bucket]["detail"].pop("calendar")
        data["revenue"]["waiting"].pop("detail")
        OfficeSnapshot.objects.filter(page=counts.PAGE).update(payload=data)
        response = call(self.approver, "get", "/revenue/?from=2027-01-01&to=2027-12-31")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.context["calendar"]["first"], response.context["range_figures"]), (None, None))  # no false £0: the normal page

    def test_assumptions_equal_the_real_figures_at_100_and_0_and_apply_paying_and_dropoff_exactly(self):
        from datetime import date

        from plans.models import SiteSettings

        self.build()
        data = self.figures()["revenue"]
        plain = counts.revenue_assumptions(data, 20)
        for bucket in ("approved", "waiting"):
            self.assertEqual((plain[bucket]["assumed_total_ex"], plain[bucket]["assumed_total_inc"]), (plain[bucket]["total_ex"], plain[bucket]["total_inc"]))
            self.assertEqual(plain[bucket]["total_ex"], data[bucket]["year_pence"])
            for row in plain[bucket]["by_plan"]:
                self.assertEqual(row["assumed_total_ex"], row["total_ex"])
        # by hand: one member at 39900 a month, 80% paying, 10% leaving each month, first 3 payments; and Gold's fee at 80% with no drop-off
        stored = {"approved": {"by_plan": [{"slug": "tier-2", "name": "Tier 2", "kind": "tier"}, {"slug": "gold", "name": "Gold", "kind": "gold"}],
                               "detail": {"calendar": {"due": {"tier-2": {"2027-01-01": {"1": [39900, 1]}, "2027-02-01": {"2": [39900, 1]}, "2027-03-01": {"3": [39900, 1]}},
                                                                "gold": {"2027-01-01": {"1": [19900, 1]}}}}}}}
        SiteSettings.objects.filter(singleton_key="site").update(revenue_paying_percent=80, revenue_dropoff_percent=10)
        got = counts.revenue_between(stored, date(2027, 1, 1), date(2027, 3, 1), 20)["approved"]
        tier, gold = got["by_plan"]
        self.assertEqual(tier["assumed_total_ex"], Decimal("86503.2"))  # 39900 x 0.8 x (1 + 0.9 + 0.81)
        self.assertEqual(gold["assumed_total_ex"], Decimal(19900) * Decimal("0.8"))
        self.assertEqual((tier["total_ex"], gold["total_ex"]), (Decimal(119700), Decimal(19900)))  # the real figures ignore the assumptions
        page = call(self.approver, "get", "/revenue/").context["assumptions"]
        self.assertEqual((page["paying_percent"], page["dropoff_percent"], page["changed"]), (Decimal("80"), Decimal("10"), True))


class RevenueDatesPageTests(Base):
    """The Revenue page's date filter and "With your assumptions": what the page says in each state (the figures themselves are tested above)."""

    john = RevenueBreakdownTests.john

    def setUp(self):
        super().setUp()
        approvals.decide(self.john("dates.john@example.com").pk, "approved", self.approver)  # 6 payments at 319.20 then 6 at 399.00, 1 Jan to 1 Dec 2027
        self.figures()

    def text(self, query="", path="/revenue/"):
        import html

        return html.unescape(call(self.approver, "get", f"{path}{query}").content.decode())

    def outside_the_form(self, page):
        return page.split('<div class="o-revenue"', 1)[1]  # everything under the filter

    def assume(self, paying, dropoff):
        from plans.models import SiteSettings

        SiteSettings.objects.filter(singleton_key="site").update(revenue_paying_percent=paying, revenue_dropoff_percent=dropoff)

    def test_the_default_page_has_the_field_and_no_date_wording_anywhere_else(self):
        page = self.text()
        self.assertIn('data-date-picker data-mode="range" data-format="d/m/Y"', page)
        self.assertIn('data-min="2027-01-01" data-max="2027-12-01"', page)
        self.assertIn("Money is due from 01/01/2027 to 01/12/2027. Based on an assumed start date.", page)  # the assumed date is in the calendar's note and nowhere else
        rest = self.outside_the_form(page)
        for text in ("01/01/2027", "Money due", "Clear dates", "all dates", "any time", "In these dates", "Not limited to the dates", "Each member's own first 12 months, starting when he starts paying"):
            self.assertNotIn(text, rest)
        for text in ("Estimate from approved people", "A year, excluding VAT. Not money received.", "A year</th>", "A month</th>", "The same figure as the top of this page.",
                     "An estimate for each member's first 12 months at today's prices. VAT at 20%.", "By plan and tier</h2>"):
            self.assertIn(text, rest)
        self.assertNotIn("With your assumptions", page)  # nothing is changed
        self.assertNotIn("data-revenue-assumed", page)

    def test_dates_chosen_the_total_reads_what_is_due_and_the_year_and_month_columns_go(self):
        page = self.text("?from=2027-02-01&to=2027-03-31")
        card = page.split('data-revenue-total', 1)[1].split("</section>", 1)[0]
        self.assertIn("Due from approved people", card)
        self.assertIn('data-revenue-year data-revenue-range>£638<', card)  # two payments of 319.20, exactly 638.40
        self.assertIn("01/02/2027 to 31/03/2027, excluding VAT. Not money received.", card)
        self.assertIn("In these dates", card)
        self.assertIn("2 payments due.", card)
        self.assertIn("Including VAT</th><td>£766<", card)
        for text in ("A year", "A month", "Members", "Average"):
            self.assertNotIn(text, card)
        self.assertIn("Anyone without his own start date is counted from 01/01/2027, an assumed date until the opening date is set. Change it in System > Revenue.", card)
        self.assertIn('<span data-revenue-range-line>Money due 01/02/2027 to 31/03/2027</span><a class="o-quiet" href="/revenue/" data-clear>Clear dates</a>', page)
        table = page.split("data-revenue-table", 1)[1].split("</section>", 1)[0]
        self.assertIn("By plan and tier, in these dates", table)
        for head in ("Payments due", "Due, excl. VAT", "Due, incl. VAT"):
            self.assertIn(head, table)
        for gone in ("Members", "Month, excl. VAT", "Average a member a year", "With your assumptions"):
            self.assertNotIn(gone, table)
        self.assertEqual(table.count("data-revenue-row="), 2)  # Tier 2 (the only plan with payments) and All
        self.assertIn("An estimate of payments due at today's prices. VAT at 20%.", page)
        self.assertIn("Possible, from those waiting", page)
        self.assertIn("Nobody waiting has a payment due in these dates.", page)

    def test_the_breakdown_never_changes_but_three_lines_of_its_wording_do(self):
        plain, dated = self.text(), self.text("?from=2027-02-01&to=2027-03-31")
        for page in (plain, dated):
            self.assertIn("£4,309", page.split("data-bd-sum-total", 1)[1])  # the full year, with or without dates
        self.assertIn("The same figure as the top of this page.", plain)
        self.assertNotIn("The full 12-month estimate, not just the dates above.", plain)
        self.assertNotIn("Not limited to the dates above.", plain)
        self.assertEqual(plain.count("data-revenue-basis"), 0)
        self.assertIn("The full 12-month estimate, not just the dates above.", dated)
        self.assertNotIn("The same figure as the top of this page.", dated)
        self.assertIn("Not limited to the dates above. Who pays what, for how long, and what it comes to over each member's first 12 months.", dated)
        self.assertEqual(dated.count("data-revenue-basis"), 2)  # the total card and the breakdown's first section

    def test_a_backwards_range_shows_the_error_and_the_normal_page_with_both_fields_empty(self):
        page = self.text("?from=2027-03-01&to=2027-02-01")
        self.assertIn('<p class="o-field-error" role="alert" data-revenue-range-error>The end date can\'t be before the start date. Showing the full estimate instead.</p>', page)
        self.assertIn("Estimate from approved people", page)
        self.assertNotIn("Clear dates", page)
        self.assertNotIn("In these dates", page)
        self.assertIn('name="from" value=""', page)
        self.assertIn('name="to" value=""', page)
        self.assertIn("A year</th>", page)

    def test_with_one_end_in_the_address_the_page_states_the_true_dates(self):
        self.assertIn("Money due 01/01/2027 to 01/02/2027", self.text("?to=2027-02-01"))  # the start is the first due date
        only_from = self.text("?from=2027-11-01")
        self.assertIn("Money due 01/11/2027 to 01/12/2027", only_from)  # the end is the last due date
        self.assertIn('name="from" value="2027-11-01"', only_from)
        self.assertIn('name="to" value="2027-12-01"', only_from)

    def test_nothing_due_in_the_dates_says_so_and_drops_the_grid_tile_cards_and_table(self):
        self.assume(80, 0)
        page = self.text("?from=2030-01-01&to=2030-02-01")
        card = page.split('data-revenue-total', 1)[1].split("</section>", 1)[0]
        self.assertIn("£0<", card)
        self.assertIn("Nothing falls due from approved people in these dates.", card)
        for text in ("data-revenue-grid", "data-revenue-assumed", "payments due."):
            self.assertNotIn(text, card)
        for text in ("data-revenue-plans", "data-revenue-table"):
            self.assertNotIn(text, page)

    def assumed_year(self):
        """John's year with 80% paying and 10% leaving each month, by hand: 31920 for 6 months then 39900 for 6, each month reduced once more than the one before."""
        from office.templatetags.office_tags import pounds

        return pounds(sum(Decimal(m) * Decimal("0.8") * Decimal("0.9") ** (n - 1) for n, m in enumerate([31920] * 6 + [39900] * 6, start=1)))

    def test_assumed_figures_appear_only_when_changed_and_never_change_the_real_one(self):
        self.assertNotIn("With your assumptions", self.text())
        self.assertNotIn("With your assumptions", self.text("?from=2027-02-01&to=2027-03-31"))
        self.assume(80, 10)
        page = self.text()
        card = page.split("data-revenue-total", 1)[1].split("</section>", 1)[0]
        self.assertIn("Real figure, from approved people", card)
        self.assertIn('data-revenue-year>£4,309<', card)  # the real figure is exactly what it was
        self.assertIn("A year, excluding VAT. Every approved person paying. Not money received.", card)
        self.assertIn(f'<p class="o-rev-assumed-num">{self.assumed_year()}</p>', card)
        self.assertIn("If 80% of them pay and 10% leave each month. Your own guess. The real figure does not change.", card)
        self.assertNotIn("Due 01/", card)
        table = page.split("data-revenue-table", 1)[1].split("</section>", 1)[0]
        self.assertIn("With your assumptions, year, excl. VAT", table)
        self.assertEqual(table.count('<td class="num o-assumed">'), 2)  # Tier 2 and the All row, both tinted
        self.assertIn("With your assumptions, a year, excl. VAT", page.split("data-revenue-plans", 1)[1])  # the phone cards and the Possible panel say a year
        self.assertNotIn("With your assumptions", self.outside_the_form(page).split("data-revenue-breakdown", 1)[1].split("data-bd-waiting", 1)[0])  # the breakdown is never touched

    def test_the_assumption_names_what_is_changed_and_the_dates_when_there_are_dates(self):
        self.assume(80, 0)
        self.assertIn("If 80% of them pay. Your own guess.", self.text())
        self.assertNotIn("leave each month", self.text())
        self.assume(100, 5)
        self.assertIn("If 5% leave each month. Your own guess.", self.text())
        self.assume(80, 10)
        page = self.text("?from=2027-01-01&to=2027-12-31")
        card = page.split("data-revenue-total", 1)[1].split("</section>", 1)[0]
        self.assertIn("Real figure, due from approved people", card)
        self.assertIn("01/01/2027 to 31/12/2027, excluding VAT. Every approved person paying. Not money received.", card)
        self.assertIn(f'<p class="o-rev-assumed-num">{self.assumed_year()}</p>', card)  # the whole calendar is the whole year
        self.assertIn("Due 01/01/2027 to 31/12/2027.", card)
        table = page.split("data-revenue-table", 1)[1].split("</section>", 1)[0]
        self.assertIn("With your assumptions, excl. VAT", table)
        self.assertIn("With your assumptions, incl. VAT", table)
        self.assertIn("With your assumptions, excl. VAT", page.split("data-revenue-plans", 1)[1])

    def test_assumed_figures_wait_for_the_stored_calendar(self):
        from insights.models import OfficeSnapshot

        self.assume(80, 10)
        data = self.figures()
        for bucket in ("approved", "waiting"):
            (data["revenue"][bucket].get("detail") or {}).pop("calendar", None)
        OfficeSnapshot.objects.filter(page=counts.PAGE).update(payload=data)
        page = self.text()
        self.assertNotIn("With your assumptions", page)  # they would read 0 until the next hourly update
        self.assertNotIn("data-filter-form", page)  # and with no calendar there is nothing to choose between: no filter
        self.assertIn("Estimate from approved people", page)

    def test_a_sale_name_is_escaped_in_the_breakdown(self):
        InterestRegistration.objects.filter(sale_name="Launch").update(sale_name="<b>Spring</b> & co")
        self.figures()
        raw = call(self.approver, "get", "/revenue/?from=2027-01-01&to=2027-12-31").content.decode()
        self.assertIn("&lt;b&gt;Spring&lt;/b&gt; &amp; co", raw)
        self.assertNotIn("<b>Spring", raw)

    def test_site_date_follows_the_date_format_setting(self):
        from datetime import date

        from django.template import Context, Template

        from plans.models import SiteSettings

        def shown(value):
            return Template("{% load office_tags %}{{ v|site_date }}").render(Context({"v": value}))

        for setting, expected in (("dd/mm/yyyy", "01/03/2027"), ("mm/dd/yyyy", "03/01/2027"), ("yyyy-mm-dd", "2027-03-01")):
            SiteSettings.objects.filter(singleton_key="site").update(date_format=setting)
            self.assertEqual((shown("2027-03-01"), shown(date(2027, 3, 1))), (expected, expected), setting)
        self.assertEqual((shown(""), shown(None), shown("banana")), ("", "", ""))
        SiteSettings.objects.filter(singleton_key="site").update(date_format="mm/dd/yyyy")
        page = self.text("?from=2027-02-01&to=2027-03-31")
        self.assertIn("Money due 02/01/2027 to 03/31/2027", page)
        self.assertIn('data-format="m/d/Y"', page)
        self.assertIn('name="from" value="2027-02-01"', page)  # the form always carries ISO dates


class AnalyticsRevenueTests(Base):
    """The short Revenue section on Analytics: two donut cards for those who may see Revenue, nothing at all for anyone else."""
    john = RevenueBreakdownTests.john
    build = RevenueBreakdownTests.build

    def test_an_approver_sees_both_cards_with_the_right_total_and_a_link_to_revenue(self):
        data = self.build()
        total = data["approved"]["year_pence"]
        for user in (self.approver, self.admin):
            page = call(user, "get", "/analytics/")
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, "Revenue by plan")
            self.assertContains(page, "Who is on what price")
            self.assertContains(page, 'class="o-quiet o-seelink" href="/revenue/"', count=2)
            self.assertContains(page, f'<span class="o-donut-total o-donut-total--money">{pounds_compact(total)}</span><span class="o-donut-word">a year</span>', html=True)
            self.assertContains(page, "first 12 months. The dates above don", count=2)
            self.assertEqual(page.context["data"]["revenue_card"]["plan"]["total_pence"], total)

    def test_a_plain_reader_gets_neither_card_nor_any_figure_in_page_or_json(self):
        data = self.build()
        page = call(self.reader, "get", "/analytics/")
        self.assertEqual(page.status_code, 200)
        for text in ("Revenue by plan", "Who is on what price", "See Revenue", "revenue_card", "chart-revenue"):
            self.assertNotContains(page, text)
        self.assertNotIn("revenue_card", page.context["data"])
        body = call(self.reader, "get", "/analytics/data/")
        self.assertEqual(body.status_code, 200)
        self.assertNotIn("revenue_card", body.json())
        self.assertNotContains(body, str(data["approved"]["year_pence"]))
        self.assertIn("revenue_card", call(self.approver, "get", "/analytics/data/").json())

    def test_the_shared_snapshot_is_not_changed_by_adding_the_cards(self):
        self.build()
        call(self.approver, "get", "/analytics/")
        self.assertNotIn("revenue_card", call(self.reader, "get", "/analytics/data/").json())

    def test_percents_and_counts_for_a_known_mix(self):
        from office import analytics_revenue

        stored = {"revenue": {"approved": {"count": 7, "year_pence": 1_000_000, "by_plan": [
            {"slug": "tier-1", "name": "Tier 1", "kind": "tier", "count": 1, "year_pence": 100_001},
            {"slug": "tier-2", "name": "Tier 2", "kind": "tier", "count": 4, "year_pence": 600_000},
            {"slug": "tier-3", "name": "Tier 3", "kind": "tier", "count": 0, "year_pence": 0},
            {"slug": "gold", "name": "Gold Card", "kind": "gold", "count": 2, "year_pence": 299_999}],
            "detail": {"groups": [{"kind": "sale", "count": 2}, {"kind": "sale", "count": 1}, {"kind": "agreed", "count": 1}, {"kind": "full", "count": 1}], "months": [0] * 12}}}}
        card = analytics_revenue.build(stored)
        self.assertEqual([(r["label"], r["value"], r["share_bp"]) for r in card["plan"]["rows"]], [("Tier 1", 100_001, 1000), ("Tier 2", 600_000, 6000), ("Gold Card", 299_999, 3000)])
        self.assertEqual(card["plan"]["summary"], "Tier 2 brings in £6,000 of £10,000 a year.")
        self.assertEqual(card["price"]["members"], 5)
        self.assertEqual([(r["label"], r["value"], r["share_bp"]) for r in card["price"]["rows"]], [("On a sale price", 3, 6000), ("On an agreed price", 1, 2000), ("At full price", 1, 2000)])
        self.assertEqual(card["price"]["summary"], "3 of 5 members are on a sale price.")

    def test_the_real_figures_match_the_stored_ones(self):
        data = self.build()
        from office import analytics_revenue

        card = analytics_revenue.build(counts.read())
        self.assertEqual(card["plan"]["total_pence"], data["approved"]["year_pence"])
        self.assertEqual(card["price"]["members"], sum(r["count"] for r in data["approved"]["by_plan"] if r["kind"] == "tier"))
        self.assertEqual(sum(r["value"] for r in card["plan"]["rows"]), data["approved"]["year_pence"])  # exact pence, not rounded pounds

    def test_an_old_payload_or_nothing_approved_shows_the_empty_state_with_no_error(self):
        self.build()
        stored = counts.read()
        for bucket in ("approved", "waiting"):
            stored["revenue"][bucket].pop("detail", None)
        OfficeSnapshot.objects.filter(page=counts.PAGE, range=counts.RANGE).update(payload=stored)
        for path in ("/analytics/", "/analytics/data/"):
            self.assertEqual(call(self.approver, "get", path).status_code, 200)
        page = call(self.approver, "get", "/analytics/")
        self.assertContains(page, "Revenue by plan")
        self.assertContains(page, "Nothing approved yet.")
        self.assertContains(page, 'data-chart="revenue-plan" data-empty-text="Nothing approved yet." data-empty')
        self.assertEqual(call(self.reader, "get", "/analytics/").status_code, 200)

    def test_nothing_approved_at_all_is_the_empty_state(self):
        self.figures()
        page = call(self.approver, "get", "/analytics/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-chart="revenue-price" data-empty-text="No Tier members approved yet." data-empty')
