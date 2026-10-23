"""Settings loading, storage choice and the prod safety checks. No network, no real folders."""
import importlib
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from common.envloader import Env, PrivateDir, example_keys, load_env, pick_settings_module
from common.settings_helpers import build_databases, build_media_storage, describe_database


def make_tmp(test):
    """A temp folder that is always removed after the test."""
    folder = tempfile.TemporaryDirectory()
    test.addCleanup(folder.cleanup)
    return Path(folder.name)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class EnvLoaderTests(SimpleTestCase):
    def setUp(self):
        self.tmp = make_tmp(self)
        self.base = self.tmp / "project"
        self.base.mkdir()

    def test_missing_private_dir_falls_back_to_project_private_folder(self):
        env = load_env(self.base, environ={"SPA99_PRIVATE_DIR": str(self.tmp / "does-not-exist")})
        self.assertTrue(env.private_dir.using_fallback)
        self.assertEqual(env.private_dir.path, self.base / ".private")
        self.assertTrue((self.base / ".private").is_dir())
        self.assertEqual(env.get("ANYTHING", "default"), "default")
        self.assertEqual(env.used_sources(), ["defaults"])

    def test_load_order_environment_then_private_then_project_then_defaults(self):
        private = self.tmp / "private"
        write(private / "env" / ".env", "A=private\nB=private\nC=private\n")
        write(self.base / ".env", "B=project\nC=project\nD=project\n")
        env = load_env(self.base, environ={"SPA99_PRIVATE_DIR": str(private), "A": "environment"})
        self.assertFalse(env.private_dir.using_fallback)
        self.assertEqual(
            [env.get(k) for k in "ABCD"], ["environment", "private", "private", "project"]
        )
        self.assertEqual(env.get("E", "fallback"), "fallback")
        self.assertEqual(env.used_sources(), ["environment", "private .env", "project .env", "defaults"])

    def test_missing_keys_are_reported_but_optional_ones_are_skipped(self):
        write(self.base / ".env.example", "# needed\nNEEDED=x\n\n# (optional) not needed\nOPTIONAL=x\n\nALSO=y\n")
        write(self.base / ".env", "ALSO=1\n")
        env = load_env(self.base, environ={"SPA99_PRIVATE_DIR": str(self.tmp / "nope")})
        self.assertEqual(env.missing_example_keys(), ["NEEDED"])
        self.assertEqual(example_keys(self.base / ".env.example"), ["NEEDED", "ALSO"])

    def test_settings_module_is_read_from_env_files_and_environment_wins(self):
        write(self.base / ".env", "DJANGO_SETTINGS_MODULE=config.settings.prod\n")
        nope = {"SPA99_PRIVATE_DIR": str(self.tmp / "nope")}
        self.assertEqual(pick_settings_module(self.base, "config.settings.dev", nope), "config.settings.prod")
        override = {**nope, "DJANGO_SETTINGS_MODULE": "x.y"}
        self.assertEqual(pick_settings_module(self.base, "config.settings.dev", override), "x.y")
        self.assertEqual(pick_settings_module(self.tmp, "config.settings.dev", nope), "config.settings.dev")

    def test_empty_values_count_as_unset(self):
        env = Env([("environment", {"X": ""}), ("project .env", {"X": "real"})], None)
        self.assertEqual(env.get("X"), "real")


class StorageAndDatabaseTests(SimpleTestCase):
    def env(self, **values):
        return Env([("environment", values)], None)

    def test_s3_used_when_configured_with_dev_prefix(self):
        env = self.env(AWS_STORAGE_BUCKET_NAME="spa99-media", AWS_ACCESS_KEY_ID="k", AWS_SECRET_ACCESS_KEY="s")
        storage, description = build_media_storage(env, "dev/", "/x", require_credentials=True)
        self.assertEqual(storage["BACKEND"], "storages.backends.s3.S3Storage")
        self.assertEqual(storage["OPTIONS"]["location"], "dev/")
        self.assertTrue(storage["OPTIONS"]["querystring_auth"])
        self.assertEqual(storage["OPTIONS"]["region_name"], "eu-west-2")
        self.assertEqual(description, "s3:spa99-media/dev/")

    def test_falls_back_to_local_files_without_s3_settings_or_credentials(self):
        for values in ({}, {"AWS_STORAGE_BUCKET_NAME": "spa99-media"}):
            storage, description = build_media_storage(self.env(**values), "dev/", "/media-dir", True)
            self.assertTrue(storage["BACKEND"].endswith("FileSystemStorage"))
            self.assertEqual(storage["OPTIONS"]["location"], "/media-dir")
            self.assertTrue(description.startswith("local:"))

    def test_prod_uses_instance_role_so_no_keys_needed(self):
        storage, _ = build_media_storage(self.env(AWS_STORAGE_BUCKET_NAME="b"), "prod/", "/x", require_credentials=False)
        self.assertNotIn("access_key", storage["OPTIONS"])
        self.assertEqual(storage["OPTIONS"]["location"], "prod/")

    def test_database_defaults_and_description_hide_credentials(self):
        sqlite = build_databases(None, "/tmp/db.sqlite3")
        self.assertEqual(describe_database(sqlite), "sqlite3:/tmp/db.sqlite3")
        postgres = build_databases("postgres://user:secret@db.example.com:5432/spa99", None, require_ssl=True)
        self.assertEqual(postgres["default"]["OPTIONS"]["sslmode"], "require")
        description = describe_database(postgres)
        self.assertEqual(description, "postgresql:spa99@db.example.com")
        self.assertNotIn("secret", description)


