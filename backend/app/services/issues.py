"""Turn sync outcomes into tracked data issues that a person owns until resolved.

Automatic issues are de-duplicated: one open issue per (connector, code). New evidence is appended to the
existing issue instead of opening another one. A sync-failure issue is resolved automatically when the
connector syncs successfully again; data-quality issues stay open until a person confirms root cause and
customer communication, because "the next sync looked fine" is not a resolution for missing history.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Connector, DataIssue, SyncLog


def _open_issue(db: Session, connector_id: int, code: str) -> DataIssue | None:
    return db.scalar(select(DataIssue).where(DataIssue.connector_id == connector_id, DataIssue.code == code,
                                             DataIssue.status != "resolved"))


def _upsert(db: Session, connector: Connector, sync_log: SyncLog, code: str, title: str, severity: str,
            asset_ids: list[int], evidence: dict[str, Any], hypotheses: str | None = None,
            period: tuple[datetime | None, datetime | None] = (None, None)) -> DataIssue:
    issue = _open_issue(db, connector.id, code)
    if issue is None:
        issue = DataIssue(code=code, title=title, severity=severity, source="auto", connector_id=connector.id,
                          provider_id=connector.provider_id, sync_log_id=sync_log.id, affected_asset_ids=sorted(set(asset_ids)),
                          evidence={"syncs": [sync_log.id], **evidence}, hypotheses=hypotheses,
                          period_start=period[0], period_end=period[1], detected_at=datetime.now(UTC))
        db.add(issue)
    else:
        issue.title = title
        issue.affected_asset_ids = sorted(set(issue.affected_asset_ids or []) | set(asset_ids))
        syncs = (issue.evidence or {}).get("syncs", [])
        issue.evidence = {**(issue.evidence or {}), **evidence, "syncs": (syncs + [sync_log.id])[-20:]}
        if period[0] and (issue.period_start is None or period[0] < issue.period_start.replace(tzinfo=issue.period_start.tzinfo or UTC)):
            issue.period_start = period[0]
        if period[1]:
            issue.period_end = period[1]
    return issue


def raise_sync_failure_issue(db: Session, connector: Connector, sync_log: SyncLog) -> None:
    _upsert(db, connector, sync_log, "sync_failed", f"{connector.connector_name}: sync failing ({sync_log.error_code})",
            "high", [], {"last_error": sync_log.error_message},
            "Credentials missing/expired · provider outage · API contract change · network/firewall")
    db.commit()


def raise_issues_from_sync(db: Session, connector: Connector, sync_log: SyncLog, impl, validation, provider_issues, now) -> None:
    # recovery: close an automatic sync-failure issue
    failing = _open_issue(db, connector.id, "sync_failed")
    if failing is not None:
        failing.status, failing.resolved_at = "resolved", now
        failing.resolution = f"Sync #{sync_log.id} succeeded ({sync_log.status}); closed automatically."

    asset_by_series = {k: v.get("asset_id") for k, v in impl.mapping["series"].items() if v.get("asset_id")}

    denied_ids = {i.context.get("asset_id") for i in provider_issues if i.code == "authorisation_denied"}

    # incomplete plant / dataset data (plants refused by the data holder are tracked by their own issue)
    weak = [s for s in validation.series if s.expected and s.completeness < 98
            and asset_by_series.get(s.series_key) not in denied_ids]
    if weak:
        starts = [datetime.fromisoformat(p["start"]) for s in weak for p in s.missing_periods]
        ends = [datetime.fromisoformat(p["end"]) for s in weak for p in s.missing_periods]
        names = _names(db, [asset_by_series.get(s.series_key) for s in weak])
        label = ", ".join(names or [s.series_key for s in weak][:4])
        _upsert(db, connector, sync_log, "incomplete_data",
                f"{connector.connector_name}: incomplete data for {label}",
                "high" if any(s.completeness < 90 for s in weak) else "medium",
                [a for a in (asset_by_series.get(s.series_key) for s in weak) if a],
                {"series": {s.series_key: {"completeness": s.completeness, "missing_periods": s.missing_periods[:10]} for s in weak}},
                "Provider has not published yet (lag) · metering/communication fault at the plant · "
                "provider-side outage · our request window or time-zone handling is wrong",
                (min(starts) if starts else None, max(ends) if ends else None))

    # authorisation mismatch between GridLink and the data holder
    denied = [i for i in provider_issues if i.code == "authorisation_denied"]
    if denied:
        ids = [i.context.get("asset_id") for i in denied if i.context.get("asset_id")]
        _upsert(db, connector, sync_log, "authorisation_denied",
                f"{connector.connector_name}: data holder refuses access for {', '.join(_names(db, ids))}", "high", ids,
                {"responses": [i.context.get("provider_response") for i in denied][:5]},
                "Owner revoked consent · consent expired · consent given for a different metering point · "
                "our authorisation record is out of date")

    estimated = [i for i in provider_issues if i.code == "estimated_values"]
    if estimated:
        ids = [i.context.get("asset_id") for i in estimated if i.context.get("asset_id")]
        _upsert(db, connector, sync_log, "estimated_values",
                f"{connector.connector_name}: estimated (not metered) values for {', '.join(_names(db, ids))}", "low", ids,
                {"counts": {i.context.get("asset_name"): i.context.get("count") for i in estimated}},
                "Meter communication failure; the DSO estimates and replaces values later — expect revisions")

    if validation.duplicate_count:
        _upsert(db, connector, sync_log, "duplicate_records",
                f"{connector.connector_name}: provider delivered {validation.duplicate_count} duplicate readings", "low", [],
                {"duplicates": validation.duplicate_count, "conflicting": validation.conflicting_duplicates},
                "Provider export bug · overlapping request windows · DST handling on provider side")
    db.commit()


def _names(db: Session, asset_ids) -> list[str]:
    ids = [a for a in asset_ids if a]
    if not ids:
        return []
    return [a.name for a in db.scalars(select(Asset).where(Asset.id.in_(ids)).order_by(Asset.name))]
