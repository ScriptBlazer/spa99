"""System > Launch (Developer, unlocked, CSRF, audited): one page, one button. The work and the safety are in system/launch.py;
the typed-word confirm is the page's `data-system-confirm` form, and the server checks the word itself (it works without JS)."""
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from plans.models import SiteSettings

from . import launch
from .permissions import unlocked
from .views import page


@unlocked
@require_http_methods(["GET", "POST"])
def launch_page(request):
    if request.method == "POST":
        if request.POST.get("confirm") != launch.WORD:
            messages.error(request, f"Type {launch.WORD} exactly to launch. Nothing was changed.")
        else:
            result = launch.launch(request.user)
            if result.get("payments_failed"):
                send = messages.error
            else:
                send = messages.success if result["launched"] else messages.info
            send(request, result["message"])
        return redirect("system_launch")
    site = SiteSettings.load()
    last = launch.last_launch() if site.launched_at else None
    context = {"site": site, "steps": launch.plan(site), "checks": launch.checks(site), "word": launch.WORD,
               "launched_text": launch.when_text(site.launched_at) if site.launched_at else "", "launched_by": site.launched_by,
               "changed": (last.detail.get("changed") if last else []) or [], "payments_left": bool(last and last.detail.get("payments") != "opened")}
    return page(request, "system/launch.html", "launch", context)
