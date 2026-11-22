"""Connector health. HTTP 200 is not "healthy": health combines sync outcomes, request reliability,
completeness, validity and data freshness computed from stored records."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Connector, EnergyRecord, QualityReport, SyncError, SyncLog

HISTORY = 20
SEVERITY = ["healthy", "warning", "degraded", "failed"]
FRESHNESS_ORDER = ["fresh", "delayed", "stale"]


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def data_freshness(db: Session, connector: Connector, now: datetime) -> dict[str, Any]:
    """Latest non-null interval end per metric for this connector's records."""
    rows = db.execute(
        select(EnergyRecord.metric_type, func.max(EnergyRecord.timestamp_utc), func.max(EnergyRecord.interval_minutes))
        .where(EnergyRecord.connector_id == connector.id, EnergyRecord.value.is_not(None))
        .group_by(EnergyRecord.metric_type)
    ).all()
    lag_limit = connector.max_data_lag_minutes
    metrics = {}
    worst = None
    for metric, latest, interval in rows:
        latest = _aware(latest)
        lag = (now - (latest + timedelta(minutes=interval or 15))).total_seconds() / 60
        status = "fresh" if lag <= lag_limit else "delayed" if lag <= 2 * lag_limit else "stale"
        metrics[metric] = {"latest": latest.isoformat(), "lag_minutes": round(lag, 1), "status": status}
        if metric != "day_ahead_price":  # prices are published ahead; they never define staleness
            if worst is None or FRESHNESS_ORDER.index(status) > FRESHNESS_ORDER.index(worst):
                worst = status
    return {"status": worst or ("unknown" if not metrics else "fresh"), "max_lag_minutes": lag_limit, "metrics": metrics}


def compute_connector_health(db: Session, connector_id: int, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    connector = db.get(Connector, connector_id)
    if connector is None:
        raise ValueError("connector not found")

    logs = list(db.scalars(
        select(SyncLog).where(SyncLog.connector_id == connector_id, SyncLog.status != "running")
        .order_by(SyncLog.started_at.desc()).limit(HISTORY)
    ))
    report = db.scalars(
        select(QualityReport).where(QualityReport.connector_id == connector_id)
        .order_by(QualityReport.created_at.desc()).limit(1)
    ).first()
    recent_errors = list(db.scalars(
        select(SyncError).join(SyncLog).where(SyncLog.connector_id == connector_id, SyncError.severity == "error")
        .order_by(SyncError.id.desc()).limit(10)
    ))
    freshness = data_freshness(db, connector, now)

    n = len(logs)
    ok_syncs = sum(1 for log in logs if log.status in ("success", "partial"))
    sync_success_rate = round(100 * ok_syncs / n, 1) if n else None
    requests = sum(log.requests_made for log in logs)
    req_failed = sum(log.requests_failed for log in logs)
    request_success_rate = round(100 * (requests - req_failed) / requests, 1) if requests else None
    last = logs[0] if logs else None
    fetched = last.records_fetched if last else 0
    failed_records = last.records_failed if last else 0
    completeness = report.completeness_score if report else None

    status, reasons = "healthy", []

    def raise_to(level: str, reason: str) -> None:
        nonlocal status
        reasons.append({"level": level, "reason": reason})
        if SEVERITY.index(level) > SEVERITY.index(status):
            status = level

    if connector.status == "awaiting_credentials":
        raise_to("failed", "Awaiting credentials: no API token configured")
    if not logs:
        raise_to("failed", "Never synced")
    else:
        if last.status == "failed":
            if not connector.last_successful_sync or freshness["status"] in ("stale", "unknown"):
                raise_to("failed", f"Last sync failed ({last.error_code}): {last.error_message}")
            else:
                raise_to("degraded", f"Last sync failed ({last.error_code}) but previously ingested data is still usable")
        elif last.status == "partial":
            raise_to("warning", f"Last sync was partial: {failed_records} of {fetched} records rejected")
        if sync_success_rate is not None and sync_success_rate < 80:
            raise_to("degraded", f"Only {sync_success_rate}% of the last {n} syncs succeeded")
        elif sync_success_rate is not None and sync_success_rate < 95:
            raise_to("warning", f"{sync_success_rate}% sync success rate over the last {n} syncs")
        if request_success_rate is not None and request_success_rate < 90:
            raise_to("warning", f"Request success rate {request_success_rate}% (retries: {sum(x.retry_count for x in logs)})")
        if last.retry_count:
            raise_to("warning", f"Last sync needed {last.retry_count} retries")

    if report:
        if completeness is None:
            raise_to("warning", "Completeness could not be measured: no settled intervals in the last sync window")
        elif completeness < 90:
            raise_to("degraded", f"Completeness {completeness}% in last sync window (HTTP success alone is not health)")
        elif completeness is not None and completeness < 98:
            raise_to("warning", f"Completeness {completeness}% - {report.missing_interval_count} intervals missing")
        if report.invalid_record_count and fetched and report.invalid_record_count / fetched > 0.05:
            raise_to("degraded", f"{report.invalid_record_count} invalid records (>5%)")
        elif report.invalid_record_count:
            raise_to("warning", f"{report.invalid_record_count} invalid records rejected")
        # A healthy average must not hide one badly incomplete dataset.
        weak = [s for s in (report.validation_details or {}).get("series", []) if s.get("completeness", 100) < 90]
        if weak:
            raise_to("warning", "Incomplete datasets: " + ", ".join(
                f"{s['series_key']} {s['completeness']}%" for s in weak[:4]) + (" …" if len(weak) > 4 else ""))
        if report.duplicate_count:
            raise_to("warning", f"{report.duplicate_count} duplicate records in last delivery")
    if freshness["status"] == "stale":
        raise_to("degraded", f"Data is stale (expected within {connector.max_data_lag_minutes} min)")
    elif freshness["status"] == "delayed":
        raise_to("warning", "Data delivery is delayed beyond the expected publication lag")

    if connector.data_origin == "simulated":
        reasons.append({"level": "info", "reason": "SIMULATED fixture data - not a live provider connection"})

    return {
        "connector_id": connector.id,
        "status": status,
        "reasons": reasons,
        "data_origin": connector.data_origin,
        "last_successful_sync": connector.last_successful_sync,
        "last_failed_sync": connector.last_failed_sync,
        "last_sync_status": last.status if last else None,
        "sync_success_rate": sync_success_rate,
        "request_success_rate": request_success_rate,
        "http_error_rate": round(100 - request_success_rate, 1) if request_success_rate is not None else None,
        "retry_count": sum(x.retry_count for x in logs),
        "syncs_considered": n,
        "completeness": completeness,
        "freshness": freshness,
        "failed_records_last_sync": failed_records,
        "records_fetched_last_sync": fetched,
        "recent_errors": [
            {"id": e.id, "sync_log_id": e.sync_log_id, "stage": e.stage, "code": e.code, "message": e.message,
             "created_at": e.created_at}
            for e in recent_errors
        ],
        "computed_at": now,
    }
