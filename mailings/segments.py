"""Groups (segments) for group sends, as code. Each group builds a queryset of people; `count()` is the live count and
`rows()` the people to email. Always left out: suppressed addresses (bounce or complaint) and inactive accounts. A News mailing
also needs consent (`User.marketing_consent`; for Gold applicants the application's tick) and leaves out people who
unsubscribed without an account.

The "Journey leads" group is different: people who left an address at the journey gate and have no account. News only (they
never registered, so a service message has no reason to reach them); the gate tick is their consent.

"Registered" means a person with a registered interest (the early list), not a team account. Tier = the plan they
registered interest in. Plain ORM only, so it behaves the same on SQLite and Postgres."""
import datetime
from dataclasses import dataclass, field

from django.db.models import CharField, Exists, F, OuterRef, UUIDField, Value
from django.db.models.functions import Lower

from gold.models import GoldApplication
from journey.models import JourneySession
from notifications.models import EmailSuppression
from plans.models import Plan
from users.models import User

from .models import EmailOptOut, Mailing

REASON_ACCOUNT = "because you registered with Spa 99"
REASON_GOLD = "because you applied for a Spa 99 Gold Card"
REASON_LEAD = "because you asked to hear about Spa 99 opening"


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    description: str
    reason: str  # "You are receiving this ..." for service messages
    params: tuple = field(default_factory=tuple)  # ({"name", "type": choice|date, "label", "required"}, ...)
    people: str = "users"  # "users", "applicants" or "leads"
    news_only: bool = False


def _users():
    """Registered, active people (they have a registered interest)."""
    return User.objects.filter(is_active=True, interest__isnull=False)


def _everyone(params):
    return _users()


def _tier(params):
    return _users().filter(interest__plan__slug=params["plan"])


def _gold(params):
    return _users().filter(interest__plan__slug="gold")


def _opted_in(params):
    return _users().filter(marketing_consent=True)


def _unconfirmed(params):
    return _users().filter(email_verified_at__isnull=True)


