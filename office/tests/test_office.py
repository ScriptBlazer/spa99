"""Office: host routing and roles, stored-figure pages with a fixed query count, people and Gold actions."""
import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from gold import invites
from gold import services as gold_services
from gold.models import GoldApplication
from gold.tests.test_gold import application_data
from insights import rollup
from insights.models import OfficeGoal
from insights.tests.test_metrics import finished_journey
from plans.management.commands.seed_phase1 import seed_all
from users import services
from users.tests.test_register import cleaned

User = get_user_model()
OFFICE = "office.localhost"


def staff(role=None, email=None, **extra):
    user = User.objects.create_user(email or f"{role or 'norole'}@example.com".lower(), "x", is_staff=True, **extra)
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def get(user, path, host=OFFICE, **kwargs):
    client = Client(HTTP_HOST=host)
    if user:
        client.force_login(user)
    return client.get(path, **kwargs)


def post(user, path, host=OFFICE, **data):
    client = Client(HTTP_HOST=host)
    client.force_login(user)
    return client.post(path, data)


class OfficeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        call_command("setup_roles", stdout=StringIO())


class RoutingAndRoleTests(OfficeTestCase):
    def test_office_host_needs_sign_in_and_has_its_own_login_and_noindex(self):
        response = get(None, "/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        login = get(None, "/login/")
        self.assertContains(login, "Spa 99 Office")
        self.assertEqual(login["X-Robots-Tag"], "noindex, nofollow")
        self.assertNotContains(login, "/register/")
        self.assertContains(login, "common/js/forms.js")  # the password toggle and live validation scripts are on the page
        self.assertContains(login, 'id="validation-config"')

    def test_office_sign_in_posts_and_shows_errors(self):
        user = staff("Owner", "signin@example.com")
        user.set_password("a-long-test-password-1")
        user.save()
        client = Client(HTTP_HOST=OFFICE)
        bad = client.post("/login/", {"username": "signin@example.com", "password": "wrong"})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, "form-error")
        good = client.post("/login/", {"username": "signin@example.com", "password": "a-long-test-password-1"})
        self.assertEqual(good.status_code, 302)

    def test_members_and_staff_without_a_role_are_refused_and_roles_can_read(self):
        member = User.objects.create_user("member@example.com", "x")
        self.assertEqual(get(member, "/").status_code, 403)
        self.assertEqual(get(staff(), "/").status_code, 403)
        for role in ("Owner", "Manager", "Viewer"):
            user = staff(role)
            for path in ("/", "/analytics/", "/people/", "/gold/", "/dashboard.json", "/analytics/data/", "/analytics/pages/"):
                self.assertEqual(get(user, path).status_code, 200, f"{role} {path}")

    def test_a_member_account_in_a_role_group_is_not_let_in(self):
        member = User.objects.create_user("memberrole@example.com", "x")  # not staff
        member.groups.add(Group.objects.get(name="Owner"))
        for path in ("/", "/people/", "/gold/", "/insights/summary/"):
            self.assertEqual(get(member, path).status_code, 403, path)

    def test_lists_vary_on_htmx_and_are_not_cached(self):
        response = get(staff("Viewer"), "/people/")
        self.assertIn("HX-Request", response["Vary"])
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertIn("HX-Request", get(staff("Owner"), "/gold/")["Vary"])

    def test_the_office_is_not_on_the_public_or_control_host(self):
        owner = staff("Owner")
        self.assertEqual(get(owner, "/people/", host="localhost").status_code, 404)
        self.assertEqual(get(owner, "/people/", host="control.localhost").status_code, 404)
        self.assertEqual(get(owner, "/insights/summary/", host=OFFICE).status_code, 200)
        self.assertEqual(get(owner, "/insights/summary/", host="control.localhost").status_code, 404)

    def test_viewer_is_read_only_everywhere(self):
        viewer = staff("Viewer")
        person = services.register_interest(cleaned()).user
        application = gold_services.submit_application(application_data())[0]
        self.assertEqual(get(viewer, "/people/export.csv").status_code, 403)
        self.assertEqual(get(viewer, f"/people/{person.pk}/export/").status_code, 403)
        self.assertEqual(post(viewer, f"/people/{person.pk}/delete/").status_code, 403)
        for action in ("approve", "decline", "resend"):
            self.assertEqual(post(viewer, f"/gold/{application.pk}/{action}/").status_code, 403)
        page = get(viewer, f"/gold/{application.pk}/").content.decode()
        self.assertNotIn("data-approve", page)
        self.assertNotIn("data-decline", page)
        self.assertNotIn("data-export-csv", get(viewer, "/people/").content.decode())
        self.assertTrue(User.objects.filter(pk=person.pk).exists())

    def test_manager_acts_but_only_an_owner_deletes(self):
        manager, owner = staff("Manager"), staff("Owner")
        person = services.register_interest(cleaned()).user
        self.assertEqual(get(manager, "/people/export.csv").status_code, 200)
        self.assertEqual(post(manager, f"/people/{person.pk}/delete/").status_code, 403)
        self.assertEqual(post(owner, f"/people/{person.pk}/delete/").status_code, 302)
        self.assertFalse(User.objects.filter(pk=person.pk).exists())
        post(owner, f"/people/{owner.pk}/delete/")  # never a staff account, never yourself
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())


