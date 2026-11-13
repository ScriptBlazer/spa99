"""common 0003 drops the six tables of the removed WhatsApp app on a database that has them (live) and does nothing on one that does not (a fresh install)."""
import importlib

from django.db import connection
from django.test import TransactionTestCase

migration = importlib.import_module("common.migrations.0003_drop_whatsapp_tables")


class DropWhatsappTablesTests(TransactionTestCase):
    def tables(self):
        return set(connection.introspection.table_names())

    def run_migration(self):
        with connection.schema_editor() as editor:
            migration.drop_tables(None, editor)

    def test_a_database_with_the_tables_loses_them_and_the_old_migration_rows_and_a_fresh_one_is_untouched(self):
        self.run_migration()  # a fresh database: nothing to drop, and no error
        with connection.cursor() as cursor:
            for table in migration.TABLES:
                cursor.execute(f"CREATE TABLE {table} (id integer PRIMARY KEY)")
            cursor.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('whatsapp', '0001_initial', CURRENT_TIMESTAMP)")
        self.assertTrue(set(migration.TABLES) <= self.tables())
        self.run_migration()
        self.assertFalse(set(migration.TABLES) & self.tables())
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM django_migrations WHERE app = 'whatsapp'")
            self.assertEqual(cursor.fetchone()[0], 0)  # so a rollback to the old release rebuilds the (empty) tables by itself
        self.run_migration()  # twice is fine
