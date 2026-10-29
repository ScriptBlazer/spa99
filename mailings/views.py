"""Public pages: the unsubscribe link and the personal invite link. No login, rate limited, nothing trusted beyond what the signed
token or the invite row says."""
from django.contrib.auth.decorators import login_not_required
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from common.audit import client_ip
from common.ratelimit import hit
from system import defaults

from . import invites, optout, tokens
from .models import MailingImage


def _message(request, title, text, status=200):
    return render(request, "users/message.html", {"title": title, "text": text}, status=status)


def _mask(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 2)}@{domain}"


@login_not_required  # PUBLIC: the link in every news email. Signed token, no expiry; the only effect is turning that address's news off.
@csrf_exempt  # mail clients POST here for the one-click header (RFC 8058) with no session or CSRF cookie; the signed token is the proof
@require_http_methods(["GET", "POST"])
def unsubscribe(request, token):
    """GET shows a confirm page (a mail scanner opening the link changes nothing); POST (the button, or a mail client's one-click)
    switches news off. Idempotent."""
    if not hit("unsubscribe", client_ip(request) or "unknown", 30, 60):
        return _message(request, "Please wait", "Too many attempts. Please try again in a minute.", status=429)
    email = tokens.read_unsubscribe_token(token)
    if email is None:
        return _message(request, "Link not valid", "This unsubscribe link is not valid. Reply to any Spa 99 email and we will stop them for you.", status=400)
    if request.method == "POST":
        result = optout.unsubscribe(email)
        return render(request, "mailings/unsubscribe.html", {"done": True, "email": _mask(email), "has_account": result["account"], "token": token})
    return render(request, "mailings/unsubscribe.html", {"done": False, "email": _mask(email), "token": token})


@login_not_required  # PUBLIC: the personal link in an invite. Marks it opened, then sends the person to the questionnaire or Register (System > Defaults).
@require_GET
def invite_link(request, token):
    """The session remembers the invite so the questionnaire's email step and Register can pre-fill name and email. A link that is unknown,
    expired or not sent yet looks the same as a good one: same redirect, nothing remembered."""
    if not hit("invite-link", client_ip(request) or "unknown", 60, 60):
        return _message(request, "Please wait", "Too many attempts. Please try again in a minute.", status=429)
    invite = invites.good_invite(token)
    if invite is not None:
        request.session[invites.SESSION_KEY] = invite.token
        invites.mark_opened(invite)  # a real click (SENT only, once); a mail scanner's GET also counts, an accepted limit
    to = request.GET.get("to")  # a button in a group mailing picks its own destination; anything else uses the System > Defaults choice
    if to not in ("journey", "register"):
        to = defaults.get(request).invite_landing
    return redirect("register" if to == "register" else "journey")


@login_not_required  # PUBLIC: pictures in emails. Mail clients (and their image proxies) fetch these with no session. The id is a random UUID.
@require_GET
def email_image(request, image_id, ext=""):
    """/email-image/<id>.<ext> or /email-image/<id>/ (the extension in the address is only for caches; the real type comes from the row).
    Stream an uploaded email picture from the (private) media storage. Never changes, so it is cached for a year."""
    # No rate limit on purpose: Gmail and Outlook fetch through shared proxy addresses, so after a big send one IP legitimately asks for the
    # same picture thousands of times, and a limit would break the images for real people. It is a primary-key lookup of a random UUID
    # (an unknown id is a fast 404) and a cached read; the one-year cache header keeps repeat traffic away.
    image = MailingImage.objects.filter(pk=image_id).first()
    if image is None:
        raise Http404
    try:
        handle = image.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404 from None
    response = FileResponse(handle, content_type=image.content_type)
    response["Content-Length"] = image.size
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response
