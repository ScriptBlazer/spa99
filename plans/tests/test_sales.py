"""Sales: the model rules (window, overlap), live_sale boundaries, prices, the kept-price snapshot on a registration, End now and the
preview link. Mocked: no outside calls."""
import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from plans import sales
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan, Sale
from users import services
from users.models import InterestRegistration, User
from users.tests.test_register import cleaned

HOUR = timedelta(hours=1)


def make_sale(start=-1, end=24, plans=("tier-2", "tier-3"), name="Christmas sale", percent=20, months=3, **extra):
    now = timezone.now()
    sale = Sale.objects.create(name=name, percent_off=percent, months_at_price=months, starts_at=now + start * HOUR, ends_at=now + end * HOUR, **extra)
    sale.plans.set(Plan.objects.filter(slug__in=plans))
    return sale


class SaleRuleTests(TestCase):
    def setUp(self):
        seed_all()

    def test_window_percent_and_plan_rules(self):
        now = timezone.now()
        bad_end = Sale(name="x", percent_off=20, months_at_price=3, starts_at=now, ends_at=now)
        with self.assertRaises(ValidationError) as caught:
            bad_end.full_clean()
        self.assertIn("ends_at", caught.exception.message_dict)
        for percent in (0, 91):
            with self.assertRaises(ValidationError) as caught:
                Sale(name="x", percent_off=percent, months_at_price=3, starts_at=now, ends_at=now + HOUR).full_clean()
            self.assertIn("percent_off", caught.exception.message_dict)
        sale = make_sale(plans=())
        with self.assertRaises(ValidationError) as caught:
            sale.full_clean()
        self.assertIn("plans", caught.exception.message_dict)

    def test_overlap_is_refused_and_an_ended_early_window_frees_the_slot(self):
        first = make_sale(start=10, end=20)
        clash = Sale(name="B", percent_off=10, months_at_price=1, starts_at=first.starts_at + HOUR, ends_at=first.ends_at + HOUR)
        with self.assertRaises(ValidationError) as caught:
            clash.full_clean()
        self.assertIn("starts_at", caught.exception.message_dict)
        edge = Sale(name="C", percent_off=10, months_at_price=1, starts_at=first.ends_at, ends_at=first.ends_at + HOUR)
        edge.full_clean()  # touching, not overlapping
        first.ended_early_at = first.starts_at + HOUR  # ended an hour in: the rest is free
        first.save()
        clash.full_clean()
        first.ended_early_at = first.starts_at  # cancelled before it ever ran: no window at all
        first.save()
        Sale(name="D", percent_off=10, months_at_price=1, starts_at=first.starts_at - HOUR, ends_at=first.ends_at + HOUR).full_clean()

    def test_live_sale_boundaries_start_inclusive_end_exclusive_end_now_counts(self):
        sale = make_sale(start=1, end=3)
        self.assertIsNone(sales.live_sale(sale.starts_at - timedelta(seconds=1)))
        self.assertEqual(sales.live_sale(sale.starts_at), sale)
        self.assertEqual(sales.live_sale(sale.ends_at - timedelta(seconds=1)), sale)
        self.assertIsNone(sales.live_sale(sale.ends_at))
        sale.ended_early_at = sale.starts_at + HOUR / 2
        sale.save()
        self.assertEqual(sales.live_sale(sale.starts_at + HOUR / 4), sale)
        self.assertIsNone(sales.live_sale(sale.starts_at + HOUR / 2))
        self.assertEqual(sale.status(sale.starts_at + HOUR), "ended")

    def test_prices_round_to_whole_pence(self):
        tier2 = Plan.objects.get(slug="tier-2")  # 399.00
        self.assertEqual(sales.sale_price(tier2, make_sale(percent=20)), Decimal("319.20"))
        self.assertEqual(sales.sale_price(tier2, 33), Decimal("267.33"))
        self.assertEqual(sales.sale_price(tier2, 20, vat_rate=Decimal("20")), Decimal("383.04"))
        self.assertEqual(sales.plans_text(make_sale(plans=("tier-1", "tier-2", "tier-3"), start=100, end=101)), "Tier 1, Tier 2 and Tier 3")


