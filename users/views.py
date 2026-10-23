"""Public account views: sign-up (register interest), verification, password reset, login, account page.
Logic is in services.py. The templates are bare placeholders for the frontend to replace; keep the context
names and form field names.
"""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.audit import client_ip
from common.ratelimit import hit, rate_limited_json
from common.validators import normalise_email
from gold import invites as gold_invites
from insights import visitors
from journey import services as journey_services
from plans.models import SiteSettings

from . import services, tokens
from .forms import ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm, SignUpForm
from .models import User

PENDING_EMAIL_KEY = "pending_verification_email"
HONEYPOT_FIELD = "website"
BACKEND = "django.contrib.auth.backends.ModelBackend"


def _message(request, title, text, status=200):
    return render(request, "users/message.html", {"title": title, "text": text}, status=status)


def _throttled(request, scope, limit, window):
    """True (and the caller should stop) when this IP has done too much."""
    return not hit(scope, client_ip(request) or "unknown", limit, window)


# ---------- login ----------

def _login_layout(request):
    """The sign-in template is shared by the public site, the Office and Spa 99 Control. Control has no public pages, so it
    gets the bare layout (the site header links would not resolve there)."""
    if getattr(request, "urlconf", "") == "config.urls_office":  # the Office: the same shell, its own words, no public links
        return {"layout": "base_bare.html", "control": False, "office": True}
    try:
        reverse("home")
    except NoReverseMatch:
        return {"layout": "base_bare.html", "control": True}
    return {"layout": "base.html", "control": False}

def _forget_journey_cookie(response):
    response.delete_cookie(journey_services.COOKIE_NAME, path="/", samesite="Lax")
    return response


class LoginView(auth_views.LoginView):
    """Public sign-in (Django marks LoginView as login_not_required). Limited to 10 attempts per 5 minutes per IP."""

    template_name = "users/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_login_layout(self.request))
        return context

    def form_valid(self, form):
        """Shared device: if the journey cookie holds someone else's session, drop it so this person starts fresh;
        an anonymous session just becomes theirs."""
        user = form.get_user()
        foreign = journey_services.cookie_belongs_to_someone_else(self.request.COOKIES, user)
        mine = None if foreign else journey_services.session_from_cookies(self.request.COOKIES, user)
        response = super().form_valid(form)
        journey_services.link_user(mine, user)
        return _forget_journey_cookie(response) if foreign else response

    def post(self, request, *args, **kwargs):
        if _throttled(request, "login", 10, 300):
            context = {"form": self.get_form_class()(request), "throttled": True, **_login_layout(request)}
            return render(request, self.template_name, context, status=429)
        return super().post(request, *args, **kwargs)


class LogoutView(auth_views.LogoutView):
    """Sign out (POST only). The journey cookie goes too, so the next person on this device starts a new journey."""

    def post(self, request, *args, **kwargs):
        return _forget_journey_cookie(super().post(request, *args, **kwargs))


# ---------- register interest ----------

@login_not_required  # PUBLIC: anyone can register interest
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("account")
    if not SiteSettings.load().register_interest_open:
        return _message(request, "Not open yet", "Registration is not open yet.", status=403)
    session = journey_services.session_from_cookies(request.COOKIES, request.user)
    suggested = session.suggested_plan.slug if session and session.suggested_plan_id else ""
    plan_slug = services.interest_plan_slug(request.GET.get("plan")) or services.interest_plan_slug(suggested)
    plans = services.interest_plans()
    if request.method == "POST":
        if _throttled(request, "register", 20, 3600):
            return _message(request, "Please wait", "Too many attempts. Please try again later.", status=429)
        form = SignUpForm(request.POST)
        if request.POST.get(HONEYPOT_FIELD):  # a bot: look like success, create nothing
            return redirect("register_sent")
        if form.is_valid():
            try:
                result = services.register_interest(form.cleaned_data, journey_session=session)
            except services.SignUpError as error:
                for field, texts in error.errors.items():
                    for text in texts:
                        form.add_error(field if field in form.fields else None, text)
            except services.RegistrationClosed:
                return _message(request, "Not open yet", "Registration is not open yet.", status=403)
            else:
                request.session[PENDING_EMAIL_KEY] = result.user.email
                visitors.record_step(request, "registered")
                return redirect("register_sent")
        status = 400
    else:
        form, status = SignUpForm(initial={"plan": plan_slug}), 200
    context = {"form": form, "plans": plans, "selected_plan": plan_slug, "suggested_plan": suggested, "from_journey": bool(session and session.completed)}
    return render(request, "users/register.html", context, status=status)


@login_not_required  # PUBLIC: the 'check your email' screen after sign-up
@require_GET
def register_sent(request):
    return render(request, "users/register_sent.html", {"email": request.session.get(PENDING_EMAIL_KEY, "")})


@login_not_required  # PUBLIC on purpose: live 'already registered' check; answers yes/no only, rate limited.
# POST (with the CSRF token) so the address never appears in a URL or an access log
@require_POST
@rate_limited_json("check-email", 30, 60)
def check_email(request):
    try:
        email = normalise_email(request.POST.get("email", ""))
    except ValidationError:
        return JsonResponse({"registered": False})  # the format message comes from the field check
    return JsonResponse({"registered": services.email_is_registered(email)})


