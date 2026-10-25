"""Public account views: sign-up (register interest), verification, password reset, login, account page.
Logic is in services.py. The templates are bare placeholders for the frontend to replace; keep the context
names and form field names.
"""
from functools import wraps

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from common.audit import client_ip
from common.ratelimit import hit, rate_limited_json
from common.validators import normalise_email
from journey import services as journey_services
from pages import services as pages_services
from plans import services as plan_services
from plans.models import SiteSettings

from . import member, services, tokens
from .forms import ChangePasswordForm, ForgotPasswordForm, ResetPasswordForm, SignInForm, SignUpForm
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


STAFF_URLCONFS = ("config.urls_office", "config.urls_control", "config.urls_system")


class LoginView(auth_views.LoginView):
    """Public sign-in (Django marks LoginView as login_not_required). Limited to 10 attempts per 5 minutes per IP."""

    template_name = "users/login.html"
    authentication_form = SignInForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_login_layout(self.request))
        return context

    def get_default_redirect_url(self):
        """Members land on their dashboard (LOGIN_REDIRECT_URL, /account/); the staff hosts (Office, Control, System)
        land on their own home page, which is "/" on each host. A safe `next` still wins (Django checks it first)."""
        if getattr(self.request, "urlconf", "") in STAFF_URLCONFS:
            return "/"
        return super().get_default_redirect_url()

    def form_valid(self, form):
        """Shared device: if the journey cookie holds someone else's session, drop it so this person starts fresh;
        an anonymous session just becomes theirs."""
        user = form.get_user()
        foreign = journey_services.cookie_belongs_to_someone_else(self.request.COOKIES, user)
        mine = None if foreign else journey_services.session_from_cookies(self.request.COOKIES, user)
        response = super().form_valid(form)
        if getattr(self.request, "urlconf", "") == "config.urls_office":  # Office only: set on this session, not site-wide
            self.request.session.set_expiry(settings.OFFICE_SESSION_AGE)
        journey_services.link_user(mine, user)
        return _forget_journey_cookie(response) if foreign else response

    def post(self, request, *args, **kwargs):
        if _throttled(request, "login", 10, 300):
            context = {"form": self.get_form_class()(request), "throttled": True, **_login_layout(request)}
            return render(request, self.template_name, context, status=429)
        return super().post(request, *args, **kwargs)


class LogoutView(auth_views.LogoutView):
    """Sign out (POST only). The journey cookie goes too, so the next person on this device starts a new journey."""

    def get_success_url(self):
        """Visitors on the public site land on the home page; the staff hosts keep LOGOUT_REDIRECT_URL (their sign-in)."""
        if getattr(self.request, "urlconf", "") in STAFF_URLCONFS:
            return super().get_success_url()
        return reverse("home")

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if getattr(request, "urlconf", "") not in STAFF_URLCONFS:
            messages.success(request, "You're signed out.")  # added after the session was cleared, so it shows on the next page
        return _forget_journey_cookie(response)


# ---------- register interest ----------

def _confirm_tier(request, slug):
    """A signed-in person arrives from a public page with ?plan=: nothing is saved on a GET. Already theirs or Gold goes
    straight to the dashboard; otherwise a one-button confirm screen that POSTs to account_interest."""
    plan = services.interest_plans().filter(slug=slug).first()
    if plan is None:
        return redirect("account")
    interest = getattr(request.user, "interest", None)
    if interest is not None and interest.plan_id == plan.pk:
        messages.info(request, f"{plan.name} is already your membership.")
        return redirect("account")
    if interest is not None and interest.plan is not None and interest.plan.slug == "gold":
        _tier_message(request, "gold", interest.plan)
        return redirect("account")
    site = SiteSettings.load()
    card = pages_services.plan_card(plan, site.vat_rate, plan_services.hours_ranges())
    return render(request, "users/choose_confirm.html", {**member.base_context(request.user), "plan": plan, "card": card})


REGISTER_LABELS = {
    "plan": "Membership", "first_name": "First name", "last_name": "Last name", "email": "Email", "mobile": "Mobile",
    "password": "Password", "date_of_birth": "Date of birth", "men_only_accepted": "Men-only policy", "privacy_accepted": "Privacy notice",
}


def _wants_json(request):
    """The register page sends its form with fetch so a mistake never reloads it (and empties the password)."""
    return request.headers.get("X-Requested-With") == "fetch" or "application/json" in request.headers.get("Accept", "")


def _register_errors(form):
    """[{field, label, message}] in page order (membership first), one entry per field; the same wording as the page."""
    order = ["plan", *[name for name in form.fields if name != "plan"]]
    out = []
    for name in order:
        texts = [text for text in form.errors.get(name, [])]
        if texts:
            out.append({"field": name, "label": REGISTER_LABELS.get(name, ""), "message": " ".join(texts)})
    if form.non_field_errors():
        out.append({"field": "__all__", "label": "", "message": " ".join(form.non_field_errors())})
    return out


def _register_json_failure(message, status):
    return JsonResponse({"ok": False, "errors": [{"field": "__all__", "label": "", "message": message}]}, status=status)


