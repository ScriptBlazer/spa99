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


def erase_task_records(ids, function_prefixes):
    """UK GDPR: remove django-q's records (finished, failed and still queued) of tasks whose function starts with one
    of `function_prefixes` and whose arguments include one of `ids` (ids are compared as text). Our tasks take only
    ids and return a plain status, so this clears the last trace of a person's id in the queue tables.
    Returns the number of rows removed."""
    from django.db.models import Q
    from django_q.models import OrmQ, Task

    wanted = {str(i) for i in ids}
    if not wanted:
        return 0

    def mentions(args, kwargs):
        values = [*(args or ()), *(kwargs or {}).values()]
        return any(str(value) in wanted for value in values)

    prefix_filter = Q()
    for prefix in function_prefixes:
        prefix_filter |= Q(func__startswith=prefix)
    task_ids = [t.pk for t in Task.objects.filter(prefix_filter).iterator() if mentions(t.args, t.kwargs)]
    removed = Task.objects.filter(pk__in=task_ids).delete()[0] if task_ids else 0

    queued = []  # waiting in the queue: the payload is a signed package, decoded by OrmQ.task
    for row in OrmQ.objects.all().iterator():
        package = row.task
        function = package.get("func")
        name = function if isinstance(function, str) else getattr(function, "__module__", "") + "." + getattr(function, "__name__", "")
        if name.startswith(tuple(function_prefixes)) and mentions(package.get("args"), package.get("kwargs")):
            queued.append(row.pk)
    if queued:
        removed += OrmQ.objects.filter(pk__in=queued).delete()[0]
    return removed