# ---------- verification ----------

def _verify_result(request, status, user):
    if status == tokens.VERIFIED:
        login(request, user, backend=BACKEND)
        messages.success(request, "Your email is confirmed.")
        return redirect("account")
    if status == tokens.ALREADY:
        return _message(request, "Already confirmed", "This email is already confirmed. You can sign in.")
    if status == tokens.EXPIRED:
        return _message(request, "Link expired", "This link has expired. Sign in and ask for a new one.", status=410)
    return _message(request, "Link not valid", "This link is not valid.", status=400)


@login_not_required  # PUBLIC: the link in the verification email (signed, expires, single use)
@require_http_methods(["GET", "POST"])
def verify_email(request, token):
    """GET only shows a 'Confirm my email' button, so a mail scanner opening the link uses nothing up; POST confirms
    and signs the person in."""
    if request.method == "POST":
        return _verify_result(request, *services.verify_email(token))
    status, user = tokens.read_verify_token(token)
    if user is not None and not user.email_verified_at:
        return render(request, "users/verify_confirm.html", {"first_name": user.first_name})
    return _verify_result(request, tokens.ALREADY if user is not None else status, user)


@login_not_required  # PUBLIC: asks for a new link; same answer whoever asks, rate limited
@require_POST
def resend_verification(request):
    if _throttled(request, "resend-verify", 5, 3600):
        return _message(request, "Please wait", "Too many requests. Please try again later.", status=429)
    email = request.user.email if request.user.is_authenticated else request.session.get(PENDING_EMAIL_KEY, "")
    user = User.objects.filter(email__iexact=email).first() if email else None
    services.resend_verification(user)
    return _message(request, "Check your email", "If the address needs confirming, a new link is on its way.")


# ---------- password reset ----------

@login_not_required  # PUBLIC: forgot password; the answer never says whether the email exists
@require_http_methods(["GET", "POST"])
def forgot_password(request):
    if request.method == "POST":
        if _throttled(request, "forgot", 5, 3600):
            return _message(request, "Please wait", "Too many requests. Please try again later.", status=429)
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            services.request_password_reset(form.cleaned_data["email"])
            return _message(request, "Check your email", "If that address has an account, a reset link is on its way.")
    else:
        form = ForgotPasswordForm()
    return render(request, "users/forgot.html", {"form": form})


@login_not_required  # PUBLIC: the link in the reset email (token, 1 hour, single use)
@require_http_methods(["GET", "POST"])
def reset_password(request, uidb64, token):
    if tokens.read_reset_token(uidb64, token) is None:
        return _message(request, "Link not valid", "This link has expired or was already used.", status=400)
    form = ResetPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.reset_password(uidb64, token, form.cleaned_data["password"])
        except ValidationError as error:
            form.add_error("password", error)
        else:
            return _message(request, "Password changed", "Your password has been changed. You can sign in.")
    return render(request, "users/reset.html", {"form": form}, status=400 if request.method == "POST" else 200)


# ---------- account (signed in; the default login lock applies) ----------

@require_http_methods(["GET"])
def account(request):
    interest = getattr(request.user, "interest", None)
    gold = interest is not None and interest.plan is not None and interest.plan.slug == "gold"
    return render(request, "users/account.html", {
        "interest": interest, "plans": services.interest_plans(), "verified": bool(request.user.email_verified_at),
        "gold_since": gold_invites.gold_since(request.user) if gold else None, "is_gold": gold,
    })


class ChangePasswordView(auth_views.PasswordChangeView):
    """Change password (signed in; the default login lock applies). Limited to 10 attempts an hour per IP, so a
    stolen session cannot be used to guess the current password."""

    template_name = "users/password_change.html"
    form_class = ChangePasswordForm
    success_url = reverse_lazy("account")

    def post(self, request, *args, **kwargs):
        if _throttled(request, "password-change", 10, 3600):
            return _message(request, "Please wait", "Too many attempts. Please try again later.", status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Your password has been changed.")
        return super().form_valid(form)  # keeps this session signed in


@require_POST
def account_interest(request):
    plan = services.interest_plans().filter(slug=request.POST.get("plan", "")).first()
    current = getattr(request.user, "interest", None)
    if current is not None and current.plan is not None and current.plan.slug == "gold":
        messages.info(request, "Your Gold Card is active. To change it, write to us.")  # Gold is never replaced by an interest choice
    elif plan is None:
        messages.error(request, "Choose one of the memberships.")
    else:
        services.set_interest(request.user, plan)
        messages.success(request, "Your interest is updated.")
    return redirect("account")


@require_GET
def account_export(request):
    """Download everything we hold about the signed-in person (UK GDPR)."""
    response = JsonResponse(services.export_user_data(request.user), json_dumps_params={"indent": 2})
    response["Content-Disposition"] = 'attachment; filename="spa99-my-data.json"'
    return response


@require_POST
def account_delete(request):
    """Delete the signed-in person's data after they re-enter their password."""
    user = request.user
    if authenticate(request, username=user.email, password=request.POST.get("password", "")) is None:
        messages.error(request, "That password is not right.")
        return redirect("account")
    logout(request)
    services.delete_user_data(user)
    return _forget_journey_cookie(_message(request, "Account deleted", "Your account and data have been deleted."))
