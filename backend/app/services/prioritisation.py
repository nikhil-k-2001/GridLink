"""Connection prioritisation - a transparent PRODUCT-PLANNING framework, not a market valuation.

Each factor is scored 1-5 and normalised to n = score / 5 (0.2 .. 1.0; never zero, so no division by zero).

    Priority = (CV^w1 x DI^w2 x SR^w3 x CO^w4) / (TE^w5 x AC^w6)

Default weights reproduce the documented formula (Customer Value x Data Importance x Strategic Relevance)
/ (Technical Effort x Access Complexity); commercial opportunity has weight 0 by default and can be enabled.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AppSetting, IntegrationOpportunity
from app.schemas import PrioritisationWeights

SETTINGS_KEY = "prioritisation_weights"
BENEFITS = ("customer_value", "data_importance", "strategic_relevance", "commercial_opportunity")
COSTS = ("technical_effort", "access_complexity")


def get_weights(db: Session) -> PrioritisationWeights:
    row = db.get(AppSetting, SETTINGS_KEY)
    return PrioritisationWeights(**row.value) if row else PrioritisationWeights()


def set_weights(db: Session, weights: PrioritisationWeights) -> PrioritisationWeights:
    row = db.get(AppSetting, SETTINGS_KEY)
    if row:
        row.value = weights.model_dump()
    else:
        db.add(AppSetting(key=SETTINGS_KEY, value=weights.model_dump()))
    for opp in db.query(IntegrationOpportunity):
        opp.priority_score = priority_score(opp, weights)
    db.commit()
    return weights


def normalise(score: int) -> float:
    if not 1 <= score <= 5:
        raise ValueError("scores must be between 1 and 5")
    return score / 5.0


def priority_score(opp, weights: PrioritisationWeights) -> float:
    w = weights.model_dump()
    num = 1.0
    for f in BENEFITS:
        num *= normalise(getattr(opp, f)) ** w[f]
    den = 1.0
    for f in COSTS:
        den *= normalise(getattr(opp, f)) ** w[f]
    return round(num / den, 4)


def explain(opp, weights: PrioritisationWeights) -> dict:
    w = weights.model_dump()
    return {
        "normalised": {f: normalise(getattr(opp, f)) for f in BENEFITS + COSTS},
        "weights": w,
        "formula": "(CV^w x DI^w x SR^w x CO^w) / (TE^w x AC^w), scores normalised as score/5",
        "score": priority_score(opp, weights),
    }
