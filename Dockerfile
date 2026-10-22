FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user. .private/ is the writable fallback folder the settings loader may create.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/.private /app/staticfiles \
    && chown -R app:app /app/.private /app/staticfiles
USER app

# Hashed static files are built into the image. The values below exist only so settings load at build time;
# they are not secrets and are not used at run time.
RUN SECRET_KEY="build-time-only-Zx81qLw0pVn3Rb5TyUc7Hd2Jf4Kg6Ma9" \
    DATABASE_URL="postgres://build:build@localhost:5432/build" \
    python manage.py collectstatic --noinput

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["web"]
