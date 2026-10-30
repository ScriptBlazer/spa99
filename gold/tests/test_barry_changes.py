"""Barry's changes (2026-10-29): company and role required, the business question, the new wording, Midlands, the WhatsApp message."""
import json

from django.test import Client, TestCase

from gold import rating, services
from gold.forms import GoldApplicationForm
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings


def form(**over):
    f = GoldApplicationForm({**application_data(), "privacy_accepted": True, **over})
    f.is_valid()
    return f


class FormRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_company_and_role_are_always_required(self):
        for field in ("company", "role"):
            self.assertIn(field, form(**{field: ""}).errors)
            self.assertIn(field, form(**{field: "   "}).errors)
        self.assertEqual(form().errors, {})

    def test_business_question_is_required_only_when_not_working_with_bml(self):
        self.assertIn("business_willing", form(bml_relationship="not_yet").errors)
        self.assertIn("business_willing", form(bml_relationship="not_yet", business_willing="maybe").errors)
        self.assertIs(form(bml_relationship="not_yet", business_willing="no").cleaned_data["business_willing"], False)
        self.assertIs(form(bml_relationship="not_yet", business_willing=True).cleaned_data["business_willing"], True)
        # working with BML, or not answered: never asked, never required, and any value is dropped
        self.assertEqual(form(bml_relationship="yes").errors, {})
        self.assertIsNone(form(bml_relationship="yes", business_willing="yes").cleaned_data["business_willing"])
        self.assertEqual(form(bml_relationship="").errors, {})

    def test_it_is_stored_shown_to_the_approver_and_exported(self):
        for answer, shown in (("yes", "Yes"), ("no", "No")):
            data = form(bml_relationship="not_yet", business_willing=answer, email=f"{answer}@example.com").cleaned_data
            application, _ = services.submit_application(data)
            self.assertIs(application.business_willing, answer == "yes")
            rows = dict(services.application_sections(application)[1]["rows"])
            self.assertEqual(rows["Happy to do business with BML"], shown)
            self.assertEqual(services.export_applications(application.email)[0]["business_willing"], answer == "yes")
        asked_not = services.submit_application(form(email="x@example.com").cleaned_data)[0]
        self.assertIsNone(asked_not.business_willing)
        self.assertEqual(dict(services.application_sections(asked_not)[1]["rows"])["Happy to do business with BML"], "–")

    def test_the_score_does_not_change_with_the_answer(self):
        yes = services.submit_application(form(bml_relationship="not_yet", business_willing="yes", email="a@example.com").cleaned_data)[0]
        no = services.submit_application(form(bml_relationship="not_yet", business_willing="no", email="b@example.com").cleaned_data)[0]
        self.assertEqual(yes.potential_score, no.potential_score)

    def test_endpoint_refuses_missing_company_and_business_answer(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get("/gold/options/").cookies["csrftoken"].value
        body = application_data(company="", bml_relationship="not_yet", privacy_accepted=True)
        response = client.post("/gold/apply/", json.dumps(body), content_type="application/json", headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["errors"]), {"company", "business_willing"})


class WordingAndLocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_location_is_midlands_and_the_old_value_is_gone_from_new_installs(self):
        values = dict(rating.choices("where"))
        self.assertEqual(values["midlands"], "Midlands")
        self.assertNotIn("rest_of_london", values)
        self.assertEqual(form(location="midlands").errors, {})
        self.assertIn("location", form(location="rest_of_london").errors)

    def test_working_with_bml_wording_and_the_industry_question(self):
        self.assertEqual(rating.label_for("bml", "yes"), "Yes")
        self.assertEqual(rating.label_for("bml", "not_yet"), "No")
        self.assertEqual(rating.industry_choices()[0][0], "property")
        data = Client().get("/gold/options/").json()
        self.assertEqual(data["industry"]["question"], "What industry are you in?")
        application = services.submit_application(form(note="Introductions").cleaned_data)[0]
        rows = dict(services.application_sections(application)[1]["rows"])
        self.assertEqual(rows["What benefits could he bring to BML?"], "Introductions")
        self.assertNotIn("Note from applicant", rows)

    def test_the_gold_page_gets_the_whatsapp_link_only_while_one_is_set(self):
        SiteSettings.load()
        SiteSettings.objects.update(whatsapp_number="447530117902")
        page = Client().get("/gold-card/apply/").content.decode()
        self.assertIn("/whatsapp/?from=gold&amp;msg=gold_business", page.replace("\\u0026", "&amp;"))
        SiteSettings.objects.update(whatsapp_number="")
        self.assertIn('"whatsappBusiness": ""', Client().get("/gold-card/apply/").content.decode())
