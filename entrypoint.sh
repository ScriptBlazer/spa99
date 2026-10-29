#!/bin/sh
# Container start (POSIX sh: the image's /bin/sh is dash, so no bash-isms and no pipefail; there are no pipes here).
#   web:    run migrations and create the cache table, then start gunicorn. Only web migrates.
#   worker: register the recurring jobs (safe to repeat), then start the job worker. It starts after web is healthy,
#           so the migrations are already done.
#   anything else is run as given, e.g. `docker compose run --rm web python manage.py setup_live --dry-run`.
set -eu

fail() {
    echo "entrypoint: $1" >&2
    exit 1
}

case "${1:-web}" in
  web)
    python manage.py migrate --noinput \
      || fail "migrations failed. Check DATABASE_URL and that the RDS security group lets this server in (the lines above say why)."
    python manage.py createcachetable \
      || fail "could not create the cache table (spa99_cache)."
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --worker-class gthread --threads "${GUNICORN_THREADS:-8}" \
      --worker-tmp-dir /dev/shm \
      --timeout "${GUNICORN_TIMEOUT:-300}" \
      --access-logfile - \
      --error-logfile -
    ;;
  worker)
    python manage.py register_schedules || fail "could not register the recurring jobs."
    exec python manage.py qcluster
    ;;
  *)
    exec "$@"
    ;;
esac
