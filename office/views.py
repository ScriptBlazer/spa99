"""Office views. Short: data comes from office.selectors (stored figures) and office.lists (source lists); actions call
the existing services. Permissions are decorators on every view (see office.permissions)."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from gold import approval, invites
from gold.models import GoldApplication
from insights.metrics import K
from plans.models import Plan
from users import services as user_services
from users import views as user_views
from users.models import User

from . import lists, selectors
from .permissions import admin, approver, final_approver, reader


def _greeting(user):
    hour = timezone.localtime().hour
    part = "morning" if hour < 12 else ("afternoon" if hour < 18 else "evening")
    name = user.first_name or ""
    return f"Good {part}, {name}." if name else f"Good {part}."


def _fragment(request, full, rows):
    """HTMX asks for the rows only (search, show more)."""
    return rows if request.headers.get("HX-Request") else full


def _varied(response):
    patch_vary_headers(response, ["HX-Request"])
    return response


# ---------- dashboard and analytics ----------

def _remembered_range(request, key, allowed, default):
    """?range= wins and is remembered in the session for the next visit; otherwise the remembered one."""
    asked = request.GET.get("range")
    if asked in allowed:
        if request.session.get(key) != asked:
            request.session[key] = asked
        return asked
    remembered = request.session.get(key)
    return remembered if remembered in allowed else default


@reader
@require_GET
def dashboard(request):
    data = selectors.dashboard(_remembered_range(request, "office_range_dashboard", selectors.DASHBOARD_RANGES, "7d"))
    return render(request, "office/dashboard.html", {"data": data, "greeting": _greeting(request.user), "section": "dashboard"})


@reader
@require_GET
def dashboard_json(request):
    return JsonResponse(selectors.dashboard(request.GET.get("range", "7d")))


@reader
@require_GET
def analytics(request):
    name = _remembered_range(request, "office_range_analytics", selectors.ANALYTICS_RANGES, "30d")
    context = {"data": selectors.analytics(name), "pages": selectors.pages(name), "section": "analytics"}
    return render(request, "office/analytics.html", context)


@reader
@require_GET
def analytics_data(request):
    return JsonResponse(selectors.analytics(request.GET.get("range", "30d")))


@reader
@require_GET
def analytics_pages(request):
    return JsonResponse(selectors.pages(request.GET.get("range", "30d")))


# ---------- people ----------

@reader
@require_GET
@never_cache
def people(request):
    filters, page = lists.people_filters(request), lists.page_number(request)
    rows, has_next = lists.people_page(filters, page)
    total = selectors.counters(K.REGISTRATIONS).get((K.REGISTRATIONS, ""), 0)
    context = {"rows": rows, "has_next": has_next, "page": page, "filters": filters, "total_registered": total,
               "plans": list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order").values("slug", "name")), "section": "people"}
    return _varied(render(request, _fragment(request, "office/people.html", "office/_people_rows.html"), context))


@admin
@require_GET
def people_csv(request):
    return lists.people_csv(lists.people_filters(request))


@reader
@require_GET
def person(request, pk):
    user = get_object_or_404(User, pk=pk, interest__isnull=False)
    return render(request, "office/person.html", {"person": lists.person_detail(user), "section": "people"})


@admin
@require_GET
def person_export(request, pk):
    """UK GDPR: everything we hold about this person, as a JSON download."""
    user = get_object_or_404(User, pk=pk, interest__isnull=False)
    response = JsonResponse(user_services.export_user_data(user), json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="spa99-person-{user.public_id}.json"'
    return response


@admin
@require_POST
def person_delete(request, pk):
    """UK GDPR erasure. Admin and up. Never a staff account or yourself."""
    user = get_object_or_404(User, pk=pk)
    if user.is_staff or user.is_superuser or user.pk == request.user.pk:
        messages.error(request, "A staff account cannot be deleted here.")
        return redirect("office_person", pk=user.pk)
    name = user.get_full_name() or user.email
    user_services.delete_user_data(user)
    messages.success(request, f"{name} and their data were deleted.")
    return redirect("office_people")


# ---------- gold ----------

@reader
@require_GET
@never_cache
def gold(request):
    filters, page = lists.gold_filters(request), lists.page_number(request)
    rows, has_next = lists.gold_page(filters, page)
    stored = selectors.counters(K.GOLD_APPLICATIONS, K.GOLD_BY_STATUS)
    context = {"rows": rows, "has_next": has_next, "page": page, "filters": filters, "section": "gold",
               "final_approver_missing": not approval.final_approver_exists(),
               "total_applications": stored.get((K.GOLD_APPLICATIONS, ""), 0), "waiting": selectors.waiting_count(stored)}
    return _varied(render(request, _fragment(request, "office/gold.html", "office/_gold_rows.html"), context))


@reader
@require_GET
@never_cache
def gold_application(request, pk):
    application = get_object_or_404(GoldApplication, pk=pk)
    context = {"application": lists.gold_detail(application), "section": "gold", "final_approver_missing": not approval.final_approver_exists()}
    return render(request, "office/gold_detail.html", context)


@approver
@require_GET
@never_cache
def gold_approve_confirm(request, pk):
    """The page Barry's email button opens: sign-in and Owner/Manager come first (middleware, then @admin). GET only
    shows the application; the tap POSTs to gold_approve, which holds the approval logic."""
    application = get_object_or_404(GoldApplication, pk=pk)
    context = {"application": lists.gold_confirm(application), "section": "gold", "final_approver_missing": not approval.final_approver_exists()}
    return render(request, "office/gold_confirm.html", context)


def _act(request, pk, action):
    application = get_object_or_404(GoldApplication, pk=pk)
    action(request, application)
    return redirect("office_gold_application", pk=application.pk)


@approver
@require_POST
def gold_approve(request, pk):
    def run(request, application):
        result = approval.approve(application, request.user)
        first = application.first_name or "He"
        text = {approval.AWAITING: "Sent for final approval.",
                invites.INVITED: f"{first} is approved. His invite is on its way.",
                invites.ACTIVATED: f"{first} is approved. Gold was added to his existing account.",
                invites.SKIPPED: "Nothing changed: it was already decided, or Gold could not be activated."}[result]
        messages.success(request, text) if result != invites.SKIPPED else messages.warning(request, text)
    return _act(request, pk, run)


# ---------- final approval (Low potential): Admin level or higher with the Final approver permission ----------

def _final_context(application, token, action, state, **extra):
    return {"application": lists.gold_confirm(application), "token": token, "action": action, "state": state, "section": "gold",
            "note_max": GoldApplication.NOTE_MAX, **extra}


@final_approver
@require_GET
@never_cache
def gold_final_page(request, pk, token):
    """The page the one-tap links in the final approval email open (sign-in first, then the role). Shows Confirm approval and
    Send back (with an optional note); the buttons POST to gold_final_confirm / gold_final_send_back with the token. A bad,
    expired or already used link answers 410 and shows nothing about the application."""
    application = get_object_or_404(GoldApplication, pk=pk)
    action = request.GET.get("do") if request.GET.get("do") in ("confirm", "send_back") else ""
    if not approval.token_is_valid(token, application):
        return render(request, "office/gold_final.html", {"state": "invalid", "section": "gold", "application": None}, status=410)
    return render(request, "office/gold_final.html", _final_context(application, token, action, "open"))


def _final_act(request, pk, run):
    """Shared by the two final approval buttons. A posted token (from the email page) must be valid; the Office detail page
    posts without one. Either way the application must still be awaiting final approval."""
    application = get_object_or_404(GoldApplication, pk=pk)
    token = request.POST.get("token", "")
    if token and not approval.token_is_valid(token, application):
        return render(request, "office/gold_final.html", {"state": "invalid", "section": "gold", "application": None}, status=410)
    run(application)
    return redirect("office_gold_application", pk=application.pk)


@final_approver
@require_POST
def gold_final_confirm(request, pk):
    def run(application):
        result = approval.final_confirm(application, request.user)
        first = application.first_name or "He"
        if result == invites.INVITED:
            messages.success(request, f"{first} is approved. His invite is on its way.")
        elif result == invites.ACTIVATED:
            messages.success(request, f"{first} is approved. Gold was added to his existing account.")
        else:
            messages.warning(request, "Nothing changed: it is not waiting for final approval any more.")
    return _final_act(request, pk, run)


@final_approver
@require_POST
def gold_final_send_back(request, pk):
    def run(application):
        try:
            sent = approval.send_back(application, request.user, request.POST.get("note", ""))
        except approval.NoteTooLong as error:
            messages.error(request, str(error))
            return
        if sent:
            messages.success(request, "Sent back. The approvers have been emailed.")
        else:
            messages.warning(request, "Nothing changed: it is not waiting for final approval any more.")
    return _final_act(request, pk, run)


@approver
@require_POST
def gold_resend(request, pk):
    def run(request, application):
        if invites.resend_invite(application) == invites.INVITED:
            messages.success(request, "A new invite is on its way. The old link no longer works.")
        else:
            messages.warning(request, "No invite was sent: only approved applicants without an account get one.")
    return _act(request, pk, run)


@approver
@require_POST
def gold_decline(request, pk):
    def run(request, application):
        if invites.decline_application(application):
            messages.success(request, "Declined. He will not be invited.")
        else:
            messages.warning(request, "Nothing changed: this application was already decided.")
    return _act(request, pk, run)


# ---------- change password (team members; the member area is for members only) ----------

class OfficePasswordView(user_views.TeamPasswordView):
    template_name = "office/password.html"

    @method_decorator(reader)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "section": "password"}
