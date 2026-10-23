"""The audit log: security events, sentences, hash chain, append-only, feed, CSV, prune."""
import csv
import io
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from plans.models import Plan, SiteSettings
from system import audit, feed, sentences, services
from system.models import AppendOnlyError, AuditHead, SystemChange, SystemEvent
from system.tests.test_extras import SETTINGS_POST
from system.tests.test_system import PASSWORD, SYSTEM, make_user, sign_in, unlocked_client

UA = "TestBrowser/1.0"


def kinds():
    return list(SystemEvent.objects.order_by("seq").values_list("kind", flat=True))


class EventTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def visitor(self):
        return Client(HTTP_HOST=SYSTEM, HTTP_USER_AGENT=UA, REMOTE_ADDR="203.0.113.9")

    def test_sign_in_unlock_lock_out_are_recorded_with_ip_and_browser(self):
        client = self.visitor()
        client.post("/login/", {"username": self.user.email, "password": PASSWORD})
        client.post("/unlock/", {"password": "wrong"})
        client.post("/unlock/", {"password": PASSWORD})
        client.post("/lock/")
        client.post("/logout/")
        self.assertEqual(kinds(), ["sign_in", "unlock_failed", "unlock", "lock_manual", "sign_out"])
        first = SystemEvent.objects.get(kind="sign_in")
        self.assertEqual((first.user, first.user_label, first.ip_address, first.user_agent), (self.user, self.user.email, "203.0.113.9", UA))
        self.assertEqual(SystemEvent.objects.get(kind="unlock_failed").outcome, "failed")

    def test_failed_sign_in_on_system_records_the_email_but_the_public_host_does_not(self):
        self.visitor().post("/login/", {"username": "Nobody@Example.com", "password": "x"})
        event = SystemEvent.objects.get()
        self.assertEqual((event.kind, event.user, event.user_label), ("sign_in_failed", None, "nobody@example.com"))
        Client(HTTP_HOST="localhost").post("/login/", {"username": "x@example.com", "password": "x"})
        self.assertEqual(SystemEvent.objects.count(), 1)

    def test_idle_lock_is_recorded_once_when_the_next_request_finds_it_expired(self):
        client, _ = sign_in(self.user)
        with mock.patch("system.services.time.time", return_value=1000.0):
            client.post("/unlock/", {"password": PASSWORD})
        with mock.patch("system.services.time.time", return_value=1000.0 + 2000):
            client.get("/")
            client.get("/")
        self.assertEqual(kinds().count("lock_idle"), 1)

    def test_session_expired_after_the_hard_limit(self):
        client = unlocked_client(self.user)
        with mock.patch("system.services.time.time", return_value=__import__("time").time() + 13 * 3600):
            client.get("/")
        self.assertIn("session_expired", kinds())

    def test_unlock_rate_limit_is_recorded_once(self):
        client, _ = sign_in(self.user)
        with mock.patch("system.views.hit", return_value=False):
            for _ in range(3):
                client.post("/unlock/", {"password": "x"})
        self.assertEqual(kinds().count("unlock_rate_limited"), 1)

    def test_access_denied_is_deduped_per_ip(self):
        stranger = self.visitor()
        for path in ("/", "/plans/", "/nope/"):
            self.assertEqual(stranger.get(path).status_code, 404)
        self.assertEqual(SystemEvent.objects.filter(kind="access_denied").count(), 1)
        Client(HTTP_HOST=SYSTEM, REMOTE_ADDR="198.51.100.4").get("/")
        self.assertEqual(SystemEvent.objects.filter(kind="access_denied").count(), 2)
        self.assertEqual(SystemEvent.objects.filter(kind="access_denied").first().outcome, "blocked")

    def test_roles_deactivate_undo_and_export_are_recorded(self):
        client = unlocked_client(self.user)
        other = make_user("other@example.com", system=False)
        Group.objects.get_or_create(name="Manager")
        client.post(f"/team/{other.pk}/roles/", {"roles": ["Manager"]})
        client.post(f"/team/{other.pk}/active/", {"active": "0"})
        client.post(f"/team/{other.pk}/active/", {"active": "1"})
        client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00"})
        change = SystemChange.objects.get(field="vat_rate")
        client.post(f"/changes/{change.pk}/undo/")
        client.get("/changes/export.csv")
        self.assertTrue(set(["role_changed", "user_deactivated", "user_reactivated", "undo", "export"]) <= set(kinds()))
        self.assertIn("Manager", SystemEvent.objects.get(kind="role_changed").sentence)


