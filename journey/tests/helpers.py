"""Shared by tests that finish a journey: since 2026-11-21 nothing is optional, so a finished journey needs every
visible question answered. MINIMAL is the shortest plain path (suggests Tier 2)."""
from journey import services

MINIMAL = {
    "time": ["evening"], "frequency": ["two_three"], "facilities": ["gym"], "company": ["alone"],
    "industry": ["tech"], "heard_via": ["friend"],
}


def answer_minimal(session, **overrides):
    """Answer every required question on the plain path; `overrides` change or add answers (key=[values] or key="text")."""
    for key, value in {**MINIMAL, **overrides}.items():
        values = value if isinstance(value, list) else [value]
        services.save_answer(session, key, options=values)
    return session
