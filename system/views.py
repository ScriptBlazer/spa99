"""System pages: short views; logic in services.py. Templates are minimal with stable data-system-* hooks (the design
brief is docs/design/SYSTEM.md). Every page except sign-in goes through `signed_in` or `unlocked` (404 for strangers)."""
import time

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.audit import client_ip
from common.ratelimit import hit
from notifications.models import EmailSuppression
from plans.models import SiteSettings
from users.forms import SignInForm
from users.views import LoginView, TeamPasswordView


from . import approval as approval_service
from . import audit, changes, codeview, defaults, feed, services
from . import team as team_service
from .forms import EmailsForm, SettingsForm
from .forms_rules import RISKY
from .models import SystemChange, SystemEvent
from .permissions import signed_in, unlocked

NAV = [("dashboard", "Dashboard", "system_dashboard"), ("plans", "Plans and pricing", "system_plans"), ("hours", "Hours and closures", "system_hours"),
       ("gold", "Gold rules", "system_gold"), ("approval", "Approval", "system_approval"), ("journey", "Journey", "system_journey"), ("emails", "Emails", "system_emails"), ("sales", "Sales", "system_sales"), ("suppressions", "Email suppressions", "system_suppressions"),
       ("settings", "Settings", "system_settings"), ("defaults", "Defaults", "system_defaults"), ("team", "Team", "system_team"), ("changes", "Audit log", "system_changes")]


def saved(request, text="Saved."):
    """A success toast; when this request saved undoable changes it carries the undo link (undo all for several)."""
    url = services.undo_url_for_batch(changes.current_batch())
    messages.success(request, text, extra_tags=f"undo:{url}" if url else "")


def page(request, template, section, context=None, status=200):
    """Render a System page with the navigation (stubs have no link yet)."""
    context = {"section": section, "nav": NAV, "section_labels": changes.SECTION_LABELS, **(context or {})}
    if codeview.section(section) is not None:  # the rule pages get the code view's address (the page header shows the </> icon)
        context.setdefault("code_url", reverse("system_code", args=[section]))
        context.setdefault("code_theme_default", SiteSettings.load().code_theme_default)
    return render(request, template, context, status=status)


def form_status(form):
    """409 when the row changed since the form was made (nothing saved; reload), else 400."""
    return 409 if getattr(form, "stale", False) else 400


def safe_next(request, default):
    """The `next` value if it is a path on this host, else the default."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target.startswith("/") and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return default


# ---------- sign-in, unlock, lock ----------

class SystemAuthForm(SignInForm):
    """Same sign-in form, but a person who may not use System gets the ordinary 'wrong email or password' answer."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not services.may_use_system(user):
            raise ValidationError(self.error_messages["invalid_login"], code="invalid_login",
                                  params={"username": self.username_field.verbose_name})


class SystemLoginView(LoginView):
    """The shared sign-in view (rate limited per IP) with System's own template. Signing in does not unlock."""

    template_name = "system/login.html"
    authentication_form = SystemAuthForm
    redirect_authenticated_user = False

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(services.session_age_seconds())
        self.request.session[services.SIGNED_IN_KEY] = time.time()  # the 12 hour limit counts from here
        services.lock(self.request.session)
        audit.log_event(SystemEvent.SIGN_IN, self.request, user=form.get_user())
        return response

    def form_invalid(self, form):
        audit.log_event(SystemEvent.SIGN_IN_FAILED, self.request, email=self.request.POST.get("username", "").strip().lower(),
                        detail={"reason": "wrong email or password"})
        return super().form_invalid(form)

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 429:  # the shared sign-in refused: too many tries from this IP
            audit.log_event(SystemEvent.SIGN_IN_FAILED, request, email=request.POST.get("username", "").strip().lower(),
                            outcome=SystemEvent.BLOCKED, detail={"rate_limited": True}, dedupe_seconds=300, dedupe_any_person=True)  # per IP: a typed email cannot multiply rows
        return response


@signed_in
@require_http_methods(["GET", "POST"])
def unlock(request):
    target = safe_next(request, "/")
    error = ""
    if request.method == "POST":
        by_ip = hit("system-unlock", f"{request.user.pk}:{client_ip(request) or 'unknown'}", 5, 300)
        by_person = hit("system-unlock-person", request.user.pk, 10, 900)  # whatever the IP: many addresses cannot multiply the tries
        if not (by_ip and by_person):
            audit.log_event(SystemEvent.UNLOCK_RATE_LIMITED, request, user=request.user, dedupe_seconds=300)
            return render(request, "system/unlock.html", {"next": target, "error": "Too many attempts. Please wait a few minutes.", "code_required": services.code_required()}, status=429)
        password_ok = request.user.check_password(request.POST.get("password", ""))
        code_ok = services.code_matches(request.POST.get("code", ""))  # both always checked, one generic answer
        if password_ok and code_ok:
            services.unlock(request.session)
            audit.log_event(SystemEvent.UNLOCK, request, user=request.user)
            return redirect(target)
        audit.log_event(SystemEvent.UNLOCK_FAILED, request, user=request.user, detail={"reason": "password" if not password_ok else "code"})
        error = "Password or code is wrong."
    return render(request, "system/unlock.html", {"next": target, "error": error, "code_required": services.code_required()})


