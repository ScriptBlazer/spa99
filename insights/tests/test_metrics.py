"""Stored figures: each event moves the right counters and daily rows, the roll-up is idempotent, rebuild matches the
live figures, and the cookieless visitor counter keeps no personal data. Mocked: sync queue, locmem email."""
from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone

from gold import invites
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from gold import services as gold_services
from insights import metrics, rebuild, rollup, visitors
from insights.metrics import K
from insights.models import DailyMetric, Insight, MetricCounter, MetricText, PeriodMetric, VisitorHash, VisitorSalt
from journey import engine
from journey import services as journey
from plans.management.commands.seed_phase1 import seed_all
from users import services
from users.tests.test_register import cleaned

User = get_user_model()
SAFARI = "Mozilla/5.0 (Macintosh) Safari/605.1"


def counter(key, dimension=""):
    row = MetricCounter.objects.filter(key=key, dimension=dimension).first()
    return row.value if row else 0


def today_row(key, dimension=""):
    row = DailyMetric.objects.filter(date=metrics.day(), key=key, dimension=dimension).first()
    return row.value if row else 0


def finished_journey(time="evening", frequency="two_three"):
    session = journey.create_session(SAFARI)
    for key, values in {"time": [time], "frequency": [frequency], "facilities": ["gym"], "company": ["alone"], "industry": ["finance"]}.items():
        journey.save_answer(session, key, options=values)
    journey.set_step(session, step=2)
    engine.complete(session)
    session.refresh_from_db()
    return session


class EventTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_registration_verification_plan_change_and_erasure(self):
        result = services.register_interest(cleaned(marketing_opt_in="on"))
        self.assertEqual((counter(K.REGISTRATIONS), today_row(K.REGISTRATIONS)), (1, 1))
        self.assertEqual((counter(K.REGISTRATIONS_BY_PLAN, "tier-2"), counter(K.REGISTRATIONS_BY_SOURCE, "direct"), counter(K.MARKETING_OPT_IN)), (1, 1, 1))
        user = result.user
        from users import tokens
        services.verify_email(tokens.make_verify_token(user))
        self.assertEqual((counter(K.EMAIL_VERIFIED), today_row(K.EMAIL_VERIFIED)), (1, 1))
        from plans.models import Plan
        services.set_interest(user, Plan.objects.get(slug="tier-1"))
        self.assertEqual((counter(K.REGISTRATIONS_BY_PLAN, "tier-2"), counter(K.REGISTRATIONS_BY_PLAN, "tier-1"), counter(K.REGISTRATIONS)), (0, 1, 1))
        self.assertEqual(today_row(K.REGISTRATIONS_BY_PLAN, "tier-1"), 1)
        self.assertEqual(rebuild.differences(), [])
        user.refresh_from_db()
        services.delete_user_data(user)
        self.assertEqual([counter(K.REGISTRATIONS), counter(K.REGISTRATIONS_BY_PLAN, "tier-1"), counter(K.EMAIL_VERIFIED), counter(K.MARKETING_OPT_IN)], [0, 0, 0, 0])
        self.assertEqual(rebuild.differences(), [])

    def test_journey_start_screens_completion_suggestion_and_answers(self):
        session = finished_journey()
        self.assertEqual((counter(K.JOURNEYS_STARTED), counter(K.JOURNEYS_COMPLETED), today_row(K.JOURNEYS_COMPLETED)), (1, 1, 1))
        self.assertEqual(counter(K.JOURNEY_SCREEN, "1"), 1)
        self.assertEqual(counter(K.JOURNEY_SCREEN, str(session.furthest_step - 1)), 1)  # reached up to the last screen
        self.assertEqual(counter(K.JOURNEY_ANSWER, "time:evening"), 1)
        self.assertEqual(MetricCounter.objects.filter(key=K.SUGGESTED_PLAN).first().value, 1)
        journey.create_session("Googlebot/2.1")  # bots are never counted
        self.assertEqual(counter(K.JOURNEYS_STARTED), 1)
        self.assertEqual(rebuild.differences(), [])

    def test_finishing_again_with_a_changed_answer_moves_the_counts_without_a_second_completion(self):
        session = finished_journey()
        journey.save_answer(session, "time", options=["daytime"])
        engine.complete(session)
        self.assertEqual((counter(K.JOURNEYS_COMPLETED), counter(K.JOURNEY_ANSWER, "time:evening"), counter(K.JOURNEY_ANSWER, "time:daytime")), (1, 0, 1))
        self.assertEqual(rebuild.differences(), [])

    def test_two_tabs_finishing_with_stale_copies_count_the_journey_once(self):
        from journey.models import JourneySession
        session = journey.create_session(SAFARI)
        for key, values in {"time": ["evening"], "frequency": ["two_three"], "facilities": ["gym"], "company": ["alone"], "industry": ["finance"]}.items():
            journey.save_answer(session, key, options=values)
        other_tab = JourneySession.objects.get(pk=session.pk)  # loaded before either finished
        engine.complete(session)
        engine.complete(other_tab)
        self.assertEqual((counter(K.JOURNEYS_COMPLETED), counter(K.JOURNEY_ANSWER, "time:evening")), (1, 1))
        self.assertEqual(rebuild.differences(), [])

    def test_admin_style_changes_move_the_figures(self):
        from plans.models import Plan
        user = services.register_interest(cleaned()).user
        interest = user.interest
        interest.plan = Plan.objects.get(slug="tier-1")
        interest.save()  # what the admin does
        self.assertEqual((counter(K.REGISTRATIONS_BY_PLAN, "tier-2"), counter(K.REGISTRATIONS_BY_PLAN, "tier-1")), (0, 1))
        from django.contrib.admin.sites import site
        from users.models import User as U
        user.refresh_from_db()
        site._registry[U].delete_model(None, user)  # the admin's delete goes through the erasure service
        self.assertEqual((counter(K.REGISTRATIONS), counter(K.REGISTRATIONS_BY_PLAN, "tier-1")), (0, 0))
        self.assertEqual(rebuild.differences(), [])

    def test_gold_application_approval_invite_use_decline_and_erasure(self):
        barry = User.objects.create_user("barry@example.com", "x", is_staff=True)
        first = gold_services.submit_application(application_data())[0]
        self.assertEqual((counter(K.GOLD_APPLICATIONS), counter(K.GOLD_BY_STATUS, "new"), today_row(K.GOLD_APPLICATIONS)), (1, 1, 1))
        self.assertEqual(counter(K.GOLD_BY_POTENTIAL, first.potential_level), 1)
        invites.approve_and_invite(first, barry)
        self.assertEqual((counter(K.GOLD_BY_STATUS, "new"), counter(K.GOLD_BY_STATUS, "approved"), counter(K.GOLD_APPROVED), counter(K.GOLD_INVITES_SENT)), (0, 1, 1, 1))
        token = invites.make_token(first.invites.get())
        invites.accept_invite(token, {"password": "correct horse battery staple", "date_of_birth": date(1990, 1, 1), "mobile": ""})
        self.assertEqual((counter(K.GOLD_INVITES_USED), counter(K.EMAIL_VERIFIED), counter(K.REGISTRATIONS_BY_PLAN, "gold")), (1, 1, 1))
        second = gold_services.submit_application(application_data(email="eli@example.com", mobile="+447911222333"))[0]
        self.assertTrue(invites.decline_application(second))
        self.assertFalse(invites.decline_application(second))
        self.assertEqual((counter(K.GOLD_BY_STATUS, "declined"), counter(K.GOLD_APPLICATIONS)), (1, 2))
        second.status = GoldApplication.CONTACTED  # the Django admin path moves the figures too
        second.save()
        self.assertEqual((counter(K.GOLD_BY_STATUS, "declined"), counter(K.GOLD_BY_STATUS, "contacted")), (0, 1))
        self.assertEqual(rebuild.differences(), [])
        services.delete_user_data(User.objects.get(email="dan@example.com"))
        self.assertEqual((counter(K.GOLD_APPLICATIONS), counter(K.GOLD_BY_STATUS, "approved"), counter(K.GOLD_APPROVED), counter(K.GOLD_INVITES_SENT)), (1, 0, 0, 0))
        self.assertEqual(rebuild.differences(), [])


class RollupAndRebuildTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_rollup_is_idempotent_writes_rates_weeks_months_and_sentences(self):
        today = metrics.day()
        DailyMetric.objects.bulk_create([
            DailyMetric(date=today, key=K.VISITORS, value=200), DailyMetric(date=today, key=K.PEOPLE_STARTED, value=50),
            DailyMetric(date=today, key=K.PEOPLE_FINISHED, value=25), DailyMetric(date=today, key=K.PEOPLE_REGISTERED, value=10), DailyMetric(date=today, key=K.REGISTRATIONS, value=10),
            DailyMetric(date=today - timedelta(days=1), key=K.VISITORS, value=100),
        ])
        rollup.run()
        snapshot = lambda: (  # noqa: E731
            sorted(DailyMetric.objects.values_list("date", "key", "dimension", "value")),
            sorted(PeriodMetric.objects.values_list("period", "start", "key", "dimension", "value")),
            sorted(MetricText.objects.values_list("key", "scope", "text")),
            sorted(MetricCounter.objects.values_list("key", "dimension", "value")),
        )
        first = snapshot()
        rollup.run()
        self.assertEqual(first, snapshot())
        self.assertEqual(DailyMetric.objects.get(date=today, key=K.RATE_JOURNEY_START).value, 2500)  # 25.00%
        self.assertEqual(DailyMetric.objects.get(date=today, key=K.RATE_JOURNEY_FINISH).value, 5000)
        self.assertEqual(DailyMetric.objects.get(date=today, key=K.RATE_REGISTER).value, 500)
        month = PeriodMetric.objects.filter(period="month", key=K.VISITORS, start=today.replace(day=1)).first()
        self.assertGreaterEqual(month.value, 200)
        self.assertTrue(PeriodMetric.objects.filter(period="week", key=K.REGISTRATIONS).exists())
        self.assertEqual(MetricCounter.objects.get(key=K.VISITORS).value, 300)
        self.assertIn("10 registrations", MetricText.objects.get(key="dashboard_changed", scope="today").text)

    def test_rebuild_matches_live_figures_and_repairs_a_wrong_one(self):
        finished_journey()
        services.register_interest(cleaned())
        self.assertEqual(rebuild.differences(), [])
        MetricCounter.objects.filter(key=K.REGISTRATIONS).update(value=99)
        DailyMetric.objects.create(date=date(2020, 1, 1), key=K.JOURNEYS_COMPLETED, value=7)
        out = StringIO()
        call_command("rebuild_metrics", "--dry-run", stdout=out)
        self.assertIn("2 difference(s)", out.getvalue())
        self.assertEqual(counter(K.REGISTRATIONS), 99)  # dry run changed nothing
        call_command("rebuild_metrics", stdout=StringIO())
        self.assertEqual(rebuild.differences(), [])
        self.assertEqual(counter(K.REGISTRATIONS), 1)


class CleanLabelTests(TestCase):
    def test_hint_is_dropped_but_a_real_parenthesis_stays(self):
        from insights.facts import clean_label
        self.assertEqual(clean_label("Often with someone (Most visits.)"), "Often with someone")
        self.assertEqual(clean_label("Early morning (5 to 9am)"), "Early morning (5 to 9am)")
        self.assertEqual(clean_label("Manager (block, estate, portfolio)"), "Manager (block, estate, portfolio)")


