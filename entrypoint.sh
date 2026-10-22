#!/bin/sh
# web: run migrations, then start gunicorn.  worker: register schedules, then start the job worker.
# Anything else is run as given (e.g. `docker compose run --rm web python manage.py shell`).
set -e

case "$1" in
  web)
    python manage.py migrate --noinput
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --worker-tmp-dir /dev/shm \
      --access-logfile - \
      --error-logfile -
    ;;
  worker)
    python manage.py register_schedules
    exec python manage.py qcluster
    ;;
  *)
    exec "$@"
    ;;
esac