@signed_in
@require_POST
def unlock_ping(request):
    """Activity ping: slides the idle window and answers {"remaining": seconds} (the server is the clock). 403 when already
    locked (the page then goes to unlock). `peek=1` only reads the time left, without sliding it."""
    if not services.is_unlocked(request.session):
        services.note_idle_lock(request)
        return JsonResponse({"remaining": 0}, status=403)
    if request.POST.get("peek") != "1":
        services.unlock(request.session)
    return JsonResponse({"remaining": services.remaining_seconds(request.session)})


@signed_in
@require_POST
def lock(request):
    if services.is_unlocked(request.session):
        audit.log_event(SystemEvent.LOCK_MANUAL, request, user=request.user)
    services.lock(request.session)
    return redirect("system_unlock")


@require_POST
@login_not_required  # sign out is harmless for anyone, and a locked-out person must always be able to leave
def sign_out(request):
    if request.user.is_authenticated and services.may_use_system(request.user) and request.session.get(services.SIGNED_IN_KEY):
        audit.log_event(SystemEvent.SIGN_OUT, request, user=request.user)
    logout(request)
    return redirect("login")


# ---------- pages ----------

@unlocked
@require_GET
def dashboard(request):
    site = SiteSettings.load()
    context = {"health": services.health_report(), "recent": services.recent_changes(defaults.get(request).dashboard_recent_changes), "site": site,
               "stages": [("Registration", site.register_interest_open), ("Subscribe", site.subscribe_open), ("Book", site.booking_open)]}
    return page(request, "system/dashboard.html", "dashboard", context)


@unlocked
@require_GET
def change_log(request):
    """The audit log. `?entry=<id>` opens the detail drawer (and shows the page that holds it); `?focus=<id>` only jumps to it."""
    params = feed.params_from(request.GET)
    entry = request.GET.get("entry", "").strip()
    page_number = request.GET.get("page")
    if not page_number and (entry or request.GET.get("focus")):
        page_number = feed.page_of(params, entry or request.GET["focus"], defaults.get(request).audit_page_size)
    result = feed.audit_feed(params, page_number, defaults.get(request).audit_page_size)
    filters = feed.query_string(params)
    number = result["page"]["number"]
    context = {"feed": result, "params": params, "people": feed.people(), "section_choices": feed.section_choices(),
               "category_choices": audit.CATEGORIES, "kind_choices": SystemEvent.KIND_CHOICES, "export_query": filters,
               "chips": feed.chips(params), "entry_count": feed.export_count(params),
               "link_query": "&".join(part for part in (filters, f"page={number}" if number > 1 else "") if part),
               "drawer": feed.entry_detail(entry) if entry else None, "filters_set": bool(filters),
               "active_filters": sum(bool(v) for v in (params["user"], params["section"], params["category"], params["range"] or params["date_from"] or params["date_to"])),
               "chain": audit.stored_status()}  # the stored result only: a full verify per page load is too costly
    return page(request, "system/changes.html", "changes", context)


@unlocked
@require_POST
def audit_check(request):
    """Check now: run the full verify, store the result, log it as an event."""
    result = audit.check_and_store()
    audit.log_event(SystemEvent.AUDIT_CHECK, request, user=request.user, outcome=SystemEvent.OK if result["ok"] else SystemEvent.FAILED,
                    detail={"ok": result["ok"], "entries": result["checked"]}, sentence=f"{request.user.email} checked the audit chain: {result['message']}"[:1000])
    (messages.success if result["ok"] else messages.error)(request, result["message"])
    return redirect(safe_next(request, "system_changes"))


@unlocked
@require_POST
def job_run(request, job):
    """Run now (roll-up or snapshot refresh): runs it, logs a job_run event, toasts the result."""
    if job not in services.RUNNABLE:
        raise Http404
    ok, message, seconds = services.run_job_now(job)
    audit.log_event(SystemEvent.JOB_RUN, request, user=request.user, outcome=SystemEvent.OK if ok else SystemEvent.FAILED,
                    detail={"job": job, "ok": ok, "duration_ms": int(seconds * 1000), "message": message},
                    sentence=f"{request.user.email} ran {services.RUNNABLE[job][1]} now: {'ok' if ok else 'failed'} ({seconds:.1f}s)")
    (messages.success if ok else messages.error)(request, message)
    return redirect("system_dashboard")