def _between(params):
    qs = _users()
    if params.get("date_from"):
        qs = qs.filter(created_at__date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(created_at__date__lte=params["date_to"])
    return qs


def _applicants(params):
    return GoldApplication.objects.filter(status=params["status"])


def _leads(params):
    """One row per journey session that left an address; people with an account, bots and linked sessions are out."""
    qs = JourneySession.objects.filter(is_bot=False, user__isnull=True).exclude(lead_email="")
    if params.get("date_from"):
        qs = qs.filter(lead_at__date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(lead_at__date__lte=params["date_to"])
    return qs


GROUPS = {g.key: g for g in [
    Group("everyone", "Everyone registered", "Every active person who has registered.", REASON_ACCOUNT),
    Group("tier", "By tier", "People who registered for one membership.", REASON_ACCOUNT,
          ({"name": "plan", "type": "choice", "label": "Membership", "required": True},)),
    Group("gold", "Gold members", "People registered for the Gold Card.", REASON_ACCOUNT),
    Group("opted_in", "Opted in to news", "People who ticked the news box.", REASON_ACCOUNT),
    Group("unconfirmed", "Email not confirmed yet", "People who have not clicked the confirm link.", REASON_ACCOUNT),
    Group("between", "Registered between dates", "People who registered in a date range (either end may be left empty).", REASON_ACCOUNT,
          ({"name": "date_from", "type": "date", "label": "From", "required": False},
           {"name": "date_to", "type": "date", "label": "To", "required": False})),
    Group("applicants", "Gold applicants by status", "People who applied for a Gold Card, by where the application stands.", REASON_GOLD,
          ({"name": "status", "type": "choice", "label": "Status", "required": True},), people="applicants"),
    Group("leads", "Journey leads", "People who left their email at the journey and have no account. News only.", REASON_LEAD,
          ({"name": "date_from", "type": "date", "label": "Given from", "required": False},
           {"name": "date_to", "type": "date", "label": "Given to", "required": False}), people="leads", news_only=True),
]}
BUILDERS = {"everyone": _everyone, "tier": _tier, "gold": _gold, "opted_in": _opted_in, "unconfirmed": _unconfirmed,
            "between": _between, "applicants": _applicants, "leads": _leads}


def param_choices(name):
    if name == "plan":
        return [(p.slug, p.name) for p in Plan.objects.exclude(kind=Plan.ONE_OFF)]
    if name == "status":
        return list(GoldApplication.STATUS_CHOICES)
    return []


def catalog():
    """For the frontend: every group with its parameters (choices filled in from the database)."""
    return [{"key": g.key, "label": g.label, "description": g.description, "reason": g.reason, "news_only": g.news_only,
             "params": [{**p, **({"choices": param_choices(p["name"])} if p["type"] == "choice" else {})} for p in g.params]}
            for g in GROUPS.values()]


def clean_params(group_key, raw):
    """(params, errors) from raw input (strings). Unknown groups and bad values are errors; extra keys are dropped."""
    group, raw, params, errors = GROUPS.get(group_key), (raw or {}), {}, {}
    if group is None:
        return {}, {"group": ["Choose a group."]}
    for spec in group.params:
        name, value = spec["name"], str(raw.get(spec["name"], "") or "").strip()
        if not value:
            if spec["required"]:
                errors[name] = [f"Choose a {spec['label'].lower()}."]
            continue
        if spec["type"] == "choice":
            if value not in {c[0] for c in param_choices(name)}:
                errors[name] = [f"{spec['label']} is not one of the choices."]
                continue
            params[name] = value
        else:
            try:
                params[name] = datetime.date.fromisoformat(value).isoformat()
            except ValueError:
                errors[name] = ["Use a date like 2026-12-31."]
    if not errors and params.get("date_from") and params.get("date_to") and params["date_from"] > params["date_to"]:
        errors["date_to"] = ["The end date is before the start date."]
    return params, errors


def queryset(group_key, params, kind):
    """People in the group who may be emailed for this kind of mailing: suppressed and inactive people are out; News also
    needs consent and leaves out people who unsubscribed without an account."""
    group = GROUPS[group_key]
    if group.people == "leads":
        return _lead_queryset(params or {}, kind == Mailing.NEWS)
    qs = BUILDERS[group_key](params or {}).annotate(r_email=Lower("email"), r_user_id=F("user_id") if group.people == "applicants" else F("pk"))
    qs = qs.exclude(Exists(EmailSuppression.objects.filter(email=OuterRef("r_email"))))
    if kind == Mailing.NEWS:
        qs = qs.filter(marketing_consent=True).exclude(Exists(EmailOptOut.objects.filter(email=OuterRef("r_email"))))
    return qs


def _lead_queryset(params, allowed):
    qs = (_leads(params) if allowed else JourneySession.objects.none()).annotate(r_email=Lower("lead_email"), first_name=Value("", output_field=CharField()),
                                 r_user_id=Value(None, output_field=UUIDField()))
    qs = qs.exclude(Exists(User.objects.annotate(u_email=Lower("email")).filter(u_email=OuterRef("r_email"))))  # any account, staff included
    qs = qs.exclude(Exists(EmailSuppression.objects.filter(email=OuterRef("r_email"))))
    return qs.exclude(Exists(EmailOptOut.objects.filter(email=OuterRef("r_email"))))


def count(group_key, params, kind):
    """How many different addresses would get it."""
    return queryset(group_key, params, kind).order_by().values("r_email").distinct().count()


def rows(group_key, params, kind):
    """(email, first_name, user_id or None) once per address, in address order. Streams: no big lists in memory."""
    seen = None
    people = queryset(group_key, params, kind).order_by("r_email", "pk").values_list("r_email", "first_name", "r_user_id")
    for email, first_name, user_id in people.iterator(chunk_size=500):
        if email != seen:
            seen = email
            yield email, first_name or "", user_id
