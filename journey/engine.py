"""Turns a session's answers into a suggested plan (with reasons) and a Gold potential rating.
All numbers come from data: Option.plan_points, SuggestionRule rows, GoldRule rows, Plan rows."""
from dataclasses import dataclass, field

from django.utils import timezone

from gold import rating as gold_rating
from plans import services as plan_services

from . import services
from .conditions import matches
from .models import SuggestionRule

MAX_REASONS = 3
MAX_ANSWER_REASONS = 2
# How the result page presents each Gold potential (journey.md "Gold nudge").
GOLD_PRESENTATION = {gold_rating.HIGH: "panel", gold_rating.MEDIUM: "line", gold_rating.LOW: "none"}


@dataclass
class Suggestion:
    plan: object
    scores: dict = field(default_factory=dict)
    excluded: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    tie_broken: bool = False


def _rule_plan_slugs(rule, plans):
    slugs = set(rule.plan_slugs or [])
    if rule.target_daytime_only:
        slugs |= {p.slug for p in plans if p.is_daytime_only}
    return slugs


def compute_suggestion(session):
    """Points per plan from the answers, then the rules (exclude, add points), then the tie-break.
    Returns a Suggestion, or None if there are no plans to suggest."""
    plans = list(plan_services.monthly_plans())
    if not plans:
        return None
    answers = services.effective_answers(session)
    values = {key: [o.value for o in a.options.all()] for key, a in answers.items()}

    scores = {p.slug: 0 for p in plans}
    support = {p.slug: [] for p in plans}  # (points, reason) that backed each plan
    for answer in answers.values():
        for option in answer.options.all():
            for slug, points in (option.plan_points or {}).items():
                if slug in scores and points:
                    scores[slug] += points
                    if points > 0 and option.reason:
                        support[slug].append((points, option.reason))

    excluded, tie_orders = set(), []
    for rule in SuggestionRule.objects.filter(active=True):
        if not matches(rule.conditions, values):
            continue
        if rule.kind == SuggestionRule.EXCLUDE:
            excluded |= _rule_plan_slugs(rule, plans)
        elif rule.kind == SuggestionRule.ADD_POINTS:
            for slug in _rule_plan_slugs(rule, plans) & set(scores):
                scores[slug] += rule.points
                if rule.points > 0 and rule.reason:
                    support[slug].append((rule.points, rule.reason))
        elif rule.kind == SuggestionRule.TIE_BREAK:
            tie_orders.extend(rule.plan_slugs or [])

    eligible = [p for p in plans if p.slug not in excluded] or plans  # never leave the visitor with nothing
    best = max(scores[p.slug] for p in eligible)
    tied = [p for p in eligible if scores[p.slug] == best]

    def preference(plan):
        return tie_orders.index(plan.slug) if plan.slug in tie_orders else len(tie_orders) + plan.order

    chosen = min(tied, key=preference)
    return Suggestion(
        plan=chosen,
        scores=scores,
        excluded=sorted(excluded),
        reasons=_reasons(chosen, support[chosen.slug]),
        tie_broken=len(tied) > 1,
    )


def _reasons(plan, supports):
    """Up to two reasons from his answers (strongest first), then facts about the plan, three in all."""
    reasons = []
    for _, text in sorted(supports, key=lambda item: -item[0]):
        if text not in reasons and len(reasons) < MAX_ANSWER_REASONS:
            reasons.append(text)
    for fact in plan_services.plan_facts(plan):
        if len(reasons) >= MAX_REASONS:
            break
        if fact not in reasons:
            reasons.append(fact)
    return reasons


def gold_signals(session):
    """Gold rating inputs from the journey answers (shared with the Gold application)."""
    answers = services.effective_answers(session)

    def single(key):
        answer = answers.get(key)
        first = answer.options.all()[0].value if answer and answer.options.all() else None
        return first

    link = single("property_link")
    if not link and single("industry") == "law" and single("property_law") == "yes":
        link = "property_lawyer"
    signals = {"property_link": link, "size": single("property_size")}
    extra = sum(o.gold_points for a in answers.values() for o in a.options.all())
    return {k: v for k, v in signals.items() if v}, extra


def compute_gold(session):
    signals, extra = gold_signals(session)
    return gold_rating.rate_potential(signals, extra_points=extra)


def complete(session):
    """Work out and store the suggestion and Gold potential, mark the journey finished. Returns the result dict."""
    suggestion = compute_suggestion(session)
    rating = compute_gold(session)
    detail = {
        "scores": suggestion.scores if suggestion else {},
        "excluded": suggestion.excluded if suggestion else [],
        "reasons": suggestion.reasons if suggestion else [],
        "gold_reasons": rating.reasons,
    }
    plan = suggestion.plan if suggestion else None
    changed = (
        session.suggested_plan_id != (plan.pk if plan else None)
        or session.suggestion_detail != detail
        or session.gold_potential != rating.level
        or session.gold_score != rating.score
        or not session.completed
    )
    if changed:
        last = services.result_step(session)
        session.suggested_plan = plan
        session.suggestion_detail = detail
        session.gold_potential, session.gold_score = rating.level, rating.score
        session.current_step = session.furthest_step = last
        if not session.completed:
            session.completed, session.completed_at = True, timezone.now()
        session.save()
    return build_result(session, suggestion, rating)


def build_result(session, suggestion, rating):
    vat = plan_services.SiteSettings.load().vat_rate
    plans = list(plan_services.monthly_plans())
    if suggestion is None:
        return {"suggested": None, "others": [], "gold": {"potential": rating.level, "presentation": "none"}}
    suggested = plan_services.plan_display(suggestion.plan, vat)
    suggested["reasons"] = suggestion.reasons
    others = []
    for plan in plans:
        if plan.pk != suggestion.plan.pk:
            data = plan_services.plan_display(plan, vat)
            data["not_a_fit"] = plan.slug in suggestion.excluded  # e.g. daytime only, but he wants evenings
            others.append(data)
    return {
        "suggested": suggested,
        "others": others,
        "gold": {
            "potential": rating.level,
            "score": rating.score,
            "presentation": GOLD_PRESENTATION[rating.level],
        },
    }
