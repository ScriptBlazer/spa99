"""Background tasks (django-q2, database queue). Example task plus a thin enqueue helper."""
import logging

from django.utils import timezone

logger = logging.getLogger("spa99.tasks")


def heartbeat():
    """Trivial scheduled task: proves the worker and scheduler are alive."""
    now = timezone.now()
    logger.info("Worker heartbeat at %s", now.isoformat())
    return now.isoformat()


def enqueue(function_path, *args, **kwargs):
    """Queue `function_path` (e.g. 'common.tasks.heartbeat') for the worker. Runs inline when Q_CLUSTER sync is on."""
    from django_q.tasks import async_task

    return async_task(function_path, *args, **kwargs)