@unlocked
@require_GET
def audit_export(request):
    """The filtered audit feed as a CSV download (streamed; written to the log as an export event first)."""
    params = feed.params_from(request.GET)
    rows = feed.export_count(params)
    audit.log_event(SystemEvent.EXPORT, request, user=request.user, detail={"rows": rows, "filters": {k: v for k, v in params.items() if v}})
    response = StreamingHttpResponse(feed.export_rows(params), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="spa99-system-audit.csv"'
    response["Cache-Control"] = "no-store"
    return response


SCRIPT_CODE_ASK = "Enter the System code to undo a script change."


def _script_code_gate(request, section):
    """Undoing a script's change asks for the System code again. None = go ahead, else the JSON refusal. Same code check and
    same rate limit buckets as /unlock/ (so the two cannot be brute-forced side by side); wrong tries are written to the log."""
    if not services.code_required():
        return None  # no code configured (dev, CI): nothing to ask, the same as the unlock
    typed = request.POST.get("code", "")
    if not typed.strip():
        return JsonResponse({"ok": False, "needs_code": True, "message": SCRIPT_CODE_ASK}, status=403)
    by_ip = hit("system-unlock", f"{request.user.pk}:{client_ip(request) or 'unknown'}", 5, 300)
    by_person = hit("system-unlock-person", request.user.pk, 10, 900)
    if not (by_ip and by_person):
        audit.log_event(SystemEvent.UNDO_RATE_LIMITED, request, user=request.user, section=section, dedupe_seconds=300)
        return JsonResponse({"ok": False, "needs_code": True, "message": "Too many attempts. Please wait a few minutes."}, status=429)
    if not services.code_matches(typed):
        audit.log_event(SystemEvent.UNDO_CODE_FAILED, request, user=request.user, section=section)
        return JsonResponse({"ok": False, "needs_code": True, "message": "That code is wrong."}, status=403)
    return None


@unlocked
@require_POST
def undo(request, pk):
    change = get_object_or_404(SystemChange, pk=pk)
    script = services.made_by_script(change)
    if script and (refusal := _script_code_gate(request, change.section)):
        return refusal
    try:
        services.undo_change(change, request.user)  # the new entry's actor is whoever is signed in: the developer, not a script
        audit.log_event(SystemEvent.UNDO, request, user=request.user, section=change.section,
                        detail={"change": str(change.pk), "was": change.sentence, **({"script_change": True} if script else {})},
                        sentence=f"{request.user.email} undid: {change.sentence}"[:1000])
        messages.success(request, "Put back as a new change.")
    except services.ChangeRefused as error:
        messages.error(request, str(error))
    return redirect(safe_next(request, "system_changes"))


@unlocked
@require_POST
def undo_all(request, batch):
    entries = SystemChange.objects.filter(batch_id=batch)
    sections = set(entries.values_list("section", flat=True))
    script = entries.filter(kind=SystemChange.UPDATED, undo_of__isnull=True, undone_by__isnull=True, user__isnull=True, user_label="").exists()
    if script and (refusal := _script_code_gate(request, next(iter(sections)) if len(sections) == 1 else "changes")):
        return refusal
    done, refused = services.undo_batch(batch, request.user)
    if done:
        audit.log_event(SystemEvent.UNDO_ALL, request, user=request.user, section=sections.pop() if len(sections) == 1 else "changes",
                        detail={"batch": str(batch), "count": done, "refused": refused})
        messages.success(request, f"Put back {done} change{'s' if done != 1 else ''} as new changes.")
    for text in refused:
        messages.error(request, text)
    if not done and not refused:
        messages.info(request, "Nothing to undo.")
    return redirect(safe_next(request, "system_changes"))


def _edit_site(request, form_class, template, section, extra=None):
    site = SiteSettings.load()
    form = form_class(request.POST or None, instance=site)
    if request.method == "POST" and form.is_valid():
        try:
            if services.save_form(form, request.user):
                saved(request)
            else:
                messages.info(request, "Nothing changed.")
            return redirect(request.path)
        except ValidationError as error:  # a model rule, or the row changed since the page was made
            form.add_error(None, error)
    context = {"form": form, "risky_fields": RISKY.get(section, []), **(extra() if extra else {})}
    return page(request, template, section, context, status=form_status(form) if request.method == "POST" else 200)


@unlocked
@require_http_methods(["GET", "POST"])
def emails(request):
    from . import emails as emails_logic

    return _edit_site(request, EmailsForm, "system/emails.html", "emails", extra=lambda: emails_logic.overview(request))


@unlocked
@require_GET
def suppressions(request):
    return page(request, "system/suppressions.html", "suppressions", {"rows": EmailSuppression.objects.all()[:500]})


@unlocked
@require_POST
def suppression_remove(request, pk):
    row = get_object_or_404(EmailSuppression, pk=pk)
    try:
        services.remove_suppression(request, row)
        messages.success(request, "Removed. This address can be emailed again.")
    except services.ChangeRefused as error:
        messages.error(request, str(error))
    return redirect("system_suppressions")


@unlocked
@require_http_methods(["GET", "POST"])
def site_settings(request):
    return _edit_site(request, SettingsForm, "system/settings.html", "settings")


@unlocked
@require_GET
def team(request):
    context = {"staff": team_service.rows(request.user), "level_choices": team_service.level_choices(request.user)}
    return page(request, "system/team.html", "team", context)


def _team_action(request, action, text="Saved."):
    """Run a Team change; a refusal is shown as an error toast, never a crash."""
    try:
        action()
        saved(request, text)
    except services.ChangeRefused as error:
        messages.error(request, str(error))
    return redirect("system_team")


def _person(request, pk):
    return get_object_or_404(team_service.team_queryset(), pk=pk)  # team members only; members are managed in the Office


@unlocked
@require_POST
def team_access(request, pk):
    target, level = _person(request, pk), request.POST.get("level", "")
    return _team_action(request, lambda: team_service.set_access(request.user, target, level))


@unlocked
@require_POST
def team_active(request, pk):
    target = _person(request, pk)
    return _team_action(request, lambda: team_service.set_active(request.user, target, request.POST.get("active") == "1"))


@unlocked
@require_POST
def team_remove(request, pk):
    target = _person(request, pk)
    return _team_action(request, lambda: team_service.remove_from_team(request.user, target), "Removed from the team. Their account and any membership stay.")


@unlocked
@require_POST
def team_invite(request, pk):
    target = _person(request, pk)
    return _team_action(request, lambda: team_service.resend_invite(request.user, target), "A new invite is on its way.")


@unlocked
@require_POST
def team_add(request):
    email, level = request.POST.get("email", ""), request.POST.get("level", "")

    def run():
        user, created = team_service.add_member(request.user, email, level)
        messages.info(request, "An email is on its way for them to choose a password." if created else "They already had an account, so they keep their password.")
    return _team_action(request, run, "Added to the team.")


@unlocked
@require_http_methods(["GET", "POST"])
def team_merge(request):
    """Step 1 (GET with ?keep=&remove=, or POST): choose the two emails and see what would move. Step 2 (POST confirm=1) does it."""
    keep_email = request.POST.get("keep") or request.GET.get("keep", "")
    remove_email = request.POST.get("remove") or request.GET.get("remove", "")
    context = {"keep": keep_email, "remove": remove_email, "preview": None}
    if keep_email and remove_email:
        try:
            if request.method == "POST" and request.POST.get("confirm") == "1":
                keep, moved = team_service.merge_accounts(request.user, keep_email, remove_email)
                saved(request, f"Merged into {keep.email}.")
                return redirect("system_team")
            context["keep_user"], context["remove_user"], context["preview"] = team_service.merge_preview(request.user, keep_email, remove_email)
        except services.ChangeRefused as error:
            messages.error(request, str(error))
    return page(request, "system/team_merge.html", "team", context)


# ---------- approval: who approves Gold, and who gives the final approval ----------

@unlocked
@require_GET
def approval(request):
    return page(request, "system/approval.html", "approval", approval_service.context(request.user))


def _approval_action(request, action, text="Saved.", nothing="Nothing changed."):
    """Run an Approval change; a refusal is an error toast, never a crash."""
    try:
        done = action()
        saved(request, text) if done is not False else messages.info(request, nothing)
    except services.ChangeRefused as error:
        messages.error(request, str(error))
    return redirect("system_approval")


def _ids(request):
    return request.POST.getlist("user") or request.POST.getlist("users") or request.POST.getlist("user_ids")


@unlocked
@require_POST
def approval_add(request, role):
    return _approval_action(request, lambda: approval_service.add(request.user, role, _ids(request)), "Added.", "Nobody new to add.")


@unlocked
@require_POST
def approval_remove(request, role, pk):
    return _approval_action(request, lambda: approval_service.remove(request.user, role, pk), "Removed.")


@unlocked
@require_POST
def approval_delivery(request, pk):
    return _approval_action(request, lambda: approval_service.set_delivery(
        request.user, pk, request.POST.get("use_account_email") == "1", request.POST.get("other_email", "")), "Saved.")


# ---------- change password (behind the unlock) ----------

class SystemPasswordView(TeamPasswordView):
    template_name = "system/password.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        audit.log_event(SystemEvent.PASSWORD_CHANGED, self.request, user=self.request.user)  # never the password itself
        return response

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "section": "", "nav": NAV, "section_labels": changes.SECTION_LABELS}
