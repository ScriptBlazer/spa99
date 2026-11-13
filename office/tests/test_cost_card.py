"""The Assistant page's Developer-only total-cost card: stored figures (the hourly job), shown to Developer level and up, nowhere else."""
from datetime import datetime, timezone as utc
from decimal import Decimal

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from chat.models import Conversation
from common import levels
from insights.models import OfficeSnapshot
from office import counts
from office.tests.test_office import OFFICE, OfficeTestCase
from plans.tests.helpers import make_team_member
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
NOW = datetime(2026, 7, 15, 12, 0, tzinfo=LONDON)  # summer time: London is one hour ahead of UTC


def chat(pence, when, staff_test=False):
    row = Conversation.objects.create(total_cost_pence=Decimal(pence), staff_test=staff_test)
    Conversation.objects.filter(pk=row.pk).update(created_at=when)
    return row


class StoredFiguresTests(OfficeTestCase):
    def test_totals_match_hand_sums_with_london_edges(self):
        chat("10", datetime(2026, 5, 20, 9, 0, tzinfo=utc.utc))                      # older: all time only
        chat("20", datetime(2026, 6, 30, 22, 30, tzinfo=utc.utc))                    # 23:30 London on 30 June: not this month
        chat("30", datetime(2026, 6, 30, 23, 30, tzinfo=utc.utc))                    # 00:30 London on 1 July: this month
        chat("40", datetime(2026, 7, 14, 22, 30, tzinfo=utc.utc))                    # 23:30 London on 14 July: not today
        chat("50", datetime(2026, 7, 14, 23, 30, tzinfo=utc.utc))                    # 00:30 London on 15 July: today
        chat("0.6", datetime(2026, 7, 15, 9, 0, tzinfo=utc.utc), staff_test=True)    # a staff test: counted as spend, today
        got = counts.compute_assistant_cost(NOW)
        self.assertEqual((Decimal(got["all"]["pence"]), got["all"]["chats"]), (Decimal("150.6"), 6))
        self.assertEqual((Decimal(got["month"]["pence"]), got["month"]["chats"]), (Decimal("120.6"), 4))
        self.assertEqual((Decimal(got["today"]["pence"]), got["today"]["chats"]), (Decimal("50.6"), 2))
        self.assertEqual((Decimal(got["test_pence"]), got["test_chats"]), (Decimal("0.6"), 1))

    def test_no_chats_is_zero_and_the_job_stores_it(self):
        got = counts.compute_all()["assistant_cost"]
        self.assertEqual((Decimal(got["all"]["pence"]), got["all"]["chats"]), (0, 0))

    def test_an_approval_refresh_keeps_the_stored_figure(self):
        counts._write({**counts.compute_all(), "assistant_cost": {"marker": 1}})
        counts.refresh_approvals()
        self.assertEqual(counts.read()["assistant_cost"], {"marker": 1})


class CardTests(OfficeTestCase):
    def setUp(self):
        self.url = "/chats/"
        chat("59", timezone.now())
        chat("2.1", timezone.now(), staff_test=True)

    def store(self):
        counts._write({**counts.empty(), "updating": False, "assistant_cost": counts.compute_assistant_cost()})

    def login(self, user):
        self.client = Client(HTTP_HOST=OFFICE)
        self.client.force_login(user)
        return self.client

    def get_as(self, level):
        user = make_team_member(f"{level}@example.test", level)
        return self.login(user).get(self.url)

    def test_developer_sees_the_card_with_the_stored_figures(self):
        self.store()
        html = self.get_as(levels.DEVELOPER).content.decode()
        self.assertIn("Total cost", html)
        self.assertIn("This month", html)
        self.assertIn("£0.611", html)               # 61.1p
        self.assertIn("2 chats", html)
        self.assertIn("including £0.021 of team tests", html)
        self.assertIn("£0.79 to the dollar", html)
        self.assertIn("Figures update every hour.", html)

    def test_other_levels_get_no_card_and_no_figure(self):
        self.store()
        for level in (levels.OFFICE, levels.ADMIN):
            html = self.get_as(level).content.decode()
            for needle in ("Total cost", "o-costcard", "£0.611", "team tests", "to the dollar", "data-cost"):
                self.assertNotIn(needle, html, f"{level}: {needle}")

    def test_non_developer_view_never_reads_the_stored_cost(self):
        self.store()
        user = make_team_member("office-only@example.test", levels.OFFICE)
        self.login(user)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)
        self.assertFalse([q for q in queries if "office_officesnapshot" in q["sql"] or "insights_officesnapshot" in q["sql"]])

    def test_a_missing_stored_figure_says_updating(self):
        OfficeSnapshot.objects.all().delete()
        html = self.get_as(levels.DEVELOPER).content.decode()
        self.assertIn("Updating", html)
        self.assertNotIn("£0.000", html)

    def test_the_page_runs_no_sum_over_chat_tables(self):
        self.store()
        user = make_team_member("dev2@example.test", levels.DEVELOPER)
        self.login(user)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)
        bad = [q["sql"] for q in queries if "chat_" in q["sql"].lower() and any(f in q["sql"].upper() for f in ("SUM(", "COUNT(", "AVG("))]
        self.assertEqual(bad, [])
