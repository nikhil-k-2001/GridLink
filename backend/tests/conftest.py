from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.config import Settings
from app.db import Base, get_db
from app.models import Connector, Provider

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(rel: str) -> bytes:
    return (FIXTURES / rel).read_bytes()


@pytest.fixture
def settings():
    return Settings(entsoe_api_token=None, http_max_retries=2, http_backoff_base_seconds=0.0,
                    database_url="sqlite://", gemini_api_key=None)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    db_module._SessionLocal = Session
    with Session() as s:
        yield s


@pytest.fixture
def providers(db):
    smard = Provider(slug="smard", name="SMARD", country_code="DE", status="connected", licence="CC BY 4.0",
                     attribution="Bundesnetzagentur | SMARD.de")
    entsoe = Provider(slug="entsoe", name="ENTSO-E", country_code="EU", status="access_requested")
    db.add_all([smard, entsoe])
    db.commit()
    return {"smard": smard, "entsoe": entsoe}


@pytest.fixture
def smard_connector(db, providers):
    c = Connector(provider_id=providers["smard"].id, connector_name="SMARD test", connector_type="smard_csv",
                  config={"categories": ["generation"], "lookback_days": 1}, max_data_lag_minutes=360)
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def entsoe_connector(db, providers):
    c = Connector(provider_id=providers["entsoe"].id, connector_name="ENTSO-E test", connector_type="entsoe_api",
                  config={"area": "DE-LU", "datasets": ["generation"]}, max_data_lag_minutes=240)
    db.add(c)
    db.commit()
    return c


@pytest.fixture
def client(engine, db):
    from app.main import app

    Session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    def _get_db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


NOW = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)
