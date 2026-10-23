from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from gold.models import GoldApplication
from insights import services
from journey import engine
from journey import services as journey
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan
from users.models import InterestRegistration, User


def session_with(answers, finish=True, user_agent="Mozilla/5.0 Safari", **fields):
    session = journey.create_session(user_agent, referrer=fields.pop("referrer", ""), utm=fields.pop("utm", None))
    for key, values in answers.items():
        journey.save_answer(session, key, options=values)
    if finish:
        engine.complete(session)
    for name, value in fields.items():
        setattr(session, name, value)
    session.save()
    return session


class StatisticsTests(TestCase):
    """A small, known set of visitors so every number can be checked by hand."""

    @classmethod
    def setUpTestData(cls):
        seed_all()
        # Visitor 1: evenings, 2-3 a week, sometimes with a guest, property owner with a big portfolio. Suggested Tier 3.
        cls.s1 = session_with({
            "time": ["evening"], "frequency": ["two_three"], "facilities": ["gym", "wet_sauna"], "company": ["sometimes"],
            "industry": ["property"], "property_link": ["owner_investor"], "property_size": ["50_199"],
            "heard_via": ["social_media"],
        }, referrer="https://l.instagram.com/", utm={"utm_source": "instagram"})
        # Visitor 2: daytime, once a week, alone, finance. Suggested Tier 1.
        cls.s2 = session_with({
            "time": ["daytime"], "frequency": ["weekly"], "facilities": ["gym"], "company": ["alone"],
            "industry": ["finance"], "heard_via": ["friend"],
        })
        # Visitor 3: daytime and evening, most days; stopped after screen 2 (never finished).
        cls.s3 = session_with({"time": ["daytime", "evening"], "frequency": ["most_days"]}, finish=False)
        journey.set_step(cls.s3, step=2)
        # A bot: never counted.
        cls.bot = session_with({"time": ["evening"]}, finish=False, user_agent="Googlebot/2.1")

        # Visitor 1 registers for Tier 2 (differs from the Tier 3 suggestion); visitor 2 takes Tier 1 (agrees).
        for session, email, slug in [(cls.s1, "one@example.com", "tier-2"), (cls.s2, "two@example.com", "tier-1")]:
            user = User.objects.create_user(email, "x")
            session.user = user
            session.save()
            InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug=slug), source="journey", journey_session=session)
        GoldApplication.objects.create(
            first_name="One", last_name="Owner", email="one@example.com", property_link="owner_investor", journey_session=cls.s1,
        )

    def test_bots_are_excluded_and_the_funnel_counts_drop_off_per_screen(self):
        data = services.funnel(services.sessions())
        self.assertEqual(data["started"], 3)
        self.assertEqual([(s["screen"], s["reached"], s["drop_off"]) for s in data["steps"]], [(1, 3, 0), (2, 3, 0), (3, 2, 1), (4, 2, 0)])
        self.assertEqual((data["result"], data["registered"], data["gold"]), (2, 2, 1))

    def test_facility_interest_percent(self):
        data = {o["value"]: (o["count"], o["percent"]) for o in services.facilities(services.sessions())["options"]}
        self.assertEqual(data["gym"], (2, 100.0))
        self.assertEqual(data["wet_sauna"], (1, 50.0))
        self.assertEqual(data["massage_room"], (0, 0.0))

    def test_demand_by_time_band_weighted_by_frequency(self):
        bands = {b["value"]: b for b in services.demand_by_time(services.sessions())["bands"]}
        # evening: visitor 1 (2.5 a week) + half of visitor 3 (5 a week shared over two bands) = 5.0
        self.assertEqual(bands["evening"]["expected_weekly_visits"], 5.0)
        self.assertEqual(bands["evening"]["by_frequency"]["two_three"], 1)
        self.assertEqual(bands["evening"]["by_frequency"]["most_days"], 1)
        self.assertEqual(bands["daytime"]["expected_weekly_visits"], 3.5)  # visitor 2 (1) + half of visitor 3 (2.5)

    def test_tier_mix_and_projected_revenue_use_current_prices(self):
        data = services.tier_mix(services.sessions())
        plans = {p["slug"]: p for p in data["plans"]}
        self.assertEqual((plans["tier-3"]["suggested"], plans["tier-1"]["suggested"]), (1, 1))
        self.assertEqual((plans["tier-2"]["chosen"], plans["tier-1"]["chosen"]), (1, 1))
        self.assertEqual(data["chose_differently"], {"compared": 2, "different": 1, "percent": 50.0})
        self.assertEqual(data["projected_monthly_revenue_chosen"], {"ex_vat": "698.00", "inc_vat": "837.60"})
        Plan.objects.filter(slug="tier-2").update(price_ex_vat=Decimal("500.00"))  # price change shows straight away
        self.assertEqual(services.tier_mix(services.sessions())["projected_monthly_revenue_chosen"]["ex_vat"], "799.00")

    def test_industries_property_share_gold_spread_company_and_sources(self):
        qs = services.sessions()
        industries = services.industries(qs)
        self.assertEqual((industries["answered"], industries["property_sessions"], industries["property_percent"]), (2, 1, 50.0))
        self.assertEqual(industries["gold_potential"], {"high": 1, "medium": 0, "low": 1})
        company = {o["value"]: o["count"] for o in services.company(qs)["options"]}
        self.assertEqual((company["sometimes"], company["alone"]), (1, 1))
        sources = services.sources(qs)
        self.assertEqual({o["value"]: o["count"] for o in sources["heard_via"]}["social_media"], 1)
        self.assertEqual(sources["referrers"], [{"host": "l.instagram.com", "count": 1}])
        self.assertEqual(sources["utm_sources"], [{"source": "instagram", "count": 1}])

    def test_trend_filters_and_completed_only(self):
        today = timezone.localdate()
        self.assertEqual(services.trend(), [{"date": today.isoformat(), "registrations": 2, "gold": 1}])
        everything = services.summary()
        self.assertEqual(everything["funnel"]["started"], 3)
        tomorrow = today + timedelta(days=1)
        self.assertEqual(services.summary(date_from=tomorrow)["funnel"]["started"], 0)
        self.assertEqual(services.summary(date_from=today, date_to=today)["funnel"]["started"], 3)
        self.assertEqual(services.summary(completed=False)["funnel"]["started"], 1)
        self.assertEqual(services.summary(source="instagram")["funnel"]["started"], 1)


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        call_command("setup_roles", stdout=StringIO())

    def get(self, user=None, path="/insights/summary/", host="office.localhost"):
        client = Client(HTTP_HOST=host)
        if user:
            client.force_login(user)
        return client.get(path)

    def staff(self, email, group=None):
        user = User.objects.create_user(email, "x", is_staff=True)
        if group:
            user.groups.add(Group.objects.get(name=group))
        return user

    def test_anonymous_is_sent_to_login_and_staff_without_a_role_is_refused(self):
        anonymous = self.get()
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("/login/", anonymous["Location"])
        self.assertEqual(self.get(self.staff("norole@example.com")).status_code, 403)
        public_member = User.objects.create_user("member@example.com", "x")
        self.assertEqual(self.get(public_member).status_code, 403)

    def test_roles_can_read(self):
        for role in ("Owner", "Manager", "Viewer"):
            response = self.get(self.staff(f"{role}@example.com", role))
            self.assertEqual(response.status_code, 200, role)
            self.assertIn("funnel", response.json())
        superuser = User.objects.create_superuser("root@example.com", "x")
        self.assertEqual(self.get(superuser).status_code, 200)

    def test_bad_dates_and_the_public_host_has_no_such_page(self):
        viewer = self.staff("viewer2@example.com", "Viewer")
        self.assertEqual(self.get(viewer, "/insights/summary/?from=yesterday").status_code, 400)
        self.assertEqual(self.get(viewer, host="localhost").status_code, 404)

    def test_viewer_is_read_only_and_manager_cannot_manage_the_team(self):
        viewer = Group.objects.get(name="Viewer").permissions.values_list("codename", flat=True)
        self.assertTrue(all(code.startswith("view_") for code in viewer))
        manager = set(Group.objects.get(name="Manager").permissions.values_list("codename", flat=True))
        self.assertIn("change_plan", manager)
        self.assertNotIn("change_goldapplication", manager)
        self.assertNotIn("change_user", manager)
        self.assertNotIn("add_group", manager)
        owner = set(Group.objects.get(name="Owner").permissions.values_list("codename", flat=True))
        self.assertTrue({"change_goldapplication", "change_user", "add_group"} <= owner)
        call_command("setup_roles", stdout=StringIO())  # safe to run again
        self.assertEqual(Group.objects.count(), 4)
