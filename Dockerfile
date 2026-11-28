# Live image. Built by GitHub Actions on a version tag (1.2.3) and pulled by the server; never built on the server.
# No secrets in here: every live value comes from the server .env at run time.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# Runtime dependencies only (requirements-dev.txt never goes in the image).
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code is owned by root and read-only to the app. .private/ (empty fallback folder) and staticfiles/ are the only
# folders the app user may write; nothing in them outlives the container (uploads go to S3, data to RDS).
COPY . .
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/.private /app/staticfiles \
    && chown -R app:app /app/.private /app/staticfiles \
    && chmod +x /app/entrypoint.sh
# Country data (DB-IP Country Lite, CC BY 4.0): this month's file, else last month's. The build carries on without it
# (every country then shows as "unknown"; a later build picks it up). Not part of git, never needs a secret.
ENV GEOIP_DB_PATH=/app/geoip/dbip-country-lite.mmdb
RUN mkdir -p /app/geoip && (python -m common.geoip_fetch "$GEOIP_DB_PATH" || echo "GeoIP file not downloaded: building without it")

USER app

# Hashed static files are built into the image (WhiteNoise serves them). The build settings need no secrets.
RUN DJANGO_SETTINGS_MODULE=config.settings.build SPA99_PRIVATE_DIR=/nonexistent python manage.py collectstatic --noinput

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["web"]
