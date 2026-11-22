"""First-start setup for serverless deployments (AUTO_SETUP=true).

Runs Alembic migrations and seeds the demo workspace when the database is empty. A Postgres advisory lock
makes concurrent cold starts safe: one instance sets up, the others wait and then find it done. Failures are
logged and reported by /health instead of crashing the app, so a missing database is diagnosable.
"""
import logging
from pathlib import Path

from sqlalchemy import text

from app.db import get_engine

log = logging.getLogger("gridlink.setup")
LOCK_ID = 42_4242
STATE: dict[str, str | None] = {"status": "not_run", "error": None}


def ensure_ready() -> None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": LOCK_ID})
            try:
                from alembic.config import Config

                from alembic import command

                cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
                command.upgrade(cfg, "head")
                seeded = conn.execute(text("SELECT count(*) FROM providers")).scalar()
                if not seeded:
                    from app.seed import seed

                    seed()
                    log.info("demo workspace seeded")
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
                conn.commit()
        STATE.update(status="ready", error=None)
    except Exception as exc:  # report, don't crash: /health explains what is wrong
        STATE.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:300]}")
        log.exception("setup failed")
