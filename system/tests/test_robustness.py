"""System robustness pass (2026-10-25): stale-page saves are refused, bad JSON is a field error not a 500, rules live in the
models so undo obeys them, headers, the audit of password changes, the last superuser, and the new bounds."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib import admin
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from common.jsonshape import parse_whole
from gold.models import GoldRule
from journey.models import Option, Question
from notifications.models import EmailSuppression
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan, SiteSettings
from system import forms as system_forms
from system import forms_rules as f
from system import services, team
from system.models import SystemChange, SystemEvent
from system.tests.test_rules import RulesTestCase, form_data
from system.tests.test_system import LOCMEM, PASSWORD, SYSTEM, make_user, unlocked_client
from system.tests.test_team import at
from users.admin import UserAdmin
from users.models import User

STALE = services.STALE_MESSAGE
SETTINGS_POST = {"opening_text": "January 2027", "register_interest_open": "on", "journey_email_gate": "on", "join_wording": "register_interest", "vat_rate": "20.00", "lock_idle_minutes": "15", "max_sign_in_hours": "12"}


def plan_post(plan, **changes):
    """What the plan's row form posts: its current values and token, with `changes`."""
    return form_data(f.PlanForm(instance=Plan.objects.get(pk=plan.pk), prefix=str(plan.pk)), str(plan.pk), **changes)


class StalePageTests(RulesTestCase):
    def test_an_old_page_cannot_overwrite_another_developers_change(self):
        plan = Plan.objects.get(slug="tier-2")
        old_page = plan_post(plan)  # developer B opens the page
        self.assertIn(f"{plan.pk}-row_token", old_page)
        self.assertEqual(self.client.post(f"/plans/{plan.pk}/", plan_post(plan, price_ex_vat="319.00")).status_code, 302)  # developer A
        stale = {**old_page, f"{plan.pk}-name": "Renamed"}  # B saves a rename from the old page: its price box still says the old price
        response = self.client.post(f"/plans/{plan.pk}/", stale)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, STALE, status_code=409)
        plan.refresh_from_db()
        self.assertEqual((plan.price_ex_vat, plan.name == "Renamed"), (Decimal("319.00"), False))
        self.assertEqual(SystemChange.objects.filter(model_label="plans.plan", field="name").count(), 0)
        fresh = self.client.post(f"/plans/{plan.pk}/", plan_post(plan, name="Renamed"))  # after a reload it saves
        self.assertEqual(fresh.status_code, 302)

    def test_the_token_is_on_every_row_form_and_form_validation_needs_no_request(self):
        for path in ("/plans/", "/hours/", "/gold/", "/journey/", "/settings/", "/emails/"):
            self.assertContains(self.client.get(path), 'row_token"', msg_prefix=path)
        plan = Plan.objects.get(slug="tier-1")
        self.assertContains(self.client.get("/plans/"), f'form="f-{plan.pk}"')
        self.assertEqual(services.row_fingerprint(plan, ["name", "price_ex_vat"]), services.row_fingerprint(Plan.objects.get(pk=plan.pk), ["name", "price_ex_vat"]))
        data = plan_post(plan)
        Plan.objects.filter(pk=plan.pk).update(name="Changed elsewhere")
        form = f.PlanForm(data, instance=Plan.objects.get(pk=plan.pk), prefix=str(plan.pk))  # no request anywhere
        form.initial[system_forms.TOKEN] = data[f"{plan.pk}-row_token"]
        self.assertFalse(form.is_valid())
        self.assertTrue(form.stale)
        self.assertIn(STALE, form.non_field_errors())

    def test_settings_and_emails_are_checked_and_capacity_is_not_hit_by_a_settings_save(self):
        site = SiteSettings.load()
        settings_form = system_forms.SettingsForm(instance=site)
        capacity_form = f.CapacityForm(instance=site, prefix="capacity")
        old_settings = {**SETTINGS_POST, "row_token": settings_form.initial["row_token"]}
        self.assertEqual(self.client.post("/settings/", old_settings | {"vat_rate": "25.00"}).status_code, 302)
        self.assertEqual(self.client.post("/settings/", old_settings | {"opening_text": "March 2027"}).status_code, 409)
        self.assertEqual(SiteSettings.load().opening_text, "January 2027")
        base = form_data(capacity_form, "capacity", capacity="30")  # made before the settings save: still current
        self.assertEqual(self.client.post("/hours/capacity/", base).status_code, 302)
        emails = {"gold_approver_cc": "", "contact_email": "", "row_token": "not-the-current-one"}
        self.assertEqual(self.client.post("/emails/", emails).status_code, 409)


