"""2026-11-21: nothing is optional in the journey. Real people must never get stuck, so these walk whole journeys through the
real endpoints on every branch, and check the page script and the server agree on what is required."""
import json
import random
import shutil
import subprocess
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase

from common.models import RateHit
from content.models import Section
from journey import engine, services
from journey.models import Answer, JourneySession, Option, Question
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings

REQUIRED = ["time", "frequency", "facilities", "company", "industry", "property_link", "property_size", "property_law",
            "heard_via", "industry_other", "heard_via_other"]


class Walker:
    """Behaves like journey.js: answers what is shown screen by screen, never skips, moves on only when the server allows."""

    def __init__(self, test, choose=None):
        self.test, self.client, self.choose = test, Client(), choose or {}
        self.client.get("/journey/state/")

    def post(self, path, data):
        return self.client.post(path, json.dumps(data), content_type="application/json")

    def state(self):
        data = self.client.get("/journey/state/").json()
        assert "screens" in data, data
        return data

    def questions(self, state):
        return [q for s in state["screens"] for q in s["questions"]]

    def answer(self, q):
        if q["type"] == "text":
            payload = {"question": q["key"], "text": self.choose.get(q["key"], "a")}
        else:
            picked = self.choose.get(q["key"]) or [q["options"][0]["value"]]
            payload = {"question": q["key"], "options": picked if q["type"] == "multi" else picked[:1]}
        reply = self.post("/journey/answer/", payload)
        self.test.assertEqual(reply.status_code, 200, (q["key"], reply.content))

    def unmet(self, state, screen=None):
        return [q for q in self.questions(state) if q["visible"] and q["required"] and (screen is None or q["screen"] == screen)
                and not (q["answer"] and not q["answer"]["skipped"] and (q["answer"]["text"].strip() if q["type"] == "text" else q["answer"]["options"]))]

    def fill_screen(self, number):
        for _ in range(20):  # answering one can show a follow-up on the same screen
            todo = self.unmet(self.state(), number)
            if not todo:
                return
            self.answer(todo[0])
        raise AssertionError("never settled")

    def finish(self):
        """Screen by screen: answer what is shown, press Continue (the step endpoint), then arrive at the result."""
        numbers = sorted({q["screen"] for q in self.questions(self.state()) if q["visible"]})
        for number in numbers:
            self.fill_screen(number)
            reply = self.post("/journey/step/", {"direction": "next"})
            self.test.assertEqual(reply.status_code, 200, (number, reply.content))
        result = self.post("/journey/result/", {})
        self.test.assertEqual(result.status_code, 200, result.content)
        self.test.assertEqual(self.unmet(self.state()), [])
        session = JourneySession.objects.get()
        self.test.assertTrue(session.completed)
        return session


class RequiredBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        site = SiteSettings.load()
        site.journey_email_gate = False
        site.save()


class EveryQuestionRequiredTests(RequiredBase):
    def test_the_seed_makes_all_eleven_required_and_nothing_else_is_optional(self):
        got = dict(Question.objects.filter(active=True).values_list("key", "min_choices"))
        self.assertEqual(sorted(got), sorted(REQUIRED))
        self.assertTrue(all(v == 1 for v in got.values()), got)

    def test_server_refuses_skipping_or_empty_on_every_visible_required_question(self):
        walker = Walker(self)
        for key in ("time", "frequency", "facilities", "company", "industry", "heard_via"):
            self.assertEqual(walker.post("/journey/answer/", {"question": key, "skipped": True}).status_code, 400, key)
            self.assertEqual(walker.post("/journey/answer/", {"question": key, "options": []}).status_code, 400, key)
        self.assertEqual(Answer.objects.count(), 0)

    def test_blank_or_whitespace_text_is_refused_and_one_letter_passes(self):
        walker = Walker(self, {"industry": ["other"], "heard_via": ["other"]})
        for key in ("industry", "heard_via"):
            walker.answer(next(q for q in walker.questions(walker.state()) if q["key"] == key))
        for key in ("industry_other", "heard_via_other"):
            for bad in ({"text": ""}, {"text": "   \n "}, {"skipped": True}, {}):
                self.assertEqual(walker.post("/journey/answer/", {"question": key, **bad}).status_code, 400, (key, bad))
            self.assertEqual(walker.post("/journey/answer/", {"question": key, "text": "a"}).status_code, 200)
        self.assertEqual(Answer.objects.get(question__key="industry_other").text_value, "a")
        self.assertEqual(Answer.objects.get(question__key="heard_via_other").text_value, "a")

    def test_a_hidden_question_is_never_required_and_cannot_be_answered(self):
        session = services.create_session()
        self.assertNotIn("industry_other", services.missing_required(session))
        self.assertNotIn("property_link", services.missing_required(session))
        with self.assertRaises(services.AnswerError):
            services.save_answer(session, "industry_other", text="a")


