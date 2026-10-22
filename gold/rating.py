"""The Gold potential engine. Shared by the Gold application and the journey result (one engine, one set of
GoldRule rows). Pure rating: no sending, no saving.

signals: dict with any of  property_link, size, where, bml, referred  (answer values).
"""
from dataclasses import dataclass, field

from .models import GoldRule

HIGH, MEDIUM, LOW = "high", "medium", "low"
DEFAULT_THRESHOLDS = {HIGH: 6, MEDIUM: 3}  # only used if the threshold rows were deleted
SCORED_GROUPS = [GoldRule.PROPERTY_LINK, GoldRule.SIZE, GoldRule.WHERE, GoldRule.BML, GoldRule.REFERRED]


@dataclass
class Rating:
    level: str
    score: int
    reasons: list = field(default_factory=list)
    is_property: bool = False


def _rules():
    return {(r.group, r.match_value): r for r in GoldRule.objects.filter(active=True)}


def thresholds(rules=None):
    rules = rules if rules is not None else _rules()
    return {
        level: rules[(GoldRule.THRESHOLD, level)].points if (GoldRule.THRESHOLD, level) in rules else default
        for level, default in DEFAULT_THRESHOLDS.items()
    }


def is_property_link(value, rules=None):
    """Does this property-link answer count as a property person? (editable: GoldRule.is_property)"""
    rules = rules if rules is not None else _rules()
    rule = rules.get((GoldRule.PROPERTY_LINK, value))
    return bool(rule and rule.is_property)


def rate_potential(signals, extra_points=0):
    """Add up the points for the signals and compare with the thresholds. Returns a Rating with plain reasons."""
    rules = _rules()
    score = int(extra_points)
    reasons = []
    for group in SCORED_GROUPS:
        value = signals.get(group)
        rule = rules.get((group, value)) if value else None
        if rule is None or rule.points == 0:
            continue
        score += rule.points
        reasons.append(f"{rule.label or rule.match_value} ({rule.points:+d})")
    if extra_points:
        reasons.append(f"Extra points from answers ({int(extra_points):+d})")
    limits = thresholds(rules)
    if score >= limits[HIGH]:
        level = HIGH
    elif score >= limits[MEDIUM]:
        level = MEDIUM
    else:
        level = LOW
    return Rating(level, score, reasons, is_property_link(signals.get(GoldRule.PROPERTY_LINK), rules))
