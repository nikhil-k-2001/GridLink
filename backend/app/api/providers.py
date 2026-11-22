import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DB, Paging, get_or_404, paginate
from app.models import Connector, Dataset, Provider, ProviderFact
from app.schemas import (
    DatasetOut,
    Page,
    ProviderCreate,
    ProviderDetail,
    ProviderFactIn,
    ProviderFactOut,
    ProviderOut,
    ProviderUpdate,
)

router = APIRouter(tags=["providers"])


def _out(db, p: Provider, detail=False):
    data = ProviderOut.model_validate(p).model_dump()
    data["dataset_count"] = db.scalar(select(func.count()).where(Dataset.provider_id == p.id)) or 0
    data["connector_count"] = db.scalar(select(func.count()).where(Connector.provider_id == p.id)) or 0
    if detail:
        data["facts"] = [ProviderFactOut.model_validate(f) for f in p.facts]
        data["datasets"] = [DatasetOut.model_validate(d) for d in p.datasets]
        return ProviderDetail(**data)
    return ProviderOut(**data)


def _url(v):
    return str(v) if v is not None else None


@router.get("/providers", response_model=Page[ProviderOut])
def list_providers(db: DB, paging: Paging, country: str | None = None, status_: str | None = Query(None, alias="status"),
                   q: str | None = None):
    stmt = select(Provider).order_by(Provider.name)
    if country:
        stmt = stmt.where(Provider.country_code == country.upper())
    if status_:
        stmt = stmt.where(Provider.status == status_)
    if q:
        stmt = stmt.where(or_(Provider.name.ilike(f"%{q}%"), Provider.description.ilike(f"%{q}%")))
    items, total = paginate(db, stmt, paging)
    return Page(items=[_out(db, p) for p in items], total=total, limit=paging.limit, offset=paging.offset)


@router.post("/providers", response_model=ProviderDetail, status_code=status.HTTP_201_CREATED)
def create_provider(body: ProviderCreate, db: DB):
    slug = body.slug or re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:64]
    if db.scalar(select(Provider).where(Provider.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A provider with slug '{slug}' already exists")
    data = body.model_dump(exclude={"slug"})
    data["website"], data["documentation_url"] = _url(body.website), _url(body.documentation_url)
    p = Provider(slug=slug, **data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(db, p, detail=True)


@router.get("/providers/{provider_id}", response_model=ProviderDetail)
def get_provider(provider_id: int, db: DB):
    return _out(db, get_or_404(db, Provider, provider_id, "Provider"), detail=True)


@router.patch("/providers/{provider_id}", response_model=ProviderDetail)
def update_provider(provider_id: int, body: ProviderUpdate, db: DB):
    p = get_or_404(db, Provider, provider_id, "Provider")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, _url(v) if k in ("website", "documentation_url") else v)
    db.commit()
    db.refresh(p)
    return _out(db, p, detail=True)


@router.post("/providers/{provider_id}/facts", response_model=ProviderFactOut, status_code=201)
def add_fact(provider_id: int, body: ProviderFactIn, db: DB):
    get_or_404(db, Provider, provider_id, "Provider")
    f = ProviderFact(provider_id=provider_id, category=body.category, statement=body.statement,
                     evidence_level=body.evidence_level, source_url=_url(body.source_url),
                     checked_at=datetime.now(UTC))
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


@router.delete("/providers/{provider_id}/facts/{fact_id}", status_code=204)
def delete_fact(provider_id: int, fact_id: int, db: DB):
    f = get_or_404(db, ProviderFact, fact_id, "Fact")
    if f.provider_id != provider_id:
        raise HTTPException(404, "Fact not found for this provider")
    db.delete(f)
    db.commit()


@router.get("/datasets", response_model=Page[DatasetOut], tags=["datasets"])
def list_datasets(db: DB, paging: Paging, provider_id: int | None = None, metric_type: str | None = None,
                  active: bool | None = None):
    stmt = select(Dataset).order_by(Dataset.provider_id, Dataset.metric_type, Dataset.dataset_name)
    if provider_id:
        stmt = stmt.where(Dataset.provider_id == provider_id)
    if metric_type:
        stmt = stmt.where(Dataset.metric_type == metric_type)
    if active is not None:
        stmt = stmt.where(Dataset.is_active == active)
    items, total = paginate(db, stmt, paging)
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)
