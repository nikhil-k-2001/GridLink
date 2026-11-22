from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, text

from app.api.deps import DB
from app.config import get_settings
from app.models import Connector, Dataset, EnergyRecord, Provider, QualityReport, SyncError, SyncLog
from app.schemas import AIRequest
from app.services import ai
from app.services.health import compute_connector_health

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "time": datetime.now(UTC)}


@router.get("/settings/status")
def settings_status():
    s = get_settings()
    return {
        "entsoe_token_configured": bool(s.entsoe_api_token),
        "entsoe_base_url": s.entsoe_base_url,
        "gemini_configured": bool(s.gemini_api_key),
        "gemini_model": s.gemini_model,
        "scheduler_enabled": s.scheduler_enabled,
        "http": {"timeout_seconds": s.http_timeout_seconds, "max_retries": s.http_max_retries,
                 "backoff_base_seconds": s.http_backoff_base_seconds},
        "note": "Secrets are read from environment variables only and are never returned by the API.",
    }


@router.get("/overview")
def overview(db: DB):
    now = datetime.now(UTC)
    connectors = list(db.scalars(select(Connector).order_by(Connector.id)))
    healths = []
    for c in connectors:
        h = compute_connector_health(db, c.id, now)
        healths.append({"id": c.id, "name": c.connector_name, "provider": c.provider.name,
                        "country_code": c.provider.country_code, "data_origin": c.data_origin,
                        "status": h["status"], "completeness": h["completeness"],
                        "freshness": h["freshness"]["status"], "last_successful_sync": c.last_successful_sync,
                        "reasons": h["reasons"][:3]})
    counts = {s: sum(1 for h in healths if h["status"] == s) for s in ("healthy", "warning", "degraded", "failed")}
    by_origin = dict(db.execute(select(EnergyRecord.data_origin, func.count()).group_by(EnergyRecord.data_origin)).all())
    since = now - timedelta(days=7)
    recent_syncs = db.execute(select(SyncLog.status, func.count()).where(SyncLog.started_at >= since)
                              .group_by(SyncLog.status)).all()
    recent_errors = db.scalar(select(func.count()).select_from(SyncError).where(SyncError.created_at >= since,
                                                                                SyncError.severity == "error"))
    provider_status = dict(db.execute(select(Provider.status, func.count()).group_by(Provider.status)).all())
    latest_reports = db.execute(select(QualityReport.overall_status, func.count()).group_by(QualityReport.overall_status)).all()
    last_syncs = [
        {"id": s.id, "connector_id": s.connector_id, "status": s.status, "started_at": s.started_at,
         "records_saved": s.records_saved, "records_failed": s.records_failed, "error_code": s.error_code}
        for s in db.scalars(select(SyncLog).order_by(SyncLog.started_at.desc()).limit(8))
    ]
    return {
        "connectors": healths, "connector_status_counts": counts,
        "records": {"total": sum(by_origin.values()), "by_origin": by_origin},
        "datasets": db.scalar(select(func.count()).select_from(Dataset)),
        "providers": {"total": sum(provider_status.values()), "by_status": provider_status},
        "syncs_last_7d": dict(recent_syncs), "errors_last_7d": recent_errors or 0,
        "quality_reports_by_status": dict(latest_reports), "recent_syncs": last_syncs, "generated_at": now,
    }


@router.post("/ai/assist")
def ai_assist(body: AIRequest, db: DB):
    context = body.text or ""
    if body.task == "summarise_errors" and body.connector_id:
        errs = db.scalars(select(SyncError).join(SyncLog).where(SyncLog.connector_id == body.connector_id)
                          .order_by(SyncError.id.desc()).limit(40))
        context = "\n".join(f"[{e.stage}/{e.code}] {e.message}" for e in errs) or "No errors recorded."
    if body.task == "explain_dataset" and body.dataset_id:
        d = db.get(Dataset, body.dataset_id)
        if d is None:
            raise HTTPException(404, "Dataset not found")
        context = (f"Provider: {d.provider.name}\nDataset: {d.dataset_name}\nMetric: {d.metric_type}\nSource: "
                   f"{d.energy_source}\nPublished unit: {d.unit}\nFrequency: {d.frequency}\nDescription: {d.description}\n"
                   "GridLink canonical unit: MW average power (or EUR/MWh for prices).")
    if not context.strip():
        raise HTTPException(422, "No context provided")
    try:
        return {"task": body.task, "text": ai.generate(get_settings(), body.task, context), "model": get_settings().gemini_model,
                "disclaimer": "AI-generated summary. Verify against logs and provider documentation."}
    except ai.AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
