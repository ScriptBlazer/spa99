"""System > FAQ (Developer level, unlocked): a list of small forms with an add form; each save goes through the change log (undoable).
Minimal on purpose: list, edit, order, suggested, hide. Entries are hidden rather than deleted."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST

from chat.models import FaqItem

from . import services
from .forms_faq import FaqForm
from .permissions import unlocked
from .views import form_status, page, saved


def _page(request, bound=None, status=200):
    bound = bound or {}
    rows = [{"obj": o, "form": bound.get(str(o.pk)) or FaqForm(instance=o, prefix=str(o.pk))} for o in FaqItem.objects.all()]
    return page(request, "system/faq.html", "assistant", {"rows": rows, "add_form": bound.get("new") or FaqForm(prefix="new")}, status)


@unlocked
@require_GET
def faq(request):
    return _page(request)


@unlocked
@require_POST
def faq_save(request, pk=None):
    obj = get_object_or_404(FaqItem, pk=pk) if pk else None
    key = "new" if pk is None else str(pk)
    form = FaqForm(request.POST, instance=obj, prefix=key)
    if form.is_valid():
        try:
            if services.save_form(form, request.user):
                saved(request)
            else:
                messages.info(request, "Nothing changed.")
            return redirect("system_faq")
        except ValidationError as error:
            form.add_error(None, error)
    return _page(request, {key: form}, form_status(form))
