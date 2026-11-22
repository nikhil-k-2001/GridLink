from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.api.deps import DB, get_or_404
from app.models import INVESTIGATION_SECTIONS, Provider, ProviderFact, ProviderInvestigation
from app.schemas import InvestigationCreate, InvestigationOut, InvestigationUpdate
from app.services.reports import completion, to_csv, to_markdown

router = APIRouter(tags=["investigations"])


def _out(inv: ProviderInvestigation) -> InvestigationOut:
    o = InvestigationOut.model_validate(inv)
    o.provider_name = inv.provider.name
    o.completion = completion(inv)
    return o


@router.get("/investigations/template")
def template():
    return [{"key": k, "title": t, "number": i} for i, (k, t) in enumerate(INVESTIGATION_SECTIONS, start=1)]


@router.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(db: DB, provider_id: int | None = None):
    stmt = select(ProviderInvestigation).order_by(ProviderInvestigation.updated_at.desc())
    if provider_id:
        stmt = stmt.where(ProviderInvestigation.provider_id == provider_id)
    return [_out(i) for i in db.scalars(stmt)]


@router.post("/investigations", response_model=InvestigationOut, status_code=201)
def create_investigation(body: InvestigationCreate, db: DB):
    get_or_404(db, Provider, body.provider_id, "Provider")
    if db.scalar(select(ProviderInvestigation).where(ProviderInvestigation.provider_id == body.provider_id)):
        raise HTTPException(409, "An investigation already exists for this provider; update it instead")
    inv = ProviderInvestigation(**body.model_dump())
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _out(inv)


@router.get("/investigations/export.csv", response_class=PlainTextResponse)
def export_all_csv(db: DB):
    rows = [(i, i.provider) for i in db.scalars(select(ProviderInvestigation))]
    return PlainTextResponse(to_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="gridlink-investigations.csv"'})


@router.get("/investigations/{inv_id}", response_model=InvestigationOut)
def get_investigation(inv_id: int, db: DB):
    return _out(get_or_404(db, ProviderInvestigation, inv_id, "Investigation"))


@router.put("/investigations/{inv_id}", response_model=InvestigationOut)
def update_investigation(inv_id: int, body: InvestigationUpdate, db: DB):
    inv = get_or_404(db, ProviderInvestigation, inv_id, "Investigation")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(inv, k, v)
    db.commit()
    db.refresh(inv)
    return _out(inv)


@router.get("/investigations/{inv_id}/export")
def export_investigation(inv_id: int, db: DB, format: str = Query("md", pattern="^(md|csv)$")):
    inv = get_or_404(db, ProviderInvestigation, inv_id, "Investigation")
    slug = inv.provider.slug
    if format == "csv":
        return PlainTextResponse(to_csv([(inv, inv.provider)]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="{slug}-investigation.csv"'})
    facts = list(db.scalars(select(ProviderFact).where(ProviderFact.provider_id == inv.provider_id)))
    return PlainTextResponse(to_markdown(inv, inv.provider, facts), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{slug}-onboarding-report.md"'})
