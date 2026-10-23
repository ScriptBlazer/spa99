"""Job last-run recording: wrap a job function with @tracked("name") and it stores started, finished, ok, a short message and
the duration in system.JobStatus, whoever runs it (worker, command or button). Recording never breaks the job."""
import time
from functools import wraps

from django.db import transaction
from django.utils import timezone


def _save(name, **fields):
    try:
        from system.models import JobStatus

        with transaction.atomic():
            JobStatus.objects.update_or_create(name=name, defaults=fields)
    except Exception:  # a broken status row must never stop the job
        import logging

        logging.getLogger("spa99.jobs").exception("Could not record job status for %s", name)


def tracked(name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            started, clock = timezone.now(), time.monotonic()
            _save(name, last_started_at=started)
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                _save(name, last_finished_at=timezone.now(), last_ok=False, last_message=f"{type(error).__name__}: {error}"[:300],
                      duration_ms=int((time.monotonic() - clock) * 1000))
                raise
            message = result if isinstance(result, str) else (", ".join(f"{k} {v}" for k, v in result.items()) if isinstance(result, dict) else "ok")
            _save(name, last_finished_at=timezone.now(), last_ok=True, last_message=str(message)[:300], duration_ms=int((time.monotonic() - clock) * 1000))
            return result
        return wrapper
    return decorator
