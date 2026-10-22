"""The website pages render with seeded data, point at real static files and wire the shared scripts."""
import re

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.utils import timezone

from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan

PUBLIC_PAGES = [
    "/", "/the-spa/", "/memberships/", "/gold-card/", "/gold-card/apply/", "/gold-card/apply/property/", "/book/", "/visit/",
    "/privacy/", "/terms/", "/journey/", "/journey/your-time/", "/journey/what-draws-you/", "/journey/company/",
    "/journey/about-you/", "/journey/your-membership/", "/register/", "/login/", "/forgot-password/", "/robots.txt", "/sitemap.xml",
]


class PageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def test_every_public_page_renders(self):
        for path in PUBLIC_PAGES:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_unknown_journey_screens_are_404(self):
        self.assertEqual(self.client.get("/journey/nope/").status_code, 404)
        self.assertEqual(self.client.get("/gold-card/apply/nope/").status_code, 404)
        self.assertEqual(self.client.get("/journey/screen-5/").status_code, 200)  # the screens are data and can grow

    def test_static_files_in_pages_exist(self):
        """Every /static/ file a page asks for is really there (the manifest storage would fail on a missing one)."""
        missing = set()
        for path in PUBLIC_PAGES[:-2]:
            html = self.client.get(path).content.decode()
            for url in re.findall(r'(?:src|href|srcset)="(/static/[^"\s,#]+)', html):
                if not finders.find(url.removeprefix("/static/")):
                    missing.add(url)
        self.assertEqual(missing, set())

    def test_stylesheet_and_modules_reference_real_files(self):
        """CSS url() and @import and JS imports resolve (they are hashed by the manifest storage)."""
        base = finders.find("common/css/app.css")
        from pathlib import Path

        css_dir = Path(base).parent
        for css in css_dir.glob("*.css"):
            for ref in re.findall(r'(?:url\(|@import )["\']?([^"\')\s;]+)', css.read_text()):
                if ref.startswith(("data:", "#", "http")):
                    continue
                self.assertTrue((css_dir / ref).resolve().exists(), f"{css.name} refers to missing {ref}")
        js_dir = Path(finders.find("common/js/app.js")).parent
        for js in js_dir.glob("*.js"):
            for ref in re.findall(r"from '(\./[^']+)'|import '(\./[^']+)'", js.read_text()):
                name = ref[0] or ref[1]
                self.assertTrue((js_dir / name).exists(), f"{js.name} imports missing {name}")

    def test_home_shows_the_journey_entry_and_prices_from_plans(self):
        html = self.client.get("/").content.decode()
        self.assertIn("Beyond Luxury.", html)
        self.assertIn('data-entry-option="evening"', html)
        self.assertIn("Early morning", html)
        self.assertIn("&pound;399", html)
        self.assertIn("&pound;478.80 inc VAT", html)

    def test_home_whats_inside_uses_data_and_hides_the_capacity_line_until_filled(self):
        from content.models import Section

        html = self.client.get("/").content.decode()
        self.assertIn("5am to 3am", html)
        self.assertIn(">22<", html)  # hours a day from the open periods
        for name in ["Dry sauna", "Kitchenette"]:
            self.assertIn(name, html)
        self.assertIn('href="/the-spa/#showers"', html)
        self.assertNotIn("guests at most", html)
        Section.objects.filter(page__key="home", key="facts_capacity_label").update(body="guests at most, at any time")
        html = self.client.get("/").content.decode()
        self.assertIn("guests at most, at any time", html)
        self.assertIn(">25<", html)

    def test_home_preloads_the_arrival_render_and_runs_no_smooth_scroll(self):
        html = self.client.get("/").content.decode()
        self.assertRegex(html, r'rel="preload"[^>]*fetchpriority="high"[^>]*arrival-')
        self.assertIn('data-smooth="off"', html)

    def test_memberships_show_ex_and_inc_vat_and_hide_hidden_plans(self):
        html = self.client.get("/memberships/").content.decode()
        for needle in ["Tier 1", "Tier 2", "Tier 3", "Single visit", "Recommended", "&pound;299", "&pound;358.80 inc VAT", "Prices exclude VAT at 20%"]:
            self.assertIn(needle, html)
        Plan.objects.filter(slug="tier-3").update(visible=False)
        self.assertNotIn("Tier 3", self.client.get("/memberships/").content.decode())

    def test_spa_page_lists_every_facility_with_a_finished_image_or_placeholder(self):
        html = self.client.get("/the-spa/").content.decode()
        for name in ["Dry sauna", "Wet sauna", "Cold plunge", "Showers", "Relaxing zone", "Massage room", "Gym", "Kitchenette"]:
            self.assertIn(name, html)
        self.assertIn("photo-placeholder", html)  # the new renders do not exist yet
        self.assertNotIn("<img src=\"\"", html)

    def test_gold_page_perks_come_from_the_gold_plan(self):
        html = self.client.get("/gold-card/").content.decode()
        self.assertIn("Unlimited visits", html)
        self.assertIn("Bring 2 guests a month", html)
        self.assertIn("BML members&#x27; events", html)

    def test_book_page_is_a_placeholder_without_fake_actions(self):
        html = self.client.get("/book/").content.decode()
        self.assertIn("Booking opens soon.", html)
        self.assertIn("January 2027", html)
        self.assertIn("Tier 1 books a day ahead.", html)
        self.assertNotIn("<form", html)

    def test_journey_page_loads_its_module_and_uses_the_state_endpoint(self):
        response = self.client.get("/journey/")
        html = response.content.decode()
        self.assertIn("common/js/journey.js", html)
        self.assertIn('id="journey-config"', html)
        self.assertIn("csrftoken", response.cookies)  # the first-party CSRF cookie the endpoints need
        source = open(finders.find("common/js/journey.js")).read()
        for endpoint in ["/journey/state/", "/journey/answer/", "/journey/step/", "/journey/result/", "/journey/restart/"]:
            self.assertIn(endpoint, source)

    def test_gold_apply_page_posts_to_the_gold_endpoint(self):
        html = self.client.get("/gold-card/apply/").content.decode()
        self.assertIn("common/js/gold-apply.js", html)
        source = open(finders.find("common/js/gold-apply.js")).read()
        self.assertIn("/gold/apply/", source)
        self.assertIn("/gold/options/", source)

    def test_register_form_wires_the_shared_validation(self):
        html = self.client.get("/register/?plan=tier-2").content.decode()
        self.assertIn("data-live-validate", html)
        self.assertIn('data-check-email-url="/register/check-email/"', html)
        self.assertIn("common/js/register.js", html)
        self.assertIn('value="tier-2"', html)
        self.assertRegex(html, r'value="tier-2"[^>]*checked')
        self.assertIn("common/js/app.js", html)  # app.js attaches validate.js to every data-live-validate form
        self.assertIn("initValidation", open(finders.find("common/js/app.js")).read())

    def test_register_marketing_opt_in_is_not_ticked_and_men_only_is_asked(self):
        html = self.client.get("/register/").content.decode()
        self.assertNotRegex(html, r'name="marketing_opt_in"[^>]*checked')
        self.assertIn("men-only spa", html)

    def test_account_page_greets_and_shows_finished_placeholders(self):
        user = get_user_model().objects.create_user("daniel@example.com", "a-long-password-1", first_name="Daniel")
        user.email_verified_at = timezone.now()
        user.save()
        self.client.force_login(user)
        html = self.client.get("/account/").content.decode()
        self.assertRegex(html, r"Good (morning|afternoon|evening), Daniel\.")
        for name in ["Visits", "Bookings", "Membership"]:
            self.assertIn(name, html)
        self.assertIn("Opens January 2027", html)
        self.assertIn("Delete my account", html)

    def test_control_sign_in_uses_the_bare_layout(self):
        response = self.client.get("/login/", HTTP_HOST="control.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Spa 99 Control", response.content.decode())

    def test_error_pages_use_the_branded_layout(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertIn("This page isn't here.", response.content.decode())

    def test_copy_has_no_exclamation_marks_or_em_dashes(self):
        for path in ["/", "/the-spa/", "/memberships/", "/gold-card/", "/book/", "/visit/"]:
            text = re.sub(r"<script.*?</script>|<style.*?</style>", "", self.client.get(path).content.decode(), flags=re.S)
            visible = re.sub(r"<[^>]+>", " ", text)
            self.assertNotIn("!", visible, path)
            self.assertNotIn("—", visible, path)
