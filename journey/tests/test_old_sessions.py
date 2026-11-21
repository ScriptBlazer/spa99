"""2026-11-21: journeys that started before "nothing is optional" must keep working and never leave anyone stuck."""
import csv
import json
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from common.models import RateHit
from journey import engine, services
from journey.models import Answer, JourneySession, Option, Question
from office import snapshots
from office.tests.test_office import OFFICE, OfficeTestCase, get, staff
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings

from .helpers import answer_minimal


def skipped(session, key):
    return Answer.objects.create(session=session, question=Question.objects.get(key=key), skipped=True)


def old_style_session(finished=True):
    """A journey made under the old rules: frequency, company and heard_via skipped, and "Where?" typed empty (as skipped)."""
    session = services.create_session("Mozilla/5.0 (Macintosh) Safari/605.1")
    services.save_answer(session, "time", options=["evening"])
    services.save_answer(session, "facilities", options=["gym"])
    services.save_answer(session, "industry", options=["other"])
    skipped(session, "frequency")
    skipped(session, "company")
    skipped(session, "industry_other")
    skipped(session, "heard_via")
    if finished:
        JourneySession.objects.filter(pk=session.pk).update(completed=True, completed_at=timezone.now(), current_step=5, furthest_step=5)
    return JourneySession.objects.get(pk=session.pk)


class OldFinishedSessionTests(OfficeTestCase):
    def test_results_state_export_metrics_and_the_office_still_work_and_nothing_is_rewritten(self):
        session = old_style_session()
        services.save_lead(session, "old@example.com", True)
        # "Where?" empty on a chosen Other, with heard_via = Other chosen: another old shape
        other = old_style_session()
        Answer.objects.filter(session=other, question__key="heard_via").delete()
        answer = Answer.objects.create(session=other, question=Question.objects.get(key="heard_via"))
        answer.options.set(Option.objects.filter(question__key="heard_via", value="other"))
        Answer.objects.create(session=other, question=Question.objects.get(key="heard_via_other"), text_value="", skipped=True)
        before = list(Answer.objects.order_by("pk").values_list("pk", "skipped", "text_value"))

        self.assertTrue(engine.preview(session)["suggested"])
        self.assertTrue(engine.preview(other)["suggested"])
        self.assertTrue(services.build_state(session)["screens"])
        self.assertEqual(services.effective_answers(session).keys(), {"time", "facilities", "industry"})
        self.assertTrue(engine.compute_gold(other))
        self.assertTrue(Client().get("/journey/state/").status_code == 200)

        # the same people's own data export reads it

        call_command("rebuild_metrics", stdout=StringIO())
        snapshots.build_everything()
        admin = staff("Admin", "admin@example.com")
        self.assertContains(get(admin, "/leads/"), "old@example.com")
        body = get(admin, "/leads/export.csv").content.decode()
        self.assertIn("old@example.com", body)
        list(csv.reader(StringIO(body)))  # parses
        for path in ("/analytics/", "/analytics/?range=all"):
            self.assertEqual(get(admin, path).status_code, 200, path)
        self.assertEqual(get(admin, f"/leads/{session.pk}/").status_code, 200)
        self.assertEqual(list(Answer.objects.order_by("pk").values_list("pk", "skipped", "text_value")), before)  # nothing rewritten

    def test_the_page_can_still_show_an_old_finished_result_and_nothing_is_re_stored(self):
        """The result page always POSTs /journey/result/ (See my last suggestion, a reload, a bookmark). Reviewer 2026-11-21:
        it used to answer 400 and send him back to screen 1."""
        site = SiteSettings.load()
        site.journey_email_gate = False
        site.save()
        client = Client()
        client.get("/journey/state/")
        session = services.session_from_cookies({"spa99_journey": client.cookies["spa99_journey"].value})
        services.save_answer(session, "time", options=["evening"])
        services.save_answer(session, "facilities", options=["gym"])
        services.save_answer(session, "industry", options=["finance"])
        for key in ("frequency", "company", "heard_via"):
            skipped(session, key)
        JourneySession.objects.filter(pk=session.pk).update(completed=True, completed_at=timezone.now(), current_step=5, furthest_step=5)
        stored = JourneySession.objects.filter(pk=session.pk).values("completed_at", "suggested_plan_id", "gold_score").get()
        RateHit.objects.all().delete()
        reply = client.post("/journey/result/", "{}", content_type="application/json")
        self.assertEqual(reply.status_code, 200, reply.content)
        self.assertTrue(reply.json()["suggested"])
        self.assertEqual(JourneySession.objects.filter(pk=session.pk).values("completed_at", "suggested_plan_id", "gold_score").get(), stored)


class UnfinishedOldSessionTests(TestCase):
    """Someone halfway through at deploy, with a now-required answer skipped on an earlier screen."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        site = SiteSettings.load()
        site.journey_email_gate = False
        site.save()
        self.client = Client()
        self.client.get("/journey/state/")
        self.session = services.session_from_cookies({"spa99_journey": self.client.cookies["spa99_journey"].value})
        # screen 1: time answered, frequency skipped; screen 2 done; screen 3 company skipped; he is on screen 4
        services.save_answer(self.session, "time", options=["evening"])
        services.save_answer(self.session, "facilities", options=["gym"])
        services.save_answer(self.session, "industry", options=["other"])
        for key in ("frequency", "company"):
            skipped(self.session, key)
        JourneySession.objects.filter(pk=self.session.pk).update(current_step=4, furthest_step=4)

    def post(self, path, data):
        RateHit.objects.all().delete()
        return self.client.post(path, json.dumps(data), content_type="application/json")

    def test_coming_back_starts_at_screen_one_with_the_skipped_questions_shown_as_unanswered(self):
        state = self.client.get("/journey/state/").json()
        self.assertEqual(state["session"]["resume_step"], 1)
        by_key = {q["key"]: q for s in state["screens"] for q in s["questions"]}
        self.assertTrue(by_key["frequency"]["answer"]["skipped"])
        self.assertTrue(by_key["frequency"]["required"])

    def test_pressing_continue_or_finishing_names_every_missing_question_never_a_dead_end(self):
        result = self.post("/journey/result/", {})
        self.assertEqual(result.status_code, 400)
        missing = result.json()["missing"]
        self.assertEqual(missing, ["frequency", "company", "heard_via", "industry_other"])  # in screen order: the page bounces to screen 1
        step = self.post("/journey/step/", {"step": 5})
        self.assertEqual((step.status_code, step.json()["missing"][0]), (400, "frequency"))

    def test_answering_what_the_server_names_one_screen_at_a_time_always_reaches_the_result(self):
        for _ in range(10):
            reply = self.post("/journey/result/", {})
            if reply.status_code == 200:
                break
            key = reply.json()["missing"][0]  # what the page bounces to: the first screen with something missing
            q = Question.objects.get(key=key)
            payload = {"question": key, "text": "a"} if q.type == Question.TEXT else {"question": key, "options": [q.options.first().value]}
            self.assertEqual(self.post("/journey/answer/", payload).status_code, 200, key)
        self.assertEqual(reply.status_code, 200)
        self.assertTrue(JourneySession.objects.get(pk=self.session.pk).completed)

    def test_going_forward_screen_by_screen_works_too(self):
        JourneySession.objects.filter(pk=self.session.pk).update(current_step=1, furthest_step=4)
        self.assertEqual(self.post("/journey/step/", {"step": 2}).status_code, 400)  # frequency still missing
        self.post("/journey/answer/", {"question": "frequency", "options": ["weekly"]})
        self.assertEqual(self.post("/journey/step/", {"step": 2}).status_code, 200)