class SentenceTests(TestCase):
    def test_money_percent_bool_choice_and_lists(self):
        plan = Plan.objects.first() or Plan.objects.create(name="Tier 1", slug="tier-1", price_ex_vat="299.00")
        self.assertEqual(sentences.change_sentence("updated", Plan, "Tier 1", "price_ex_vat", "299.00", "319.00"),
                         "Changed Tier 1 · Price ex VAT from £299.00 to £319.00")
        self.assertIn("from 20% to 25%", sentences.change_sentence("updated", SiteSettings, "Site", "vat_rate", "20.00", "25.00"))
        self.assertIn("from off to on", sentences.change_sentence("updated", SiteSettings, "Site", "booking_open", False, True))
        self.assertIn("added: B", sentences.change_sentence("updated", Plan, "T", "perks", [{"label": "A"}], [{"label": "A"}, {"label": "B"}]))
        self.assertEqual(sentences.show(None, ["a", "b"]), "a, b")
        self.assertEqual(sentences.change_sentence("deleted", Plan, "Tier 9"), "Deleted plan · Tier 9")
        self.assertTrue(plan)

    def test_choices_show_their_label(self):
        field = SystemChange._meta.get_field("kind")
        self.assertEqual(sentences.show(field, "updated"), "Changed")

    def test_a_saved_change_stores_its_sentence_and_request_details(self):
        client = unlocked_client(make_user())
        client.post("/settings/", SETTINGS_POST | {"vat_rate": "25.00"}, HTTP_USER_AGENT=UA)
        row = SystemChange.objects.get(field="vat_rate")
        self.assertIn("from 20% to 25%", row.sentence)
        self.assertEqual((row.user_agent, row.path), (UA, "/settings/"))
        self.assertTrue(row.hash and row.seq)


class ChainTests(TestCase):
    def setUp(self):
        self.user = make_user()
        for n in range(3):
            audit.log_event("sign_in", user=self.user, email=str(n))
        SystemChange.objects.create(section="settings", model_label="plans.sitesettings", field="capacity", kind="updated", old_value=1, new_value=2, sentence="x")
        audit.log_event("sign_out", user=self.user)

    def test_a_clean_chain_verifies_and_the_command_says_ok(self):
        self.assertTrue(audit.verify()["ok"])
        out = io.StringIO()
        call_command("verify_audit_log", stdout=out)
        self.assertIn("OK", out.getvalue())

    def test_an_edited_row_is_found(self):
        row = SystemEvent.objects.order_by("seq")[1]
        with connection.cursor() as cursor:  # a tamperer with database access
            cursor.execute("UPDATE system_systemevent SET sentence = 'hacked' WHERE id = %s", [row.pk.hex if connection.vendor == "sqlite" else str(row.pk)])
        result = audit.verify()
        self.assertFalse(result["ok"])
        self.assertEqual(result["broken"][2], row.seq)
        with self.assertRaises(CommandError):
            call_command("verify_audit_log")

    def test_a_deleted_row_and_a_deleted_newest_row_are_found(self):
        SystemEvent.objects.filter(seq=2)._prune_delete()
        self.assertIn("missing", audit.verify()["message"])

    def test_deleting_the_newest_row_is_found(self):
        SystemEvent.objects.order_by("-seq").first().pk
        SystemEvent.objects.filter(seq=5)._prune_delete()
        self.assertFalse(audit.verify()["ok"])

    def test_rows_refuse_edit_and_delete(self):
        event, change = SystemEvent.objects.first(), SystemChange.objects.first()
        for obj in (event, change):
            with self.assertRaises(AppendOnlyError):
                obj.save()
            with self.assertRaises(AppendOnlyError):
                obj.delete()
        with self.assertRaises(AppendOnlyError):
            SystemEvent.objects.all().delete()
        with self.assertRaises(AppendOnlyError):
            SystemChange.objects.all().update(section="x")
        with self.assertRaises(AppendOnlyError):
            SystemChange.objects.bulk_create([SystemChange()])

    def test_deleting_a_person_keeps_the_chain_valid(self):
        self.user.delete()
        self.assertTrue(audit.verify()["ok"])

    def test_prune_reanchors_and_verification_continues_from_the_anchor(self):
        SystemEvent.objects.filter(seq__lte=2)._prune_update  # exists
        old = timezone.now() - timedelta(days=100)
        for row in SystemEvent.objects.filter(seq__lte=2):
            with connection.cursor() as cursor:
                cursor.execute("UPDATE system_systemevent SET created_at = %s WHERE seq = %s", [old, row.seq])
        # created_at is sealed: re-seal the test rows is not possible, so prune first, then verify only what is kept
        dry = audit.prune(30, dry_run=True)
        self.assertEqual((dry["events"], SystemEvent.objects.count()), (2, 4))
        audit.prune(30)
        head = AuditHead.objects.get(pk=1)
        self.assertEqual(head.anchor_seq, 2)
        self.assertEqual(SystemEvent.objects.filter(seq__lte=2).count(), 0)
        self.assertTrue(audit.verify()["ok"])
        self.assertTrue(SystemEvent.objects.filter(kind="audit_pruned").exists())

    def test_retention_zero_keeps_everything(self):
        self.assertEqual(audit.prune(0)["events"], 0)
        call_command("prune_audit_log", stdout=io.StringIO())
        self.assertEqual(SystemEvent.objects.count(), 4)


