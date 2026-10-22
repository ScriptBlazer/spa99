import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from gold.models import GoldRule
from journey import engine, services
from journey.models import Answer, JourneySession, Option, SuggestionRule
from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan

User = get_user_model()


def make_session(**answers):
    """A session with answers given as key=value or key=[values]."""
    session = services.create_session("Mozilla/5.0 (iPhone) Mobile Safari")
    for key, value in answers.items():
        values = value if isinstance(value, list) else [value]
        services.save_answer(session, key, options=values)
    return session


class SuggestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def slug(self, **answers):
        return engine.compute_suggestion(make_session(**answers)).plan.slug

    def test_evening_excludes_daytime_only_plans(self):
        # Without the rule, "daytime + evening, now and then" would favour Tier 1 (6 points to 5).
        self.assertEqual(self.slug(time=["daytime"], frequency="now_and_then"), "tier-1")
        suggestion = engine.compute_suggestion(make_session(time=["daytime", "evening"], frequency="now_and_then"))
        self.assertEqual(suggestion.plan.slug, "tier-2")
        self.assertEqual(suggestion.excluded, ["tier-1"])

    def test_tie_goes_to_tier_2_and_that_is_data(self):
        suggestion = engine.compute_suggestion(make_session())  # no answers: everything ties on zero
        self.assertEqual((suggestion.plan.slug, suggestion.tie_broken), ("tier-2", True))
        SuggestionRule.objects.filter(kind=SuggestionRule.TIE_BREAK).update(plan_slugs=["tier-3", "tier-2", "tier-1"])
        self.assertEqual(engine.compute_suggestion(make_session()).plan.slug, "tier-3")

    def test_typical_visitors(self):
        self.assertEqual(self.slug(time=["daytime"], frequency="weekly"), "tier-1")
        self.assertEqual(self.slug(time=["evening"], frequency="two_three", company="alone"), "tier-2")
        self.assertEqual(self.slug(time=["evening"], frequency="most_days"), "tier-3")
        # evenings, 2-3 times a week and often with a guest tips to Tier 3 (rule adds points)
        self.assertEqual(self.slug(time=["evening"], frequency="two_three", company="often"), "tier-3")

    def test_three_reasons_from_answers_and_plan_facts(self):
        suggestion = engine.compute_suggestion(make_session(time=["evening"], frequency="two_three", company="alone"))
        self.assertEqual(suggestion.reasons, ["Two to three visits a week", "Evenings suit you", "Book up to 3 days ahead"])

    def test_changing_points_or_a_plan_changes_the_suggestion_without_code(self):
        session = make_session(time=["daytime"], frequency="two_three")
        self.assertEqual(engine.compute_suggestion(session).plan.slug, "tier-2")
        Option.objects.filter(question__key="frequency", value="two_three").update(plan_points={"tier-3": 9})
        self.assertEqual(engine.compute_suggestion(session).plan.slug, "tier-3")
        Plan.objects.filter(slug="tier-3").update(visible=False)  # a hidden plan is never suggested
        self.assertEqual(engine.compute_suggestion(session).plan.slug, "tier-1")  # next best by points

    def test_result_is_stored_and_marks_the_journey_complete(self):
        session = make_session(time=["evening"], frequency="two_three")
        result = engine.complete(session)
        session.refresh_from_db()
        self.assertTrue(session.completed)
        self.assertEqual(session.suggested_plan.slug, "tier-2")
        self.assertEqual(result["suggested"]["slug"], "tier-2")
        self.assertEqual(len(result["suggested"]["reasons"]), 3)
        tier_1 = next(p for p in result["others"] if p["slug"] == "tier-1")
        self.assertTrue(tier_1["not_a_fit"])  # daytime only, but he wants evenings
        self.assertEqual(result["suggested"]["price_inc_vat"], "478.80")


class GoldPotentialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def level(self, **answers):
        return engine.compute_gold(make_session(**answers))

    def test_thresholds_from_the_journey(self):
        self.assertEqual(self.level().level, "low")
        self.assertEqual(self.level(industry="finance").level, "low")
        owner = self.level(industry="property", property_link="owner_investor")
        self.assertEqual((owner.level, owner.score), ("medium", 5))  # a property link without scale
        scaled = self.level(industry="property", property_link="owner_investor", property_size="50_199")
        self.assertEqual((scaled.level, scaled.score), ("high", 7))
        self.assertEqual(self.level(industry="property", property_link="firm").level, "medium")
        self.assertEqual(self.level(industry="law", property_law="yes").level, "medium")  # property lawyer
        self.assertEqual(self.level(industry="law", property_law="no").level, "low")

    def test_weights_and_thresholds_are_editable(self):
        GoldRule.objects.filter(group="threshold", match_value="high").update(points=5)
        self.assertEqual(self.level(industry="property", property_link="owner_investor").level, "high")
        GoldRule.objects.filter(group="property_link", match_value="owner_investor").update(points=0)
        self.assertEqual(self.level(industry="property", property_link="owner_investor").level, "low")

    def test_hidden_answers_do_not_count(self):
        session = make_session(industry="property", property_link="owner_investor", property_size="200_plus")
        self.assertEqual(engine.compute_gold(session).level, "high")
        services.save_answer(session, "industry", options=["finance"])  # property questions disappear
        self.assertEqual(engine.compute_gold(session).level, "low")


class AnswerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_saving_is_idempotent_and_changes_are_kept_in_history(self):
        session = services.create_session()
        answer, changed = services.save_answer(session, "frequency", options=["weekly"])
        self.assertTrue(changed)
        _, changed_again = services.save_answer(session, "frequency", options=["weekly"])
        self.assertFalse(changed_again)
        self.assertEqual(Answer.objects.filter(session=session).count(), 1)
        history_before = answer.history.count()
        services.save_answer(session, "frequency", options=["most_days"])
        answer.refresh_from_db()
        self.assertEqual(answer.values(), ["most_days"])
        self.assertEqual(Answer.objects.filter(session=session).count(), 1)  # one current answer
        self.assertGreater(answer.history.count(), history_before)  # the old answer is still in history

    def test_validation_against_question_type(self):
        session = services.create_session()
        bad = [
            ("frequency", ["weekly", "most_days"]),  # single choice, two given
            ("time", []),  # multi needs at least one
            ("frequency", ["not-an-option"]),
            ("nope", ["x"]),
        ]
        for key, options in bad:
            with self.assertRaises(services.AnswerError, msg=key):
                services.save_answer(session, key, options=options)
        answer, _ = services.save_answer(session, "time", skipped=True)  # always skippable
        self.assertTrue(answer.skipped)
        self.assertEqual(answer.values(), [])
        self.assertEqual(Answer.objects.count(), 1)

    def test_retired_options_and_questions_are_not_offered_but_old_answers_stay(self):
        session = make_session(frequency="weekly")
        Option.objects.filter(question__key="frequency", value="weekly").update(active=False)
        state = services.build_state(session)
        freq = next(q for s in state["screens"] for q in s["questions"] if q["key"] == "frequency")
        self.assertNotIn("weekly", [o["value"] for o in freq["options"]])
        with self.assertRaises(services.AnswerError):
            services.save_answer(session, "frequency", options=["weekly"])
        self.assertTrue(Answer.objects.filter(session=session, question__key="frequency").exists())

    def test_conditional_questions_and_steps(self):
        session = services.create_session()
        visible = lambda: [q.key for q in services.visible_questions(session)[0]]  # noqa: E731
        self.assertNotIn("property_link", visible())
        with self.assertRaises(services.AnswerError):  # cannot answer a question that is not shown
            services.save_answer(session, "property_link", options=["developer"])
        services.save_answer(session, "industry", options=["property"])
        self.assertIn("property_link", visible())
        self.assertNotIn("property_size", visible())
        services.save_answer(session, "property_link", options=["developer"])
        self.assertIn("property_size", visible())
        self.assertNotIn("property_law", visible())
        self.assertEqual(services.result_step(session), 5)
        self.assertEqual(services.set_step(session, direction="next"), 2)
        self.assertEqual(services.set_step(session, step=4), 3)  # not past the screen after the furthest one reached
        self.assertEqual(services.set_step(session, direction="next"), 4)
        self.assertEqual(services.set_step(session, direction="next"), 5)  # the result
        self.assertEqual(services.set_step(session, direction="back"), 4)
        self.assertEqual(services.set_step(session, step=99), 5)
        session.refresh_from_db()
        self.assertEqual(session.furthest_step, 5)


class EndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def post(self, client, path, data, token):
        return client.post(path, json.dumps(data), content_type="application/json", headers={"X-CSRFToken": token})

    def test_cookie_csrf_resume_and_result(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/journey/state/?utm_source=instagram&ref=https://l.instagram.com/")
        self.assertEqual(response.status_code, 200)
        cookie = response.cookies["spa99_journey"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(int(cookie["max-age"]), 365 * 24 * 60 * 60)
        token = response.cookies["csrftoken"].value

        no_token = client.post("/journey/answer/", json.dumps({"question": "frequency", "options": ["weekly"]}), content_type="application/json")
        self.assertEqual(no_token.status_code, 403)  # CSRF protected

        saved = self.post(client, "/journey/answer/", {"question": "frequency", "options": ["weekly"]}, token)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.post(client, "/journey/answer/", {"question": "frequency", "options": ["bogus"]}, token).status_code, 400)
        self.post(client, "/journey/step/", {"step": 2}, token)

        resumed = client.get("/journey/state/").json()  # same cookie: same session, same screen, answers shown
        self.assertEqual(resumed["session"]["current_step"], 2)
        freq = next(q for s in resumed["screens"] for q in s["questions"] if q["key"] == "frequency")
        self.assertEqual(freq["answer"]["options"], ["weekly"])
        self.assertEqual(JourneySession.objects.count(), 1)
        session = JourneySession.objects.get()
        self.assertEqual((session.utm_source, session.device_type), ("instagram", "unknown"))

        result = client.get("/journey/result/").json()  # a GET only reads: nothing is stored
        self.assertIn(result["suggested"]["slug"], {"tier-1", "tier-2", "tier-3"})
        self.assertEqual(result["gold"]["presentation"], "none")
        session.refresh_from_db()
        self.assertEqual((session.completed, session.furthest_step, session.suggested_plan_id), (False, 2, None))
        self.assertEqual(self.post(client, "/journey/step/", {"step": 99}, token).json()["furthest_step"], 3)  # funnel cannot be inflated

        stored = self.post(client, "/journey/result/", {}, token)  # arriving at the result stores it
        self.assertEqual(stored.json()["suggested"]["slug"], result["suggested"]["slug"])
        session.refresh_from_db()
        self.assertTrue(session.completed)
        self.assertEqual(session.suggested_plan.slug, result["suggested"]["slug"])
        self.assertEqual(Client().get("/journey/result/").status_code, 404)  # no cookie, no journey

    def test_honeypot_hides_a_bot_from_the_statistics(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get("/journey/state/").cookies["csrftoken"].value
        response = self.post(client, "/journey/answer/", {"question": "frequency", "options": ["weekly"], "website": "http://spam"}, token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Answer.objects.count(), 0)
        self.assertTrue(JourneySession.objects.get().is_bot)


class SharedDeviceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_a_session_owned_by_someone_is_not_reused_by_anyone_else(self):
        owner = User.objects.create_user("owner@example.com", "a-long-password-1")
        other = User.objects.create_user("other@example.com", "a-long-password-1")
        session = services.create_session(user=owner)
        self.assertEqual(services.get_or_create_session(session.key, user=owner), (session, False))
        for visitor in (None, other):  # anonymous next person, or another account, on the same browser
            fresh, created = services.get_or_create_session(session.key, user=visitor)
            self.assertTrue(created)
            self.assertNotEqual(fresh.pk, session.pk)
            self.assertIsNone(services.session_from_cookies({"spa99_journey": session.key}, visitor))
        anonymous = services.create_session()
        self.assertEqual(services.get_or_create_session(anonymous.key, user=other), (anonymous, False))

    def test_login_drops_a_foreign_cookie_and_logout_always_does(self):
        owner = User.objects.create_user("owner@example.com", "a-long-password-1")
        other = User.objects.create_user("other@example.com", "a-long-password-1")
        theirs = services.create_session(user=owner)
        client = Client()
        client.cookies["spa99_journey"] = theirs.key
        response = client.post("/login/", {"username": "other@example.com", "password": "a-long-password-1"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies["spa99_journey"]["max-age"], 0)  # cookie removed: next visit starts fresh

        mine = services.create_session()  # an anonymous journey simply becomes the signed-in person's
        client = Client()
        client.cookies["spa99_journey"] = mine.key
        response = client.post("/login/", {"username": "other@example.com", "password": "a-long-password-1"})
        self.assertNotIn("spa99_journey", response.cookies)
        mine.refresh_from_db()
        self.assertEqual(mine.user_id, other.pk)
        self.assertEqual(client.post("/logout/").cookies["spa99_journey"]["max-age"], 0)
