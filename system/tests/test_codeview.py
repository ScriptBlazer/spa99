"""The System code view: render -> parse -> plan round trips, saving through the normal logged path (one batch, undo all), the
refusals (read only, unknown keys, injection, size, stale, risky, removal), the audit event, and access."""
import json
import re
from unittest import mock

from django.test import Client, TestCase
from django.utils import timezone

from gold.models import GoldRule
from journey.models import Question
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Closure, Plan, SiteSettings
from system import feed
from system.codeview import plan_changes
from system.codeview import render, service
from system.codeview.parse import CodeError, parse
from system.models import SystemChange, SystemEvent
from system.tests.test_system import make_user, sign_in, unlocked_client

SECTIONS = ["plans", "hours", "gold", "journey", "settings", "emails"]


def set_key(code, key, literal, nth=0):
    """The code with the nth `"key": ...,` line given a new literal."""
    matches = list(re.finditer(rf'^(\s*"{key}": ).*?,(\s*#.*)?$', code, re.M))
    m = matches[nth]
    return code[:m.start()] + f"{m.group(1)}{literal}," + code[m.end():]


def line_of(code, needle, nth=0):
    return [i for i, line in enumerate(code.splitlines(), 1) if needle in line][nth]


class CodeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)

    def open(self, section):
        data = self.client.get(f"/code/{section}/").json()
        return data["code"], data["version"]

    def post(self, section, action, code, version, client=None, **extra):
        body = {"code": code, "version": version, **extra}
        return (client or self.client).post(f"/code/{section}/{action}/", json.dumps(body), content_type="application/json")

    def apply(self, section, code, version, **extra):
        return self.post(section, "apply", code, version, confirm_risky=True, **extra)


class RenderParseTests(CodeTestCase):
    def test_round_trip_gives_no_changes_for_every_section(self):
        for key in SECTIONS:
            with self.subTest(key):
                code, version = self.open(key)
                plan = plan_changes(key, parse(key, code))
                self.assertEqual((plan.errors, plan.changes, plan.creates, plan.deletes, plan.stale), ([], [], [], [], False))
                response = self.post(key, "preview", code, version)
                self.assertEqual((response.status_code, response.json()["count"], response.json()["diff"]), (200, 0, ""))

    def test_text_is_deterministic_literals_with_header_read_only_marks_and_strings_for_money_and_times(self):
        code, _ = render.render("plans")
        again, _ = render.render("plans")
        self.assertEqual(code.splitlines()[2:], again.splitlines()[2:])
        lines = code.splitlines()
        self.assertEqual(lines[0], "# spa99 / rules / plans.py")
        self.assertTrue(lines[1].startswith("# Generated from the database at ") and lines[1].endswith(" by System. Edit and Apply."))
        self.assertTrue(lines[2].startswith("PLANS = ["))
        self.assertRegex(code, r'"id": "[0-9a-f-]{36}",\s+# read only')
        self.assertRegex(code, r'"slug": "tier-1",\s+# read only')
        self.assertRegex(code, r'"price_ex_vat": "\d+\.\d\d",')
        self.assertIn('        "visible": True,', code)
        hours, _ = render.render("hours")
        self.assertRegex(hours, r'"start_time": "\d\d:\d\d",')
        self.assertIn('    "rules": [', hours)

    def test_parse_errors_carry_line_and_column(self):
        with self.assertRaises(CodeError) as caught:
            parse("emails", 'EMAILS = {\n    "contact_email": "a@b.co"\n    "gold_approver_cc": "",\n}\n')
        self.assertEqual((caught.exception.errors[0]["line"], caught.exception.status), (3, 400))
        self.assertGreaterEqual(caught.exception.errors[0]["col"], 1)

    def test_injection_attempts_are_refused_with_a_position_and_nothing_runs(self):
        code, version = self.open("emails")
        attacks = ["__import__('os').system('touch /tmp/spa99-pwned')", "print(1)", "(lambda: 1)()", "'a'.upper", "f'{1}'",
                   "[x for x in range(3)]", "1 + 2", "open('x')", "{**{}}", "True if 1 else 2", "b'bytes'", "1e999",
                   "[" * 5000, "(" * 150 + ")" * 150, "- " * 3000 + "1"]
        for attack in attacks:
            with self.subTest(attack[:30]):
                bad = set_key(code, "contact_email", attack)
                response = self.post("emails", "preview", bad, version)
                self.assertEqual(response.status_code, 400, attack[:30])
                self.assertTrue(response.json()["errors"][0]["line"] >= 1)
        import os

        self.assertFalse(os.path.exists("/tmp/spa99-pwned"))
        for text in ("import os\nEMAILS = {}\n", "EMAILS = {}\nEMAILS = {}\n", "OTHER = 1\n"):
            self.assertEqual(self.post("emails", "preview", text, version).status_code, 400)
        deep = "EMAILS = " + "[" * 100 + "]" * 100 + "\n"
        self.assertEqual(self.post("emails", "preview", deep, version).status_code, 400)

    def test_over_128_kb_is_refused_413(self):
        code, version = self.open("emails")
        big = code + "# " + "x" * (128 * 1024) + "\n"
        response = self.post("emails", "apply", big, version)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["errors"][0]["line"], 1)


