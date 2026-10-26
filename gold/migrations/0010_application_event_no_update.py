"""Database-level guard for the Gold audit trail: a trigger that refuses any UPDATE of a gold_applicationevent row, so a raw
SQL or _base_manager edit fails too. The one allowed update is Django's own ON DELETE SET NULL when a team member's account is
deleted (actor_id becomes NULL, every other column unchanged). DELETE stays allowed: cascade and GDPR erasure need it.
Vendor-specific: SQLite and PostgreSQL each get their own SQL; any other database gets no trigger. Schema only, no data."""
from django.db import migrations

TABLE = "gold_applicationevent"
SAME = ["id", "application_id", "at", "actor_label", "action", "channel", "from_status", "to_status", "message"]


def create(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        changed = " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in [*SAME, "meta"])
        schema_editor.execute(
            f"CREATE TRIGGER {TABLE}_no_update BEFORE UPDATE ON {TABLE} "
            f"WHEN ({changed}) OR NEW.actor_id IS NOT NULL OR OLD.actor_id IS NULL "
            f"BEGIN SELECT RAISE(ABORT, 'The Gold audit trail cannot be edited.'); END")
    elif vendor == "postgresql":
        same = ", ".join(f"NEW.{c}" for c in [*SAME, "meta::text"])
        old = ", ".join(f"OLD.{c}" for c in [*SAME, "meta::text"])
        schema_editor.execute(
            f"CREATE FUNCTION {TABLE}_no_update() RETURNS trigger AS $$ BEGIN "
            f"IF NEW.actor_id IS NULL AND OLD.actor_id IS NOT NULL AND ({same}) IS NOT DISTINCT FROM ({old}) THEN RETURN NEW; END IF; "
            f"RAISE EXCEPTION 'The Gold audit trail cannot be edited.'; END; $$ LANGUAGE plpgsql")
        schema_editor.execute(f"CREATE TRIGGER {TABLE}_no_update BEFORE UPDATE ON {TABLE} FOR EACH ROW EXECUTE FUNCTION {TABLE}_no_update()")


def drop(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_update")
    elif vendor == "postgresql":
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_update ON {TABLE}")
        schema_editor.execute(f"DROP FUNCTION IF EXISTS {TABLE}_no_update()")


class Migration(migrations.Migration):
    dependencies = [("gold", "0009_application_event")]
    operations = [migrations.RunPython(create, drop)]