class StoredFigureTests(OfficeTestCase):
    def setUp(self):
        self.owner = staff("Owner", "q@example.com")

    def queries(self, path):
        client = Client(HTTP_HOST=OFFICE)
        client.force_login(self.owner)
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(client.get(path).status_code, 200)
        return len(ctx)

    def test_pages_run_a_small_fixed_number_of_queries_whatever_the_data(self):
        paths = ["/", "/?range=30d", "/dashboard.json", "/analytics/", "/analytics/?range=all", "/analytics/data/?range=90d", "/analytics/pages/"]
        empty = {p: self.queries(p) for p in paths}
        for i in range(4):  # more data must not mean more queries
            finished_journey(time="evening" if i % 2 else "daytime")
            services.register_interest(cleaned(email=f"p{i}@example.com", mobile=f"0791234567{i}"))
            gold_services.submit_application(application_data(email=f"g{i}@example.com", mobile=f"+44791122233{i}"))
        rollup.run()
        for path in paths:
            self.assertEqual(self.queries(path), empty[path], path)
            self.assertLessEqual(empty[path], 20, path)

    def test_dashboard_and_analytics_json_shapes(self):
        finished_journey()
        services.register_interest(cleaned())
        gold_services.submit_application(application_data())
        OfficeGoal.objects.create(key="registrations", range="7d", target=4)
        rollup.run()
        owner = staff("Owner")
        data = get(owner, "/dashboard.json?range=7d").json()
        self.assertEqual(data["waiting"]["count"], 1)
        rings = {r["key"]: r for r in data["rings"]}
        self.assertEqual(list(rings), ["journeys_started", "journeys_completed", "registrations"])
        self.assertEqual((rings["registrations"]["value"], rings["registrations"]["goal"], rings["registrations"]["percent"]), (1, 4, 25))
        self.assertEqual((rings["journeys_started"]["value"], rings["journeys_started"]["previous"], rings["journeys_started"]["change"]), (1, 0, 1))
        self.assertIsNone(rings["journeys_completed"]["goal"])  # no goal row: "No goal set"
        self.assertIsNone(rings["journeys_completed"]["percent"])
        self.assertEqual(data["gold_waiting"], 1)
        self.assertEqual([s["key"] for s in data["stats"]], ["registrations", "journeys_completed", "visitors", "page_views"])
        self.assertIn("change", data["stats"][0])
        self.assertEqual([f["previous_value"] for f in data["funnel"]], [None, 0, 1, 1])
        self.assertEqual(len(data["stats"][0]["series"]), 7)
        self.assertTrue(data["what_changed"])
        analytics = get(owner, "/analytics/data/?range=7d").json()
        self.assertEqual(len(analytics["labels"]), 7)
        self.assertEqual(analytics["series"]["registrations"]["total"], 1)
        self.assertEqual(analytics["funnel"][2]["value"], 1)
        self.assertEqual({a["value"]: a["count"] for a in analytics["journey_answers"]["time"]}["evening"], 1)
        self.assertEqual(analytics["summaries"]["funnel"], "No visitors in this range yet.")
        self.assertEqual(get(owner, "/analytics/data/?range=all").json()["granularity"], "day")
        self.assertIn("top_pages", get(owner, "/analytics/pages/").json())


