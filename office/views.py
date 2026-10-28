"""Office views. Short: data comes from office.selectors (stored figures) and office.lists (source lists); actions call
the existing services. Permissions are decorators on every view (see office.permissions)."""
from datetime import datetime
from urllib.parse import urlencode, urlparse

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from chat import services as chat_services
from chat.models import Conversation, Message
from django.db.models import OuterRef, Subquery
from gold import actions as gold_actions
from gold import approval, audit, invites
from gold import services as gold_services
from gold.forms import DeclineForm, NoteForm, RespondForm
from gold.models import GoldApplication
from insights.metrics import K
from journey import services as journey_services
from journey.models import JourneySession
from plans.models import Plan
from common import levels
from users import services as user_services
from users import views as user_views
from users.models import User

from system import defaults

from . import lists, profile, selectors
from . import leads as lead_lists
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

def _remembered_range(request, key, allowed, default):  # `default` comes from System > Defaults
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
    data = selectors.dashboard(_remembered_range(request, "office_range_dashboard", selectors.DASHBOARD_RANGES, defaults.get(request).dashboard_range), request)
    return render(request, "office/dashboard.html", {"data": data, "greeting": _greeting(request.user), "section": "dashboard"})


@reader
@require_GET
def dashboard_json(request):
    return JsonResponse(selectors.dashboard(request.GET.get("range", defaults.get(request).dashboard_range), request))


@reader
@require_GET
def analytics(request):
    name = _remembered_range(request, "office_range_analytics", selectors.ANALYTICS_RANGES, defaults.get(request).analytics_range)
    context = {"data": selectors.analytics(name), "pages": selectors.pages(name), "section": "analytics"}
    return render(request, "office/analytics.html", context)


@reader
@require_GET
def analytics_data(request):
    return JsonResponse(selectors.analytics(request.GET.get("range", defaults.get(request).analytics_range), request))


@reader
@require_GET
def analytics_pages(request):
    return JsonResponse(selectors.pages(request.GET.get("range", defaults.get(request).analytics_range), request))


# ---------- people ----------

