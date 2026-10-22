import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase

from gold import rating, services
from gold.models import GoldApplication, GoldRule
from journey import engine
from journey import services as journey
from notifications.models import EmailLog
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings

User = get_user_model()


def application_data(**over):
    data = {
        "first_name": "Dan", "last_name": "Cohen", "email": "dan@example.com", "mobile": "+447912345678",
        "property_link": "owner_investor", "size_range": "50_199", "location": "north_london", "company": "Acme Estates",
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

    def journey_session(self):
        session = journey.create_session()
        journey.save_answer(session, "time", options=["evening", "late_night"])
        journey.save_answer(session, "frequency", options=["two_three"])
        journey.save_answer(session, "facilities", options=["gym", "cold_plunge"])
        journey.save_answer(session, "company", options=["often"])
        journey.save_answer(session, "heard_via", options=["bml"])
        engine.complete(session)
        return session

    def test_submit_creates_no_account_and_emails_barry_with_three_sections(self):
        session = self.journey_session()
        application, created = services.submit_application(application_data(), session=session)
        self.assertTrue(created)
        self.assertEqual(User.objects.count(), 0)  # applying never creates an account
        self.assertEqual((application.potential_level, application.potential_score), ("high", 12))
        self.assertEqual(application.journey_session, session)
        self.assertEqual(session.gold_applications.count(), 1)

        barry, thanks = mail.outbox
        self.assertEqual(barry.to, ["barry@bmlgroup.co.uk"])
        self.assertEqual(barry.cc, ["moishe.berkowitz@bmlgroup.co.uk"])
        self.assertEqual(barry.reply_to, ["hello@spa99.uk"])
        self.assertEqual(barry.subject, "Gold Card application: Dan Cohen (High potential)")
        body = barry.body
        positions = [body.index(h) for h in ("1. PERSONAL DETAILS", "2. PROPERTY PROFILE", "3. WHAT THE SITE COLLECTED")]
        self.assertEqual(positions, sorted(positions))
        for expected in ("dan@example.com", "Owner / investor", "Potential: High (12 points)", "Owner or investor (+5)",
                         "Evening (6-10pm), Late night (10pm-3am)", "Cold plunge, Gym", "Often with someone",
                         "Suggested membership: Tier 3", f"/gold/{application.pk}/", "Open in Control", application.reference):
            self.assertIn(expected, body)
        html = barry.alternatives[0][0]
        self.assertIn("Open in Control", html)
        self.assertEqual(thanks.to, ["dan@example.com"])
        self.assertIn("We have your Gold Card application", thanks.body)

        application.refresh_from_db()
        self.assertIsNotNone(application.email_sent_at)
        self.assertEqual(EmailLog.objects.filter(status="sent").count(), 2)

    def test_recipients_come_from_settings_and_a_double_click_sends_nothing_new(self):
        SiteSettings.objects.update(gold_alert_to="a@bml.example, b@bml.example", gold_alert_cc="")
        first, _ = services.submit_application(application_data())
        again, created = services.submit_application(application_data())
        self.assertEqual((again.pk, created), (first.pk, False))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["a@bml.example", "b@bml.example"])
        self.assertEqual(mail.outbox[0].cc, [])

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
        services.resend_barry_email(application)
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
        self.assertEqual(data["prefill"], {"property_link": "developer", "size_range": "200_plus"})
        self.assertIn({"value": "none", "label": "None of these"}, data["property_link"])
