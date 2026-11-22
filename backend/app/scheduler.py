"""Optional background sync (APScheduler). Disabled by default: GridLink's primary workflow is an explicit,
auditable manual sync. Enable with SCHEDULER_ENABLED=true; each connector with sync_interval_minutes is
scheduled at that interval."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db import session_factory
from app.models import Connector
from app.services.sync import run_sync

log = logging.getLogger("gridlink.scheduler")
_scheduler: BackgroundScheduler | None = None


def _job(connector_id: int) -> None:
    with session_factory()() as db:
        c = db.get(Connector, connector_id)
        if c is None or c.status != "active":
            return
        run_sync(db, connector_id, trigger="scheduled")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    with session_factory()() as db:
        for c in db.scalars(select(Connector).where(Connector.sync_interval_minutes.is_not(None))):
            _scheduler.add_job(_job, "interval", minutes=c.sync_interval_minutes, args=[c.id], id=f"sync-{c.id}",
                               max_instances=1, coalesce=True)
            log.info("scheduled connector", extra={"connector_id": c.id, "minutes": c.sync_interval_minutes})
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