@reader
@require_GET
@never_cache
def people(request):
    filters, page = lists.people_filters(request), lists.page_number(request)
    rows, has_next = lists.people_page(filters, page, defaults.get(request).list_page_size)
    total = selectors.counters(K.REGISTRATIONS).get((K.REGISTRATIONS, ""), 0)
    context = {"rows": rows, "has_next": has_next, "page": page, "filters": filters, "total_registered": total,
               "plans": list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order").values("slug", "name")), "section": "people"}
    return _varied(render(request, _fragment(request, "office/people.html", "office/_people_rows.html"), context))


@admin
@require_GET
def people_csv(request):
    return lists.people_csv(lists.people_filters(request))


def _timeline_context(request, person):
    """The timeline for the page: the default number of events, grouped by day; ?tl=2 (HTMX 'Show earlier') asks for the next page."""
    try:
        number = max(int(request.GET.get("tl", "1")), 1)
    except ValueError:
        number = 1
    days, more = lead_lists.timeline_page(person["timeline"], number, defaults.get(request).timeline_page_size)
    for day in days:
        for item in day["items"]:
            item["time"] = f"{timezone.localtime(datetime.fromisoformat(item['at'])):%H:%M}" if item["at"] else ""  # the day is the heading above
    return {"timeline_days": days, "timeline_more": more, "timeline_next": number + 1}


def _person_extras(request, person):
    """Values the person page draws that no list holds: the furthest status, the journey his answers come from (the latest
    finished one, else the latest), where the back link goes, and the score that makes a Gold potential High."""
    from gold import rating

    journeys = person["journeys"]
    finished = [j for j in journeys if j["completed"]]
    latest = max(finished, key=lambda j: j["completed_at"] or j["started"]) if finished else (journeys[-1] if journeys else None)
    status = lead_lists.status_of(person["kind"] == "account", [a["status"] for a in person["gold"]["applications"]])
    referer = urlparse(request.META.get("HTTP_REFERER", ""))
    came = {"/leads/": ("Leads", "office_leads"), "/people/": ("People", "office_people")}.get(referer.path)
    label, name = came or (("Leads", "office_leads") if person["kind"] == "lead" else ("People", "office_people"))
    back = reverse(name) + (f"?{referer.query}" if came and referer.query and referer.netloc == request.get_host() else "")
    return {"person_status": status, "latest_journey": latest, "latest_finished": bool(finished), "back": {"label": label, "url": back},
            "gold_high_at": rating.thresholds()[rating.HIGH]}


@reader
@require_GET
def person(request, pk):
    user = get_object_or_404(User, pk=pk, interest__isnull=False)
    person = lists.person_detail(user)
    context = {"person": person, "section": "people", **_timeline_context(request, person), **_person_extras(request, person)}
    return render(request, "office/_timeline.html" if request.headers.get("HX-Request") and "tl" in request.GET else "office/person.html", context)


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


# ---------- leads (an email given at the journey gate, no account yet) ----------

@reader
@require_GET
@never_cache
def leads(request):
    filters, number = lead_lists.filters_from(request), lists.page_number(request)
    rows, has_next = lead_lists.page(filters, number, defaults.get(request).leads_page_size)
    filtered = lead_lists.is_filtered(filters, request)
    summary = selectors.leads_summary(filters["range"], request)
    context = {"rows": rows, "has_next": has_next, "page": number, "filters": filters, "filtered": filtered, "summary": summary,
               "total_leads": None if filtered else summary.get("leads_total"), "choices": lead_lists.filter_choices(), "section": "leads",
               "site_defaults": defaults.get(request)}
    return _varied(render(request, _fragment(request, "office/leads.html", "office/_leads_rows.html"), context))


@admin
@require_GET
def leads_csv(request):
    return lead_lists.csv_response(lead_lists.filters_from(request), request.user.pk)


def _lead_session(pk):
    session = get_object_or_404(JourneySession, pk=pk)
    found = lead_lists.lead_for(session)
    if found is None:
        raise Http404
    return session, found


@reader
@require_GET
@never_cache
def lead(request, pk):
    """A lead's page by the opaque id of any of his sessions (never the address). Once the address has an account the same
    link opens the account page."""
    session, (kind, data) = _lead_session(pk)
    if kind == "account":
        return redirect("office_person", pk=data.pk)
    context = {"person": data, "section": "leads", **_timeline_context(request, data), **_person_extras(request, data)}
    return render(request, "office/_timeline.html" if request.headers.get("HX-Request") and "tl" in request.GET else "office/lead.html", context)


@admin
@require_GET
def lead_export(request, pk):
    """UK GDPR: everything held for this address (journeys and answers, Gold applications), as a JSON download."""
    session, (kind, data) = _lead_session(pk)
    if kind == "account":
        return redirect("office_person_export", pk=data.pk)
    body = {"email": data["email"], "sessions": journey_services.export_lead(data["email"]),
            "emails": journey_services.export_lead_emails(data["email"]),
            "chats": chat_services.export_conversations(email=data["email"]),
            "gold_applications": gold_services.export_applications(data["email"])}
    response = JsonResponse(body, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = 'attachment; filename="spa99-lead.json"'
    return response


@admin
@require_POST
def lead_delete(request, pk):
    """Erase the address from his journeys (the answers stay without it). Gold applications are not touched here."""
    session, (kind, data) = _lead_session(pk)
    if kind == "account":
        return redirect("office_person", pk=data.pk)
    cleared = journey_services.erase_lead_data(data["email"])
    messages.success(request, f"The email was cleared from {cleared} journey{'s' if cleared != 1 else ''}. The answers stay, without it.")
    return redirect("office_leads")


# ---------- chats (Ask us) ----------

@reader
@require_GET
@never_cache
def chats(request):
    """The Ask us conversations, newest first, a page at a time (one extra row instead of a count). View only."""
    first = Message.objects.filter(conversation=OuterRef("pk"), role=Message.USER).order_by("created_at").values("text")[:1]
    queryset = Conversation.objects.filter(staff_test=False).annotate(preview=Subquery(first)).select_related("user")
    page = lists.page_number(request)
    rows, has_next = lists.cut(queryset, page, defaults.get(request).list_page_size)
    return render(request, "office/chats.html", {"rows": rows, "has_next": has_next, "page": page, "section": "chats"})


@reader
@require_GET
@never_cache
def chat_detail(request, pk):
    conversation = get_object_or_404(Conversation.objects.select_related("user"), pk=pk)
    return render(request, "office/chat_detail.html", {"conversation": conversation, "messages_list": conversation.messages.all(), "section": "chats"})


# ---------- gold ----------

@reader
@require_GET
@never_cache
def gold(request):
    filters, page = lists.gold_filters(request), lists.page_number(request)
    rows, has_next = lists.gold_page(filters, page, defaults.get(request).list_page_size)
    stored = selectors.counters(K.GOLD_APPLICATIONS, K.GOLD_BY_STATUS)
    context = {"rows": rows, "has_next": has_next, "page": page, "filters": filters, "section": "gold",
               "final_approver_missing": not approval.final_approver_exists(),
               "total_applications": stored.get((K.GOLD_APPLICATIONS, ""), 0), "waiting": selectors.waiting_count(stored),
               "awaiting_final_count": stored.get((K.GOLD_BY_STATUS, "awaiting_final"), 0)}
    return _varied(render(request, _fragment(request, "office/gold.html", "office/_gold_rows.html"), context))


GOLD_FORMS = ("decline", "respond", "note")  # ?do= on the application page opens that form (the approver email's Decline and Respond links)


def _can_open(application, name):
    """The forms offered right now: Decline while waiting, Respond while open, a note any time."""
    return {"decline": application.status in GoldApplication.WAITING, "respond": application.status in gold_actions.OPEN, "note": True}.get(name, False)


def _gold_page(request, application, status=200, open_form="", form=None):
    """The application page. `form` (a bound, invalid Django form) re-opens its dialog with the typed text and the errors, so a
    mistake never loses what was written. `open_form` opens a dialog on load (an email link)."""
    acts = levels.is_approver(request.user)
    opened = ""
    if form is not None:
        opened = open_form
    elif open_form in GOLD_FORMS and acts:
        opened = open_form if _can_open(application, open_form) else ""
        if not opened:
            messages.info(request, "This application has already been decided, so that is not available now.")
    context = {"application": lists.gold_detail(application), "section": "gold", "final_approver_missing": not approval.final_approver_exists(),
               "open_form": opened, "decline_prefill": gold_services.declined_prefill(application) if acts else "",
               "form_errors": {field: [str(m) for m in found] for field, found in form.errors.items()} if form is not None else {},
               "form_values": form.data if form is not None else {},
               # the approver email's signed token rides along so the audit says the approval came from the email link
               "approve_token": _email_token(request, application) if acts else ""}
    return render(request, "office/gold_detail.html", context, status=status)


def _email_token(request, application):
    token = request.GET.get("t", "")
    return token if token and approval.approve_token_is_valid(token, application) else ""


@reader
@require_GET
@never_cache
def gold_application(request, pk):
    application = get_object_or_404(GoldApplication, pk=pk)
    return _gold_page(request, application, open_form=request.GET.get("do", ""))


@approver
@require_GET
@never_cache
def gold_approve_confirm(request, pk):
    """Old email links (before 2026-10-26) pointed here: send them to the full application page, keeping the token."""
    application = get_object_or_404(GoldApplication, pk=pk)
    token = request.GET.get("t", "")
    url = reverse("office_gold_application", args=[application.pk])
    return redirect(f"{url}?{urlencode({'t': token})}" if token else url)


def _act(request, pk, action):
    application = get_object_or_404(GoldApplication, pk=pk)
    action(request, application)
    return redirect("office_gold_application", pk=application.pk)


def _approve_channel(request, application):
    """email_link only with the signed token from the approver email's Approve link; a posted channel is ignored."""
    return audit.EMAIL_LINK if approval.approve_token_is_valid(request.POST.get("token", ""), application) else audit.OFFICE


@approver
@require_POST
def gold_approve(request, pk):
    def run(request, application):
        result = approval.approve(application, request.user, channel=_approve_channel(request, application))
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
    run(application, audit.EMAIL_LINK if token else audit.OFFICE)  # a valid token means the email's one-tap page
    return redirect("office_gold_application", pk=application.pk)


@final_approver
@require_POST
def gold_final_confirm(request, pk):
    def run(application, channel):
        result = approval.final_confirm(application, request.user, channel=channel)
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
    def run(application, channel):
        try:
            sent = approval.send_back(application, request.user, request.POST.get("note", ""), channel=channel)
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
        if invites.resend_invite(application, request.user, channel=audit.OFFICE) == invites.INVITED:
            messages.success(request, "A new invite is on its way. The old link no longer works.")
        else:
            messages.warning(request, "No invite was sent: only approved applicants without an account get one.")
    return _act(request, pk, run)


def _form_act(request, pk, name, form_class, run):
    """Decline, Respond and Add note: validate, then act. A mistake re-opens the form with its errors and the typed text (400)."""
    application = get_object_or_404(GoldApplication, pk=pk)
    form = form_class(request.POST)
    if not form.is_valid() and not _can_open(application, name):  # decided by someone else meanwhile: no dialog to show it in
        messages.warning(request, "Already decided by someone else. Nothing was sent.")
        return redirect("office_gold_application", pk=application.pk)
    if not form.is_valid():
        return _gold_page(request, application, status=400, open_form=name, form=form)
    run(application, form.cleaned_data)
    return redirect("office_gold_application", pk=application.pk)


@approver
@require_POST
def gold_decline(request, pk):
    def run(application, data):
        emailing = data["email_applicant"]
        if invites.decline_application(application, request.user, data["reason"], channel=audit.OFFICE, email_message=data["email_message"] if emailing else None):
            messages.success(request, "Declined. He will not be invited." + (" He has been emailed." if emailing else ""))
        else:
            messages.warning(request, "Nothing changed: this application was already decided.")
    return _form_act(request, pk, "decline", DeclineForm, run)


@approver
@require_POST
def gold_respond(request, pk):
    def run(application, data):
        result, _ = gold_actions.respond(application, request.user, data["message"], channel=audit.OFFICE)
        if result == gold_actions.DONE:
            messages.success(request, f"Your message is on its way to {application.first_name or 'him'}. It is in the history.")
        elif result == gold_actions.DUPLICATE:
            messages.info(request, "That message was already sent.")
        else:
            messages.warning(request, "Nothing sent: this application was already decided.")
    return _form_act(request, pk, "respond", RespondForm, run)


@approver
@require_POST
def gold_note(request, pk):
    def run(application, data):
        result, _ = gold_actions.add_note(application, request.user, data["note"], channel=audit.OFFICE)
        messages.success(request, "Note added to the history.") if result == gold_actions.DONE else messages.info(request, "That note was already added.")
    return _form_act(request, pk, "note", NoteForm, run)


# ---------- change password (team members; the member area is for members only) ----------

class OfficePasswordView(user_views.TeamPasswordView):
    template_name = "office/password.html"

    @method_decorator(reader)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "section": "password"}