class SnapshotTests(TestCase):
    def setUp(self):
        seed_all()
        self.n = 0

    def register(self, plan="tier-2"):
        self.n += 1
        result = services.register_interest(cleaned(email=f"p{self.n}@example.com", mobile=f"0791234567{self.n}", plan=plan))
        return result.user.interest

    def test_registering_during_a_sale_copies_it_and_editing_the_sale_never_changes_it(self):
        sale = make_sale()
        interest = self.register("tier-2")
        self.assertEqual((interest.sale, interest.sale_name, interest.sale_percent_off, interest.sale_months), (sale, "Christmas sale", 20, 3))
        self.assertIsNotNone(interest.sale_locked_at)
        sale.name, sale.percent_off = "Renamed", 50
        sale.save()
        interest.refresh_from_db()
        self.assertEqual((interest.sale_name, interest.sale_percent_off), ("Christmas sale", 20))
        sale.delete()
        interest.refresh_from_db()
        self.assertEqual((interest.sale, interest.sale_percent_off, interest.sale_months), (None, 20, 3))
        self.assertIn("20% off Tier 2 for 3 months", sales.kept_price(interest)["text"])

    def test_a_plan_the_sale_does_not_cover_gets_nothing(self):
        make_sale()
        self.assertIsNone(self.register("tier-1").sale_percent_off)

    def test_plan_change_keeps_clears_or_adds_the_snapshot(self):
        make_sale(plans=("tier-2", "tier-3"))
        interest = self.register("tier-2")
        locked_at = interest.sale_locked_at
        kept = services.set_interest(interest.user, Plan.objects.get(slug="tier-3"))
        self.assertEqual((kept.sale_percent_off, kept.sale_locked_at), (20, locked_at))  # same sale covers it: keep
        cleared = services.set_interest(interest.user, Plan.objects.get(slug="tier-1"))
        self.assertIsNone(cleared.sale_percent_off)
        self.assertEqual(InterestRegistration.history.filter(id=interest.id).first().sale_percent_off, None)
        self.assertTrue(any(h.sale_percent_off == 20 for h in InterestRegistration.history.filter(id=interest.id)))  # history keeps it
        again = services.set_interest(interest.user, Plan.objects.get(slug="tier-2"))
        self.assertEqual(again.sale_percent_off, 20)  # a new choice inside a live sale is a new snapshot

    def test_nothing_is_added_after_the_sale_ended_but_a_held_price_stays_on_a_covered_plan(self):
        sale = make_sale()
        holder = self.register("tier-2")
        late = self.register("tier-1")
        sales.end_now(sale, None)
        self.assertIsNone(services.set_interest(late.user, Plan.objects.get(slug="tier-2")).sale_percent_off)
        self.assertIsNone(self.register("tier-2").sale_percent_off)
        self.assertEqual(services.set_interest(holder.user, Plan.objects.get(slug="tier-3")).sale_percent_off, 20)
        self.assertEqual(sales.kept_price(User.objects.get(pk=holder.user_id).interest)["sale_price_ex_vat"], "399.20")


class EndNowAndPreviewTests(TestCase):
    def setUp(self):
        seed_all()

    def test_end_now_ends_a_live_sale_cancels_an_upcoming_one_and_refuses_an_ended_one(self):
        live, upcoming = make_sale(), make_sale(start=100, end=101)
        sales.end_now(live, None)
        live.refresh_from_db()
        self.assertEqual(live.status(), "ended")
        self.assertIsNone(sales.live_sale())
        sales.end_now(upcoming, None)
        upcoming.refresh_from_db()
        self.assertEqual((upcoming.status(), upcoming.ended_early_at), ("ended", upcoming.starts_at))
        with self.assertRaises(ValidationError):
            sales.end_now(live, None)

    def test_the_bar_is_public_host_only_and_a_preview_token_expires(self):
        sale = make_sale(start=48, end=72)
        factory = RequestFactory()

        def request(path="/", urlconf=None):
            req = factory.get(path)
            req.session = {}
            if urlconf:
                req.urlconf = urlconf
            return req

        self.assertIsNone(sales.sale_bar_for_request(request()))  # upcoming: no bar without the link
        token = sales.preview_token(sale)
        opened = request(f"/?sale_preview={token}")
        sales.start_preview(opened)
        shown = sales.sale_bar_for_request(opened)
        self.assertEqual((shown["name"], shown["plans_text"], shown["preview"]), ("Christmas sale", "Tier 2 and Tier 3", True))
        self.assertIsNone(sales.sale_bar_for_request(request("/", "config.urls_system")))
        garbage = request("/?sale_preview=garbage")
        sales.start_preview(garbage)
        self.assertIsNone(sales.sale_bar_for_request(garbage))
        with mock.patch("django.core.signing.time.time", return_value=time.time() + sales.PREVIEW_SECONDS + 5):
            self.assertIsNone(sales.sale_from_token(token))
        req = request(f"/?sale_preview={token}")
        sales.start_preview(req)  # opened: the browser keeps it for an hour, then it stops
        again = request()
        again.session = req.session
        self.assertIsNotNone(sales.sale_bar_for_request(again))
        later = request()
        later.session = req.session
        with mock.patch("plans.sales.time.time", return_value=time.time() + sales.PREVIEW_SECONDS + 5):
            self.assertIsNone(sales.sale_bar_for_request(later))
        make_sale(start=-1, end=5, name="Live one")
        self.assertEqual(sales.sale_bar_for_request(request())["name"], "Live one")


class MemberContextTests(TestCase):
    def setUp(self):
        seed_all()

    def test_register_offer_and_the_members_kept_price_say_the_same_facts(self):
        self.assertIsNone(sales.register_offer())
        make_sale()
        offer = sales.register_offer()
        self.assertEqual(set(offer["prices"]), {"tier-2", "tier-3"})
        self.assertEqual(offer["prices"]["tier-2"]["sale_price_ex_vat"], "319.20")
        self.assertEqual(offer["text"], "Register during the Christmas sale and keep 20% off Tier 2 and Tier 3 for 3 months from your first payment.")
        user = services.register_interest(cleaned(plan="tier-3")).user
        from users import member

        kept = member.membership_context(user)["kept_price"]
        self.assertEqual((kept["text"], kept["sale_price_inc_vat"]), ("You keep 20% off Tier 3 for 3 months from your first payment.", "479.04"))