class InsightTests(TestCase):
    """The stored "what people want" table: written by the roll-up from the daily rows, never on a page load."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def snapshot(self):
        return sorted(Insight.objects.values_list("range", "key", "rank", "label", "value", "of_total", "sentence"))

    def test_nothing_is_written_without_data(self):
        rollup.run()
        self.assertEqual(Insight.objects.count(), 0)  # no "0 of 0"

    def test_roll_up_writes_insights_matching_the_daily_rows_and_is_idempotent(self):
        from journey.models import Option

        finished_journey(time="evening")
        finished_journey(time="evening")
        finished_journey(time="daytime")
        services.register_interest(cleaned())
        rollup.run()
        first = self.snapshot()
        rollup.run()
        self.assertEqual(first, self.snapshot())
        top, second = (Insight.objects.get(range="7d", key="time", rank=r) for r in (1, 2))
        label = lambda value: Option.objects.get(question__key="time", value=value).label  # noqa: E731
        self.assertEqual((top.label, top.value, top.of_total), (label("evening"), 2, 3))
        self.assertEqual((second.label, second.value), (label("daytime"), 1))
        self.assertIn("2 of 3", top.sentence)
        self.assertEqual(top.value, DailyMetric.objects.get(key=K.JOURNEY_ANSWER, dimension="time:evening").value)
        picked = Insight.objects.get(range="all", key="tier_picked", rank=1)
        self.assertEqual((picked.value, picked.of_total), (1, 1))
        self.assertFalse(Insight.objects.filter(key="source").exists())  # no referrer data: skipped
        DailyMetric.objects.filter(key=K.JOURNEY_ANSWER).delete()  # data gone: the rows go too
        rollup.run()
        self.assertFalse(Insight.objects.filter(key="time").exists())

    def test_rebuild_restores_insights_and_pages_read_them_in_one_query(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from office import selectors

        finished_journey(time="evening")
        rollup.run()
        before = self.snapshot()
        Insight.objects.all().delete()
        call_command("rebuild_metrics", stdout=StringIO())
        self.assertEqual(before, self.snapshot())
        with CaptureQueriesContext(connection) as ctx:
            data = selectors.insights_for("7d", 2)
        self.assertEqual(len(ctx), 1)
        self.assertIn("time", [i["key"] for i in data])
        pair = selectors.tier_pair(selectors.insights_for("all", 6))
        self.assertTrue(all({"label", "picked", "suggested"} <= set(p) for p in pair))


class VisitorCounterTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        visitors.forget_salts()

    def view(self, path="/", agent=SAFARI, host="localhost", addr="203.0.113.7", referer=""):
        extra = {"HTTP_USER_AGENT": agent, "HTTP_HOST": host, "REMOTE_ADDR": addr}
        if referer:
            extra["HTTP_REFERER"] = referer
        return self.factory.get(path, **extra)

    def count(self, request, status=200, content_type="text/html; charset=utf-8"):
        from django.http import HttpResponse
        from insights.middleware import VisitorCounterMiddleware

        request.urlconf = "config.urls"
        return VisitorCounterMiddleware(lambda r: HttpResponse("x", status=status, content_type=content_type))(request)

    def test_counts_views_and_one_unique_a_day_and_stores_no_personal_data(self):
        for path in ("/", "/plans/", "/plans/tier-2/"):
            self.count(self.view(path, referer="https://www.l.instagram.com/p/secret?utm=1"))
        self.count(self.view("/", addr="198.51.100.9"))
        self.assertEqual((today_row(K.VISITORS), today_row(K.PAGE_VIEWS), today_row(K.PAGE_VIEWS, "plans"), today_row(K.PAGE_VIEWS, "home")), (2, 4, 2, 2))
        self.assertEqual((today_row(K.REFERRERS, "l.instagram.com"), today_row(K.REFERRERS, "direct")), (3, 1))
        everything = " ".join(str(v) for model in (VisitorHash, VisitorSalt, DailyMetric, MetricCounter) for v in model.objects.values_list())
        for secret in ("203.0.113.7", "198.51.100.9", "Safari", "Macintosh", "secret", "utm=1"):
            self.assertNotIn(secret, everything)
        self.assertEqual(VisitorHash.objects.count(), 2)

    def test_people_steps_count_once_a_day_nest_and_store_no_ip(self):
        request = self.view()
        request.urlconf = "config.urls"
        visitors.record_step(request, "started")
        visitors.record_step(request, "started")  # a second window, same person: still one
        self.assertEqual((today_row(K.VISITORS), today_row(K.PEOPLE_STARTED), today_row(K.PEOPLE_FINISHED)), (1, 1, 0))  # never seen as a page view: still a visitor
        visitors.record_step(request, "registered")  # skipping a step still counts the earlier ones
        visitors.record_step(request, "finished")
        self.assertEqual([today_row(k) for k in (K.VISITORS, K.PEOPLE_STARTED, K.PEOPLE_FINISHED, K.PEOPLE_REGISTERED)], [1, 1, 1, 1])
        self.count(request)  # the page view of the same person adds no second visitor
        self.assertEqual(today_row(K.VISITORS), 1)
        other = self.view(addr="198.51.100.9")
        other.urlconf = "config.urls"
        visitors.record_step(other, "started")
        self.assertEqual([today_row(K.VISITORS), today_row(K.PEOPLE_STARTED), today_row(K.PEOPLE_REGISTERED)], [2, 2, 1])
        everything = " ".join(str(v) for model in (VisitorHash, VisitorSalt, DailyMetric) for v in model.objects.values_list())
        for secret in ("203.0.113.7", "198.51.100.9", "Safari", "Macintosh"):
            self.assertNotIn(secret, everything)

    def test_people_steps_skip_bots_staff_hosts_and_never_raise(self):
        bot = self.view(agent="Googlebot/2.1")
        bot.urlconf = "config.urls"
        staff = self.view(host="office.localhost")
        staff.urlconf = "config.urls_office"
        for request in (bot, staff):
            visitors.record_step(request, "started")
        self.assertEqual((VisitorHash.objects.count(), today_row(K.PEOPLE_STARTED)), (0, 0))
        request = self.view()
        request.urlconf = "config.urls"
        with mock.patch("insights.visitors.todays_salt", side_effect=RuntimeError("boom")):
            visitors.record_step(request, "started")  # logged and swallowed
        self.assertEqual(today_row(K.PEOPLE_STARTED), 0)

    def test_bots_staff_hosts_static_and_non_pages_are_not_counted(self):
        self.count(self.view(agent="Googlebot/2.1"))
        self.count(self.view(agent=""))
        self.count(self.view("/static/a.css"))
        self.count(self.view(), status=404)
        self.count(self.view(), content_type="application/json")
        request = self.view(host="office.localhost")
        from django.http import HttpResponse
        from insights.middleware import VisitorCounterMiddleware
        request.urlconf = "config.urls_office"
        VisitorCounterMiddleware(lambda r: HttpResponse("x"))(request)
        self.assertFalse(DailyMetric.objects.filter(key=K.PAGE_VIEWS).exists())

    def test_sentence_refresh_is_queued_not_run_in_the_request(self):
        with mock.patch("common.tasks.enqueue") as queued, mock.patch("insights.summaries.write_visitor_sentences") as direct:
            self.count(self.view())
        queued.assert_called_once_with("insights.summaries.write_visitor_sentences")
        direct.assert_not_called()

    def test_a_failure_never_breaks_the_page(self):
        with mock.patch("insights.visitors.record_page_view", side_effect=RuntimeError("db down")):
            response = self.count(self.view())
        self.assertEqual(response.status_code, 200)

    def test_hash_changes_with_the_daily_salt_and_rollup_wipes_finished_days(self):
        self.assertNotEqual(visitors.visitor_hash("salt-a", "1.2.3.4", "ua"), visitors.visitor_hash("salt-b", "1.2.3.4", "ua"))
        yesterday = metrics.day() - timedelta(days=1)
        VisitorSalt.objects.create(date=yesterday, salt="old")
        VisitorHash.objects.create(date=yesterday, hash="a" * 64)
        self.count(self.view())
        rollup.run()
        self.assertEqual((VisitorHash.objects.filter(date=yesterday).count(), VisitorSalt.objects.filter(date=yesterday).count()), (0, 0))
        self.assertEqual(VisitorHash.objects.filter(date=metrics.day()).count(), 1)  # today's is kept for de-duplication
