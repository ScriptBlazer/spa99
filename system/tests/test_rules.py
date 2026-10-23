"""System rule sections: each saves through the change log (old -> new), undo works, validation shows field errors,
and everyone else gets a 404."""
from decimal import Decimal

from django.test import Client, TestCase

from gold.models import GoldRule
from journey.models import Option, Question, SuggestionRule
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Closure, OpeningRule, Plan, SiteSettings
from system.models import SystemChange
from system.tests.test_system import make_user, unlocked_client


def form_data(form, prefix, **changes):
    """The current values of a bound-less form as POST data, with `changes` applied (field names without the prefix)."""
    data = {}
    for name, field in form.fields.items():
        value = form.initial.get(name)
        if value is None or value is False:
            continue
        if isinstance(value, (dict, list)):
            import json

            value = json.dumps(value)
        data[f"{prefix}-{name}"] = "on" if value is True else value
    for name, value in changes.items():
        data[f"{prefix}-{name}"] = value
    return data


class RulesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        self.user = make_user()
        self.client = unlocked_client(self.user)


class SectionAccessTests(RulesTestCase):
    def test_all_four_sections_render_for_developers_and_404_for_everyone_else(self):
        office = Client(HTTP_HOST="system.localhost")
        office.force_login(make_user("office@example.com", system=False))
        for path in ("/plans/", "/hours/", "/gold/", "/journey/"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
            self.assertEqual(Client(HTTP_HOST="system.localhost").get(path).status_code, 404, path)
            self.assertEqual(office.get(path).status_code, 404, path)
        self.assertEqual(office.post("/plans/add/").status_code, 404)
        self.assertEqual(office.post("/hours/capacity/").status_code, 404)


class PlansTests(RulesTestCase):
    def test_edit_logs_old_and_new_undo_restores_and_inc_vat_is_display_only(self):
        plan = Plan.objects.get(slug="tier-2")
        old_price = plan.price_ex_vat
        page = self.client.get("/plans/")
        self.assertContains(page, "data-system-price-inc-vat")
        data = form_data(page.context["rows"][[r["obj"].pk for r in page.context["rows"]].index(plan.pk)]["form"], str(plan.pk), price_ex_vat="123.00")
        self.assertEqual(self.client.post(f"/plans/{plan.pk}/", data).status_code, 302)
        plan.refresh_from_db()
        self.assertEqual(plan.price_ex_vat, Decimal("123.00"))
        change = SystemChange.objects.get(model_label="plans.plan", field="price_ex_vat")
        self.assertEqual((change.old_value, change.new_value, change.section, change.user), (str(old_price), "123.00", "plans", self.user))
        self.client.post(f"/changes/{change.pk}/undo/")
        plan.refresh_from_db()
        self.assertEqual(plan.price_ex_vat, old_price)

    def test_bad_values_show_field_errors_and_save_nothing(self):
        plan = Plan.objects.get(slug="tier-2")
        page = self.client.get("/plans/")
        form = next(r["form"] for r in page.context["rows"] if r["obj"].pk == plan.pk)
        data = form_data(form, str(plan.pk), price_ex_vat="-5", perks='[{"key": "a"}]')
        response = self.client.post(f"/plans/{plan.pk}/", data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("price_ex_vat", next(r["form"] for r in response.context["rows"] if r["obj"].pk == plan.pk).errors)
        self.assertIn("perks", next(r["form"] for r in response.context["rows"] if r["obj"].pk == plan.pk).errors)
        plan.refresh_from_db()
        self.assertNotEqual(plan.price_ex_vat, Decimal("-5"))
        self.assertFalse(SystemChange.objects.filter(model_label="plans.plan").exists())

    def test_add_and_hide_a_plan_never_delete(self):
        add = {"new-slug": "tier-9", "new-kind": "monthly", "new-name": "Tier 9", "new-price_ex_vat": "9.00", "new-hours": "any",
               "new-booking_window_days": "1", "new-upcoming_limit": "1", "new-cancel_hours": "10", "new-guests_per_month": "0",
               "new-perks": "[]", "new-order": "9", "new-visible": "on"}
        self.assertEqual(self.client.post("/plans/add/", add).status_code, 302)
        plan = Plan.objects.get(slug="tier-9")
        self.assertTrue(SystemChange.objects.filter(kind="created", object_pk=str(plan.pk)).exists())
        form = next(r["form"] for r in self.client.get("/plans/").context["rows"] if r["obj"].pk == plan.pk)
        data = form_data(form, str(plan.pk))
        data.pop(f"{plan.pk}-visible")  # an unticked box is hiding the plan (the Visible toggle in the row)
        self.client.post(f"/plans/{plan.pk}/", data)
        plan.refresh_from_db()
        self.assertFalse(plan.visible)
        self.assertTrue(SystemChange.objects.filter(field="visible", new_value=False).exists())
        self.assertEqual(self.client.post("/plans/add/", add).status_code, 400)  # duplicate slug


class HoursTests(RulesTestCase):
    def test_capacity_saves_logs_and_validates(self):
        site = SiteSettings.load()
        base = {"capacity-capacity": "30", "capacity-slot_length_minutes": "120", "capacity-slot_step_minutes": "30", "capacity-booking_notice_minutes": "10"}
        self.assertEqual(self.client.post("/hours/capacity/", base).status_code, 302)
        change = SystemChange.objects.get(field="capacity")
        self.assertEqual((change.old_value, change.new_value, change.section), (site.capacity, 30, "hours"))
        self.client.post(f"/changes/{change.pk}/undo/")
        self.assertEqual(SiteSettings.load().capacity, site.capacity)
        bad = self.client.post("/hours/capacity/", base | {"capacity-slot_length_minutes": "10"})
        self.assertEqual(bad.status_code, 400)
        self.assertIn("slot_length_minutes", bad.context["capacity_form"].errors)

    def test_opening_rule_times_and_offsets_are_validated(self):
        period = OpeningRule.objects.filter(kind=OpeningRule.PERIOD).first()
        base = {"label": period.label, "start_time": "09:00", "end_time": "17:00", "order": period.order, "active": "on"}
        self.assertEqual(self.client.post(f"/hours/rules/{period.pk}/", {f"{period.pk}-{k}": v for k, v in base.items()}).status_code, 302)
        self.assertTrue(SystemChange.objects.filter(model_label="plans.openingrule", field="start_time").exists())
        same = self.client.post(f"/hours/rules/{period.pk}/", {f"{period.pk}-{k}": v for k, v in (base | {"end_time": "09:00"}).items()})
        self.assertEqual(same.status_code, 400)
        offset = OpeningRule.objects.filter(kind=OpeningRule.CLOSE_BEFORE_CANDLES).first()
        if offset:
            bad = self.client.post(f"/hours/rules/{offset.pk}/", {f"{offset.pk}-label": offset.label, f"{offset.pk}-order": "1", f"{offset.pk}-offset_minutes": "5000"})
            self.assertEqual(bad.status_code, 400)

    def test_closures_add_edit_and_delete_are_logged(self):
        add = {"new-closure-name": "Deep clean", "new-closure-starts_at": "2027-02-01T09:00", "new-closure-ends_at": "2027-02-01T17:00", "new-closure-active": "on"}
        self.assertEqual(self.client.post("/hours/closures/add/", add).status_code, 302)
        closure = Closure.objects.get(name="Deep clean")
        backwards = self.client.post("/hours/closures/add/", add | {"new-closure-ends_at": "2027-02-01T08:00"})
        self.assertEqual(backwards.status_code, 400)
        key = str(closure.pk)
        edit = {f"{key}-name": "Deep clean 2", f"{key}-starts_at": "2027-02-01T09:00", f"{key}-ends_at": "2027-02-01T17:00", f"{key}-active": "on"}
        self.client.post(f"/hours/closures/{closure.pk}/", edit)
        change = SystemChange.objects.get(model_label="plans.closure", field="name")
        self.assertEqual((change.old_value, change.new_value), ("Deep clean", "Deep clean 2"))
        self.client.post(f"/changes/{change.pk}/undo/")
        closure.refresh_from_db()
        self.assertEqual(closure.name, "Deep clean")
        self.client.post(f"/hours/closures/{closure.pk}/delete/")
        self.assertFalse(Closure.objects.filter(pk=closure.pk).exists())
        deleted = SystemChange.objects.get(kind="deleted", model_label="plans.closure")
        self.assertEqual((deleted.user, deleted.undoable), (self.user, False))


class GoldTests(RulesTestCase):
    def test_points_and_property_flag_save_log_and_undo(self):
        rule = GoldRule.objects.exclude(group="threshold").filter(points__gt=0).first()
        key = str(rule.pk)
        data = {f"{key}-label": rule.label, f"{key}-points": str(rule.points + 5), f"{key}-active": "on"}
        if rule.is_property:
            data[f"{key}-is_property"] = "on"
        self.assertEqual(self.client.post(f"/gold/{rule.pk}/", data).status_code, 302)
        change = SystemChange.objects.get(model_label="gold.goldrule", field="points")
        self.assertEqual((change.old_value, change.new_value, change.section), (rule.points, rule.points + 5, "gold"))
        self.client.post(f"/changes/{change.pk}/undo/")
        rule.refresh_from_db()
        self.assertEqual(rule.points, change.old_value)

    def test_high_threshold_cannot_fall_below_medium(self):
        high = GoldRule.objects.get(group="threshold", match_value="high")
        medium = GoldRule.objects.get(group="threshold", match_value="medium")
        key = str(high.pk)
        response = self.client.post(f"/gold/{high.pk}/", {f"{key}-label": high.label, f"{key}-points": str(medium.points - 1), f"{key}-active": "on"})
        self.assertEqual(response.status_code, 400)
        high.refresh_from_db()
        self.assertGreaterEqual(high.points, medium.points)


class JourneyTests(RulesTestCase):
    def test_option_points_save_log_and_undo_and_bad_points_are_refused(self):
        option = Option.objects.filter(plan_points__has_key="tier-2").first() or Option.objects.exclude(plan_points={}).first()
        key = str(option.pk)
        base = {f"{key}-label": option.label, f"{key}-order": str(option.order), f"{key}-active": "on", f"{key}-gold_points": "0", f"{key}-reason": option.reason}
        response = self.client.post(f"/journey/options/{option.pk}/", base | {f"{key}-plan_points": '{"nope": 1}'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Not a plan: nope", status_code=400)
        self.assertEqual(self.client.post(f"/journey/options/{option.pk}/", base | {f"{key}-plan_points": '{"tier-2": 7}', f"{key}-gold_points": "2"}).status_code, 302)
        change = SystemChange.objects.get(model_label="journey.option", field="plan_points")
        self.assertEqual(change.new_value, {"tier-2": 7})
        self.client.post(f"/changes/{change.pk}/undo/")
        option.refresh_from_db()
        self.assertEqual(option.plan_points, change.old_value)

    def test_question_hide_and_min_choices_rule(self):
        question = Question.objects.filter(type="single", active=True).first()
        key = str(question.pk)
        base = {f"{key}-text": question.text, f"{key}-screen": str(question.screen), f"{key}-order": str(question.order), f"{key}-min_choices": "0", f"{key}-active": "on"}
        too_many = self.client.post(f"/journey/questions/{question.pk}/", base | {f"{key}-min_choices": "99"})
        self.assertEqual(too_many.status_code, 400)
        self.client.post(f"/journey/questions/{question.pk}/", {k: v for k, v in base.items() if not k.endswith("active")})
        question.refresh_from_db()
        self.assertFalse(question.active)
        self.assertTrue(SystemChange.objects.filter(model_label="journey.question", field="active").exists())

    def test_adding_a_duplicate_option_and_a_bad_suggestion_rule_are_refused(self):
        question = Question.objects.filter(type="single").first()
        existing = question.options.first()
        bad = self.client.post(f"/journey/questions/{question.pk}/options/add/", {f"new-{question.pk}-value": existing.value, f"new-{question.pk}-label": "X", f"new-{question.pk}-order": "1", f"new-{question.pk}-gold_points": "0"})
        self.assertEqual(bad.status_code, 400)
        rule = SuggestionRule.objects.first()
        if rule:
            key = str(rule.pk)
            response = self.client.post(f"/journey/suggestions/{rule.pk}/", {f"{key}-name": rule.name, f"{key}-kind": rule.kind, f"{key}-conditions": '[{"question": "zzz", "any_of": ["a"]}]', f"{key}-plan_slugs": "[]", f"{key}-points": "0", f"{key}-order": "0", f"{key}-active": "on"})
            self.assertEqual(response.status_code, 400)
