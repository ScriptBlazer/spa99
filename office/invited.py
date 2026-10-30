"""Invited, not registered: people with an invite sent (or whose link was clicked) and no account yet, one row per address
showing the latest invite. A personal follow-up list: nothing is sent from here (invites go out from System > Emails > Groups).
`Invite.status` OPENED means he clicked the personal link (not that he opened the email), so the list says "Clicked the link".
All DB-side with Lower/Exists (SQLite and Postgres alike); paged with one extra row, no count; fixed number of queries."""
import csv
import logging

from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower
from django.http import HttpResponse
from django.utils import timezone

from journey.models import JourneySession
from mailings.models import ContactListMember, Invite
from users.models import User

from . import lists

logger = logging.getLogger("spa99.office")

QUALIFYING = (Invite.SENT, Invite.OPENED)
STATES = ("unclicked", "clicked", "expired", "all")
STATE_LABELS = [("unclicked", "Not clicked"), ("clicked", "Clicked the link"), ("expired", "Expired"), ("all", "All")]
DEFAULT_STATE = "unclicked"  # the people to chase: invited and never clicked or registered
CSV_CHUNK = 200


def filters_from(request):
    state = request.GET.get("state", DEFAULT_STATE)
    return {"q": request.GET.get("q", "").strip(), "state": state if state in STATES else DEFAULT_STATE}


def is_filtered(filters):
    return bool(filters["q"] or filters["state"] != DEFAULT_STATE)


def queryset(filters, now=None):
    """The latest qualifying invite per address, no account for the address (any case), annotated `clicked` (any invite of his was clicked)."""
    now = now or timezone.now()
    invites = Invite.objects.filter(status__in=QUALIFYING).annotate(email_key=Lower("email"))
    newer = (Invite.objects.filter(status__in=QUALIFYING).annotate(k=Lower("email")).filter(k=OuterRef("email_key"))
             .filter(Q(created_at__gt=OuterRef("created_at")) | Q(created_at=OuterRef("created_at"), id__gt=OuterRef("id"))))
    accounts = User.objects.annotate(k=Lower("email")).filter(k=OuterRef("email_key"))
    clicked = Invite.objects.annotate(k=Lower("email")).filter(k=OuterRef("email_key"), opened_at__isnull=False)
    found = invites.filter(~Exists(newer), ~Exists(accounts)).annotate(clicked=Exists(clicked))
    for word in filters["q"].lower().split():
        found = found.filter(Q(email_key__contains=word) | Q(name__icontains=word))
    if filters["state"] == "unclicked":
        found = found.filter(clicked=False, expires_at__gt=now)
    elif filters["state"] == "clicked":
        found = found.filter(clicked=True)
    elif filters["state"] == "expired":
        found = found.filter(expires_at__lte=now)
    return found.order_by("-created_at", "-id")


def build_rows(invites, now=None):
    """Rows for these invites: lists they are on (one query) and the lead page when he left his email at the journey (one query)."""
    now = now or timezone.now()
    emails = [i.email_key for i in invites]
    on = {}
    for key, name in (ContactListMember.objects.annotate(k=Lower("email")).filter(k__in=emails).order_by("list__name").values_list("k", "list__name")):
        on.setdefault(key, []).append(name)
    leads = {}
    for key, pk in (JourneySession.objects.filter(is_bot=False).annotate(k=Lower("lead_email")).filter(k__in=emails).order_by("created_at").values_list("k", "pk")):
        leads[key] = pk  # newest wins
    from .leads import _url

    return [{"name": i.name, "email": i.email_key, "lists": on.get(i.email_key, []), "invited_at": (i.sent_at or i.created_at).isoformat(),
             "clicked": i.clicked, "expired": i.expires_at <= now, "status": i.status,
             "href": _url("office_lead", leads[i.email_key]) if i.email_key in leads else ""} for i in invites]


def page(filters, number, size=None):
    found, has_next = lists.cut(queryset(filters), number, size)
    return build_rows(found), has_next


def csv_response(filters, user_id=None):
    logger.info("Invited, not registered CSV exported by account %s", user_id)  # who; never the addresses
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="spa99-invited-not-registered.csv"'
    writer = csv.writer(response)
    writer.writerow(["name", "email", "lists", "invited_at", "clicked_the_link", "invite_expired"])
    found, offset = queryset(filters), 0
    while True:
        chunk = list(found[offset:offset + CSV_CHUNK])
        if not chunk:
            break
        offset += CSV_CHUNK
        for r in build_rows(chunk):
            writer.writerow([lists.safe_cell(x) for x in (r["name"], r["email"], "; ".join(r["lists"]), r["invited_at"],
                                                          "yes" if r["clicked"] else "no", "yes" if r["expired"] else "no")])
    return response