class BranchJourneyTests(RequiredBase):
    """Minimal answers, finished end to end through the real views, on every branch."""

    def test_plain_path(self):
        session = Walker(self, {"industry": ["finance"]}).finish()
        self.assertEqual(session.answers.count(), 6)

    def test_property_with_link_and_size(self):
        session = Walker(self, {"industry": ["property"]}).finish()
        self.assertEqual({a.question.key for a in session.answers.all()} - {"time", "frequency", "facilities", "company", "heard_via"},
                         {"industry", "property_link", "property_size"})

    def test_law_with_property_law(self):
        session = Walker(self, {"industry": ["law"]}).finish()
        self.assertTrue(session.answers.filter(question__key="property_law").exists())

    def test_other_industry_and_other_heard_via_with_one_letter(self):
        session = Walker(self, {"industry": ["other"], "heard_via": ["other"]}).finish()
        self.assertEqual(session.answers.get(question__key="industry_other").text_value, "a")
        self.assertEqual(session.answers.get(question__key="heard_via_other").text_value, "a")

    def test_every_follow_up_at_once(self):
        session = Walker(self, {"industry": ["property", "law", "other"], "heard_via": ["other"]}).finish()
        self.assertEqual(session.answers.count(), 11)

    def test_every_option_of_every_choice_question_can_be_the_minimal_answer(self):
        for question in Question.objects.exclude(type=Question.TEXT):
            for option in question.options.filter(active=True):
                RateHit.objects.all().delete()  # the endpoints are rate limited per address
                walker = Walker(self, {question.key: [option.value]})
                walker.finish()
                JourneySession.objects.all().delete()

    def test_changing_an_answer_so_a_follow_up_hides_does_not_block(self):
        walker = Walker(self, {"industry": ["property", "other"], "heard_via": ["other"]})
        walker.fill_screen(1)
        walker.fill_screen(2)
        walker.fill_screen(3)
        walker.fill_screen(4)  # every follow-up shown and answered
        for key, picked in (("industry", ["finance"]), ("heard_via", ["friend"])):  # both Others and Property go away
            self.assertEqual(walker.post("/journey/answer/", {"question": key, "options": picked}).status_code, 200)
        state = walker.state()
        shown = {q["key"] for q in walker.questions(state) if q["visible"]}
        self.assertFalse(shown & {"property_link", "property_size", "industry_other", "heard_via_other"})
        self.assertEqual(walker.unmet(state), [])
        session = walker.finish()
        self.assertTrue(session.completed)

    def test_a_follow_up_that_appears_after_the_change_blocks_until_answered_then_lets_him_through(self):
        walker = Walker(self)
        for number in (1, 2, 3, 4):
            walker.fill_screen(number)
        walker.post("/journey/step/", {"direction": "next"})
        walker.post("/journey/answer/", {"question": "industry", "options": ["other"]})
        self.assertEqual([q["key"] for q in walker.unmet(walker.state())], ["industry_other"])
        self.assertEqual(walker.post("/journey/result/", {}).status_code, 400)
        walker.answer(next(q for q in walker.questions(walker.state()) if q["key"] == "industry_other"))
        self.assertEqual(walker.post("/journey/result/", {}).status_code, 200)

    def test_old_finished_sessions_with_skipped_answers_still_work(self):
        session = services.create_session()
        for key in ("time", "frequency", "facilities", "company", "industry"):
            Answer.objects.create(session=session, question=Question.objects.get(key=key), skipped=True)
        JourneySession.objects.filter(pk=session.pk).update(completed=True)
        session.refresh_from_db()
        self.assertEqual(engine.compute_suggestion(session).plan.slug, "tier-2")  # reads fine, nothing is rewritten
        self.assertEqual(Answer.objects.filter(session=session, skipped=True).count(), 5)
        self.assertTrue(services.build_state(session)["screens"])


