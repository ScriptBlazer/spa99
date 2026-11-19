"""Office 2: the WhatsApp chat app is gone, so its six tables are dropped. This is schema clean-up, not a data backfill, and it is the whole reason this migration exists.

Why here and not in a `whatsapp` app: the app no longer exists in the code. Django would never run a migration inside it, and the tables would stay on live with their foreign keys to
users and Gold applications, which block deleting a person. A migration in `common` runs on every deploy (the entrypoint runs `migrate`), on any database:
  * a database that has the tables (live): they are dropped, children first;
  * a fresh database, or a throwaway one built from main's state: they never existed, `IF EXISTS` does nothing.
The `django_migrations` rows of the old app are deleted as well. That is what makes a rollback to the previous release safe: its `migrate` then rebuilds the (empty) tables by itself,
and the chats come back only from the RDS snapshot taken before the deploy (docs/GO-LIVE.md, "Office 2"). Plain `DROP TABLE IF EXISTS`, no CASCADE: the same SQL on SQLite and PostgreSQL.
Not reversible on purpose: there is nothing to rebuild the chats from."""
from django.db import migrations

# children first: the foreign keys point message -> contact, message -> template, contactread -> contact
TABLES = ["whatsapp_message", "whatsapp_contactread", "whatsapp_pushsubscription", "whatsapp_whatsappprefs", "whatsapp_contact", "whatsapp_template"]


def drop_tables(apps, schema_editor):
    quote = schema_editor.connection.ops.quote_name
    for table in TABLES:
        schema_editor.execute(f"DROP TABLE IF EXISTS {quote(table)}")
    schema_editor.execute("DELETE FROM django_migrations WHERE app = %s", ["whatsapp"])


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(drop_tables, migrations.RunPython.noop),
    ]
