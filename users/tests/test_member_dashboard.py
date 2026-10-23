from django.test import TestCase
from django.utils import timezone

from journey.models import JourneySession
from plans.models import Plan, SiteSettings
from plans.management.commands.seed_phase1 import seed_all
from users.models import InterestRegistration, User

PASSWORD = "a-long-password-1"
SCREENS = {"account": "home", "account_book": "book", "account_membership": "membership", "account_you": "you"}


def make_user(email="m@example.com", plan=None, verified=True, **extra):
    user = User.objects.create_user(email, PASSWORD, first_name="Daniel", email_verified_at=timezone.now() if verified else None, **extra)
    if plan is not None:
        InterestRegistration.objects.create(user=user, plan=plan)
    return user


def plan(slug):
    return Plan.objects.get(slug=slug)


class MemberScreenTests(TestCase):
    def setUp(self):
        seed_all()

    def test_every_screen_needs_login_and_renders_with_key_context(self):
        user = make_user(plan=plan("tier-2"))
        for name in SCREENS:
            url = {"account": "/account/", "account_book": "/account/book/", "account_membership": "/account/membership/", "account_you": "/account/you/"}[name]
            self.assertEqual(self.client.get(url).status_code, 302, url)
        self.assertEqual(self.client.get("/account/you/password/").status_code, 302)
        self.client.force_login(user)
        home = self.client.get("/account/")
        self.assertEqual((home.status_code, home.context["status"], home.context["status_name"]), (200, "registered", plan("tier-2").name))
        self.assertEqual(home.context["account_id"], user.public_id_display)
        book = self.client.get("/account/book/")
        self.assertEqual(book.status_code, 200)
        self.assertEqual(len(book.context["booking_lines"]), 1)  # only their plan's line
        self.assertTrue(book.context["hours"] and book.context["stay_pills"])
        membership = self.client.get("/account/membership/")
        self.assertEqual(membership.context["current_plan"]["slug"], "tier-2")
        self.assertTrue(all(t["price_inc"] and t["price_whole"] for t in membership.context["plan_tiles"]))
        self.assertEqual(self.client.get("/account/you/").context["marketing_consent"], False)
        self.assertEqual(self.client.get("/account/you/password/").status_code, 200)

    def test_gold_and_no_plan_statuses(self):
        self.client.force_login(make_user(plan=plan("gold")))
        context = self.client.get("/account/membership/").context
        self.assertTrue(context["is_gold"])
        self.assertEqual(context["status"], "gold")
        self.client.force_login(make_user("n@example.com", verified=False))
        home = self.client.get("/account/")
        self.assertEqual(home.context["status"], "none")
        self.assertFalse(home.context["verified"])
        self.assertContains(home, "data-verify-banner")
        self.assertGreater(len(self.client.get("/account/book/").context["booking_lines"]), 1)  # no plan: every line

    def test_suggestion_comes_from_the_latest_finished_journey(self):
        user = make_user(plan=plan("tier-1"))
        JourneySession.objects.create(user=user, completed=True, completed_at=timezone.now(), suggested_plan=plan("tier-3"))
        JourneySession.objects.create(user=user, completed=False, suggested_plan=plan("tier-2"))
        self.client.force_login(user)
        context = self.client.get("/account/membership/").context
        self.assertEqual((context["suggested_plan"]["slug"], context["suggestion_differs"]), ("tier-3", True))

    def test_booking_reassurance_follows_the_flag(self):
        self.client.force_login(make_user(plan=plan("tier-2")))
        off = self.client.get("/account/book/").content.decode()
        self.assertIn("Booking opens in January 2027.", off)
        self.assertNotIn("We'll write to", off)
        site = SiteSettings.load()
        site.notify_booking_open = True
        site.save()
        self.assertIn("We&#x27;ll write to m@example.com when booking opens.", self.client.get("/account/book/").content.decode().replace("'", "&#x27;"))

    def test_login_lands_on_account_and_a_safe_next_wins(self):
        make_user()
        response = self.client.post("/login/", {"username": "m@example.com", "password": PASSWORD})
        self.assertRedirects(response, "/account/", fetch_redirect_response=False)
        self.client.logout()
        response = self.client.post("/login/?next=/account/book/", {"username": "m@example.com", "password": PASSWORD})
        self.assertRedirects(response, "/account/book/", fetch_redirect_response=False)
        self.client.logout()
        response = self.client.post("/login/?next=https://evil.example/", {"username": "m@example.com", "password": PASSWORD})
        self.assertRedirects(response, "/account/", fetch_redirect_response=False)

    def test_old_password_address_redirects(self):
        self.assertRedirects(self.client.get("/account/password/"), "/account/you/password/", status_code=307, fetch_redirect_response=False)

    def test_interest_change_returns_to_membership(self):
        self.client.force_login(make_user(plan=plan("tier-1")))
        self.assertRedirects(self.client.post("/account/interest/", {"plan": "tier-3"}), "/account/membership/", fetch_redirect_response=False)
        self.assertEqual(InterestRegistration.objects.get().plan.slug, "tier-3")


class ConsentTests(TestCase):
    def test_marketing_consent_on_off_is_logged_and_needs_login(self):
        self.assertEqual(self.client.post("/account/emails/", {"marketing": "1"}).status_code, 302)
        user = make_user()
        self.client.force_login(user)
        self.assertRedirects(self.client.post("/account/emails/", {"marketing": "1"}), "/account/you/", fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.marketing_consent and user.marketing_consent_at)
        first = user.history.count()
        self.client.post("/account/emails/", {"marketing": "1"})  # no change: no new history row
        self.assertEqual(user.history.count(), first)
        response = self.client.post("/account/emails/", {}, headers={"accept": "application/json"})
        self.assertEqual(response.json(), {"saved": True, "marketing": False})
        user.refresh_from_db()
        self.assertFalse(user.marketing_consent)
        self.assertEqual(user.history.count(), first + 1)


class WebsiteMenuTests(TestCase):
    def setUp(self):
        seed_all()

    def test_header_and_footer_show_my_spa_99_only_when_signed_in_and_no_book_link(self):
        html = self.client.get("/").content.decode()
        self.assertIn(">Sign in<", html)
        self.assertNotIn("My Spa 99</a>", html)
        self.assertNotIn('href="/book/"', html)
        self.client.force_login(make_user())
        html = self.client.get("/").content.decode()
        self.assertIn('href="/account/">My Spa 99</a>', html)
        self.assertNotIn(">Sign in<", html)
        self.assertNotIn('href="/book/"', html)

    def test_book_redirects_members_and_teases_visitors(self):
        teaser = self.client.get("/book/")
        self.assertEqual(teaser.status_code, 200)
        self.assertContains(teaser, "/login/?next=/account/book/")
        self.client.force_login(make_user())
        self.assertRedirects(self.client.get("/book/"), "/account/book/", fetch_redirect_response=False)

    def test_sitemap_excludes_book(self):
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("/book/", body)
        self.assertIn("/memberships/", body)


class PasswordScreenShellTests(TestCase):
    def test_confirmed_member_sees_no_verify_banner_on_password_screen(self):
        from django.utils import timezone
        user = User.objects.create_user(email="pw.shell@example.test", password="Correct-horse-9")
        user.email_verified_at = timezone.now()
        user.save()
        self.client.force_login(user)
        response = self.client.get("/account/you/password/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-verify-banner")