class PageScriptAgreesWithServerTests(RequiredBase):
    def test_required_and_visibility_logic_in_journey_js_matches_the_server(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        rng = random.Random(2026)
        cases, expected = [], []
        for _ in range(120):
            session = services.create_session()
            for _ in range(3):  # a few passes so follow-ups get their chance
                for q in services.visible_questions(session)[0]:
                    roll = rng.random()
                    if roll < 0.25:
                        continue
                    try:
                        if q.type == Question.TEXT:
                            services.save_answer(session, q.key, text=rng.choice(["a", "  ", "Word of mouth"]))
                        else:
                            values = [o.value for o in q.active_options]
                            picked = rng.sample(values, rng.randint(1, min(3, len(values)))) if q.type == Question.MULTI else [rng.choice(values)]
                            services.save_answer(session, q.key, options=picked)
                    except services.AnswerError:
                        pass
                if rng.random() < 0.4:  # a change of mind
                    q = rng.choice(services.visible_questions(session)[0])
                    if q.type == Question.MULTI:
                        services.save_answer(session, q.key, options=[q.active_options[0].value])
            state = services.build_state(session)
            answers = {}
            for s in state["screens"]:
                for q in s["questions"]:
                    if q["answer"]:
                        answers[q["key"]] = q["answer"]
            cases.append({"state": state, "answers": answers})
            missing = set(services.missing_required(session))
            by_screen = {s["number"]: sorted(q["key"] for q in s["questions"] if q["key"] in missing) for s in state["screens"]}
            expected.append({"unmet": {str(k): v for k, v in by_screen.items()},
                             "visible": sorted(q["key"] for s in state["screens"] for q in s["questions"] if q["visible"])})
        script = Path(__file__).with_name("required_check.js")
        journey_js = Path(settings.BASE_DIR) / "common/static/common/js/journey.js"
        run = subprocess.run([node, str(script), str(journey_js)], input=json.dumps(cases), capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout), expected)


    def test_an_answer_on_a_retired_option_counts_as_unanswered_on_the_page_as_on_the_server(self):
        """Reviewer 2026-11-21: the page used to count a retired option as an answer while the server did not, so Continue
        looked active and every tap bounced back with no message."""
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        session = services.create_session()
        for key, value in (("time", "evening"), ("frequency", "weekly"), ("facilities", "gym"), ("company", "alone"),
                           ("industry", "finance"), ("heard_via", "friend")):
            services.save_answer(session, key, options=[value])
        Option.objects.filter(question__key="heard_via", value="friend").update(active=False)
        Option.objects.filter(question__key="facilities", value="gym").update(active=False)
        self.assertEqual(set(services.missing_required(session)), {"heard_via", "facilities"})
        state = services.build_state(session)
        answers = {q["key"]: q["answer"] for s in state["screens"] for q in s["questions"] if q["answer"]}
        self.assertIn("friend", answers["heard_via"]["options"])  # the page does receive the retired value
        script = Path(__file__).with_name("required_check.js")
        journey_js = Path(settings.BASE_DIR) / "common/static/common/js/journey.js"
        run = subprocess.run([node, str(script), str(journey_js)], input=json.dumps([{"state": state, "answers": answers}]),
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        unmet = sorted(k for keys in json.loads(run.stdout)[0]["unmet"].values() for k in keys)
        self.assertEqual(unmet, ["facilities", "heard_via"])


class BackfillRequiredTests(RequiredBase):
    def run_command(self, *args):
        out = StringIO()
        call_command("backfill_site_data", *args, stdout=out)
        return out.getvalue()

    def make_old(self):
        Question.objects.filter(key__in=REQUIRED).update(min_choices=0)
        Question.objects.filter(key="time").update(min_choices=1)  # was already required
        Question.objects.filter(key="facilities").update(min_choices=2)  # set by hand in Control: stays
        Section.objects.filter(page__key="journey", key="need_text").delete()
        Section.objects.filter(page__key="journey", key="screen_4").update(body="Optional, and only to suggest the right fit.")

    def mins(self):
        return dict(Question.objects.values_list("key", "min_choices"))

    def test_dry_run_lists_changes_and_saves_nothing_then_run_changes_only_zeros_and_is_idempotent(self):
        self.make_old()
        before = self.mins()
        dry = self.run_command("--dry-run")
        self.assertIn("Would change 9 x journey.Question (answer required)", dry)
        self.assertEqual(self.mins(), before)
        self.assertFalse(Section.objects.filter(page__key="journey", key="need_text").exists())
        first = self.run_command()
        self.assertIn("Changed 9 x journey.Question (answer required)", first)
        got = self.mins()
        self.assertTrue(all(v == 1 for k, v in got.items() if k not in ("facilities",)), got)
        self.assertEqual(got["facilities"], 2)
        self.assertEqual(Section.objects.get(page__key="journey", key="need_text").body, "Please write a few words.")
        self.assertEqual(Section.objects.get(page__key="journey", key="screen_4").body, "Only to suggest the right fit.")
        self.assertNotIn("answer required", self.run_command())  # second run: nothing left
        self.assertEqual(self.mins(), got)
        # Moishe later makes a question optional in Control: a later backfill run (GO-LIVE says to re-run it) leaves it alone
        Question.objects.filter(key="company").update(min_choices=0)
        self.assertNotIn("answer required", self.run_command())
        self.assertEqual(self.mins()["company"], 0)


class OtherBoxTests(RequiredBase):
    """Moishe 2026-11-21: "In a few words" sits right under Industry, says which Other it is for, and is needed only when Other
    is the only industry ticked. "Where?" says the same for How did you hear about us."""

    def setUp(self):
        super().setUp()
        self.session = services.create_session()
        for key, value in (("time", "evening"), ("frequency", "weekly"), ("facilities", "gym"), ("company", "alone"), ("heard_via", "friend")):
            services.save_answer(self.session, key, options=[value])

    def test_other_alone_needs_words_other_with_another_industry_does_not(self):
        services.save_answer(self.session, "industry", options=["other"])
        self.assertEqual(services.missing_required(self.session), ["industry_other"])
        with self.assertRaises(services.AnswerError):
            services.save_answer(self.session, "industry_other", skipped=True)
        services.save_answer(self.session, "industry", options=["other", "finance"])
        self.assertEqual(services.missing_required(self.session), [])
        services.save_answer(self.session, "industry_other", skipped=True)  # clearing it is fine now
        self.assertEqual(engine.complete(self.session)["suggested"] is not None, True)
        services.save_answer(self.session, "industry", options=["other"])  # back to Other alone: words needed again
        self.assertEqual(services.missing_required(self.session), ["industry_other"])

    def test_other_with_property_shows_the_box_first_then_the_property_questions(self):
        services.save_answer(self.session, "industry", options=["property", "other"])
        keys = [q.key for q in services.visible_questions(self.session)[0] if q.screen == 4]
        self.assertEqual(keys, ["industry", "industry_other", "property_link", "heard_via"])
        state = services.build_state(self.session)
        by_key = {q["key"]: q for s in state["screens"] for q in s["questions"]}
        self.assertEqual(by_key["industry_other"]["help"], "You picked Other under Industry.")
        self.assertEqual(by_key["heard_via_other"]["help"], "You picked Other under How did you hear about us.")

    def test_a_retired_industry_next_to_other_does_not_make_the_words_optional(self):
        services.save_answer(self.session, "industry", options=["other", "finance"])
        self.assertEqual(services.missing_required(self.session), [])
        Option.objects.filter(question__key="industry", value="finance").update(active=False)
        self.assertEqual(services.missing_required(self.session), ["industry_other"])  # the page shows Other alone ticked
        node = shutil.which("node")
        if node is None:
            return
        state = services.build_state(self.session)
        answers = {q["key"]: q["answer"] for sc in state["screens"] for q in sc["questions"] if q["answer"]}
        run = subprocess.run([node, str(Path(__file__).with_name("required_check.js")), str(Path(settings.BASE_DIR) / "common/static/common/js/journey.js")],
                             input=json.dumps([{"state": state, "answers": answers}]), capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)[0]["unmet"]["4"], ["industry_other"])

    def test_where_is_still_needed_when_other_is_picked(self):
        services.save_answer(self.session, "industry", options=["finance"])
        services.save_answer(self.session, "heard_via", options=["other"])
        self.assertEqual(services.missing_required(self.session), ["heard_via_other"])
        services.save_answer(self.session, "heard_via_other", text="a")
        self.assertEqual(services.missing_required(self.session), [])


