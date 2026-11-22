from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, get_or_404
from app.models import IntegrationOpportunity, Provider
from app.schemas import OpportunityCreate, OpportunityOut, OpportunityUpdate, PrioritisationWeights
from app.services.prioritisation import explain, get_weights, priority_score, set_weights

router = APIRouter(tags=["prioritisation"])
DISCLAIMER = ("Priority scores are a product-planning framework based on the team's own 1-5 judgements. "
              "They are not an objective market valuation.")


def _ranked(db, items):
    ordered = sorted(items, key=lambda o: o.priority_score, reverse=True)
    out = []
    for rank, o in enumerate(ordered, start=1):
        m = OpportunityOut.model_validate(o)
        m.provider_name, m.country_code, m.rank = o.provider.name, o.provider.country_code, rank
        out.append(m)
    return out


@router.get("/integration-opportunities")
def list_opportunities(db: DB, country: str | None = None, decision_status: str | None = None):
    stmt = select(IntegrationOpportunity)
    if decision_status:
        stmt = stmt.where(IntegrationOpportunity.decision_status == decision_status)
    items = list(db.scalars(stmt))
    if country:
        items = [o for o in items if o.provider.country_code == country.upper()]
    weights = get_weights(db)
    return {"items": _ranked(db, items), "weights": weights, "disclaimer": DISCLAIMER,
            "formula": "Priority = (CV^w x DI^w x SR^w x CO^w) / (TE^w x AC^w); each score normalised as score/5"}


@router.post("/integration-opportunities", response_model=OpportunityOut, status_code=201)
def create_opportunity(body: OpportunityCreate, db: DB):
    get_or_404(db, Provider, body.provider_id, "Provider")
    o = IntegrationOpportunity(**body.model_dump())
    o.priority_score = priority_score(o, get_weights(db))
    db.add(o)
    db.commit()
    db.refresh(o)
    return next(m for m in _ranked(db, list(db.scalars(select(IntegrationOpportunity)))) if m.id == o.id)


@router.get("/integration-opportunities/{opp_id}")
def get_opportunity(opp_id: int, db: DB):
    o = get_or_404(db, IntegrationOpportunity, opp_id, "Opportunity")
    m = OpportunityOut.model_validate(o)
    m.provider_name, m.country_code = o.provider.name, o.provider.country_code
    return {"opportunity": m, "explanation": explain(o, get_weights(db))}


@router.patch("/integration-opportunities/{opp_id}", response_model=OpportunityOut)
def update_opportunity(opp_id: int, body: OpportunityUpdate, db: DB):
    o = get_or_404(db, IntegrationOpportunity, opp_id, "Opportunity")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(o, k, v)
    o.priority_score = priority_score(o, get_weights(db))
    db.commit()
    return next(m for m in _ranked(db, list(db.scalars(select(IntegrationOpportunity)))) if m.id == o.id)


@router.delete("/integration-opportunities/{opp_id}", status_code=204)
def delete_opportunity(opp_id: int, db: DB):
    db.delete(get_or_404(db, IntegrationOpportunity, opp_id, "Opportunity"))
    db.commit()


@router.get("/prioritisation/weights", response_model=PrioritisationWeights)
def read_weights(db: DB):
    return get_weights(db)


@router.put("/prioritisation/weights", response_model=PrioritisationWeights)
def write_weights(body: PrioritisationWeights, db: DB):
    return set_weights(db, body)
