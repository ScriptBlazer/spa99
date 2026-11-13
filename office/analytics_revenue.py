"""The short Revenue section on Analytics (2026-11-06): two donut cards read from the stored Revenue figures (`counts.read()`), never from people.
Only people who may see Revenue (`permissions.abilities(user)["can_revenue"]`) get this in their page or their JSON; everyone else gets nothing.
Money stays in exact whole pence; a percent is worked out from the exact figures (never from rounded ones) as basis points, half up."""
from . import counts
from .templatetags.office_tags import pounds

PRICE_LABELS = {counts.SALE: "On a sale price", counts.AGREED: "On an agreed price", counts.FULL: "At full price"}
PRICE_PHRASES = {counts.SALE: "on a sale price", counts.AGREED: "on an agreed price", counts.FULL: "at full price"}
EMPTY = {"plan": {"total_pence": 0, "rows": [], "summary": ""}, "price": {"members": 0, "rows": [], "summary": ""}}


def share_bp(part, whole):
    """Basis points of a whole, half up, from exact integers."""
    return (part * 20000 + whole) // (whole * 2) if whole else 0


def build(stored=None):
    """{"plan": {total_pence, rows [{label, value (pence), count, share_bp}], summary}, "price": {members, rows [{label, kind, value (people), share_bp}], summary}}.
    An old payload with no detail, or nothing approved, gives the empty cards."""
    approved = ((stored if stored is not None else counts.read()).get("revenue") or {}).get(counts.APPROVED) or {}
    detail = approved.get("detail")
    total = int(approved.get("year_pence") or 0)
    if not detail or not approved.get("count") or total <= 0:
        return EMPTY
    plans = [{"label": row["name"], "value": int(row["year_pence"]), "count": int(row["count"]), "share_bp": share_bp(int(row["year_pence"]), total)}
             for row in approved.get("by_plan", []) if row.get("count", 0) > 0]
    plan = {"total_pence": total, "rows": plans, "summary": ""}
    if plans:
        top = max(plans, key=lambda r: r["value"])
        plan["summary"] = f"{top['label']} brings in {pounds(top['value'])} of {pounds(total)} a year."
    groups = {kind: sum(int(g.get("count", 0)) for g in detail.get("groups", []) if g.get("kind") == kind) for kind in PRICE_LABELS}
    members = sum(groups.values())
    prices = [{"label": PRICE_LABELS[kind], "kind": kind, "value": groups[kind], "share_bp": share_bp(groups[kind], members)} for kind in PRICE_LABELS if groups[kind] > 0]
    price = {"members": members, "rows": prices, "summary": ""}
    if prices:
        top = max(prices, key=lambda r: r["value"])  # a tie keeps the first: sale, agreed, full
        price["summary"] = f"{top['value']} of {members} member{'s are' if members != 1 else ' is'} {PRICE_PHRASES[top['kind']]}."
    return {"plan": plan, "price": price}
