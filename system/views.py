"""System pages: short views; logic in services.py. Templates are minimal with stable data-system-* hooks (the design
brief is docs/design/SYSTEM.md). Every page except sign-in goes through `signed_in` or `unlocked` (404 for strangers)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.audit import client_ip
from common.ratelimit import hit
from plans.models import SiteSettings
from users.views import LoginView

from . import changes, services
from .forms import EmailsForm, SettingsForm
from .models import SystemChange
from .permissions import signed_in, unlocked

NAV = [("dashboard", "Dashboard", "system_dashboard"), ("plans", "Plans and pricing", "system_plans"), ("hours", "Hours and closures", "system_hours"),
       ("gold", "Gold rules", "system_gold"), ("journey", "Journey", "system_journey"), ("emails", "Emails", "system_emails"),
       ("settings", "Settings", "system_settings"), ("changes", "Change log", "system_changes"), ("team", "Team", "system_team")]


def page(request, template, section, context=None, status=200):
    """Render a System page with the navigation (stubs have no link yet)."""
    context = {"section": section, "nav": NAV, "section_labels": changes.SECTION_LABELS, **(context or {})}
    return render(request, template, context, status=status)


def safe_next(request, default):
    """The `next` value if it is a path on this host, else the default."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target.startswith("/") and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return default


# ---------- sign-in, unlock, lock ----------

class SystemAuthForm(AuthenticationForm):
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
        self.request.session.set_expiry(settings.SYSTEM_SESSION_AGE)
        self.request.session[services.SIGNED_IN_KEY] = True
        services.lock(self.request.session)
        return response


@signed_in
@require_http_methods(["GET", "POST"])
def unlock(request):
    target = safe_next(request, "/")
    error = ""
    if request.method == "POST":
        if not hit("system-unlock", f"{request.user.pk}:{client_ip(request) or 'unknown'}", 5, 300):
            return render(request, "system/unlock.html", {"next": target, "error": "Too many attempts. Please wait a few minutes."}, status=429)
        if request.user.check_password(request.POST.get("password", "")):
            services.unlock(request.session)
            return redirect(target)
        error = "That password is not right."
    return render(request, "system/unlock.html", {"next": target, "error": error})


@signed_in
@require_POST
def lock(request):
    services.lock(request.session)
    return redirect("system_unlock")


@require_POST
@login_not_required  # sign out is harmless for anyone, and a locked-out person must always be able to leave
def sign_out(request):
    logout(request)
    return redirect("login")


# ---------- pages ----------

@unlocked
@require_GET
def dashboard(request):
    site = SiteSettings.load()
    context = {"health": services.health_report(), "recent": services.recent_changes(10), "site": site,
               "stages": [("Register interest", site.register_interest_open), ("Subscribe", site.subscribe_open), ("Book", site.booking_open)]}
    return page(request, "system/dashboard.html", "dashboard", context)


@unlocked
@require_GET
def change_log(request):
    params = {key: request.GET.get(key, "") for key in ("section", "user", "date_from", "date_to")}
    entries = services.change_list(params, request.GET.get("page"))
    return page(request, "system/changes.html", "changes", {"entries": entries, "params": params})


@unlocked
@require_POST
def undo(request, pk):
    change = get_object_or_404(SystemChange, pk=pk)
    try:
        services.undo_change(change, request.user)
        messages.success(request, "Put back as a new change.")
    except services.ChangeRefused as error:
        messages.error(request, str(error))
    return redirect(safe_next(request, "system_changes"))


def _edit_site(request, form_class, template, section):
    site = SiteSettings.load()
    form = form_class(request.POST or None, instance=site)
    if request.method == "POST" and form.is_valid():
        if form.changed_data:
            services.save_logged(form.instance, request.user, fields=form.changed_data)
            messages.success(request, "Saved.")
        else:
            messages.info(request, "Nothing changed.")
        return redirect(request.path)
    return page(request, template, section, {"form": form}, status=400 if request.method == "POST" else 200)


@unlocked
@require_http_methods(["GET", "POST"])
def emails(request):
    return _edit_site(request, EmailsForm, "system/emails.html", "emails")


@unlocked
@require_http_methods(["GET", "POST"])
def site_settings(request):
    return _edit_site(request, SettingsForm, "system/settings.html", "settings")


@unlocked
@require_GET
def team(request):
    return page(request, "system/team.html", "team", {"staff": services.staff_users(), "roles": services.ROLES})


def _team_action(request, pk, action):
    from django.contrib.auth import get_user_model

    target = get_object_or_404(get_user_model(), pk=pk, is_staff=True)
    try:
        action(target)
        messages.success(request, "Saved.")
    except services.ChangeRefused as error:
        messages.error(request, str(error))
    return redirect("system_team")


@unlocked
@require_POST
def team_roles(request, pk):
    return _team_action(request, pk, lambda target: services.set_roles(request.user, target, request.POST.getlist("roles")))


@unlocked
@require_POST
def team_active(request, pk):
    return _team_action(request, pk, lambda target: services.set_active(request.user, target, request.POST.get("active") == "1"))