@login_not_required  # PUBLIC: anyone can register interest
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:  # every "choose this tier" link ends here (compare page, journey result, Gold page): save it
        return _confirm_tier(request, request.GET.get("plan", ""))
    as_json = request.method == "POST" and _wants_json(request)
    if not SiteSettings.load().register_interest_open:
        if as_json:
            return _register_json_failure("Registration is not open yet.", 403)
        return _message(request, "Not open yet", "Registration is not open yet.", status=403)
    session = journey_services.session_from_cookies(request.COOKIES, request.user)
    suggested = session.suggested_plan.slug if session and session.suggested_plan_id else ""
    plan_slug = services.interest_plan_slug(request.GET.get("plan")) or services.interest_plan_slug(suggested)
    plans = services.interest_plans()
    if request.method == "POST":
        if _throttled(request, "register", 20, 3600):
            if as_json:
                return _register_json_failure("Too many attempts. Please try again later.", 429)
            return _message(request, "Please wait", "Too many attempts. Please try again later.", status=429)
        form = SignUpForm(request.POST)
        if request.POST.get(HONEYPOT_FIELD):  # a bot: look like success, create nothing
            if as_json:
                return JsonResponse({"ok": True, "redirect": reverse("register_sent")})
            return redirect("register_sent")
        if form.is_valid():
            try:
                result = services.register_interest(form.cleaned_data, journey_session=session)
            except services.SignUpError as error:
                for field, texts in error.errors.items():
                    for text in texts:
                        form.add_error(field if field in form.fields else None, text)
            except services.RegistrationClosed:
                if as_json:
                    return _register_json_failure("Registration is not open yet.", 403)
                return _message(request, "Not open yet", "Registration is not open yet.", status=403)
            else:
                request.session[PENDING_EMAIL_KEY] = result.user.email
                if as_json:
                    return JsonResponse({"ok": True, "redirect": reverse("register_sent")})
                return redirect("register_sent")
        if as_json:
            return JsonResponse({"ok": False, "errors": _register_errors(form)}, status=400)
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

def member_area(view):
    """Only people with a membership (and superusers) open the member area; anyone else signed in gets a calm page that
    says so, with a link back to the website (never a 404: they are signed in and did nothing wrong)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not member.can_open(request.user):
            return render(request, "users/no_membership.html", {"email": request.user.email})
        return view(request, *args, **kwargs)
    return wrapper


def _screen(template, build):
    """A signed-in member screen: GET only, the login lock applies. `build(user)` returns the context."""

    @member_area
    @require_GET
    def view(request):
        return render(request, template, build(request.user))

    return view


account = _screen("users/account_home.html", member.home_context)
account_book = _screen("users/account_book.html", member.book_context)
account_membership = _screen("users/account_membership.html", member.membership_context)
account_you = _screen("users/account_you.html", member.you_context)


@login_not_required  # PUBLIC: only redirects (the old password address); the new one is behind the login lock
def password_change_old(request):
    return HttpResponseRedirect(reverse("password_change"), status=307)  # 307 keeps the method, so an old form post still lands


@member_area
@require_POST
def account_emails(request):
    """Marketing emails on or off (UK GDPR consent, logged in the person's history). 20 a minute per person."""
    wants_json = "application/json" in request.headers.get("accept", "")
    if not hit("account-emails", request.user.pk, 20, 60):
        if wants_json:
            return JsonResponse({"saved": False}, status=429)
        messages.error(request, "Too many changes. Please try again in a minute.")
        return redirect("account_you")
    on = request.POST.get("marketing", "") in ("1", "on", "true")
    member.set_marketing_consent(request.user, on)
    if wants_json:
        return JsonResponse({"saved": True, "marketing": on})
    messages.success(request, "Saved.")
    return redirect("account_you")


class _PasswordChange(auth_views.PasswordChangeView):
    """Change password (signed in). Limited to 10 attempts an hour per IP, so a stolen session cannot be used to guess the
    current password."""

    form_class = ChangePasswordForm

    def post(self, request, *args, **kwargs):
        if _throttled(request, "password-change", 10, 3600):
            return _message(request, "Please wait", "Too many attempts. Please try again later.", status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Your password has been changed.")
        return super().form_valid(form)  # keeps this session signed in


class ChangePasswordView(_PasswordChange):
    """The member area's change password (members only)."""

    template_name = "users/password_change.html"
    success_url = reverse_lazy("account_you")

    @method_decorator(member_area)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        # the member shell (verify banner, greeting, email) needs the same base context as the other screens
        return {**member.base_context(self.request.user), **super().get_context_data(**kwargs)}


class TeamPasswordView(_PasswordChange):
    """Change password for team members on the Office and System hosts (they may hold no membership, so no member area).
    The caller's access check wraps this view; it lands back on `/password/` of the same host."""

    success_url = "/password/"


def _tier_message(request, outcome, plan):
    if outcome == "gold":
        messages.info(request, "Your Gold Card is active. To change it, write to us.")  # Gold is never replaced by an interest choice
    elif outcome == "invalid":
        messages.error(request, "Choose one of the memberships.")
    elif outcome == "same":
        messages.info(request, f"{plan.name} is already your membership.")
    else:
        messages.success(request, f"Saved. Your membership is {plan.name}.")
    return outcome


@require_POST  # any signed-in person (the login lock applies): choosing a tier is what gives a member area to someone without one
def account_interest(request):
    outcome = _tier_message(request, *services.choose_tier(request.user, request.POST.get("plan", "")))
    if outcome == "invalid":
        return redirect("account_membership" if member.can_open(request.user) else "memberships")
    return redirect("account")


@member_area
@require_GET
def account_export(request):
    """Download everything we hold about the signed-in person (UK GDPR)."""
    response = JsonResponse(services.export_user_data(request.user), json_dumps_params={"indent": 2})
    response["Content-Disposition"] = 'attachment; filename="spa99-my-data.json"'
    return response


@member_area
@require_POST
def account_delete(request):
    """Delete the signed-in person's data after they re-enter their password."""
    user = request.user
    if authenticate(request, username=user.email, password=request.POST.get("password", "")) is None:
        messages.error(request, "That password is not right.")
        return redirect("account_you")
    logout(request)
    services.delete_user_data(user)
    return _forget_journey_cookie(_message(request, "Account deleted", "Your account and data have been deleted."))
