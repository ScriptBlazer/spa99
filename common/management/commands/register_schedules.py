from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule

SCHEDULES = [
    {"name": "heartbeat", "func": "common.tasks.heartbeat", "schedule_type": Schedule.HOURLY},
    {"name": "metrics-rollup", "func": "insights.rollup.scheduled", "schedule_type": Schedule.HOURLY},
    {"name": "system-audit-verify", "func": "system.audit.scheduled", "schedule_type": Schedule.HOURLY},
    # Daily from the next 00:01 London (`at`): "today" starts empty and the Dashboard must not wait for the next hourly run
    {"name": "metrics-rollup-midnight", "func": "insights.rollup.scheduled", "schedule_type": Schedule.DAILY, "at": (0, 1)},
]


def next_at(hour, minute):
    """The next London wall-clock time hour:minute, as an aware datetime."""
    now = timezone.localtime()
    first = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return first if first > now else first + timedelta(days=1)


class Command(BaseCommand):
    help = "Create or update the recurring jobs (safe to run on every worker start)."

    def handle(self, *args, **options):
        for spec in SCHEDULES:
            defaults = {key: value for key, value in spec.items() if key not in ("name", "at")}
            existing = Schedule.objects.filter(name=spec["name"]).exists()
            if "at" in spec and not existing:
                defaults["next_run"] = next_at(*spec["at"])  # only a new schedule is given its first run; later ones keep their rhythm
            _, created = Schedule.objects.update_or_create(name=spec["name"], defaults=defaults)
            self.stdout.write(f"{'Created' if created else 'Checked'} schedule: {spec['name']}")
