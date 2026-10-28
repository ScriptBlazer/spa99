"""System > Defaults: one page of editable defaults, grouped by area (Developer level, behind the unlock, like Settings).
Saved through the same path as Settings (change log, audit, undo). Reset to default restores one row's code value."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods, require_POST

from . import defaults, forms_defaults as f, services
from .models import SiteDefaults
from .permissions import unlocked
from .views import form_status, page, saved

SNAPSHOT_FIELDS = {"analytics_options", "top_pages"}  # stored in the Analytics snapshots: a change shows at the next refresh


def _refresh_snapshots(changed):
    if SNAPSHOT_FIELDS & set(changed):
        from office import snapshots

        snapshots.request_refresh()


def _context(form):
    groups = [{"title": title, "rows": [{"field": form[name], "unit": unit, "hint": f.hint(name),
                                         "is_default": form.initial.get(name) == SiteDefaults.code_default(name)} for name, unit in rows]}
              for title, rows in f.GROUPS]
    return {"form": form, "groups": groups, "risky_fields": f.RISKY}


@unlocked
@require_http_methods(["GET", "POST"])
def defaults_page(request):
    form = f.DefaultsForm(request.POST or None, instance=SiteDefaults.load())
    if request.method == "POST" and form.is_valid():
        try:
            changed = list(form.changed_data)
            if services.save_form(form, request.user):
                _refresh_snapshots(changed)
                defaults.forget(request)
                saved(request)
            else:
                messages.info(request, "Nothing changed.")
            return redirect("system_defaults")
        except ValidationError as error:  # a model rule, or the row changed since the page was made
            form.add_error(None, error)
    return page(request, "system/defaults.html", "defaults", _context(form), status=form_status(form) if request.method == "POST" else 200)


@unlocked
@require_POST
def defaults_reset(request):
    name = request.POST.get("field", "")
    if name not in f.FIELDS:
        messages.error(request, "That default does not exist.")
        return redirect("system_defaults")
    with transaction.atomic():
        row = SiteDefaults.objects.select_for_update().get(pk=SiteDefaults.load().pk)
        if getattr(row, name) == SiteDefaults.code_default(name):
            messages.info(request, "Already at the default.")
            return redirect("system_defaults")
        setattr(row, name, SiteDefaults.code_default(name))
        services.save_logged(row, request.user, fields=[name])
    _refresh_snapshots([name])
    defaults.forget(request)
    saved(request, "Reset to the default.")
    return redirect("system_defaults")