class SaveTests(CodeTestCase):
    EDITS = {"plans": ("price_ex_vat", '"123.00"'), "hours": ("capacity", "30"), "gold": ("label", '"Changed label"'),
             "journey": ("text", '"A new question text"'), "settings": ("opening_text", '"February 2027"'),
             "emails": ("contact_email", '"hello@example.com"')}

    def test_one_edit_per_section_is_one_logged_change_and_undo_all_restores(self):
        for key, (field, literal) in self.EDITS.items():
            with self.subTest(key):
                code, version = self.open(key)
                SystemChange.objects.all()  # lazily evaluated below
                before = SystemChange.objects.count()
                response = self.apply(key, set_key(code, field, literal), version)
                self.assertEqual(response.status_code, 200, response.content)
                payload = response.json()
                new = list(SystemChange.objects.order_by("created_at", "seq")[before:])
                self.assertEqual([c.field for c in new], [field])
                self.assertEqual(payload["message"], "Saved 1 change.")
                self.assertIn(f"/changes/{new[0].pk}/undo/", payload["undo_url"])
                self.assertNotEqual(payload["version"], version)
                self.client.post(payload["undo_url"])
                self.assertEqual(self.open(key)[0].splitlines()[2:], code.splitlines()[2:])

    def test_several_changes_share_the_request_batch_with_the_event_and_undo_all_puts_them_back(self):
        code, version = self.open("plans")
        edited = set_key(set_key(set_key(code, "price_ex_vat", '"111.00"'), "name", '"Renamed"'), "cancel_hours", "11", nth=1)
        payload = self.apply("plans", edited, version).json()
        changes = list(SystemChange.objects.filter(section="plans"))
        self.assertEqual(len(changes), 3)
        event = SystemEvent.objects.get(kind="code_edit")
        self.assertEqual({c.batch_id for c in changes}, {event.batch_id})
        self.assertTrue(event.batch_id)
        self.assertRegex(payload["undo_url"], r"/changes/batch/[0-9a-f-]+/undo/")
        self.client.post(payload["undo_url"])
        self.assertEqual(self.open("plans")[0].splitlines()[2:], code.splitlines()[2:])

    def test_nothing_changed_is_a_no_op_with_no_event(self):
        code, version = self.open("plans")
        response = self.apply("plans", code + "# a comment\n", version)
        self.assertEqual((response.status_code, response.json()["message"]), (200, "Nothing to change."))
        self.assertFalse(SystemEvent.objects.filter(kind="code_edit").exists())

    def test_stale_version_is_409_with_the_fresh_code_and_saves_nothing(self):
        code, version = self.open("plans")
        plan = Plan.objects.get(slug="tier-1")
        plan.name = "Someone else"
        plan.save()
        for action in ("preview", "apply"):
            response = self.post("plans", action, set_key(code, "price_ex_vat", '"1.00"'), version)
            self.assertEqual(response.status_code, 409)
            body = response.json()
            self.assertEqual(body["message"], "Changed since you opened it. Reload to see the latest.")
            self.assertIn("Someone else", body["code"])
            self.assertNotEqual(body["version"], version)
        self.assertNotEqual(Plan.objects.get(slug="tier-1").price_ex_vat, 1)

    def test_risky_change_needs_confirmation(self):
        code, version = self.open("plans")
        edited = set_key(code, "price_ex_vat", '"123.00"')
        self.assertTrue(self.post("plans", "preview", edited, version).json()["risky"])
        response = self.post("plans", "apply", edited, version)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["needs_confirm"])
        self.assertFalse(SystemChange.objects.filter(section="plans").exists())
        plain = set_key(code, "short_description", '"Quiet words"')
        self.assertFalse(self.post("plans", "preview", plain, version).json()["risky"])
        self.assertEqual(self.post("plans", "apply", plain, version).status_code, 200)

    def test_preview_lists_field_changes_with_readable_values_and_a_diff(self):
        code, version = self.open("plans")
        body = self.post("plans", "preview", set_key(code, "price_ex_vat", '"123.00"'), version).json()
        change = body["changes"][0]
        self.assertEqual((change["field"], change["label"], change["new_display"], change["risky"]), ("price_ex_vat", "Price ex VAT", "£123.00", True))
        self.assertTrue(change["old_display"].startswith("£") and change["row_label"] and change["line"] >= 3)
        self.assertEqual([r["type"] for r in body["diff_lines"] if r["type"] != "hunk"][:3], ["ctx", "ctx", "ctx"])
        self.assertTrue(any(r["type"] == "add" and "123.00" in r["text"] for r in body["diff_lines"]))
        self.assertNotIn("Generated from the database", body["diff"])  # the timestamp line is never a change

    def test_cross_field_rule_is_caught_with_its_line_and_nothing_is_saved(self):
        code, version = self.open("gold")
        rule_high = GoldRule.objects.get(group="threshold", match_value="high")
        block = code.index(str(rule_high.pk))
        line = code[:block].count("\n") + 1
        points_line = line + 2 + [i for i, ln in enumerate(code[block:].splitlines()) if '"points"' in ln][0] - 2
        medium = GoldRule.objects.get(group="threshold", match_value="medium").points
        edited = code.splitlines()
        edited[points_line - 1] = re.sub(r"\d+,", f"{max(medium - 1, 1)},", edited[points_line - 1])
        response = self.apply("gold", "\n".join(edited) + "\n", version)
        self.assertEqual(response.status_code, 400)
        error = response.json()["errors"][0]
        self.assertEqual(error["line"], points_line)
        self.assertIn("High threshold cannot be lower", error["message"])
        self.assertEqual(GoldRule.objects.get(pk=rule_high.pk).points, rule_high.points)

    def test_wrong_kinds_of_value_are_errors_not_silent_changes(self):
        code, version = self.open("plans")
        for key, literal in (("visible", '"no"'), ("visits_per_month", "True"), ("name", "5"), ("price_ex_vat", "[1]")):
            response = self.post("plans", "preview", set_key(code, key, literal), version)
            self.assertEqual(response.status_code, 400, key)
            self.assertEqual(response.json()["errors"][0]["line"], line_of(code, f'"{key}"'), key)
        gone = re.sub(r'^\s+"visible": .*\n', "", code, count=1, flags=re.M)
        self.assertIn('Missing key "visible"', self.post("plans", "preview", gone, version).json()["message"])


