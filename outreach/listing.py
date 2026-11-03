"""The approach list query: three states worked out in the database (R5), sortable columns (R1) and the per-tab counts.

open        not done, and he has no verified account that came AFTER he was added
registered  not done, and his account was verified after the entry was added (`registered_at` = User.email_verified_at > added_at): Barry
            marks him done as usual. Someone who was already registered when he was added to the list stays Open (he did not register
            because of the approach)
done        marked done (whatever happened to his account since)

"Has a verified account" is read four ways, the first that answers wins: the entry's own user, the user of his Gold application,
a verified account whose email equals the lead address (any case), one that equals the application's email (any case). All plain
Lower/Subquery/Coalesce: SQLite and Postgres alike."""
from django.db.models import Case, CharField, Count, F, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce, Lower, NullIf

from common import sorting
from common.sorting import Column
from users.models import User

from .models import OutreachEntry

OPEN, REGISTERED, DONE = "open", "registered", "done"
STATES = (OPEN, REGISTERED, DONE)
TIEBREAK = ("-added_at", "-pk")


def _verified_by_email(expression):
    """Subquery: when the verified account whose email equals `expression` (lower case) was verified."""
    return Subquery(User.objects.filter(email_verified_at__isnull=False).annotate(account_key=Lower("email")).filter(account_key=expression)
                    .order_by("email_verified_at").values("email_verified_at")[:1])


AFTER_ADDED = Q(registered_at__gt=F("added_at"))
NOT_AFTER_ADDED = Q(registered_at__isnull=True) | Q(registered_at__lte=F("added_at"))


def with_state(queryset):
    """Annotate `registered_at` (see the module text): a date, or NULL while he has no verified account."""
    return queryset.annotate(registered_at=Coalesce(
        "user__email_verified_at", "gold_application__user__email_verified_at",
        _verified_by_email(OuterRef("lead_email")), _verified_by_email(Lower(OuterRef("gold_application__email")))))


_NAME = Case(When(user__isnull=False, then=Lower("user__first_name")), When(gold_application__isnull=False, then=Lower("gold_application__first_name")),
             default=Lower("lead_email"), output_field=CharField())
_MOBILE = Case(When(user__isnull=False, then=NullIf("user__mobile", Value(""))), When(gold_application__isnull=False, then=NullIf("gold_application__mobile", Value(""))),
               default=Value(None, output_field=CharField()), output_field=CharField())
_FROM = Case(When(user__isnull=False, then=Value("Person")), When(gold_application__isnull=False, then=Value("Gold")), default=Value("Lead"), output_field=CharField())


def columns(state):
    """Sortable headers (R1). The date column is Done on the Done tab, Added on the others; Registered shows the account date."""
    return [
        Column("name", "Name", _NAME),
        Column("mobile", "Mobile", _MOBILE, css="c-contact"),
        Column("from", "From", _FROM, css="c-from"),
        Column("reason", "Reason", NullIf(Lower("reason"), Value("")), css="c-reason"),
        Column("done", "Done", "done_at", first=sorting.DESC, css="c-added") if state == DONE else Column("added", "Added", "added_at", first=sorting.DESC, css="c-added"),
        Column("registered", "Registered", "registered_at", first=sorting.DESC, hidden=state != REGISTERED),
    ]


def state_from(get):
    return get.get("state") if get.get("state") in STATES else OPEN


def sort_from(get, state):
    """(sort key, dir). The default is newest first by the tab's date."""
    return sorting.resolve(columns(state), get, "done" if state == DONE else "added", sorting.DESC)[:2]


def queryset(state, sort=None, direction=None):
    found = with_state(OutreachEntry.objects.select_related("user", "gold_application"))
    if state == DONE:
        found = found.filter(done_at__isnull=False)
    else:
        found = found.filter(AFTER_ADDED if state == REGISTERED else NOT_AFTER_ADDED, done_at__isnull=True)
    default = "done" if state == DONE else "added"
    return found.order_by(*sorting.ordering_from(columns(state), {"sort": sort, "dir": direction}, default, TIEBREAK))


def counts():
    """{open, registered, done}: one query."""
    found = with_state(OutreachEntry.objects.all()).aggregate(
        open=Count("pk", filter=Q(done_at__isnull=True) & NOT_AFTER_ADDED),
        registered=Count("pk", filter=Q(done_at__isnull=True) & AFTER_ADDED),
        done=Count("pk", filter=Q(done_at__isnull=False)))
    return found