class BadInputTests(RulesTestCase):
    def test_wrong_shapes_are_field_errors_never_a_500(self):
        plan = Plan.objects.get(slug="tier-2")
        response = self.client.post(f"/plans/{plan.pk}/", plan_post(plan, perks='[{"key": ["a"], "label": "x", "value": 1}]'))
        self.assertEqual(response.status_code, 400)
        rule = next(r for r in self.client.get("/journey/").context["suggestion_rules"])
        form = f.SuggestionRuleForm(instance=rule["obj"], prefix="x")
        data = form_data(form, "x", conditions='[{"question": ["time"], "any_of": ["evening"]}]')
        self.assertEqual(self.client.post(f"/journey/suggestions/{rule['obj'].pk}/", {k.replace("x-", f"{rule['obj'].pk}-"): v for k, v in data.items()}).status_code, 400)
        option = Option.objects.filter(question__type=Question.SINGLE).first()
        for raw in ("--5", "²", "١٢", "5000"):
            form = f.OptionForm(instance=option, prefix=str(option.pk))
            post = form_data(form, str(option.pk))
            post.pop(f"{option.pk}-plan_points", None)
            post[f"{option.pk}-plan_points.tier-2"] = raw
            self.assertEqual(self.client.post(f"/journey/options/{option.pk}/", post).status_code, 400, raw)
        self.assertEqual((parse_whole("--5"), parse_whole("²"), parse_whole("-5")), ("--5", "²", -5))

    def test_arabic_indic_digits_are_refused_in_money_and_numbers(self):
        plan = Plan.objects.get(slug="tier-2")
        old = plan.price_ex_vat
        response = self.client.post(f"/plans/{plan.pk}/", plan_post(plan, price_ex_vat="١٢"))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Use the digits 0-9.", status_code=400)
        plan.refresh_from_db()
        self.assertEqual(plan.price_ex_vat, old)

    def test_new_bounds_dates_and_points(self):
        plan = Plan.objects.get(slug="tier-2")
        for field, value in (("cancel_hours", "721"), ("guests_per_month", "51"), ("booking_window_days", "366"), ("visits_per_month", "101")):
            self.assertEqual(self.client.post(f"/plans/{plan.pk}/", plan_post(plan, **{field: value})).status_code, 400, field)
        site = SiteSettings.load()
        base = form_data(f.CapacityForm(instance=site, prefix="capacity"), "capacity")
        for field, value in (("capacity", "501"), ("slot_length_minutes", "1441"), ("slot_step_minutes", "0"), ("booking_notice_minutes", "1441")):
            self.assertEqual(self.client.post("/hours/capacity/", base | {f"capacity-{field}": value}).status_code, 400, field)
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        past = self.client.post("/settings/", SETTINGS_POST | {"opening_date": yesterday})
        self.assertEqual(past.status_code, 400)
        SiteSettings.objects.update(opening_date=timezone.localdate() - timedelta(days=30))  # an existing past date is fine
        self.assertEqual(self.client.post("/settings/", SETTINGS_POST | {"opening_date": (timezone.localdate() - timedelta(days=30)).isoformat(), "vat_rate": "21.00"}).status_code, 302)
        ended = {"new-closure-name": "Old", "new-closure-starts_at": "2020-01-01T10:00", "new-closure-ends_at": "2020-01-02T10:00", "new-closure-active": "on"}
        self.assertEqual(self.client.post("/hours/closures/add/", ended).status_code, 400)
        rule = GoldRule.objects.exclude(group="threshold").first()
        data = form_data(f.GoldRuleForm(instance=rule, prefix=str(rule.pk)), str(rule.pk), points="1001")
        self.assertEqual(self.client.post(f"/gold/{rule.pk}/", data).status_code, 400)


