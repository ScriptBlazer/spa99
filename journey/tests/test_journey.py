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
        # evenings, 2-3 times a week and sometimes with a guest tips to Tier 3 (rule adds points)
        self.assertEqual(self.slug(time=["evening"], frequency="two_three", company="sometimes"), "tier-3")
        # one guest visit a month is Tier 3 only (GST-01): "Sometimes" has points for it, "Often" is gone
        self.assertEqual(Option.objects.get(question__key="company", value="sometimes").plan_points, {"tier-3": 3})

    def test_sometimes_with_someone_is_never_tier_1_and_wins_ties_for_tier_3(self):
        # daytime + now and then is Tier 1 on points alone; "sometimes" excludes it
        self.assertEqual(self.slug(time=["daytime"], frequency="now_and_then"), "tier-1")
        suggestion = engine.compute_suggestion(make_session(time=["daytime"], frequency="now_and_then", company="sometimes"))
        self.assertNotEqual(suggestion.plan.slug, "tier-1")
        self.assertIn("tier-1", suggestion.excluded)
        # a tie goes to Tier 3 (it goes to Tier 2 without the answer)
        tied = engine.compute_suggestion(make_session(company="sometimes"))
        self.assertEqual(tied.plan.slug, "tier-3")

    def test_company_and_heard_via_options_for_new_journeys(self):
        state = services.build_state(make_session())
        options = {q["key"]: [o["value"] for o in q["options"]] for s in state["screens"] for q in s["questions"]}
        self.assertEqual(options["company"], ["alone", "sometimes"])
        self.assertEqual(options["heard_via"], ["friend", "bml", "social_media", "other"])
        self.assertEqual(Option.objects.get(question__key="heard_via", value="bml").label, "BML member")

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
        session = make_session(time=["evening"], frequency="two_three", facilities=["gym"], industry="tech")
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
        self.assertEqual(self.level(industry="finance").level, "medium")  # Finance, Business owner, Law: 3 points (2026-10-23)
        self.assertEqual(self.level(industry="business_owner").level, "medium")
        self.assertEqual(self.level(industry="tech").level, "low")
        self.assertEqual(self.level(industry="medical").level, "low")
        owner = self.level(industry="property", property_link="owner_investor")
        self.assertEqual((owner.level, owner.score), ("medium", 5))  # a property link without scale
        scaled = self.level(industry="property", property_link="owner_investor", property_size="50_199")
        self.assertEqual((scaled.level, scaled.score), ("high", 7))
        self.assertEqual(self.level(industry="property", property_link="firm").level, "medium")
        self.assertEqual(self.level(industry="law", property_law="yes").level, "high")  # law 3 + property lawyer 3
        self.assertEqual(self.level(industry="law", property_law="no").level, "medium")

    def test_weights_and_thresholds_are_editable(self):
        GoldRule.objects.filter(group="threshold", match_value="high").update(points=5)
        self.assertEqual(self.level(industry="property", property_link="owner_investor").level, "high")
        GoldRule.objects.filter(group="property_link", match_value="owner_investor").update(points=0)
        self.assertEqual(self.level(industry="property", property_link="owner_investor").level, "low")

    def test_hidden_answers_do_not_count(self):
        session = make_session(industry="property", property_link="owner_investor", property_size="200_plus")
        self.assertEqual(engine.compute_gold(session).level, "high")
        services.save_answer(session, "industry", options=["tech"])  # property questions disappear
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
        answer, _ = services.save_answer(session, "heard_via", skipped=True)  # optional questions can be skipped
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
        services.save_answer(session, "time", options=["daytime"])
        services.save_answer(session, "facilities", options=["gym"])
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


