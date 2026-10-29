"""System > Sales through the views: access (U5), create/edit rules, live locks, End now with undo, the preview link, the public bar."""
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from plans.management.commands.seed_phase1 import seed_all
from plans.models import Plan, Sale
from plans.tests.helpers import open_memberships
from plans.tests.test_sales import HOUR, make_sale
from system.models import SystemChange
from system.tests.test_system import make_user, sign_in, unlocked_client

PATHS = ["/sales/", "/sales/new/"]


def local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def form(start=2, end=30, **over):
    now = timezone.now()
    data = {"name": "Spring sale", "percent_off": 15, "months_at_price": 2, "starts_at": local(now + start * HOUR), "ends_at": local(now + end * HOUR),
            "plans": [Plan.objects.get(slug="tier-1").pk]}
    data.update(over)
    return data


class SalesTests(TestCase):
    def setUp(self):
        seed_all()
        open_memberships()
        self.dev = make_user()
        self.client = unlocked_client(self.dev)

    def test_only_unlocked_developers_get_in_everyone_else_gets_404(self):
        sale = make_sale()
        office = make_user("office@example.com", system=False)
        for client in (Client(HTTP_HOST="system.localhost"), sign_in(office)[0]):
            for path in [*PATHS, f"/sales/{sale.pk}/"]:
                self.assertEqual(client.get(path).status_code, 404, path)
            for path in (f"/sales/{sale.pk}/end/", f"/sales/{sale.pk}/preview/", "/sales/new/"):
                self.assertEqual(client.post(path, form()).status_code, 404, path)
        self.assertEqual(sign_in(make_user("dev2@example.com"))[0].get("/sales/").status_code, 302)  # signed in but locked
        self.assertEqual(self.client.get("/sales/").status_code, 200)

    def test_create_is_logged_with_plans_and_an_overlap_is_refused_with_nothing_saved(self):
        self.assertEqual(self.client.post("/sales/new/", form()).status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual((sale.created_by, [p.slug for p in sale.plans.all()]), (self.dev, ["tier-1"]))
        self.assertTrue(SystemChange.objects.filter(model_label="plans.sale", section="sales", kind="created").exists())
        self.assertTrue(SystemChange.objects.filter(field="plans", section="sales").exists())
        clash = self.client.post("/sales/new/", form(start=10, end=40, name="Clash"))
        self.assertEqual(clash.status_code, 400)
        self.assertIn("overlaps", str(clash.context["form"].errors))
        self.assertEqual(self.client.post("/sales/new/", form(start=40, end=50, plans=[], name="No plans")).status_code, 400)
        self.assertEqual(Sale.objects.count(), 1)
        listing = self.client.get("/sales/")
        self.assertEqual([s.pk for s in listing.context["upcoming"]], [sale.pk])

    def test_a_live_sale_locks_only_the_start_and_edits_leave_existing_snapshots_alone(self):
        from users import services
        from users.models import InterestRegistration
        from users.tests.test_register import cleaned

        sale = make_sale()
        holder = services.register_interest(cleaned(email="h@example.com", mobile="07912345670", plan="tier-2")).user.interest
        before = self.client.get(f"/sales/{sale.pk}/")
        self.assertEqual(set(before.context["locked_fields"]), {"starts_at"})
        data = form(name="Christmas sale 2", percent_off=50, months_at_price=9, start=5, end=48, plans=[p.pk for p in Plan.objects.filter(slug__in=["tier-1", "tier-2"])])
        data["row_token"] = before.context["form"].initial["row_token"]
        data["starts_at"] = local(sale.starts_at)
        response = self.client.post(f"/sales/{sale.pk}/", data)
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        sale.refresh_from_db()
        self.assertEqual((sale.name, sale.percent_off, sale.months_at_price), ("Christmas sale 2", 50, 9))
        self.assertGreater(sale.ends_at, timezone.now() + timedelta(hours=40))
        self.assertEqual({p.slug for p in sale.plans.all()}, {"tier-1", "tier-2"})
        holder.refresh_from_db()
        self.assertEqual((holder.sale_name, holder.sale_percent_off, holder.sale_months), ("Christmas sale", 20, 3))  # the snapshot is theirs
        self.assertEqual(InterestRegistration.objects.filter(sale_percent_off=50).count(), 0)
        # the start cannot move once it has begun (the model refuses too: admin, shell)
        sale.starts_at -= HOUR
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            sale.full_clean()

    def test_the_end_cannot_be_in_the_past_but_can_be_extended_or_stopped(self):
        sale = make_sale(end=2)
        end = sale.ends_at
        token = self.client.get(f"/sales/{sale.pk}/").context["form"].initial["row_token"]
        data = {**form(start=-1, end=-1), "starts_at": local(sale.starts_at), "row_token": token}
        refused = self.client.post(f"/sales/{sale.pk}/", data)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("cannot be in the past", str(refused.context["form"].errors))
        sale.refresh_from_db()
        self.assertEqual(sale.ends_at, end)
        for by, delta in (("1h", HOUR), ("1d", 24 * HOUR), ("1w", 7 * 24 * HOUR)):
            before = Sale.objects.get(pk=sale.pk).ends_at
            self.assertEqual(self.client.post(f"/sales/{sale.pk}/extend/", {"by": by}).status_code, 302)
            self.assertEqual(Sale.objects.get(pk=sale.pk).ends_at, before + delta)
        self.assertTrue(SystemChange.objects.filter(model_label="plans.sale", field="ends_at", section="sales").exists())
        self.client.post(f"/sales/{sale.pk}/extend/", {"by": "5y"})  # not one of the choices
        self.assertEqual(self.client.post(f"/sales/{sale.pk}/end/").status_code, 302)
        sale.refresh_from_db()
        self.assertEqual(sale.status(), "ended")
        self.client.post(f"/sales/{sale.pk}/extend/", {"by": "1d"})  # an ended sale stays ended
        self.assertEqual(Sale.objects.get(pk=sale.pk).status(), "ended")

    def test_stale_form_gets_409_and_an_ended_sale_is_read_only(self):
        sale = make_sale(start=5, end=30)
        token = self.client.get(f"/sales/{sale.pk}/").context["form"].initial["row_token"]
        other = Sale.objects.get(pk=sale.pk)
        other.name = "Changed elsewhere"
        other.save()
        stale = self.client.post(f"/sales/{sale.pk}/", {**form(start=5, end=30), "row_token": token})
        self.assertEqual(stale.status_code, 409)
        self.assertContains(stale, "Changed since you opened it", status_code=409)
        past = make_sale(start=-50, end=-40, name="Old")
        page = self.client.get(f"/sales/{past.pk}/")
        self.assertTrue(page.context["read_only"])
        self.assertEqual(self.client.post(f"/sales/{past.pk}/", form(name="Hacked", start=-50, end=-40)).status_code, 400)
        past.refresh_from_db()
        self.assertEqual(past.name, "Old")

    def test_end_now_is_logged_and_undo_puts_it_back_unless_something_else_took_the_slot(self):
        sale = make_sale()
        self.assertEqual(self.client.post(f"/sales/{sale.pk}/end/").status_code, 302)
        sale.refresh_from_db()
        self.assertEqual(sale.status(), "ended")
        change = SystemChange.objects.get(model_label="plans.sale", field="ended_early_at")
        self.assertTrue(change.undoable)
        other = make_sale(start=0.5, end=5, name="Replacement")  # took the freed time
        self.client.post(f"/changes/{change.pk}/undo/")
        sale.refresh_from_db()
        self.assertIsNotNone(sale.ended_early_at)  # refused: it would overlap
        other.delete()
        self.client.post(f"/changes/{change.pk}/undo/")
        sale.refresh_from_db()
        self.assertIsNone(sale.ended_early_at)
        self.assertEqual(self.client.post(f"/sales/{make_sale(start=-60, end=-50, name='Gone').pk}/end/").status_code, 302)  # already ended: toast, no change

    def test_undo_is_refused_once_the_original_end_has_passed(self):
        sale = make_sale(start=-3, end=1)
        self.client.post(f"/sales/{sale.pk}/end/")
        change = SystemChange.objects.get(model_label="plans.sale", field="ended_early_at")
        Sale.objects.filter(pk=sale.pk).update(ends_at=timezone.now() - HOUR)
        self.client.post(f"/changes/{change.pk}/undo/")
        sale.refresh_from_db()
        self.assertIsNotNone(sale.ended_early_at)

    def test_preview_link_shows_the_bar_in_that_browser_only_and_the_live_bar_shows_for_everyone(self):
        sale = make_sale(start=48, end=72)
        link = self.client.post(f"/sales/{sale.pk}/preview/", HTTP_ACCEPT="application/json").json()["url"]
        token = link.split("sale_preview=")[1]
        public = Client()
        self.assertFalse(public.get("/memberships/").context["sale_bar"])
        self.assertFalse(public.get(f"/memberships/?sale_preview={token}").context["sale_bar"])  # a GET only offers it
        public.post("/sale-preview/", {"token": token, "next": "/memberships/"})
        self.assertEqual(public.get("/memberships/").context["sale_bar"]["name"], "Christmas sale")
        self.assertEqual(public.get("/memberships/").context["sale_bar"]["preview"], True)  # same browser keeps it
        self.assertFalse(Client().get("/memberships/").context["sale_bar"])  # another browser does not
        office = Client(HTTP_HOST="office.localhost")
        self.assertFalse(office.get("/login/").context["sale_bar"])
        make_sale(start=-1, end=2, name="Live now")
        self.assertEqual(Client().get("/memberships/").context["sale_bar"]["name"], "Live now")