class RowRuleTests(CodeTestCase):
    def test_read_only_and_unknown_things_are_refused_with_their_line(self):
        code, version = self.open("plans")
        first_id = Plan.objects.get(slug="tier-1").pk
        bad_id = code.replace(str(first_id), "11111111-1111-1111-1111-111111111111", 1)
        error = self.post("plans", "preview", bad_id, version).json()["errors"][0]
        self.assertEqual(error["line"], line_of(code, str(first_id)))
        self.assertIn("No plan has the id", error["message"])
        renamed = set_key(code, "slug", '"tier-one"')
        error = self.post("plans", "preview", renamed, version).json()["errors"][0]
        self.assertEqual(error["line"], line_of(code, '"slug"'))
        self.assertIn("read only", error["message"])
        typo = code.replace('"price_ex_vat"', '"price_ex_vatt"', 1)
        error = self.post("plans", "preview", typo, version).json()["errors"][0]
        self.assertEqual(error["line"], line_of(code, '"price_ex_vat"'))
        self.assertIn('Did you mean "price_ex_vat"?', error["message"])
        dup = code.replace(str(Plan.objects.get(slug="tier-2").pk), str(first_id), 1)
        self.assertIn("used twice", " ".join(e["message"] for e in self.post("plans", "preview", dup, version).json()["errors"]))

    def test_add_a_plan_logged_and_removing_a_plan_is_refused(self):
        code, version = self.open("plans")
        new = ('    {\n        "slug": "tier-9",\n        "kind": "monthly",\n        "name": "Tier 9",\n        "price_ex_vat": "50.00",\n    },\n]\n')
        body = self.post("plans", "preview", code[: code.rindex("]")] + new, version).json()
        self.assertEqual([(c["row_label"], c["noun"]) for c in body["creates"]], [("Tier 9", "plan")])
        self.assertEqual(self.apply("plans", code[: code.rindex("]")] + new, version).status_code, 200)
        plan = Plan.objects.get(slug="tier-9")
        self.assertEqual((plan.name, str(plan.price_ex_vat)), ("Tier 9", "50.00"))
        self.assertTrue(SystemChange.objects.filter(kind="created", object_pk=str(plan.pk)).exists())
        code, version = self.open("plans")
        gone = re.sub(r'    \{\n        "id": "%s".*?\n    \},\n' % plan.pk, "", code, flags=re.S)
        self.assertNotEqual(gone, code)
        response = self.apply("plans", gone, version)
        self.assertEqual(response.status_code, 400)
        self.assertIn('The plan "Tier 9" is missing', response.json()["message"])
        self.assertIn("visible", response.json()["message"])
        self.assertTrue(Plan.objects.filter(slug="tier-9").exists())

    def test_closures_can_be_added_and_removed_and_both_are_logged(self):
        code, version = self.open("hours")
        start = (timezone.now() + timezone.timedelta(days=30)).replace(hour=9, minute=0, second=0, microsecond=0)
        local = timezone.localtime(start)
        row = (f'        {{\n            "name": "Deep clean",\n            "starts_at": "{local:%Y-%m-%dT%H:%M}",\n'
               f'            "ends_at": "{local + timezone.timedelta(hours=3):%Y-%m-%dT%H:%M}",\n            "public_note": "",\n            "active": True,\n        }},\n')
        self.assertIn('    "closures": [],\n', code)  # none seeded
        added = code.replace('    "closures": [],\n', '    "closures": [\n' + row + '    ],\n', 1)
        self.assertEqual(self.apply("hours", added, version).status_code, 200, added)
        closure = Closure.objects.get(name="Deep clean")
        self.assertTrue(SystemChange.objects.filter(kind="created", model_label="plans.closure").exists())
        code, version = self.open("hours")
        gone = re.sub(r'        \{\n            "id": "%s".*?\n        \},\n' % closure.pk, "", code, flags=re.S)
        body = self.post("hours", "preview", gone, version).json()
        self.assertEqual((body["deletes"][0]["row_label"], body["risky"]), ("Deep clean", True))
        self.assertEqual(self.post("hours", "apply", gone, version).status_code, 400)  # removal needs the confirm step
        self.assertEqual(self.apply("hours", gone, version).status_code, 200)
        self.assertFalse(Closure.objects.filter(pk=closure.pk).exists())
        self.assertTrue(SystemChange.objects.filter(kind="deleted", object_pk=str(closure.pk)).exists())

    def test_journey_options_nest_inside_questions_and_a_question_cannot_be_removed(self):
        code, version = self.open("journey")
        self.assertIn('"options": [', code)
        self.assertIn("SUGGESTIONS = [", code)
        question = Question.objects.filter(options__isnull=False).first()
        edited = set_key(code, "reason", '"A new reason"')
        self.assertEqual(self.apply("journey", edited, version).status_code, 200)
        code, version = self.open("journey")
        gone = re.sub(r'    \{\n        "id": "%s".*?\n    \},\n(?=    \{|\])' % question.pk, "", code, count=1, flags=re.S)
        self.assertNotEqual(gone, code)
        self.assertIn("is missing", self.post("journey", "preview", gone, version).json()["message"])

    def test_hours_capacity_cross_field_rule(self):
        code, version = self.open("hours")
        response = self.post("hours", "preview", set_key(set_key(code, "slot_length_minutes", "10"), "slot_step_minutes", "30"), version)
        self.assertEqual(response.status_code, 400)
        self.assertIn("shorter than the step", response.json()["message"])
        self.assertEqual(SiteSettings.load().slot_length_minutes, 120)


