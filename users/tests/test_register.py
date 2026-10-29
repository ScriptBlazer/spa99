import re
import time
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from gold import services as gold_services
from gold.models import GoldApplication
from journey import engine
from journey import services as journey
from notifications.models import EmailLog
from plans.management.commands.seed_phase1 import seed_all
from plans.models import SiteSettings
from users import services, tokens
from users.forms import SignUpForm
from users.models import InterestRegistration, User

PASSWORD = "correct horse battery staple"


def signup_data(**over):
    data = {
        "first_name": "Hugo", "last_name": "Berkowitz", "email": "Hugo@Example.com", "mobile": "07912 345678",
        "password": PASSWORD, "date_of_birth": "1990-05-01", "men_only_accepted": "on", "privacy_accepted": "on",
        "plan": "tier-2",
    }
    data.update(over)
    return data


def cleaned(**over):
    form = SignUpForm(signup_data(**over))
    assert form.is_valid(), form.errors
    return form.cleaned_data


class SignUpFormTests(TestCase):
    def test_rules_are_the_shared_validators(self):
        today = timezone.localdate()
        under_18 = (today - timedelta(days=17 * 365)).isoformat()
        cases = {
            "date_of_birth": under_18,
            "mobile": "020 7946 0958",  # a landline
            "password": "password1234",  # too common
            "email": "not-an-email",
            "men_only_accepted": "",
            "privacy_accepted": "",
        }
        for field, value in cases.items():
            form = SignUpForm(signup_data(**{field: value}))
            self.assertFalse(form.is_valid(), field)
            self.assertIn(field, form.errors)
        similar = SignUpForm(signup_data(password="hugoberkowitz99"))
        self.assertFalse(similar.is_valid())
        self.assertIn("password", similar.errors)

    def test_valid_data_is_normalised(self):
        data = cleaned()
        self.assertEqual(data["email"], "hugo@example.com")
        self.assertEqual(data["mobile"], "+447912345678")
        self.assertFalse(data["marketing_opt_in"])  # separate, unticked opt-in


class RegisterInterestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_signup_creates_the_account_links_the_journey_and_sends_the_verification_email(self):
        session = journey.create_session()
        journey.save_answer(session, "time", options=["evening"])
        journey.save_answer(session, "frequency", options=["two_three"])
        journey.save_answer(session, "facilities", options=["gym"])
        journey.save_answer(session, "industry", options=["tech"])
        engine.complete(session)

        result = services.register_interest(cleaned(marketing_opt_in="on"), journey_session=session)
        user = result.user
        self.assertTrue(result.created)
        self.assertEqual((user.email, user.mobile, str(user.date_of_birth)), ("hugo@example.com", "+447912345678", "1990-05-01"))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertIsNotNone(user.men_only_accepted_at)
        self.assertEqual(user.privacy_accepted_version, SiteSettings.load().privacy_version)
        self.assertTrue(user.marketing_consent and user.marketing_consent_at)
        self.assertIsNone(user.email_verified_at)

        interest = user.interest
        self.assertEqual((interest.plan.slug, interest.source, interest.journey_session), ("tier-2", "journey", session))
        session.refresh_from_db()
        self.assertEqual(session.user, user)

        self.assertEqual(len(mail.outbox), 1)  # ordinary sign-ups email only the person
        self.assertEqual(mail.outbox[0].to, ["hugo@example.com"])
        self.assertEqual(mail.outbox[0].reply_to, ["from@example.test"])
        self.assertRegex(mail.outbox[0].body, r"http://localhost:8000/verify/[^/\s]+/")
        self.assertEqual(EmailLog.objects.get().template, "verify")

    def test_the_verification_email_goes_through_the_queue(self):
        with mock.patch("users.services.enqueue") as queued:
            user = services.register_interest(cleaned()).user
        queued.assert_called_once_with("users.tasks.send_verification_email", str(user.pk))
        self.assertEqual(len(mail.outbox), 0)  # queued, not sent inline
        self.assertEqual(user.interest.source, InterestRegistration.DIRECT)

    def test_duplicate_email_and_mobile_are_refused(self):
        services.register_interest(cleaned())
        User.objects.filter(email="hugo@example.com").update(created_at=timezone.now() - timedelta(hours=1))
        with self.assertRaises(services.SignUpError) as caught:
            services.register_interest(cleaned(email="HUGO@example.com", mobile="07911 111111"))
        self.assertEqual(set(caught.exception.errors), {"email"})
        with self.assertRaises(services.SignUpError) as caught:
            services.register_interest(cleaned(email="other@example.com", mobile="+44 7912 345678"))
        self.assertEqual(set(caught.exception.errors), {"mobile"})
        self.assertEqual(User.objects.count(), 1)

    def test_a_double_click_is_one_account_and_one_email(self):
        first = services.register_interest(cleaned())
        second = services.register_interest(cleaned())
        self.assertEqual((second.user.pk, second.created), (first.user.pk, False))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_plan_and_closed_stage(self):
        with self.assertRaises(services.SignUpError):
            services.register_interest(cleaned(plan="gold"))  # Gold is applied for, not registered
        SiteSettings.objects.update(register_interest_open=False)
        with self.assertRaises(services.RegistrationClosed):
            services.register_interest(cleaned())

    def test_earlier_gold_applications_with_the_same_email_are_linked(self):
        application, _ = gold_services.submit_application({
            "first_name": "Hugo", "last_name": "B", "email": "hugo@example.com", "mobile": "+447912345678",
            "property_link": "developer",
        })
        user = services.register_interest(cleaned()).user
        application.refresh_from_db()
        self.assertIsNone(application.user)  # registering proves nothing about the address
        services.verify_email(tokens.make_verify_token(user))
        application.refresh_from_db()
        self.assertEqual(application.user, user)

    def test_the_form_view_links_the_cookie_session(self):
        client = Client()
        client.get("/journey/state/")
        session = journey.session_from_cookies({"spa99_journey": client.cookies["spa99_journey"].value})
        response = client.post("/register/", signup_data())
        self.assertRedirects(response, "/register/sent/", fetch_redirect_response=False)
        session.refresh_from_db()
        self.assertEqual(session.user.email, "hugo@example.com")
        bad = client.post("/register/", signup_data(email="new@example.com", date_of_birth="2015-01-01"))
        self.assertEqual(bad.status_code, 400)  # kept on the form with the error
        self.assertEqual(User.objects.count(), 1)

    def test_email_check_answers_yes_or_no_only(self):
        services.register_interest(cleaned())
        client = Client()
        self.assertEqual(client.post("/register/check-email/", {"email": "HUGO@example.com"}).json(), {"registered": True})
        self.assertEqual(client.post("/register/check-email/", {"email": "free@example.com"}).json(), {"registered": False})
        self.assertEqual(client.post("/register/check-email/", {"email": "nonsense"}).json(), {"registered": False})
        self.assertEqual(client.get("/register/check-email/", {"email": "hugo@example.com"}).status_code, 405)  # never in a URL


class VerificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        self.user = services.register_interest(cleaned()).user
        self.token = re.search(r"/verify/([^/\s]+)/", mail.outbox[0].body).group(1)

    def test_verifying_works_once_and_sends_the_welcome_email(self):
        status, user = services.verify_email(self.token)
        self.assertEqual(status, tokens.VERIFIED)
        user.refresh_from_db()
        self.assertIsNotNone(user.email_verified_at)
        welcome = mail.outbox[1]
        self.assertEqual(welcome.subject, "Welcome to Spa 99")
        self.assertIn("Tier 2", welcome.body)
        self.assertEqual(services.verify_email(self.token)[0], tokens.ALREADY)  # single use
        self.assertEqual(len(mail.outbox), 2)  # no second welcome

    def test_replaying_the_link_never_signs_anyone_in(self):
        first, replay = Client(), Client()
        scanner = Client().get(f"/verify/{self.token}/")  # a mail scanner opening the link: only a button, nothing used up
        self.assertContains(scanner, "Confirm my email")
        self.assertFalse(User.objects.get(pk=self.user.pk).email_verified_at)
        self.assertEqual(first.post(f"/verify/{self.token}/").status_code, 302)
        self.assertIn("_auth_user_id", first.session)
        self.assertEqual(replay.get(f"/verify/{self.token}/").status_code, 200)
        self.assertEqual(replay.post(f"/verify/{self.token}/").status_code, 200)
        self.assertNotIn("_auth_user_id", replay.session)

    def test_expired_tampered_and_changed_email_links_are_refused(self):
        with mock.patch("django.core.signing.time.time", return_value=time.time() + 25 * 3600):  # past the 24 hours default
            self.assertEqual(services.verify_email(self.token)[0], tokens.EXPIRED)
        self.assertEqual(services.verify_email(self.token[:-3] + "xyz")[0], tokens.INVALID)
        old_token = tokens.make_verify_token(self.user)
        User.objects.filter(pk=self.user.pk).update(email="changed@example.com")
        self.assertEqual(services.verify_email(old_token)[0], tokens.INVALID)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email_verified_at)

    def test_resend_only_while_unverified(self):
        self.assertTrue(services.resend_verification(self.user))
        self.assertEqual(len(mail.outbox), 2)
        services.verify_email(self.token)
        self.user.refresh_from_db()
        self.assertFalse(services.resend_verification(self.user))


class PasswordResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def setUp(self):
        self.user = services.register_interest(cleaned()).user
        mail.outbox.clear()

    def link(self):
        services.request_password_reset("Hugo@example.com")
        return re.search(r"/reset/([^/\s]+)/([^/\s]+)/", mail.outbox[-1].body).groups()

    def test_unknown_address_sends_nothing(self):
        services.request_password_reset("nobody@example.com")
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_works_once_and_checks_the_new_password(self):
        uid, token = self.link()
        with self.assertRaises(ValidationError):
            services.reset_password(uid, token, "short")
        self.assertIsNotNone(services.reset_password(uid, token, "a brand new passphrase 42"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a brand new passphrase 42"))
        self.assertIsNone(services.reset_password(uid, token, "another passphrase 43"))  # single use

    def test_reset_links_expire_after_an_hour(self):
        uid, token = self.link()
        self.assertIsNotNone(tokens.read_reset_token(uid, token))
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assertIsNone(tokens.read_reset_token(uid, token))
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)


class PublicLoginTests(TestCase):
    def test_public_login_works_for_unverified_people_too(self):
        User.objects.create_user("login@example.com", PASSWORD)
        client = Client()
        self.assertEqual(client.get("/login/").status_code, 200)
        response = client.post("/login/", {"username": "LOGIN@example.com", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", client.session)
        self.assertEqual(client.get("/account/").status_code, 200)

    def test_account_pages_need_a_login(self):
        response = Client().get("/account/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class PersonDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_export_and_delete_cover_interest_journey_gold_and_email_log(self):
        session = journey.create_session("Mozilla/5.0 Safari", referrer="https://example.org/x")
        journey.save_answer(session, "frequency", options=["weekly"])
        user = services.register_interest(cleaned(), journey_session=session).user
        services.verify_email(tokens.make_verify_token(user))
        user.refresh_from_db()
        gold_services.submit_application({
            "first_name": "Hugo", "last_name": "B", "email": "hugo@example.com", "mobile": "+447912345678",
            "property_link": "developer",
        })
        other, _ = gold_services.submit_application({
            "first_name": "Zed", "last_name": "Z", "email": "zed@example.com", "mobile": "+447911111111", "property_link": "none",
        })

        data = services.export_user_data(user)
        self.assertEqual(data["interest"]["plan"], "Tier 2")
        self.assertEqual(data["journey_sessions"][0]["answers"][0]["options"], ["Weekly"])
        self.assertEqual([a["email"] for a in data["gold_applications"]], ["hugo@example.com"])
        self.assertTrue(any(e["template"] == "verify" for e in data["emails"]))
        self.assertIn("men_only_accepted_at", data["profile"])

        result = services.delete_user_data(user)
        self.assertEqual(result["gold_applications"], 1)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(InterestRegistration.objects.exists())
        self.assertEqual(InterestRegistration.history.count(), 0)
        self.assertEqual(list(GoldApplication.objects.values_list("pk", flat=True)), [other.pk])
        self.assertFalse(EmailLog.objects.filter(to__iexact="hugo@example.com").exists())
        # The journey session is kept for the statistics but is no longer about him.
        session.refresh_from_db()
        self.assertIsNone(session.user)
        self.assertEqual(session.referrer, "")
        self.assertEqual(session.answers.count(), 1)
        self.assertEqual(session.history.filter(user__isnull=False).count(), 0)


class AccountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_a_plan_link_for_a_non_interest_plan_is_ignored_not_silently_posted(self):
        response = self.client.get("/register/?plan=single-visit")
        self.assertEqual(response.context["selected_plan"], "")
        self.assertEqual(self.client.get("/register/?plan=tier-3").context["selected_plan"], "tier-3")
        self.assertEqual(services.interest_plan_slug("gold"), "")

    def test_signing_up_never_links_a_journey_owned_by_someone_else(self):
        owner = services.register_interest(cleaned()).user
        theirs = journey.create_session(user=owner)
        newcomer = services.register_interest(cleaned(email="new@example.com", mobile="07912 345679"), journey_session=theirs).user
        theirs.refresh_from_db()
        self.assertEqual(theirs.user_id, owner.pk)
        self.assertIsNone(newcomer.interest.journey_session)
        mine = journey.create_session()
        other = services.register_interest(cleaned(email="third@example.com", mobile="07912 345670"), journey_session=mine).user
        mine.refresh_from_db()
        self.assertEqual((mine.user_id, other.interest.journey_session_id), (other.pk, mine.pk))

    def test_change_password_needs_the_old_one_and_keeps_the_session(self):
        user = services.register_interest(cleaned()).user
        self.assertEqual(Client().get("/account/you/password/").status_code, 302)  # signed in only
        self.client.force_login(user)
        bad = self.client.post("/account/you/password/", {"old_password": "wrong", "new_password1": "a-new-long-password-9", "new_password2": "a-new-long-password-9"})
        self.assertEqual(bad.status_code, 200)
        self.assertTrue(User.objects.get(pk=user.pk).check_password(PASSWORD))
        weak = self.client.post("/account/you/password/", {"old_password": PASSWORD, "new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(weak.status_code, 200)
        ok = self.client.post("/account/you/password/", {"old_password": PASSWORD, "new_password1": "a-new-long-password-9", "new_password2": "a-new-long-password-9"})
        self.assertRedirects(ok, "/account/you/", fetch_redirect_response=False)
        self.assertTrue(User.objects.get(pk=user.pk).check_password("a-new-long-password-9"))
        self.assertEqual(self.client.get("/account/").status_code, 200)  # still signed in
        self.assertContains(self.client.get("/account/you/"), "Change password")


class SignUpNeedsATierTests(TestCase):
    def test_form_refuses_a_sign_up_without_a_tier(self):
        form = SignUpForm(signup_data(plan=""))
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["plan"], ["Choose a membership to continue."])

    def test_register_post_without_a_plan_shows_the_plan_error(self):
        seed_all()
        response = self.client.post("/register/", signup_data(plan=""))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Choose a membership to continue.", status_code=400)
        self.assertFalse(User.objects.filter(email="hugo@example.com").exists())


class NoPaymentAndDiscountLineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def _member_client(self):
        user = User.objects.create_user(email="m@example.com", password=PASSWORD, first_name="Moe", email_verified_at=timezone.now())
        from plans.models import Plan
        InterestRegistration.objects.create(user=user, plan=Plan.objects.get(slug="tier-2"))
        client = Client()
        client.force_login(user)
        return client, user

    def test_register_says_registering_is_free_and_shows_no_whatsapp_line(self):
        SiteSettings.objects.update(whatsapp_number="447000000000")
        html = Client().get("/register/").content.decode()
        self.assertIn("No payment is taken now. When we open, you&rsquo;ll have 2 weeks to set up your membership.", html)
        self.assertIn('href="/whatsapp/?from=register&amp;msg=rates"', html)
        self.assertIn("<span>WhatsApp us</span>", html)  # a real button now (the old "better rate" line is not on Register)
        self.assertIn("btn btn-secondary btn-whatsapp", html)
        self.assertNotIn("better rate", html)

    def test_whatsapp_line_is_on_the_signed_in_membership_page(self):
        url = "https://wa.me/447000000000"
        SiteSettings.objects.update(whatsapp_number="447000000000")
        client, _ = self._member_client()
        html = client.get("/account/membership/").content.decode()
        self.assertIn("Looking for a better rate?", html)
        self.assertIn('class="btn btn-secondary btn-whatsapp" href="/whatsapp/?from=membership&amp;msg=rates" target="_blank" rel="noopener noreferrer"', html)  # the counted short link, not the raw URL
        self.assertNotIn(url, html)
        self.assertNotIn("Barry", html)
        SiteSettings.objects.update(whatsapp_number="")
        self.assertNotContains(client.get("/account/membership/"), "better rate")
        self.assertNotContains(client.get("/account/membership/"), "btn-whatsapp")

    def test_welcome_email_carries_the_whatsapp_line_only_when_set(self):
        from users.tasks import send_welcome_email
        _, user = self._member_client()
        SiteSettings.objects.update(whatsapp_number="447000000000")
        send_welcome_email(user.pk)
        self.assertIn("/whatsapp/?from=email", mail.outbox[-1].body)
        SiteSettings.objects.update(whatsapp_number="")
        send_welcome_email(user.pk)
        self.assertNotIn("WhatsApp", mail.outbox[-1].body)


class RegisterPrefillTests(TestCase):
    """2026-10-26: the email given at the journey gate pre-fills Register (still editable)."""

    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_journey_email_prefills_the_register_form(self):
        from journey.models import JourneySession

        session = JourneySession.objects.create(lead_email="daniel@example.com", lead_at=timezone.now())
        self.client.cookies[journey.COOKIE_NAME] = session.key
        html = self.client.get("/register/").content.decode()
        self.assertIn('value="daniel@example.com"', html)

    def test_no_journey_email_leaves_it_empty(self):
        self.assertNotIn("daniel@example.com", self.client.get("/register/").content.decode())
