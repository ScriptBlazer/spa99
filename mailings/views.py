"""Public pages: the unsubscribe link and the personal invite link. No login, rate limited, nothing trusted beyond what the signed
token or the invite row says."""
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from common.audit import client_ip
from common.ratelimit import hit

from . import invites, optout, tokens


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


@login_not_required  # PUBLIC: the personal link in an invite. Sends the person to Register (opened is marked when Register renders).
@require_GET
def invite_link(request, token):
    """The session remembers the invite so Register can pre-fill name and email (and mark it opened when it renders). A link that is unknown, expired or not sent yet
    looks the same as a good one: the person lands on Register."""
    if not hit("invite-link", client_ip(request) or "unknown", 60, 60):
        return _message(request, "Please wait", "Too many attempts. Please try again in a minute.", status=429)
    invite = invites.good_invite(token)
    if invite is not None:
        request.session[invites.SESSION_KEY] = invite.token
    return redirect("register")
