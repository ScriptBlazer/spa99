"""Daily housekeeping and the job schedule: tables that would otherwise grow forever are trimmed."""
import time
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from django_q.models import Schedule, Task

from common.tasks import housekeeping
from system.models import WrongTries


def make_task(name, stopped, success):
    return Task.objects.create(id=name.ljust(32, "x"), name=name, func="x.y", started=stopped, stopped=stopped, success=success)


class HousekeepingTests(TestCase):
    def test_trims_expired_sessions_old_failures_and_quiet_wrong_tries_only(self):
        now = timezone.now()
        Session.objects.create(session_key="old", session_data="x", expire_date=now - timedelta(days=1))
        Session.objects.create(session_key="live", session_data="x", expire_date=now + timedelta(days=1))
        make_task("oldfail", now - timedelta(days=31), False)
        make_task("newfail", now - timedelta(days=2), False)
        make_task("oldok", now - timedelta(days=90), True)  # successes are capped by save_limit instead
        WrongTries.objects.create(key="quiet", count=3, last_at=time.time() - 2 * 86400)
        WrongTries.objects.create(key="recent", count=3, last_at=time.time())

        housekeeping()

        self.assertEqual(set(Session.objects.values_list("session_key", flat=True)), {"live"})
        self.assertEqual(set(Task.objects.values_list("name", flat=True)), {"newfail", "oldok"})
        self.assertEqual(set(WrongTries.objects.values_list("key", flat=True)), {"recent"})

    @override_settings(SYSTEM_AUDIT_RETENTION_DAYS=0)
    def test_audit_kept_forever_by_default(self):
        with mock.patch("system.audit.prune") as prune:
            self.assertIn("'audit': 'kept'", housekeeping())
        prune.assert_not_called()

    @override_settings(SYSTEM_AUDIT_RETENTION_DAYS=400)
    def test_one_failing_part_does_not_stop_the_others(self):
        Session.objects.create(session_key="old", session_data="x", expire_date=timezone.now() - timedelta(days=1))
        with mock.patch("system.audit.prune", side_effect=RuntimeError("boom")), self.assertLogs("spa99.tasks", "ERROR"):
            result = housekeeping()
        self.assertIn("'audit': 'failed'", result)
        self.assertFalse(Session.objects.exists())

    def test_every_prune_job_is_scheduled_once(self):
        call_command("register_schedules", stdout=StringIO())
        call_command("register_schedules", stdout=StringIO())  # every worker start: no duplicates
        funcs = list(Schedule.objects.values_list("func", flat=True))
        for func in ("common.tasks.housekeeping", "chat.tasks.prune_scheduled", "insights.rollup.scheduled"):
            self.assertIn(func, funcs)
        self.assertEqual(Schedule.objects.filter(name="housekeeping").count(), 1)
