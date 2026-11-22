"""Scheduled refresh for serverless hosting (Vercel Cron calls this daily)."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.api.deps import DB
from app.config import get_settings
from app.models import Connector
from app.services.sync import run_sync

router = APIRouter(tags=["system"])
REFRESH_TYPES = ("smard_csv", "fr_dso_sim", "es_dso_sim", "energinet_api")
REALTIME_TYPES = ("energinet_api",)


def _check(authorization: str | None) -> None:
    secret = get_settings().cron_secret
    if not secret or authorization != f"Bearer {secret}":
        raise HTTPException(401, "Cron secret required")


def _run(db, types, start, end) -> dict:
    out = []
    for c in db.scalars(select(Connector).where(Connector.connector_type.in_(types), Connector.status == "active")):
        log = run_sync(db, c.id, window_start=start, window_end=end, trigger="scheduled")
        out.append({"connector_id": c.id, "status": log.status, "saved": log.records_saved})
    return {"synced": out}


@router.get("/cron/daily-sync")
def daily_sync(db: DB, authorization: str | None = Header(default=None)):
    """Daily backstop: last 3 days for every refreshable connector (catches provider revisions)."""
    _check(authorization)
    end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    return _run(db, REFRESH_TYPES, end - timedelta(days=3), end)


@router.get("/cron/realtime-sync")
def realtime_sync(db: DB, authorization: str | None = Header(default=None)):
    """Every 15 minutes: last 3 hours of real-time sources (small, fast, within provider rate limits)."""
    _check(authorization)
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    return _run(db, REALTIME_TYPES, end - timedelta(hours=3), end)