class AuditTests(CodeTestCase):
    def test_code_edit_event_has_sha_diff_counts_and_shows_in_the_feed_and_drawer(self):
        code, version = self.open("plans")
        self.apply("plans", set_key(code, "short_description", '"Quiet words"'), version)
        event = SystemEvent.objects.get(kind="code_edit")
        detail = event.detail
        self.assertEqual((detail["section"], detail["changed_fields"], detail["diff_truncated"]), ("plans", 1, False))
        self.assertEqual(len(detail["before_sha256"]), 64)
        self.assertNotEqual(detail["before_sha256"], detail["after_sha256"])
        self.assertIn('+        "short_description": "Quiet words",', detail["diff"])
        self.assertEqual((event.sentence, event.section, event.user), (f"{self.user.email} edited Plans as code (1 change)", "plans", self.user))
        group = next(g for day in feed.audit_feed(feed.params_from({}))["days"] for g in day["groups"] if g["type"] == "event" and g["kind"] == "code_edit")
        self.assertEqual((group["icon"], group["category"]), ("code", "change"))
        self.assertEqual(group["rest"].strip(), "edited Plans as code (1 change)")
        drawer = feed.entry_detail(str(event.pk))
        self.assertTrue(any(r["type"] == "add" and "Quiet words" in r["text"] for r in drawer["diff_lines"]))
        self.assertEqual(self.client.get(f"/changes/?entry={event.pk}").status_code, 200)
        chip = feed.audit_feed(feed.params_from({"category": "change"}))
        self.assertTrue(any(g["type"] == "event" for day in chip["days"] for g in day["groups"]))

    def test_a_code_edit_is_never_saved_without_its_audit_row(self):
        code, version = self.open("plans")
        edited = set_key(code, "short_description", '"Quiet words"')
        before = Plan.objects.get(slug="tier-1").short_description
        for patch in (mock.patch("system.audit.log_event", return_value=None), mock.patch("system.audit.log_event", side_effect=RuntimeError("down"))):
            with patch:
                response = self.apply("plans", edited, version)
            self.assertEqual(response.status_code, 500)
            self.assertIn("nothing was saved", response.json()["message"])
            self.assertEqual(Plan.objects.get(slug="tier-1").short_description, before)
            self.assertFalse(SystemChange.objects.filter(section="plans").exists())

    def test_diff_is_capped_with_a_marker(self):
        text, cut = service.cap_diff("\n".join(f"+line {i}" for i in range(5000)))
        self.assertTrue(cut and len(text) < service.DIFF_CAP + 100 and text.endswith(service.TRUNCATED))
        self.assertEqual(service.diff_lines(text)[-1]["type"], "hunk")