class OtherBoxBackfillTests(RequiredBase):
    OLD = {"industry": 1, "property_link": 2, "property_size": 3, "property_law": 4, "heard_via": 5, "industry_other": 6, "heard_via_other": 7}

    def run_command(self, *args):
        out = StringIO()
        call_command("backfill_site_data", *args, stdout=out)
        return out.getvalue()

    def make_old(self):
        for key, order in self.OLD.items():
            Question.objects.filter(key=key).update(order=order)
        Question.objects.filter(key__in=["industry_other", "heard_via_other"]).update(help_text="")

    def test_moves_the_box_and_fills_the_lines_once_dry_run_saves_nothing(self):
        self.make_old()
        dry = self.run_command("--dry-run")
        self.assertIn("Would change 5 x journey.Question (In a few words moved under Industry)", dry)
        self.assertIn("Would change 2 x journey.Question (line above the Other box)", dry)
        self.assertEqual(Question.objects.get(key="industry_other").order, 6)
        self.run_command()
        orders = dict(Question.objects.filter(screen=4).values_list("key", "order"))
        self.assertEqual(orders, {"industry": 1, "industry_other": 2, "property_link": 3, "property_size": 4, "property_law": 5, "heard_via": 6, "heard_via_other": 7})
        self.assertEqual(Question.objects.get(key="industry_other").help_text, "You picked Other under Industry.")
        again = self.run_command()
        self.assertNotIn("moved under Industry", again)
        self.assertNotIn("line above", again)
        Question.objects.filter(key="industry_other").update(help_text="")  # removed in Control later: stays removed
        self.assertNotIn("line above", self.run_command())
        self.assertEqual(Question.objects.get(key="industry_other").help_text, "")

    def test_an_order_or_line_changed_in_control_is_left_alone(self):
        self.make_old()
        Question.objects.filter(key="heard_via").update(order=9)
        Question.objects.filter(key="industry_other").update(help_text="Our own words.")
        self.run_command()
        self.assertEqual(Question.objects.get(key="industry_other").order, 6)
        self.assertEqual(Question.objects.get(key="industry_other").help_text, "Our own words.")