class ModelRuleTests(RulesTestCase):
    def test_undo_refuses_when_the_old_value_now_breaks_the_gold_threshold_rule(self):
        high = GoldRule.objects.get(group="threshold", match_value="high")
        medium = GoldRule.objects.get(group="threshold", match_value="medium")
        GoldRule.objects.filter(pk=high.pk).update(points=10)
        GoldRule.objects.filter(pk=medium.pk).update(points=5)
        for rule, value in ((high, 20), (medium, 15)):
            rule = GoldRule.objects.get(pk=rule.pk)
            rule.points = value
            services.save_logged(rule, self.user, fields=["points"])
        first = SystemChange.objects.get(object_pk=str(high.pk), field="points")  # High 10 -> 20
        with self.assertRaises(services.ChangeRefused) as caught:
            services.undo_change(first, self.user)  # would put High (10) below Medium (15)
        self.assertIn("High threshold cannot be lower", str(caught.exception))
        self.assertEqual(GoldRule.objects.get(pk=high.pk).points, 20)

    def test_options_cannot_be_switched_off_below_the_questions_minimum(self):
        question = Question.objects.filter(type=Question.SINGLE, options__isnull=False).first()
        live = list(question.options.filter(active=True))
        Question.objects.filter(pk=question.pk).update(min_choices=len(live))
        option = Option.objects.get(pk=live[0].pk)
        form = f.OptionForm(form_data(f.OptionForm(instance=option, prefix="o"), "o", active=""), instance=option, prefix="o")
        form.data.pop("o-active", None)
        self.assertFalse(form.is_valid())
        self.assertIn("active", form.errors)
        Question.objects.filter(pk=question.pk).update(min_choices=len(live) - 1)
        again = f.OptionForm(form.data, instance=Option.objects.get(pk=option.pk), prefix="o")
        self.assertTrue(again.is_valid(), again.errors)


class HeaderTests(RulesTestCase):
    def test_every_system_response_is_never_cached_and_may_not_be_framed(self):
        for client, path in ((self.client, "/plans/"), (self.client, "/changes/export.csv"), (Client(HTTP_HOST=SYSTEM), "/plans/"), (Client(HTTP_HOST=SYSTEM), "/dev-login/")):
            response = client.get(path)
            self.assertIn("no-store", response["Cache-Control"], path)
            self.assertIn("no-cache", response["Cache-Control"], path)
            self.assertEqual(response["Content-Security-Policy"], "frame-ancestors 'none'", path)
        public = Client(HTTP_HOST="localhost").get("/login/")
        self.assertNotIn("Content-Security-Policy", public)


class AuditAndAdminTests(RulesTestCase):
    def test_changing_the_password_in_system_writes_an_event_without_the_password(self):
        response = self.client.post("/password/", {"old_password": PASSWORD, "new_password1": "A-new-long-pass-9", "new_password2": "A-new-long-pass-9"})
        self.assertEqual(response.status_code, 302)
        event = SystemEvent.objects.get(kind=SystemEvent.PASSWORD_CHANGED)
        self.assertEqual((event.user, event.outcome), (self.user, "ok"))
        self.assertNotIn("A-new-long-pass-9", f"{event.detail} {event.sentence}")
        self.assertTrue(SystemEvent.objects.filter(kind=SystemEvent.PASSWORD_CHANGED, id=event.id).exists())
        self.assertIn(SystemEvent.PASSWORD_CHANGED, [k for k, _ in SystemEvent.KIND_CHOICES])

    def test_team_access_is_read_only_in_the_django_admin(self):
        model_admin = UserAdmin(User, admin.site)
        readonly = model_admin.get_readonly_fields(None, make_user("x@example.com"))
        self.assertTrue({"is_staff", "is_superuser", "groups"} <= set(readonly))

    def test_removing_a_suppression_writes_the_event_and_the_delete_together(self):
        row = EmailSuppression.objects.create(email="bounced@example.com", reason=EmailSuppression.HARD_BOUNCE, first_seen=timezone.now(), last_seen=timezone.now())
        with mock.patch.object(EmailSuppression, "delete", side_effect=RuntimeError("db down")):
            with self.assertRaises(RuntimeError):
                services.remove_suppression(mock.Mock(user=self.user, META={}, path="/", headers={}), row)
        self.assertFalse(SystemEvent.objects.filter(kind=SystemEvent.SUPPRESSION_REMOVED).exists())
        self.assertTrue(EmailSuppression.objects.filter(pk=row.pk).exists())
        self.assertContains(self.client.get("/emails/suppressions/"), "data-system-confirm")