class AccessTests(CodeTestCase):
    def test_strangers_get_404_locked_developers_are_sent_to_unlock_and_pages_carry_code_url(self):
        office = Client(HTTP_HOST="system.localhost")
        office.force_login(make_user("office@example.com", system=False))
        for client in (Client(HTTP_HOST="system.localhost"), office):
            self.assertEqual(client.get("/code/plans/").status_code, 404)
            self.assertEqual(self.post("plans", "apply", "x", "y", client=client).status_code, 404)
        locked, _ = sign_in(self.user)
        self.assertEqual(locked.get("/code/plans/").status_code, 302)
        self.assertEqual(self.post("plans", "preview", "x", "y", client=locked).status_code, 302)
        self.assertEqual(self.client.get("/code/nope/").status_code, 404)
        self.assertEqual(self.client.get("/code/plans/preview/").status_code, 405)
        for key in SECTIONS:
            page = self.client.get(f"/{key}/")
            self.assertEqual(page.context["code_url"], f"/code/{key}/")
        self.assertNotIn("code_url", self.client.get("/team/").context)

    def test_csrf_is_enforced_and_preview_apply_are_rate_limited(self):
        strict = Client(HTTP_HOST="system.localhost", enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        self.assertEqual(self.post("plans", "preview", "x", "y", client=strict).status_code, 403)
        code, version = self.open("plans")
        with mock.patch("system.views_code.hit", return_value=False):
            response = self.post("plans", "preview", code, version)
        self.assertEqual((response.status_code, response["Retry-After"]), (429, "60"))
        self.assertEqual(self.post("plans", "preview", "{", version).status_code, 400)
        self.assertEqual(self.client.post("/code/plans/preview/", "not json", content_type="application/json").status_code, 400)
