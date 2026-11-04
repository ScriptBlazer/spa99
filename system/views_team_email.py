"""System > Team > Email: a team member's sending address and signature for Office emails (docs/features/office-email-chat.md, "Who an Office email comes from"). Same level as the other Team
changes (Developer, unlocked); a person may edit his own. The preview is a sandboxed `srcdoc` frame filled by a form POST (no script): what is typed is cleaned the way a send cleans it."""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from common import richtext
from emailchat import direct
from emailchat import sender as sender_mod

from . import team as team_service
from .permissions import unlocked
from .services import ChangeRefused
from .views import page, saved

PREVIEW_CSS = ("body{margin:0;padding:16px;background:#FBF9EC;color:#492E21;font:16px/26px 'Segoe UI',Helvetica,Arial,sans-serif}"
               ".e-sig>table{width:100% !important;max-width:600px !important}.e-sig img{max-width:100% !important;height:auto !important}")


def _target(request, pk):
    return get_object_or_404(team_service.team_queryset(), pk=pk)


def preview_document(target, signature):
    """The signature as typed (cleaned, our own pictures made absolute), or the plain sign-off when it is empty, as a small page for the preview frame (`srcdoc`: the System host sends
    frame-ancestors 'none' on every response, so a frame cannot load a page of its own; the frame is sandboxed, with no scripts)."""
    html = richtext.absolute_images(richtext.clean_signature(signature), settings.SITE_URL)
    body = f'<div class="e-sig">{html}</div>' if html else sender_mod.sign_off(target)[0]  # nothing typed: the plain sign-off that would go out
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{PREVIEW_CSS}</style></head><body>{body}</body></html>'


def _context(target, sending_address, signature, errors=None, preview=False):
    sender = sender_mod.sender_for(target)
    inbox = direct.inbox_address(team_service.email_sender_of(target))
    return {"person": target, "sending_address": sending_address, "signature": signature, "errors": errors or {}, "domain": sender_mod.sending_domain(),
            "preview_doc": preview_document(target, signature) if preview else "",
            "from_now": sender_mod.format_address(sender.address, sender.name), "from_source": sender.source, "own_ok": sender_mod.on_sending_domain(target.email),
            "inbox_address": inbox, "inbox_domain_set": bool(settings.EMAIL_INBOUND_DOMAIN)}


@unlocked
@require_http_methods(["GET", "POST"])
def team_email(request, pk):
    """GET the form. POST saves (a refused value shows its message and keeps what was typed); POST with `preview` saves nothing and shows the signature as typed."""
    target = _target(request, pk)
    row = team_service.email_sender_of(target)
    if request.method == "POST":
        address, signature = request.POST.get("sending_address", ""), request.POST.get("signature", "")
        if request.POST.get("preview"):
            return page(request, "system/team_email.html", "team", _context(target, address, signature, preview=True))
        try:
            changed, errors = team_service.save_email_sender(request.user, target, address, signature)
        except ChangeRefused as error:
            messages.error(request, str(error))
            return redirect("system_team")
        if not errors:
            saved(request, "Saved." if changed else "Nothing changed.")
            return redirect("system_team_email", pk=target.pk)
        return page(request, "system/team_email.html", "team", _context(target, address, signature, errors), status=400)
    return page(request, "system/team_email.html", "team", _context(target, row.sending_address if row else "", row.signature_html if row else ""))
