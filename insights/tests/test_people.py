"""Office counting rules (docs/features/office-counting-rules.md): people, one vote each, staff excluded, one stored
snapshot per page and range, and pages that read it in a fixed number of queries."""
from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from unittest import mock

from insights import metrics, people
from insights.models import Insight, OfficeSnapshot, SnapshotRefresh
from insights.tests.test_metrics import cleaned, finished_journey
from journey import services as journey
from journey.models import JourneySession
from office import selectors, snapshots
from office.tests.test_office import OFFICE, OfficeTestCase, staff
from plans.management.commands.seed_phase1 import seed_all
from users import services
from users.models import User


def today():
    return metrics.day()


class PeopleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_restart_in_the_same_browser_is_one_person(self):
        first = journey.create_session("Mozilla/5.0 (iPhone) Safari/604.1")
        again = journey.create_session("Mozilla/5.0 (iPhone) Safari/604.1", previous=first)
        self.assertEqual(again.person_key, first.person_key)
        self.assertEqual(people.load().started(None, today()), 1)

    def test_two_browsers_become_one_person_once_linked_to_one_account(self):
        a, b = finished_journey(), finished_journey(time="daytime")
        self.assertEqual(people.load().started(None, today()), 2)  # two browsers, not yet known
        user = User.objects.create_user("same@example.com", "a-long-password-1")
        journey.link_user(a, user)
        journey.link_user(b, user)
        figures = people.load()
        self.assertEqual((figures.started(None, today()), figures.finished(None, today())), (1, 1))
        voters, answers, _ = figures.vote_counts(None, today())
        self.assertEqual(voters, 1)
        self.assertEqual(answers.get("time:daytime") or answers.get("time:evening"), 1)  # one vote: the latest journey only
        self.assertNotEqual(answers.get("time:daytime"), answers.get("time:evening"))

    def test_bots_and_staff_are_never_counted(self):
        finished_journey()
        boss = User.objects.create_user("boss@example.com", "a-long-password-1", is_staff=True)
        mine = finished_journey()
        journey.link_user(mine, boss)
        journey.create_session("Googlebot/2.1")
        services.register_interest(cleaned())
        from users.models import InterestRegistration
        InterestRegistration.objects.create(user=boss)  # a staff account's registration is not counted either
        figures = people.load()
        self.assertEqual((figures.started(None, today()), figures.finished(None, today()), figures.registered(None, today())), (1, 1, 1))

    def test_answers_are_one_vote_per_person_and_agree_with_the_rings_and_insights(self):
        finished_journey(time="evening")
        finished_journey(time="evening")
        finished_journey(time="daytime")
        user = User.objects.create_user("v@example.com", "a-long-password-1")
        for session in JourneySession.objects.all()[:1]:  # one of the browsers signs up: still three people
            journey.link_user(session, user)
        snapshots.build_everything()
        dashboard = selectors.dashboard("7d")
        rings = {r["key"]: r["value"] for r in dashboard["rings"]}
        top = Insight.objects.get(range="7d", key="time", rank=1)
        self.assertEqual((rings["journeys_started"], rings["journeys_completed"]), (3, 3))
        self.assertEqual((top.value, top.of_total), (2, rings["journeys_completed"]))  # "2 of 3" and the ring say 3
        self.assertEqual({i["key"]: i["top"]["of_total"] for i in dashboard["insights"] if i["key"] == "time"}, {"time": 3})


class SnapshotTests(OfficeTestCase):
    def setUp(self):
        self.owner = staff("Owner", "q@example.com")

    def queries(self, path):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.owner)
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(client.get(path).status_code, 200)
        return len(ctx)

    def test_a_missing_snapshot_is_an_empty_state_never_computed(self):
        self.assertFalse(OfficeSnapshot.objects.exists())
        with mock.patch("insights.people.load", side_effect=AssertionError("computed on page load")):
            for path in ("/", "/?range=all", "/analytics/", "/analytics/?range=all", "/dashboard.json", "/analytics/data/", "/analytics/pages/"):
                self.queries(path)
        self.assertEqual(selectors.dashboard("7d")["rings"][0]["value"], 0)

    def test_full_pages_run_a_fixed_number_of_queries_that_does_not_grow_with_data(self):
        paths = ["/", "/?range=all", "/?range=today", "/analytics/", "/analytics/?range=all", "/analytics/?range=7d"]
        snapshots.build_everything()
        empty = {p: self.queries(p) for p in paths}
        for i in range(5):
            finished_journey(time="evening" if i % 2 else "daytime")
            services.register_interest(cleaned(email=f"n{i}@example.com", mobile=f"0791234567{i}"))
        snapshots.build_everything()
        for path in paths:
            self.assertEqual(self.queries(path), empty[path], path)
            self.assertLessEqual(empty[path], 20, path)

    def test_snapshots_are_idempotent_all_ranges_exist_and_the_all_range_has_no_previous_period(self):
        finished_journey()
        snapshots.build_everything()
        first = sorted(OfficeSnapshot.objects.values_list("page", "range", "payload"), key=str)
        snapshots.build_everything()
        self.assertEqual(first, sorted(OfficeSnapshot.objects.values_list("page", "range", "payload"), key=str))
        self.assertEqual(OfficeSnapshot.objects.count(), 4 + 4 + 4)
        everything = selectors.dashboard("all")
        self.assertEqual(everything["range"], "all")
        self.assertTrue(all(r["previous"] is None and r["change"] is None for r in everything["rings"]))

    def test_events_queue_one_debounced_refresh_after_commit_and_a_burst_queues_one(self):
        with mock.patch("common.tasks.enqueue") as queued:
            with self.captureOnCommitCallbacks(execute=True):
                services.register_interest(cleaned())
                services.register_interest(cleaned(email="two@example.com", mobile="07911111111"))
            queued.assert_called_once_with("office.snapshots.refresh")
            self.assertIsNotNone(SnapshotRefresh.objects.get().queued_at)
            with self.captureOnCommitCallbacks(execute=True):
                services.register_interest(cleaned(email="three@example.com", mobile="07922222222"))
            queued.assert_called_once()  # still waiting: no second job
        snapshots.refresh()  # the job clears the flag and rebuilds
        self.assertIsNone(SnapshotRefresh.objects.get().queued_at)
        self.assertEqual(selectors.dashboard("7d")["rings"][2]["value"], 3)


class BackfillTests(TestCase):
    def test_backfill_person_key_dry_run_then_real(self):
        seed_all()
        session = journey.create_session("Mozilla/5.0 (iPhone) Safari/604.1")
        JourneySession.objects.filter(pk=session.pk).update(person_key="")
        out = StringIO()
        call_command("backfill_person_key", "--dry-run", stdout=out)
        self.assertIn("1 journey session", out.getvalue())
        self.assertEqual(JourneySession.objects.get().person_key, "")
        call_command("backfill_person_key", stdout=StringIO())
        session.refresh_from_db()
        self.assertEqual(session.person_key, session.key)
