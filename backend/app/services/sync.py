"""Sync orchestration - identical for every provider.

authenticate -> fetch (raw payloads stored first) -> parse -> normalise -> validate -> save -> quality report

Guarantees
- A sync log is written for every attempt, including failures before any data arrives.
- Raw payloads are committed before parsing, with their outcome recorded; they are never discarded.
- A payload that fails to parse does not abort the others (partial ingestion is reported as "partial").
- Invalid / rejected records are not saved and every rejection is logged with its reason.
- Re-running the same window is idempotent (see repository.upsert_energy_records).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.connectors.base import ConnectorError, Issue, get_connector_class
from app.connectors.entsoe import redact_token
from app.connectors.http import RetryingClient
from app.models import Connector, Dataset, QualityReport, RawPayload, SyncError, SyncLog
from app.services.repository import upsert_energy_records

log = logging.getLogger("gridlink.sync")
MAX_ERROR_ROWS = 500


def _floor_quarter(dt: datetime) -> datetime:
    return dt.replace(minute=dt.minute - dt.minute % 15, second=0, microsecond=0)


def default_window(connector: Connector, now: datetime) -> tuple[datetime, datetime]:
    cfg = connector.config or {}
    if cfg.get("fixed_window"):
        s, e = cfg["fixed_window"]
        return datetime.fromisoformat(s), datetime.fromisoformat(e)
    end = _floor_quarter(now)
    return end - timedelta(days=float(cfg.get("lookback_days", 7))), end


def ensure_datasets(db: Session, provider_id: int, mapping: dict) -> dict[str, int]:
    existing = {d.dataset_key: d for d in db.query(Dataset).filter(Dataset.provider_id == provider_id)}
    fmt = {"smard": "CSV", "entsoe": "XML"}.get(mapping.get("provider", ""), "JSON")
    for spec in mapping["series"].values():
        key = spec["dataset_key"]
        if key not in existing:
            ds = Dataset(
                provider_id=provider_id, dataset_key=key, dataset_name=spec.get("dataset_name", key),
                metric_type=spec["metric_type"], energy_source=spec.get("energy_source"), format=fmt,
                unit=spec["unit"], frequency=spec.get("frequency", "PT15M"), description=spec.get("description"),
                is_active=spec.get("active", True),
            )
            db.add(ds)
            existing[key] = ds
    db.flush()
    return {k: d.id for k, d in existing.items()}


def _record_issue(db: Session, sync_log: SyncLog, issue: Issue, counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > MAX_ERROR_ROWS:
        return
    db.add(SyncError(sync_log_id=sync_log.id, stage=issue.stage, severity=issue.severity, code=issue.code,
                     message=issue.message[:2000], context=issue.context))


def build_http_client(connector_type: str, settings: Settings, transport: httpx.BaseTransport | None = None,
                      sleep=None) -> RetryingClient:
    client = httpx.Client(timeout=settings.http_timeout_seconds, transport=transport,
                          headers={"User-Agent": "GridLink/0.1 (energy-data-integration; open-source)"})
    kwargs = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    return RetryingClient(
        client,
        max_retries=settings.http_max_retries,
        backoff_base=settings.http_backoff_base_seconds,
        # ENTSO-E documents a per-user request limit; stay well below it. SMARD: be polite.
        min_interval_seconds=0.5 if connector_type.startswith("entsoe") else 0.25,
        redact=redact_token,
        **kwargs,
    )


def run_sync(
    db: Session,
    connector_id: int,
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    trigger: str = "manual",
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep=None,
    now: datetime | None = None,
) -> SyncLog:
    settings = settings or get_settings()
    now = now or datetime.now(UTC)
    connector = db.get(Connector, connector_id)
    if connector is None:
        raise ValueError(f"Connector {connector_id} not found")
    ws, we = default_window(connector, now)
    ws, we = window_start or ws, window_end or we

    sync_log = SyncLog(connector_id=connector.id, trigger=trigger, started_at=now, window_start=ws, window_end=we,
                       status="running", details={})
    db.add(sync_log)
    db.commit()
    issue_counter = [0]
    http = build_http_client(connector.connector_type, settings, transport, sleep)
    extra = {"connector_id": connector.id, "sync_id": sync_log.id, "connector_type": connector.connector_type}
    log.info("sync started", extra={**extra, "window_start": ws.isoformat(), "window_end": we.isoformat()})

    try:
        cls = get_connector_class(connector.connector_type)
        impl = cls(connector.config or {}, settings, http)

        auth = impl.authenticate()
        sync_log.details = {**sync_log.details, "auth": {"ok": auth.ok, "method": auth.method, "message": auth.message}}
        if not auth.ok:
            raise ConnectorError("authenticate", auth.code or "auth_failed", auth.message)
        if connector.status == "awaiting_credentials":
            connector.status = "active"

        payloads = impl.fetch_data(ws, we)
        raw_ids: dict[int, int] = {}
        raw_rows: dict[int, RawPayload] = {}
        for idx, p in enumerate(payloads):
            row = RawPayload(
                sync_log_id=sync_log.id, provider_id=connector.provider_id, request_url=redact_token(p.request_url),
                request_params=p.request_params, http_status=p.http_status, content_type=p.content_type,
                sha256=hashlib.sha256(p.body).hexdigest(), size_bytes=len(p.body), body=p.body, outcome="received",
            )
            db.add(row)
            raw_rows[idx] = row
        db.commit()  # raw data is durable before any transformation
        raw_ids = {i: r.id for i, r in raw_rows.items()}

        records, parse_failures = [], 0
        for idx, p in enumerate(payloads):
            try:
                parsed = impl.parse_response(p, idx)
                records.extend(parsed.records)
                for issue in parsed.issues:
                    _record_issue(db, sync_log, issue, issue_counter)
                raw_rows[idx].outcome = "parsed"
            except ConnectorError as exc:
                parse_failures += 1
                raw_rows[idx].outcome = "parse_failed"
                _record_issue(db, sync_log, Issue(exc.stage, exc.code, exc.message, context={"payload_index": idx,
                              "request": p.request_params}), issue_counter)

        normalised = impl.normalise_data(records, connector.provider_id)
        validation = impl.validate_data(normalised, ws, we, connector.max_data_lag_minutes, now=now)
        for issue in normalised.issues + validation.issues:
            _record_issue(db, sync_log, issue, issue_counter)

        dataset_ids = ensure_datasets(db, connector.provider_id, impl.mapping)
        saved = upsert_energy_records(db, validation.valid, connector_id=connector.id, dataset_ids=dataset_ids,
                                      raw_payload_ids=raw_ids)

        failed_records = normalised.rejected + validation.invalid_count
        sync_log.records_fetched = len(records)
        sync_log.records_inserted, sync_log.records_updated = saved.inserted, saved.updated
        sync_log.records_unchanged, sync_log.records_saved = saved.unchanged, saved.saved
        sync_log.records_failed = failed_records
        if payloads and parse_failures == len(payloads):
            sync_log.status = "failed"
            sync_log.error_code = "all_payloads_unparseable"
            sync_log.error_message = "Every payload failed to parse; see sync errors"
        elif parse_failures or failed_records:
            sync_log.status = "partial"
        else:
            sync_log.status = "success"

        report = QualityReport(
            connector_id=connector.id, sync_log_id=sync_log.id, completeness_score=validation.completeness_score,
            freshness_status=validation.freshness_status, duplicate_count=validation.duplicate_count,
            invalid_record_count=failed_records, null_value_count=validation.null_count,
            missing_interval_count=validation.missing_interval_count, overall_status=validation.overall_status,
            validation_details={
                **validation.checks,
                "series": [
                    {"series_key": s.series_key, "dataset_key": s.dataset_key, "interval_minutes": s.interval_minutes,
                     "expected": s.expected, "present": s.present, "nulls": s.nulls, "completeness": s.completeness,
                     "latest": s.latest_timestamp.isoformat() if s.latest_timestamp else None,
                     "freshness": s.freshness_status, "lag_minutes": s.lag_minutes,
                     "missing_periods": s.missing_periods[:50]}
                    for s in validation.series
                ],
                "window": {"start": ws.isoformat(), "end": we.isoformat()},
                "data_origin": impl.data_origin,
            },
            created_at=datetime.now(UTC),
        )
        db.add(report)
        if sync_log.status == "failed":
            connector.last_failed_sync = datetime.now(UTC)
        else:
            connector.last_successful_sync = datetime.now(UTC)
    except ConnectorError as exc:
        db.rollback()
        sync_log = db.merge(sync_log)
        connector = db.get(Connector, connector_id)
        sync_log.status, sync_log.error_code, sync_log.error_message = "failed", exc.code, exc.message
        if exc.code in ("missing_token", "invalid_token"):
            connector.status = "awaiting_credentials"  # set after rollback so it is persisted
        _record_issue(db, sync_log, Issue(exc.stage, exc.code, exc.message, context={"http_status": exc.http_status}),
                      issue_counter)
        connector.last_failed_sync = datetime.now(UTC)
        log.warning("sync failed", extra={**extra, "code": exc.code, "error": exc.message})
    except Exception as exc:  # unexpected: record it, never swallow silently
        db.rollback()
        sync_log = db.merge(sync_log)
        connector = db.get(Connector, connector_id)
        sync_log.status, sync_log.error_code = "failed", "internal_error"
        sync_log.error_message = f"{type(exc).__name__}: {exc}"
        _record_issue(db, sync_log, Issue("internal", "internal_error", sync_log.error_message), issue_counter)
        connector.last_failed_sync = datetime.now(UTC)
        log.exception("sync crashed", extra=extra)
    finally:
        sync_log.requests_made = http.stats.requests
        sync_log.requests_failed = http.stats.failures
        sync_log.retry_count = http.stats.retries
        sync_log.completed_at = datetime.now(UTC)
        sync_log.details = {**(sync_log.details or {}), "http_statuses": http.stats.statuses[-50:],
                            "rate_limited": http.stats.rate_limited, "issues_total": issue_counter[0]}
        db.commit()
        http.client.close()
    log.info("sync finished", extra={**extra, "status": sync_log.status, "saved": sync_log.records_saved,
                                     "failed": sync_log.records_failed})
    return sync_log
