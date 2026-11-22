from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, Paging, get_or_404, paginate
from app.connectors.base import CONNECTOR_REGISTRY, get_connector_class
from app.models import Connector, Provider, RawPayload, SyncError, SyncLog
from app.schemas import (
    ConnectorCreate,
    ConnectorOut,
    ConnectorUpdate,
    Page,
    RawPayloadOut,
    SyncErrorOut,
    SyncLogOut,
    SyncRequest,
)
from app.services.health import compute_connector_health
from app.services.sync import run_sync

router = APIRouter(tags=["connectors"])


def _out(db, c: Connector, with_health=True) -> ConnectorOut:
    out = ConnectorOut.model_validate(c)
    out.provider_name = c.provider.name
    out.country_code = c.provider.country_code
    if with_health:
        out.health = compute_connector_health(db, c.id)
    return out


@router.get("/connectors/types")
def connector_types():
    get_connector_class("smard_csv")  # ensure registry is populated
    return [{"connector_type": k, "provider": v.provider_slug, "data_origin": v.data_origin,
             "description": (v.__doc__ or "").strip().split("\n")[0]} for k, v in sorted(CONNECTOR_REGISTRY.items())]


@router.get("/connectors", response_model=Page[ConnectorOut])
def list_connectors(db: DB, paging: Paging, provider_id: int | None = None, include_health: bool = True):
    stmt = select(Connector).order_by(Connector.id)
    if provider_id:
        stmt = stmt.where(Connector.provider_id == provider_id)
    items, total = paginate(db, stmt, paging)
    return Page(items=[_out(db, c, include_health) for c in items], total=total, limit=paging.limit, offset=paging.offset)


@router.post("/connectors", response_model=ConnectorOut, status_code=status.HTTP_201_CREATED)
def create_connector(body: ConnectorCreate, db: DB):
    get_or_404(db, Provider, body.provider_id, "Provider")
    try:
        cls = get_connector_class(body.connector_type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if db.scalar(select(Connector).where(Connector.connector_name == body.connector_name)):
        raise HTTPException(409, f"Connector '{body.connector_name}' already exists")
    c = Connector(**body.model_dump(), data_origin=cls.data_origin, status="active")
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.get("/connectors/{connector_id}", response_model=ConnectorOut)
def get_connector(connector_id: int, db: DB):
    return _out(db, get_or_404(db, Connector, connector_id, "Connector"))


@router.patch("/connectors/{connector_id}", response_model=ConnectorOut)
def update_connector(connector_id: int, body: ConnectorUpdate, db: DB):
    c = get_or_404(db, Connector, connector_id, "Connector")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return _out(db, c)


@router.post("/connectors/{connector_id}/sync", response_model=SyncLogOut)
def sync_connector(connector_id: int, db: DB, body: SyncRequest | None = None):
    c = get_or_404(db, Connector, connector_id, "Connector")
    if c.status in ("paused", "disabled"):
        raise HTTPException(409, f"Connector is {c.status}; activate it before syncing")
    running = db.scalar(select(SyncLog).where(SyncLog.connector_id == c.id, SyncLog.status == "running"))
    if running:
        raise HTTPException(409, f"Sync {running.id} is already running for this connector")
    body = body or SyncRequest()
    if body.window_start and body.window_end and body.window_start >= body.window_end:
        raise HTTPException(422, "window_start must be before window_end")
    return run_sync(db, c.id, window_start=body.window_start, window_end=body.window_end, trigger="manual")


@router.get("/connectors/{connector_id}/health")
def connector_health(connector_id: int, db: DB):
    get_or_404(db, Connector, connector_id, "Connector")
    return compute_connector_health(db, connector_id)


@router.get("/connectors/{connector_id}/logs", response_model=Page[SyncLogOut])
def connector_logs(connector_id: int, db: DB, paging: Paging, status_filter: str | None = None):
    get_or_404(db, Connector, connector_id, "Connector")
    stmt = select(SyncLog).where(SyncLog.connector_id == connector_id).order_by(SyncLog.started_at.desc())
    if status_filter:
        stmt = stmt.where(SyncLog.status == status_filter)
    items, total = paginate(db, stmt, paging)
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)


@router.get("/connectors/{connector_id}/errors", response_model=Page[SyncErrorOut])
def connector_errors(connector_id: int, db: DB, paging: Paging, sync_log_id: int | None = None,
                     stage: str | None = None, severity: str | None = None):
    get_or_404(db, Connector, connector_id, "Connector")
    stmt = select(SyncError).join(SyncLog).where(SyncLog.connector_id == connector_id).order_by(SyncError.id.desc())
    if sync_log_id:
        stmt = stmt.where(SyncError.sync_log_id == sync_log_id)
    if stage:
        stmt = stmt.where(SyncError.stage == stage)
    if severity:
        stmt = stmt.where(SyncError.severity == severity)
    items, total = paginate(db, stmt, paging)
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)


@router.get("/connectors/{connector_id}/payloads", response_model=Page[RawPayloadOut])
def connector_payloads(connector_id: int, db: DB, paging: Paging):
    get_or_404(db, Connector, connector_id, "Connector")
    stmt = (select(RawPayload).join(SyncLog, RawPayload.sync_log_id == SyncLog.id)
            .where(SyncLog.connector_id == connector_id).order_by(RawPayload.id.desc()))
    items, total = paginate(db, stmt, paging)
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)
