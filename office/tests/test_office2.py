"""Office 2, server side: Barry's membership approval, the counts and Revenue, Leads and the approach list, the Registered lists, the wa.me button. Mocked: sync queue, in-memory mail."""
from decimal import Decimal

from django.core import mail
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
from plans.models import Plan, Subscription
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
        self.assertEqual(approved["tier-2"]["year_pence"], (int(tier2.price_ex_vat * 100) + kept) * 12)  # his own price, the kept sale price included
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
