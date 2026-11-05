"""Approvals and Revenue (Barry's view). Level: the Approver permission, or Admin and up (`editor`): a View-only team member sees neither page, their tabs nor their Home cards.
Short views: they read office.approvals and office.counts and answer. The three decisions are POSTs and are audited (office.approvals.decide)."""
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from plans.models import Plan
from system import defaults

from . import approvals, counts, lists
from .permissions import editor

ACTIONS = {"approve": approvals.APPROVED, "decline": approvals.DECLINED, "undo": approvals.WAITING}
SAID = {"approve": "approved", "decline": "declined", "undo": "back to waiting"}


def _fetch(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


def _tabs(status, stored, request):
    members = stored["memberships"]
    return [{"status": s, "label": approvals.LABELS[s], "count": members[s], "active": s == status, "url": f"{reverse('office_approvals')}?status={s}"} for s in approvals.STATUSES]


@editor
@require_GET
@never_cache
def approvals_page(request):
    """The three lists. ?status=waiting|approved|declined, ?q= (name or email), ?plan= (a Tier's slug), ?page=N. A fragment request (HX-Request) answers the rows only.
    Context: status, tabs [{status, label, count, active, url}], counts {total, waiting, approved, declined}, rows [{id, name, email, plan, plan_slug, month_pence (excluding VAT), sale, registered,
    status, decided_at, decided_by, href, approve_url, decline_url, undo_url}], has_next, page, more_url, q, plan, plans, note, gold_waiting, gold_url, section."""
    status, number = approvals.status_from(request.GET), lists.page_number(request)
    q, plan = request.GET.get("q", "").strip(), request.GET.get("plan", "")
    rows, has_next = approvals.page(status, number, defaults.get(request).list_page_size, q, plan)
    stored = counts.read()
    query = request.GET.copy()
    query["page"] = number + 1
    context = {"status": status, "tabs": _tabs(status, stored, request), "counts": stored["memberships"], "rows": rows, "has_next": has_next, "page": number,
               "more_url": f"{request.path}?{query.urlencode()}", "q": q, "plan": plan, "plans": list(Plan.objects.filter(kind=Plan.MONTHLY).order_by("order").values("slug", "name")),
               "note": approvals.NOTE, "gold_waiting": stored["gold"]["waiting"], "gold_url": f"{reverse('office_gold')}?status=waiting", "section": "approvals"}
    template = "office/_approvals_rows.html" if request.headers.get("HX-Request") else "office/approvals.html"
    response = render(request, template, context)
    patch_vary_headers(response, ["HX-Request"])
    return response


@editor
@require_POST
def approval_decide(request, pk, action):
    """Approve, Decline or Undo (back to waiting) one person. Nothing is asked and nothing is sent: the member never sees it. A fetch (X-Requested-With: fetch, or Accept: application/json) gets
    {ok, status, name, row, counts}; otherwise a toast and back to the list. Refused with a 404 for a person who is not on a Tier."""
    if action not in ACTIONS:
        raise Http404
    result, row = approvals.decide(pk, ACTIONS[action], request.user)
    if result == approvals.MISSING:
        if _fetch(request):
            return JsonResponse({"ok": False, "error": "He is not in this list."}, status=404)
        raise Http404
    stored = counts.read()
    if _fetch(request):
        return JsonResponse({"ok": True, "result": result, "status": row["status"], "name": row["name"], "row": row, "counts": stored["memberships"], "gold_waiting": stored["gold"]["waiting"]})
    messages.success(request, f"{row['name']} {SAID[action]}." if result == approvals.DONE else "Nothing changed.")
    return redirect(f"{reverse('office_approvals')}?status={request.POST.get('from', '')}" if request.POST.get("from") in approvals.STATUSES else "office_approvals")


@editor
@require_GET
@never_cache
def revenue_page(request):
    """Revenue: an estimate, never money received. Context: revenue {vat_rate, gold_fee_pence, gold_fee_inc_pence, approved, waiting}: each bucket has count, year_ex, month_ex, year_inc, month_inc,
    avg_year_ex, avg_year_inc (Decimal pence: round only for display with the `pounds` filter) and by_plan [{slug, name, kind (tier | gold), count, year_ex ... avg_year_inc}] in plan order, Gold last;
    `waiting` is the Possible panel (never added to the approved figures); counts (memberships and gold), `empty` (nothing approved yet), approvals_url, section.
    All prices are excluding VAT; the including-VAT figures use the VAT setting."""
    stored = counts.read()
    figures = counts.revenue_view(stored["revenue"])
    context = {"revenue": figures, "counts": {"memberships": stored["memberships"], "gold": stored["gold"]}, "empty": not figures["approved"]["count"],
               "approvals_url": f"{reverse('office_approvals')}?status=waiting", "section": "revenue"}
    return render(request, "office/revenue.html", context)
