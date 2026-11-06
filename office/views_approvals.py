"""Approvals and Revenue (Barry's view). Level: the Approver permission, or Admin and up (`editor`): a View-only team member sees neither page, their tabs nor their Home cards.
Short views: they read office.approvals and office.counts and answer. The three decisions are POSTs and are audited (office.approvals.decide)."""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from plans.models import Plan, SiteSettings
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
    rows, has_next = approvals.page(status, number, defaults.get(request).list_page_size, q, plan, lists.shift_from(request))
    stored = counts.read()
    query = request.GET.copy()
    query["page"] = number + 1
    query.pop("shift", None)  # the page's script adds it when it loads more
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


def _iso_date(text):
    """A YYYY-MM-DD date or None (empty or garbage)."""
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def _date_range(request):
    """{from, to, active, error} from GET `from` and `to`. Both empty (or garbage) is no range; an end before the start is refused: both ignored."""
    start, end = _iso_date(request.GET.get("from")), _iso_date(request.GET.get("to"))
    if start and end and end < start:
        return {"from": None, "to": None, "active": False, "error": "The end date can't be before the start date."}
    return {"from": start, "to": end, "active": bool(start or end), "error": ""}


def _stored_calendar(revenue):
    """The approved calendar's start and assumed flag, and the first and last due date across both buckets (None when nothing is stored: an older payload)."""
    stored = {bucket: ((revenue.get(bucket) or {}).get("detail") or {}).get("calendar") or {} for bucket in (counts.APPROVED, counts.WAITING)}
    days = {name: [c[name] for c in stored.values() if c.get(name)] for name in ("first", "last")}
    approved = stored[counts.APPROVED]
    return {"start": approved.get("start"), "assumed": approved.get("assumed"), "first": min(days["first"], default=None), "last": max(days["last"], default=None)}


@editor
@require_GET
@never_cache
def revenue_page(request):
    """Revenue: an estimate, never money received. Context: revenue {vat_rate, gold_fee_pence, gold_fee_inc_pence, approved, waiting}: each bucket has count, year_ex, month_ex, year_inc, month_inc,
    avg_year_ex, avg_year_inc (Decimal pence: round only for display with the `pounds` filter) and by_plan [{slug, name, kind (tier | gold), count, year_ex ... avg_year_inc}] in plan order, Gold last, and detail (the full breakdown: counts._detail_view, None until it is stored);
    `date_range` {from, to, active, error, shown_from, shown_to} from GET `from`/`to` (ISO dates; garbage = empty; an end before the start is refused with `range_error`), `range_figures` (counts.revenue_between: money due in
    those dates, None without a range), `calendar` {start, assumed, first, last} (stored), `assumptions` {paying_percent, dropoff_percent, changed, figures: counts.revenue_assumptions}, `assumed_shown` (changed, a stored calendar and someone approved: the only time a "With your assumptions" figure is shown), each by_plan row also has `assumed_year_ex`, `date_format` (the calendar's format string);
    `waiting` is the Possible panel (never added to the approved figures); counts (memberships and gold), `empty` (nothing approved yet), approvals_url, section.
    All prices are excluding VAT; the including-VAT figures use the VAT setting."""
    stored = counts.read()
    figures = counts.revenue_view(stored["revenue"])
    window, calendar = _date_range(request), _stored_calendar(stored["revenue"])
    if not calendar["first"]:  # nothing stored by date yet (before the first roll-up): no false £0, the normal page
        window = {**window, "active": False}
    if window["active"]:  # one end given: the other end is the stored first or last due date
        low = window["from"] or _iso_date(calendar["first"]) or window["to"]
        high = window["to"] or _iso_date(calendar["last"]) or window["from"]
        high = max(low, high)
        window = {**window, "shown_from": low, "shown_to": high}  # the dates really used: with one end in the URL the other is filled in, and the page says so
        range_figures = counts.revenue_between(stored["revenue"], low, high)
    else:
        window = {**window, "shown_from": None, "shown_to": None}
        range_figures = None
    site = SiteSettings.load()
    assumed = counts.revenue_assumptions(stored["revenue"])
    for bucket in (counts.APPROVED, counts.WAITING):  # a template cannot pair two lists: each plan row carries its own assumed year (the same figure over all stored due)
        by_slug = {row["slug"]: row["assumed_total_ex"] for row in assumed[bucket]["by_plan"]}
        for row in figures[bucket]["by_plan"]:
            row["assumed_year_ex"] = by_slug.get(row["slug"], Decimal(0))
    assumptions = {"paying_percent": site.revenue_paying_percent, "dropoff_percent": site.revenue_dropoff_percent,
                   "changed": site.revenue_paying_percent != 100 or site.revenue_dropoff_percent != 0, "figures": assumed}
    # A second figure is shown only when it can be right: changed, and the stored calendar exists (without it the assumed totals read 0 until the next hourly update), and someone is approved.
    assumed_shown = bool(assumptions["changed"] and calendar["first"] and figures["approved"]["count"])
    context = {"revenue": figures, "assumptions": assumptions, "assumed_shown": assumed_shown, "date_range": window, "range_error": window["error"], "range_figures": range_figures, "calendar": calendar,
               "date_format": site.flatpickr_date_format,
               "counts": {"memberships": stored["memberships"], "gold": stored["gold"]}, "empty": not figures["approved"]["count"],
               "approvals_url": f"{reverse('office_approvals')}?status=waiting", "section": "revenue"}
    return render(request, "office/revenue.html", context)