class ProdSettingsTests(SimpleTestCase):
    """prod.py must refuse to start without a real SECRET_KEY and DATABASE_URL."""

    GOOD = {
        "SECRET_KEY": "k8s-Zq3!xv9Lm2Pw7Tn5Rb4Hc6Jd1Fg0Ya8Ue3Oi5Kp7Ws9Qx2Mz4Vb6Nc1Ld",
        "DATABASE_URL": "postgres://u:p@db.example.com:5432/spa99",
        "ADMIN_PATH": "my-own-hidden-door-91x/",
        "DEFAULT_FROM_EMAIL": "Spa 99 <noreply@example.com>",
    }

    def import_prod(self, environ):
        tmp = make_tmp(self)
        private = PrivateDir(tmp, using_fallback=True, writable=True, fallback_path=tmp)
        fake_loader = lambda base_dir: Env([("environment", environ)], private, None)  # noqa: E731
        names = ["config.settings.base", "config.settings.prod"]
        saved = {name: sys.modules.pop(name, None) for name in names}
        try:
            with mock.patch("common.envloader.load_env", fake_loader):
                return importlib.import_module("config.settings.prod")
        finally:
            for name in names:
                sys.modules.pop(name, None)
                if saved[name] is not None:
                    sys.modules[name] = saved[name]

    def test_starts_with_real_values(self):
        settings = self.import_prod(self.GOOD)
        self.assertFalse(settings.DEBUG)
        self.assertEqual(settings.DATABASES["default"]["OPTIONS"]["sslmode"], "require")
        self.assertIn("https://control.spa99.uk", settings.CSRF_TRUSTED_ORIGINS)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)

    def test_refuses_missing_or_dev_secret_key(self):
        for secret in (None, "", "dev-insecure-key-not-for-production-use-0123456789abcdef", "change-me-please"):
            environ = {**self.GOOD}
            environ.pop("SECRET_KEY")
            if secret:
                environ["SECRET_KEY"] = secret
            with self.subTest(secret=secret), self.assertRaises(ImproperlyConfigured):
                self.import_prod(environ)

    def test_refuses_missing_database_url(self):
        with self.assertRaises(ImproperlyConfigured):
            self.import_prod({"SECRET_KEY": self.GOOD["SECRET_KEY"]})

    def test_refuses_missing_default_from_email(self):
        environ = {**self.GOOD}
        environ.pop("DEFAULT_FROM_EMAIL")
        with self.assertRaises(ImproperlyConfigured):
            self.import_prod(environ)

    def test_mail_transport_comes_from_env_but_recipients_are_not_settings_any_more(self):
        settings = self.import_prod({**self.GOOD, "GOLD_APPROVER_EMAILS": "a@example.com", "CONTACT_EMAIL": "hi@example.com"})
        self.assertEqual(settings.SERVER_EMAIL, "Spa 99 <noreply@example.com>")
        for name in ("GOLD_APPROVER_EMAILS", "GOLD_APPROVER_CC", "CONTACT_EMAIL"):  # these live in System (SiteSettings) now
            self.assertFalse(hasattr(settings, name))

    def test_system_host_is_allowed_and_trusted_in_prod(self):
        settings = self.import_prod({**self.GOOD, "SYSTEM_DOMAIN": "system.example.com"})
        self.assertEqual(settings.SYSTEM_HOST, "system.example.com")
        self.assertIn("system.example.com", settings.ALLOWED_HOSTS)
        self.assertIn("https://system.example.com", settings.CSRF_TRUSTED_ORIGINS)
        self.assertEqual(self.import_prod(self.GOOD).SYSTEM_URL, "https://system.spa99.uk")

    def test_refuses_missing_or_default_admin_path(self):
        for admin_path in (None, "backstage-7d3f9a/", "/backstage-7d3f9a"):
            environ = {**self.GOOD}
            environ.pop("ADMIN_PATH")
            if admin_path:
                environ["ADMIN_PATH"] = admin_path
            with self.subTest(admin_path=admin_path), self.assertRaises(ImproperlyConfigured):
                self.import_prod(environ)

    def test_allowed_hosts_env_adds_to_defaults(self):
        settings = self.import_prod({**self.GOOD, "ALLOWED_HOSTS": "extra.example.com"})
        for host in ("spa99.uk", "control.spa99.uk", "localhost", "127.0.0.1", "extra.example.com"):
            self.assertIn(host, settings.ALLOWED_HOSTS)

    def test_local_media_in_prod_is_flagged(self):
        self.assertTrue(self.import_prod(self.GOOD).STARTUP_REPORT["media_is_local"])


class CorruptEnvFileTests(SimpleTestCase):
    def test_unreadable_env_file_is_ignored_with_a_warning(self):
        tmp = make_tmp(self)
        (tmp / ".env").write_bytes(b"\xff\xfe\x00bad=\x80\n")
        with self.assertLogs("spa99.startup", "WARNING"):
            env = load_env(tmp, environ={"SPA99_PRIVATE_DIR": str(tmp / "nope")})
        self.assertIsNone(env.get("bad"))
