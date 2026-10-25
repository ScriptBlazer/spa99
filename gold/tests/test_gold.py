import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings

from gold import rating, services
from gold import tasks as gold_tasks
from gold.forms import GoldApplicationForm
from gold.models import GoldApplication, GoldChoice, GoldRule, GoldSignalSource
from journey import engine
from journey import services as journey
from notifications.models import EmailLog
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings
from plans.tests.helpers import set_recipients

User = get_user_model()


def application_data(**over):
    data = {
        "first_name": "Dan", "last_name": "Cohen", "email": "dan@example.com", "mobile": "+447912345678",
        "industry": "property", "property_link": "owner_investor", "size_range": "50_199", "location": "north_london", "company": "Acme Estates",
        "role": "Director", "bml_relationship": "yes", "referred_by": "Barry", "note": "", "marketing_opt_in": False,
    }
    data.update(over)
    return data


class RatingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_thresholds(self):
        cases = [
            ({}, "low"),
            ({"property_link": "none"}, "low"),
            ({"property_link": "owner_investor"}, "medium"),
            ({"property_link": "owner_investor", "size": "10_49"}, "high"),
            ({"property_link": "firm", "where": "north_london", "bml": "yes"}, "high"),
            ({"property_link": "agent"}, "medium"),
            ({"property_link": "none", "bml": "yes", "referred": "yes"}, "medium"),
        ]
        for signals, level in cases:
            self.assertEqual(rating.rate_potential(signals).level, level, signals)

    def test_reasons_and_editable_weights(self):
        result = rating.rate_potential({"property_link": "owner_investor", "size": "50_199", "bml": "yes"})
        self.assertEqual(result.score, 10)
        self.assertEqual(result.reasons, ["Owner or investor (+5)", "50 to 199 properties (+2)", "Works with BML (+3)"])
        GoldRule.objects.filter(group="bml").update(points=0)
        self.assertEqual(rating.rate_potential({"property_link": "owner_investor", "bml": "yes"}).score, 5)


class SubmitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        set_recipients()

    def journey_session(self):
        session = journey.create_session()
        journey.save_answer(session, "time", options=["evening", "late_night"])
        journey.save_answer(session, "frequency", options=["two_three"])
        journey.save_answer(session, "facilities", options=["gym", "cold_plunge"])
        journey.save_answer(session, "company", options=["sometimes"])
        journey.save_answer(session, "heard_via", options=["bml"])
        engine.complete(session)
        return session

    def test_submit_creates_no_account_and_emails_barry_with_three_sections(self):
        session = self.journey_session()
        application, created = services.submit_application(application_data(), session=session)
        self.assertTrue(created)
        self.assertEqual(User.objects.filter(is_staff=False).count(), 0)  # applying never creates an account (the approver is a team account)
        self.assertEqual((application.potential_level, application.potential_score), ("high", 12))
        self.assertEqual(application.journey_session, session)
        self.assertEqual(session.gold_applications.count(), 1)

        barry, thanks = mail.outbox
        self.assertEqual(barry.to, ["approver@example.test"])
        self.assertEqual(barry.cc, ["cc@example.test"])
        self.assertEqual(barry.reply_to, ["hello@example.test"])
        self.assertEqual(barry.subject, "Gold Card application: Dan Cohen (High potential)")
        body = barry.body
        positions = [body.index(h) for h in ("1. PERSONAL DETAILS", "2. ABOUT HIM", "3. WHAT THE SITE COLLECTED")]
        self.assertEqual(positions, sorted(positions))
        for expected in ("dan@example.com", "What he does: Property", "Owner / investor", "Potential: High (12 points)", "Owner or investor (+5)",
                         "Evening (6 to 10pm), Late night (10pm to 3am)", "Cold plunge, Gym", "Sometimes with someone",
                         "Suggested membership: Tier 3", application.reference):
            self.assertIn(expected, body)
        html = barry.alternatives[0][0]
        approve, view = (f"http://office.localhost:8000/gold/{application.pk}/approve/confirm/", f"http://office.localhost:8000/gold/{application.pk}/")
        for text in (body, html):  # both buttons point at the Office host and carry only the application id
            self.assertNotIn("Open in Control", text)
            self.assertIn(approve, text)
            self.assertIn(view, text)
        self.assertIn("Approve", html)
        self.assertIn("View application", html)
        self.assertEqual(thanks.to, ["dan@example.com"])
        self.assertIn("We have your Gold Card application", thanks.body)

        application.refresh_from_db()
        self.assertIsNotNone(application.email_sent_at)
        self.assertEqual(EmailLog.objects.filter(status="sent").count(), 2)

    def test_recipients_come_from_settings_and_a_double_click_sends_nothing_new(self):
        User.objects.filter(email="approver@example.test").update(is_active=False)
        set_recipients("a@bml.example, b@bml.example", "")
        first, _ = services.submit_application(application_data())
        again, created = services.submit_application(application_data())
        self.assertEqual((again.pk, created), (first.pk, False))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["a@bml.example", "b@bml.example"])
        self.assertEqual(mail.outbox[0].cc, [])

    def test_a_double_click_is_taken_one_after_the_other_and_makes_one_application(self):
        """The two requests of a double click must queue on the write lock; the second then sees the first as a duplicate."""
        order = []
        real_lock, real_check = services._serialise_submissions, services._recent_duplicate
        with mock.patch.object(services, "_serialise_submissions", lambda site: (order.append("lock"), real_lock(site))), \
                mock.patch.object(services, "_recent_duplicate", lambda email: (order.append("check"), real_check(email))[1]):
            first, created_first = services.submit_application(application_data())
            again, created_again = services.submit_application(application_data(email=" DAN@example.com "))
        self.assertEqual(order, ["lock", "check", "lock", "check"])  # the lock is always taken before the duplicate check
        self.assertEqual((created_first, created_again, again.pk), (True, False, first.pk))
        self.assertEqual(GoldApplication.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)  # one email to the approver, one thank-you

    def test_no_approver_configured_sends_nothing_to_anyone_but_still_thanks_the_applicant(self):
        User.objects.filter(email="approver@example.test").update(is_active=False)  # nobody left to approve
        gold_tasks._warned.clear()  # the warning is logged once per process; other tests may have used it up
        with self.assertLogs("spa99.email", "WARNING"):
            application, _ = services.submit_application(application_data())
        self.assertEqual([m.to for m in mail.outbox], [["dan@example.com"]])
        application.refresh_from_db()
        self.assertIsNone(application.email_sent_at)
        self.assertIn("System > Approval", application.email_error)

    def test_repeat_applications_are_linked_and_flagged(self):
        first, _ = services.submit_application(application_data())
        GoldApplication.objects.filter(pk=first.pk).update(created_at=first.created_at.replace(year=2026, month=1))
        second, created = services.submit_application(application_data(email="DAN@example.com", note="Second try"))
        self.assertTrue(created)
        self.assertEqual(second.repeat_of, first)
        self.assertTrue(second.is_repeat)
        barry = mail.outbox[2]  # first application sent two emails
        self.assertTrue(barry.subject.endswith("- repeat application"))
        self.assertIn(f"REPEAT APPLICATION: this person has applied before ({first.reference})", barry.body)

    def test_a_failed_email_keeps_the_application_and_can_be_resent(self):
        with mock.patch("notifications.services.EmailMultiAlternatives.send", side_effect=OSError("mail server down")):
            application, _ = services.submit_application(application_data())
        application.refresh_from_db()
        self.assertIsNone(application.email_sent_at)
        self.assertIn("mail server down", application.email_error)
        self.assertEqual(EmailLog.objects.filter(status="failed").count(), 2)  # Barry and the applicant
        services.resend_approver_email(application)
        application.refresh_from_db()
        self.assertIsNotNone(application.email_sent_at)
        self.assertEqual(application.email_error, "")
        self.assertEqual(len(mail.outbox), 1)  # only Barry's email goes again, not the thank-you

    def test_registering_later_with_the_same_email_links_the_application(self):
        application, _ = services.submit_application(application_data())
        user = User.objects.create_user("dan@example.com", "correct horse battery staple")
        services.link_user_applications(user)
        application.refresh_from_db()
        self.assertEqual(application.user, user)

    def test_closed_stage_refuses(self):
        SiteSettings.objects.update(register_interest_open=False)
        with self.assertRaises(services.ApplicationsClosed):
            services.submit_application(application_data())


class EndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def post(self, client, data):
        token = client.get("/gold/options/").cookies["csrftoken"].value
        return client.post("/gold/apply/", json.dumps(data), content_type="application/json", headers={"X-CSRFToken": token})

    def test_apply_validates_then_saves_without_an_account(self):
        client = Client(enforce_csrf_checks=True)
        payload = application_data(privacy_accepted=True, email="Dan@Example.com")
        bad = self.post(client, {**payload, "mobile": "12345", "privacy_accepted": False})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(bad.json()["errors"]), {"mobile", "privacy_accepted"})
        self.assertEqual(GoldApplication.objects.count(), 0)

        good = self.post(client, payload)
        self.assertEqual(good.status_code, 201)
        self.assertTrue(good.json()["reference"].startswith("GC-"))
        application = GoldApplication.objects.get()
        self.assertEqual(application.email, "dan@example.com")
        self.assertEqual(User.objects.count(), 0)

    def test_honeypot_saves_nothing(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post(client, {**application_data(privacy_accepted=True), "website": "spam"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(GoldApplication.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_options_prefills_from_the_journey_so_nothing_is_asked_twice(self):
        client = Client()
        client.get("/journey/state/")
        key = client.cookies["spa99_journey"].value
        session = journey.session_from_cookies({"spa99_journey": key})
        journey.save_answer(session, "industry", options=["property"])
        journey.save_answer(session, "property_link", options=["developer"])
        journey.save_answer(session, "property_size", options=["200_plus"])
        data = client.get("/gold/options/").json()
        self.assertEqual(data["prefill"], {"industry": "property", "property_link": "developer", "size_range": "200_plus"})
        self.assertIn({"value": "none", "label": "None of these"}, data["property_link"])


LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "gold-rate-limit"}}


class EditableQuestionsTests(TestCase):
    """The answer choices, the journey link and the email wording are rows, not code."""

    @classmethod
    def setUpTestData(cls):
        seed_all()
        set_recipients()

    def test_choices_come_from_rows_and_retired_ones_are_refused_but_still_readable(self):
        GoldChoice.objects.filter(group="property_link", value="agent").update(active=False)
        GoldChoice.objects.filter(group="where", value="north_london").update(label="North London (N postcodes)")
        form = GoldApplicationForm({**application_data(property_link="agent"), "privacy_accepted": True})
        self.assertIn("property_link", form.errors)
        self.assertNotIn({"value": "agent", "label": "Agent / broker"}, Client().get("/gold/options/").json()["property_link"])
        application, _ = services.submit_application(application_data(property_link="owner_investor"))
        GoldApplication.objects.filter(pk=application.pk).update(property_link="agent")  # an old answer to a retired choice
        rows = dict(services.application_sections(GoldApplication.objects.get(pk=application.pk))[1]["rows"])
        self.assertEqual(rows["Link to property"], "Agent / broker")
        self.assertEqual(rows["Where"], "North London (N postcodes)")

    def test_which_journey_answers_feed_gold_is_data(self):
        session = journey.create_session()
        journey.save_answer(session, "industry", options=["law"])
        journey.save_answer(session, "property_law", options=["yes"])
        self.assertEqual(engine.gold_signals(session)[0], {"property_link": "property_lawyer"})
        GoldSignalSource.objects.filter(question_key="property_law").update(sets_value="agent")
        self.assertEqual(engine.gold_signals(session)[0], {"property_link": "agent"})
        GoldSignalSource.objects.filter(question_key="property_law").update(active=False)
        self.assertEqual(engine.gold_signals(session)[0], {})

    def test_email_subjects_and_dates_use_rows_and_the_uk_format(self):
        from notifications.models import NotificationTemplate

        NotificationTemplate.objects.filter(key="gold_ack").update(subject="Thanks from Spa 99")
        application, _ = services.submit_application(application_data())
        self.assertEqual(mail.outbox[1].subject, "Thanks from Spa 99")
        applied = dict(services.application_sections(application)[0]["rows"])["Date applied"]
        self.assertRegex(applied, r"^\d{2}/\d{2}/\d{4}, \d{2}:\d{2}$")

    def test_the_barry_email_is_linked_to_the_applicant(self):
        services.submit_application(application_data())
        self.assertEqual(EmailLog.objects.get(template="gold_approver").subject_email, "dan@example.com")
        self.assertEqual(EmailLog.objects.get(template="gold_ack").subject_email, "dan@example.com")


@override_settings(CACHES=LOCMEM)
class RateLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_mistakes_do_not_use_up_the_limit_but_ten_valid_applications_do(self):
        from django.core.cache import cache

        cache.clear()
        client = Client(enforce_csrf_checks=True)
        token = client.get("/gold/options/").cookies["csrftoken"].value

        def send(data):
            return client.post("/gold/apply/", json.dumps(data), content_type="application/json", headers={"X-CSRFToken": token})

        for _ in range(15):  # fifteen mistakes
            self.assertEqual(send(application_data(mobile="1", privacy_accepted=True)).status_code, 400)
        for number in range(10):  # still ten valid ones allowed
            self.assertEqual(send(application_data(email=f"p{number}@example.com", privacy_accepted=True)).status_code, 201)
        self.assertEqual(send(application_data(email="p11@example.com", privacy_accepted=True)).status_code, 429)
        cache.clear()


class IndustryTests(TestCase):
    """2026-10-23: 'What do you do?' first; the property questions are for Property people only."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def form(self, **over):
        data = {**application_data(), "privacy_accepted": True, **over}
        form = GoldApplicationForm(data)
        form.is_valid()
        return form

    def test_property_questions_are_asked_only_of_property_people(self):
        self.assertIn("industry", self.form(industry="").errors)
        self.assertIn("industry", self.form(industry="nonsense").errors)
        self.assertIn("property_link", self.form(property_link="").errors)  # Property: the link is needed
        finance = self.form(industry="finance", industry_other="ignored")  # the property answers are dropped
        self.assertTrue(finance.is_valid(), finance.errors)
        self.assertEqual((finance.cleaned_data["property_link"], finance.cleaned_data["size_range"]), ("", ""))
        self.assertEqual(finance.cleaned_data["industry_other"], "")
        no_link = self.form(industry="creative", property_link="")  # nobody is told "this isn't for me"
        self.assertTrue(no_link.is_valid(), no_link.errors)
        other = self.form(industry="other", industry_other="  Sculptor ")
        self.assertEqual(other.cleaned_data["industry_other"], "Sculptor")

    def test_a_non_property_applicant_gets_no_property_points_and_barry_sees_what_he_does(self):
        data = self.form(industry="finance").cleaned_data
        application, _ = services.submit_application(data)
        # Only the non-property points count (North London 1, BML 3, referred 1): no property points.
        self.assertEqual((application.industry, application.property_link, application.potential_score), ("finance", "", 5))
        rows = dict(services.application_sections(application)[1]["rows"])
        self.assertEqual(rows["What he does"], "Finance")
        self.assertNotIn("Link to property", rows)
        self.assertEqual(services.application_sections(application)[1]["title"], "About him")
        mail.outbox.clear()
        property_app, _ = services.submit_application(self.form(industry="property", email="p@example.com").cleaned_data)
        self.assertEqual((property_app.potential_level, property_app.potential_score), ("high", 12))  # weights unchanged
        self.assertIn("Link to property", dict(services.application_sections(property_app)[1]["rows"]))

    def test_a_property_lawyer_from_the_journey_still_counts(self):
        session = journey.create_session()
        journey.save_answer(session, "industry", options=["law"])
        journey.save_answer(session, "property_law", options=["yes"])
        data = self.form(industry="law").cleaned_data
        application, _ = services.submit_application(data, session=session)
        self.assertEqual(application.property_link, "property_lawyer")

    def test_options_returns_the_question_the_condition_and_the_prefill(self):
        client = Client()
        client.get("/journey/state/")
        session = journey.session_from_cookies({"spa99_journey": client.cookies["spa99_journey"].value})
        journey.save_answer(session, "industry", options=["finance"])
        data = client.get("/gold/options/").json()
        self.assertEqual(data["industry"]["question"], "What do you do?")
        self.assertEqual([o["value"] for o in data["industry"]["options"]][:2], ["property", "finance"])
        self.assertEqual(data["industry"]["other_value"], "other")
        self.assertEqual(data["property_when"], {"question": "industry", "any_of": ["property"]})
        self.assertEqual(data["prefill"], {"industry": "finance"})  # no property prefill for a non-property person
