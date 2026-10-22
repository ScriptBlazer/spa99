from django.core.management.base import BaseCommand
from django_q.models import Schedule

SCHEDULES = [
    {"name": "heartbeat", "func": "common.tasks.heartbeat", "schedule_type": Schedule.HOURLY},
]


class Command(BaseCommand):
    help = "Create or update the recurring jobs (safe to run on every worker start)."

    def handle(self, *args, **options):
        for spec in SCHEDULES:
            defaults = {key: value for key, value in spec.items() if key != "name"}
            _, created = Schedule.objects.update_or_create(name=spec["name"], defaults=defaults)
            self.stdout.write(f"{'Created' if created else 'Checked'} schedule: {spec['name']}")