@override_settings(ROOT_URLCONF="config.urls_system")
class FeedTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def make(self, groups):
        import uuid

        for n in range(groups):
            batch = uuid.uuid4()
            for _ in range(2):
                SystemChange.objects.create(section="plans", model_label="plans.plan", field="name", kind="updated", user=self.user,
                                            user_label=self.user.email, history_id=1, batch_id=batch, sentence="Changed A · Name from a to b")
            audit.log_event("sign_in", user=self.user)

    def test_groups_by_day_and_batch_with_filters(self):
        self.make(2)
        audit.log_event("sign_in_failed", email="x@y.com", outcome="failed")
        result = feed.audit_feed({})
        self.assertEqual(len(result["days"]), 1)
        groups = result["days"][0]["groups"]
        self.assertEqual(len(groups), 7)  # 2 batches, 2 sign-ins + the test's own sign-in and unlock, 1 failure
        batch = next(g for g in groups if g["type"] == "batch")
        self.assertEqual((batch["count"], batch["section_label"]), (2, "Plans and pricing"))
        self.assertIn("changed 2 fields in Plans and pricing", batch["summary"])
        self.assertEqual(len(feed.audit_feed({"category": "failure"})["days"][0]["groups"]), 1)
        self.assertEqual(len(feed.audit_feed({"category": "change"})["days"][0]["groups"]), 2)
        self.assertEqual(len(feed.audit_feed({"q": "x@y.com"})["days"][0]["groups"]), 1)
        self.assertEqual(feed.audit_feed({"section": "gold"})["days"], [])

    def test_the_page_runs_a_fixed_number_of_queries(self):
        def count(n):
            SystemChange.objects.all()._prune_delete()
            SystemEvent.objects.all()._prune_delete()
            self.make(n)
            self.client.get("/changes/")
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get("/changes/")
            self.assertEqual(response.status_code, 200)
            return len(queries)
        self.assertEqual(count(5), count(50))

    def test_csv_export_streams_the_filtered_feed_and_is_logged(self):
        self.make(2)
        response = self.client.get("/changes/export.csv", {"category": "change"})
        rows = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode())))
        self.assertEqual(rows[0][0], "time_utc")
        self.assertEqual(len(rows), 1 + 4)
        export = SystemEvent.objects.get(kind="export")
        self.assertEqual(export.detail["rows"], 4)


class AuditPageTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def test_page_has_filters_chips_groups_and_the_drawer_for_an_entry(self):
        audit.log_event("sign_in_failed", email="x@y.com", outcome="failed")
        change = SystemChange.objects.create(section="plans", model_label="plans.plan", object_repr="Gold", field="price_ex_vat", kind="updated",
                                             user=self.user, user_label=self.user.email, history_id=1, old_value="95.00", new_value="110.00")
        page = self.client.get("/changes/")
        for hook in ("data-system-chips", "data-system-range", "data-system-day", "au-outcome", "wrong password", "Audit log", "was </span>£95.00", "now </span>£110.00"):
            self.assertContains(page, hook)
        self.assertNotContains(page, "data-system-hash")
        drawer = self.client.get("/changes/", {"entry": str(change.pk)})
        self.assertContains(drawer, 'data-system-hash="ok"')
        self.assertContains(drawer, "au-json")
        self.assertEqual(self.client.get("/changes/", {"entry": "not-an-id"}).status_code, 200)

    def test_several_categories_and_a_changed_since_reason(self):
        audit.log_event("sign_in_failed", email="x@y.com", outcome="failed")
        audit.log_event("sign_in", user=self.user)
        old = SystemChange.objects.create(section="plans", model_label="plans.plan", object_pk="1", field="price_ex_vat", kind="updated", history_id=1, user_label="a@b.c", old_value="1", new_value="2")
        SystemChange.objects.create(section="plans", model_label="plans.plan", object_pk="1", field="price_ex_vat", kind="updated", history_id=2, user_label="a@b.c", old_value="2", new_value="3")
        groups = feed.audit_feed({"category": "failure,change"})["days"][0]["groups"]
        self.assertEqual(sorted(g["category"] for g in groups), ["change", "change", "failure"])
        self.assertContains(self.client.get("/changes/"), "Changed since")
        self.assertEqual(feed.entry_detail(old.pk)["row"].blocked_pk is not None, True)


class StoredCheckTests(TestCase):
    def test_verify_writes_the_stored_record_and_a_broken_chain_is_stored_and_shown(self):
        user = make_user()
        audit.log_event("sign_in", user=user)
        self.assertIsNone(audit.stored_status())
        call_command("verify_audit_log", stdout=io.StringIO())
        status = audit.stored_status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["entries"], 1)
        client = unlocked_client(user)
        self.assertTrue(client.get("/changes/").context["chain"]["ok"])
        with connection.cursor() as cursor:
            cursor.execute("UPDATE system_systemevent SET sentence = 'hacked' WHERE seq = 1")
        audit.scheduled()
        chain = client.get("/changes/").context["chain"]
        self.assertFalse(chain["ok"])
        self.assertEqual(chain["broken_seq"], 1)
        self.assertTrue(chain["broken_at_id"])

    def test_check_now_runs_stores_and_is_logged(self):
        client = unlocked_client(make_user())
        client.post("/changes/check/")
        self.assertTrue(audit.stored_status()["ok"])
        self.assertEqual(SystemEvent.objects.filter(kind="audit_check").count(), 1)