class PeopleAndGoldTests(OfficeTestCase):
    def test_people_search_filter_csv_detail_and_gdpr_export(self):
        owner = staff("Owner")
        hugo = services.register_interest(cleaned(plan="tier-2")).user
        services.register_interest(cleaned(email="=evil@example.com", first_name="=SUM(A1)", mobile="07911111111", plan="tier-1"))
        page = get(owner, "/people/?q=hugo&plan=tier-2").context
        self.assertEqual([r["email"] for r in page["rows"]], ["hugo@example.com"])
        self.assertEqual(page["total_registered"], 2)  # the stored counter, not a count of the filtered list
        self.assertEqual(len(get(owner, "/people/?verified=yes").context["rows"]), 0)
        csv_text = get(owner, "/people/export.csv?plan=tier-1").content.decode()
        self.assertIn("'=SUM(A1)", csv_text)
        self.assertNotIn("hugo@example.com", csv_text)
        self.assertEqual(get(owner, f"/people/{hugo.pk}/").context["person"]["email"], "hugo@example.com")
        export = get(owner, f"/people/{hugo.pk}/export/")
        self.assertEqual(json.loads(export.content)["profile"]["email"], "hugo@example.com")
        self.assertIn("attachment", export["Content-Disposition"])

    def test_gold_list_detail_approve_resend_decline(self):
        mail.outbox.clear()
        owner = staff("Owner")
        a = gold_services.submit_application(application_data())[0]
        b = gold_services.submit_application(application_data(email="eli@example.com", mobile="+447911222333"))[0]
        self.assertEqual(len(get(owner, "/gold/").context["rows"]), 2)  # default filter: waiting
        detail = get(owner, f"/gold/{a.pk}/")
        self.assertEqual([s["title"] for s in detail.context["application"]["sections"]], ["Personal details", "About him", "What the site collected"])
        self.assertEqual(post(owner, f"/gold/{a.pk}/approve/").status_code, 302)
        a.refresh_from_db()
        self.assertEqual((a.status, a.approved_by), ("approved", owner))
        self.assertEqual(get(owner, "/gold/?status=approved").context["rows"][0]["invite"]["state"], "sent")
        old = a.invites.get()
        post(owner, f"/gold/{a.pk}/resend/")
        old.refresh_from_db()
        self.assertIsNotNone(old.revoked_at)  # resend replaces the old link
        self.assertEqual(a.invites.count(), 2)
        post(owner, f"/gold/{b.pk}/decline/")
        b.refresh_from_db()
        self.assertEqual(b.status, "declined")
        self.assertEqual(post(owner, f"/gold/{b.pk}/approve/").status_code, 302)  # declined stays declined
        b.refresh_from_db()
        self.assertEqual(b.status, "declined")
        self.assertEqual(len(get(owner, "/gold/?status=all").context["rows"]), 2)
        history = get(owner, f"/gold/{a.pk}/").context["application"]["history"]
        self.assertEqual([h["text"] for h in history], ["Applied", "Approved by " + (owner.get_full_name() or owner.email)])


class FreshSentenceTests(OfficeTestCase):
    def test_first_visitors_refresh_the_visitor_summary_and_funnel_never_exceeds_100(self):
        from insights import metrics, summaries
        from insights.metrics import K
        from insights.models import MetricText
        from office import selectors

        summaries.write_all()
        self.assertIn("No visitors", MetricText.objects.get(key="chart_visitors", scope="30d").text)
        client = Client(HTTP_HOST="localhost", HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1")
        client.get("/")
        self.assertNotIn("No visitors", MetricText.objects.get(key="chart_visitors", scope="30d").text)
        metrics.count(K.JOURNEYS_STARTED, "", 7, metrics.day())
        funnel = selectors.dashboard("7d")["funnel"]
        self.assertTrue(all((s["step_rate_bp"] or 0) <= 10000 for s in funnel))
        self.assertTrue(funnel[1]["partial"] and funnel[1]["step_rate_bp"] is None)
