"""System > Sales (Developer level, unlocked, CSRF): list, create, edit, End now, preview link. Short views; the rules are in
plans/sales.py and plans/models.py (Sale.clean). Saves go through the change log, so each is undoable from it (End now too)."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from plans import sales
from plans.models import Sale

from .forms_sales import SaleForm
from .views import form_status, page, saved
from .views_emails import _respond
from .permissions import unlocked


def _grouped():
    """live / upcoming / past lists; each sale carries `.state`, `.plans_label` and `.holders` (people who kept its price)."""
    now = timezone.now()
    rows = list(Sale.objects.annotate(holders=Count("interests")).prefetch_related("plans"))
    result = {"live": [], "upcoming": [], "past": []}
    for sale in rows:
        sale.state = sale.status(now)
        sale.plans_label = sales.plans_text(sale)
        result["past" if sale.state == "ended" else sale.state].append(sale)
    result["upcoming"].sort(key=lambda s: s.starts_at)
    return result


@unlocked
@require_http_methods(["GET"])
def sale_list(request):
    return page(request, "system/sales.html", "sales", _grouped())


def _form_page(request, form, sale, status=200):
    context = {"form": form, "sale": sale, "state": form.status, "locked_fields": form.locked_fields, "read_only": form.status == "ended"}
    return page(request, "system/sales_form.html", "sales", context, status=status)


@unlocked
@require_http_methods(["GET", "POST"])
def sale_edit(request, pk=None):
    """New (pk None) or edit. An upcoming sale is fully editable; a live one: name, end time and plans; an ended one is read-only."""
    sale = get_object_or_404(Sale, pk=pk) if pk else None
    form = SaleForm(request.POST or None, instance=sale)
    if request.method == "POST":
        if form.status == "ended":
            messages.error(request, "An ended sale cannot be edited.")
            return _form_page(request, SaleForm(instance=sale), sale, status=400)
        if form.is_valid():
            try:
                if sales.save_sale(form, request.user):
                    saved(request)
                else:
                    messages.info(request, "Nothing changed.")
                return redirect("system_sale_edit", pk=form.instance.pk)
            except ValidationError as error:  # overlap or live lock caught under the lock, or the row changed since the page was made
                form.add_error(None, error)
        return _form_page(request, form, sale, status=form_status(form))
    return _form_page(request, form, sale)


@unlocked
@require_POST
def sale_end(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    try:
        sales.end_now(sale, request.user)
    except ValidationError as error:
        return _respond(request, False, " ".join(error.messages), "system_sales")
    saved(request, f"{sale.name} has ended.")
    return redirect("system_sales")


@unlocked
@require_POST
def sale_preview(request, pk):
    """A signed link (one hour) that shows this sale's bar on the public site in one browser only."""
    sale = get_object_or_404(Sale, pk=pk)
    if sale.status() == "ended":
        return _respond(request, False, "An ended sale cannot be previewed.", "system_sales")
    url = sales.preview_url(sale)
    return _respond(request, True, f"Open this link within an hour to see the bar in that browser: {url}",
                    f"/sales/{sale.pk}/", extra={"url": url, "valid_minutes": sales.PREVIEW_SECONDS // 60})