class MultiIndustryTests(TestCase):
    """2026-10-26: "What do you do?" is multi-select; the facilities option Showers became Ice bucket."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_industry_is_multi_with_at_least_one_and_the_follow_ups_follow_the_choices(self):
        question = services.visible_questions(services.create_session())[0]
        industry = next(q for q in question if q.key == "industry")
        self.assertEqual((industry.type, industry.min_choices), ("multi", 1))
        session = services.create_session()
        visible = lambda: [q.key for q in services.visible_questions(session)[0]]  # noqa: E731
        with self.assertRaises(services.AnswerError):
            services.save_answer(session, "industry", skipped=True)  # required: no "prefer not to say"
        services.save_answer(session, "industry", options=["finance", "law"])
        self.assertIn("property_law", visible())  # Law among the choices
        self.assertNotIn("property_link", visible())
        self.assertNotIn("industry_other", visible())
        services.save_answer(session, "industry", options=["law", "property", "other"])
        self.assertTrue({"property_link", "property_law", "industry_other"} <= set(visible()))
        services.save_answer(session, "industry", options=["tech"])
        self.assertFalse({"property_link", "property_law", "industry_other"} & set(visible()))

    def test_gold_extra_points_use_the_highest_industry_not_the_sum(self):
        one = engine.compute_gold(make_session(industry="finance"))
        many = engine.compute_gold(make_session(industry=["finance", "business_owner", "law", "tech"]))
        self.assertEqual((one.score, many.score), (3, 3))  # three occupations worth 3 each still give 3
        Option.objects.filter(question__key="industry", value="tech").update(gold_points=4)
        self.assertEqual(engine.compute_gold(make_session(industry=["finance", "tech"])).score, 4)

    def test_every_chosen_industry_counts_as_a_vote(self):
        session = make_session(industry=["finance", "law"])
        self.assertEqual(engine.counted_answers(session), ["industry:finance", "industry:law"])

    def test_ice_bucket_replaces_showers_and_old_answers_keep_their_label(self):
        values = list(Option.objects.filter(question__key="facilities", active=True).values_list("value", flat=True))
        self.assertIn("ice_bucket", values)
        self.assertNotIn("showers", values)
        self.assertEqual(Option.objects.get(question__key="facilities", value="ice_bucket").label, "Ice bucket")


class LeadGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_signed_in_visitors_skip_the_gate_and_others_need_an_address_once(self):
        session = make_session(time="evening", facilities="gym", industry="tech")
        self.assertTrue(services.lead_required(session, None))
        with self.assertRaises(services.LeadError):
            services.save_lead(session, "nobody", True)
        with self.assertRaises(services.LeadError) as caught:
            services.save_lead(session, "a@example.com", False)
        self.assertEqual(list(caught.exception.errors), ["consent"])
        services.save_lead(session, "A@Example.com", True)
        self.assertFalse(services.lead_required(session, None))
        self.assertEqual(session.lead_email, "a@example.com")
        member = User.objects.create_user(email="m@example.com", password="x-Strong-pass-1")
        self.assertFalse(services.lead_required(make_session(), member))  # his account is his address

    def test_a_restart_in_the_same_browser_keeps_the_address(self):
        old = make_session()
        services.save_lead(old, "a@example.com", True)
        fresh = services.create_session(previous=old)
        self.assertEqual(fresh.lead_email, "a@example.com")

    def test_erasing_an_address_clears_it_from_sessions_and_history(self):
        session = make_session()
        services.save_lead(session, "a@example.com", True)
        self.assertEqual(services.erase_lead("A@example.com"), 1)
        session.refresh_from_db()
        self.assertEqual((session.lead_email, session.lead_at), ("", None))
        self.assertFalse(JourneySession.history.model.objects.filter(lead_email="a@example.com").exists())

    def test_a_bot_filling_the_hidden_field_stores_nothing(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get("/journey/state/").cookies["csrftoken"].value
        response = client.post("/journey/lead/", json.dumps({"email": "a@example.com", "consent": True, "website": "x"}),
                               content_type="application/json", headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 200)
        session = JourneySession.objects.get()
        self.assertEqual((session.lead_email, session.is_bot), ("", True))


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
        self.post(client, "/journey/answer/", {"question": "time", "options": ["daytime"]}, token)
        self.post(client, "/journey/answer/", {"question": "facilities", "options": ["gym"]}, token)
        self.post(client, "/journey/answer/", {"question": "industry", "options": ["tech", "creative"]}, token)
        self.assertEqual(self.post(client, "/journey/answer/", {"question": "frequency", "options": ["bogus"]}, token).status_code, 400)
        self.post(client, "/journey/step/", {"step": 2}, token)

        resumed = client.get("/journey/state/").json()  # same cookie: same session, same screen, answers shown
        self.assertEqual(resumed["session"]["current_step"], 2)
        freq = next(q for s in resumed["screens"] for q in s["questions"] if q["key"] == "frequency")
        self.assertEqual(freq["answer"]["options"], ["weekly"])
        self.assertEqual(JourneySession.objects.count(), 1)
        session = JourneySession.objects.get()
        self.assertEqual((session.utm_source, session.device_type), ("instagram", "unknown"))

        # The email gate: no suggested membership, price or completion until an address is left.
        self.assertEqual(client.get("/journey/state/").json()["session"]["lead_required"], True)
        blocked = client.get("/journey/result/")
        self.assertEqual((blocked.status_code, blocked.json()["needs_email"]), (403, True))
        self.assertEqual(self.post(client, "/journey/result/", {}, token).status_code, 403)
        session.refresh_from_db()
        self.assertFalse(session.completed)
        bad = self.post(client, "/journey/lead/", {"email": "not an email", "consent": False}, token)
        self.assertEqual((bad.status_code, sorted(bad.json()["errors"])), (400, ["consent", "email"]))
        self.assertEqual(self.post(client, "/journey/lead/", {"email": "Hugo@Example.com", "consent": False}, token).status_code, 400)  # consent is required
        ok = self.post(client, "/journey/lead/", {"email": " Hugo@Example.com ", "consent": True}, token)
        self.assertEqual(ok.status_code, 200)
        session.refresh_from_db()
        self.assertEqual((session.lead_email, session.lead_privacy_version != "", session.lead_at is not None), ("hugo@example.com", True, True))
        self.assertEqual(client.get("/journey/state/").json()["session"]["lead_required"], False)

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


class RequiredAndReopenTests(TestCase):
    """2026-10-23: 'Choose at least one', reopening at screen 1 with the last suggestion kept, and Start again."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_time_and_facilities_need_a_choice_before_moving_on_or_finishing(self):
        session = services.create_session()
        question = next(q for q in services.visible_questions(session)[0] if q.key == "time")
        self.assertEqual(question.min_choices, 1)
        with self.assertRaises(services.AnswerError):
            services.save_answer(session, "time", skipped=True)  # a required question cannot be skipped
        with self.assertRaises(services.AnswerError) as caught:
            services.set_step(session, direction="next")
        self.assertEqual(caught.exception.missing, ["time"])
        with self.assertRaises(services.AnswerError):
            engine.complete(session)  # nothing is computed or stored
        session.refresh_from_db()
        self.assertEqual((session.completed, session.suggested_plan_id), (False, None))
        services.save_answer(session, "time", options=["evening"])
        self.assertEqual(services.set_step(session, direction="next"), 2)
        with self.assertRaises(services.AnswerError) as caught:
            services.set_step(session, direction="next")
        self.assertEqual(caught.exception.missing, ["facilities"])
        services.save_answer(session, "facilities", options=["gym"])
        with self.assertRaises(services.AnswerError) as caught:
            engine.complete(session)  # what he does is required too (multi-select, at least one)
        self.assertEqual(caught.exception.missing, ["industry"])
        services.save_answer(session, "industry", options=["tech", "creative"])
        self.assertTrue(engine.complete(session)["suggested"])
        data = {q["key"]: q for s in services.build_state(session)["screens"] for q in s["questions"]}
        self.assertEqual((data["time"]["min_choices"], data["time"]["skippable"]), (1, False))
        self.assertEqual((data["frequency"]["min_choices"], data["frequency"]["skippable"]), (0, True))

    def test_reopening_resumes_at_screen_one_with_answers_and_the_last_suggestion(self):
        client = Client()
        client.get("/journey/state/")
        session = services.session_from_cookies({"spa99_journey": client.cookies["spa99_journey"].value})
        for key, value in (("time", ["evening"]), ("frequency", ["two_three"]), ("facilities", ["gym"]), ("industry", ["tech"])):
            services.save_answer(session, key, options=value)
        engine.complete(session)
        state = client.get("/journey/state/").json()
        self.assertEqual(state["session"]["resume_step"], 1)
        suggestion = state["last_suggestion"]
        self.assertEqual(suggestion["plan_slug"], "tier-2")
        self.assertEqual((suggestion["plan_name"], suggestion["url"]), (session.suggested_plan.name, "/journey/your-membership/"))
        time = next(q for s in state["screens"] for q in s["questions"] if q["key"] == "time")
        self.assertEqual(time["answer"]["options"], ["evening"])  # ticked
        config = client.get("/journey/").context["journey_config"]
        self.assertEqual(config["lastSuggestion"], suggestion)
        self.assertEqual(config["urls"]["restart"], "/journey/restart/")
        self.assertEqual(Client().get("/journey/").context["journey_config"]["lastSuggestion"], None)

    def test_start_again_gives_a_fresh_journey_and_keeps_the_old_one(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get("/journey/state/").cookies["csrftoken"].value
        old = services.session_from_cookies({"spa99_journey": client.cookies["spa99_journey"].value})
        for key, value in (("time", ["evening"]), ("facilities", ["gym"]), ("industry", ["tech"])):
            services.save_answer(old, key, options=value)
        engine.complete(old)
        self.assertEqual(client.post("/journey/restart/").status_code, 403)  # CSRF protected
        state = client.post("/journey/restart/", headers={"X-CSRFToken": token}).json()
        self.assertEqual((state["session"]["current_step"], state["last_suggestion"]), (1, None))
        self.assertTrue(all(q["answer"] is None for s in state["screens"] for q in s["questions"]))
        self.assertEqual(client.get("/journey/state/").json()["session"]["id"], state["session"]["id"])  # new cookie
        old.refresh_from_db()
        self.assertTrue(old.completed)  # statistics and Gold links on the old one stay
        self.assertEqual(old.answers.count(), 3)


class PeopleCountTests(TestCase):
    """2026-10-23: several journey windows from one browser count as one person started that day."""

    def test_restarting_counts_one_person_not_one_per_session(self):
        from insights import metrics, people
        from insights.metrics import K
        from insights.models import DailyMetric

        seed_all()
        client = Client(HTTP_HOST="localhost", HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1")
        client.get("/journey/state/")
        client.post("/journey/restart/")
        client.post("/journey/restart/")
        value = lambda key: DailyMetric.objects.filter(key=key).values_list("value", flat=True).first() or 0  # noqa: E731
        self.assertEqual((value(K.JOURNEYS_STARTED), value(K.VISITORS)), (3, 1))  # three sessions, one visitor
        self.assertEqual(len({s.person_key for s in JourneySession.objects.all()}), 1)  # one person
        self.assertEqual(people.load().started(None, metrics.day()), 1)
