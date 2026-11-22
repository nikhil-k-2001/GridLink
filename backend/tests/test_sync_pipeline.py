import json
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select

from app.models import Connector, EnergyRecord, QualityReport, RawPayload, SyncError
from app.services.health import compute_connector_health
from app.services.sync import run_sync
from tests.conftest import read_fixture

WS, WE = datetime(2026, 11, 20, 18, 0, tzinfo=UTC), datetime(2026, 11, 20, 19, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
NOOP = lambda s: None  # noqa: E731


def smard_transport(gen_body: bytes, cons_body: bytes | None = None):
    def handler(request: httpx.Request):
        form = json.loads(request.content)["request_form"][0]
        if form["moduleIds"][0] >= 5_000_000:
            return httpx.Response(200, content=cons_body or b"")
        return httpx.Response(200, content=gen_body, headers={"content-type": "text/csv"})
    return httpx.MockTransport(handler)


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_successful_sync_saves_normalised_records_with_provenance(db, smard_connector, settings):
    log = run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
                   transport=smard_transport(read_fixture("smard/generation_en.csv")), sleep=NOOP, now=NOW)
    # 12 values: 4 nuclear (unmapped-inactive is still mapped -> kept as nulls), 1 malformed rejected
    assert log.status == "partial" and log.records_fetched == 12 and log.records_failed == 1
    assert log.records_inserted == 11
    rec = db.scalar(select(EnergyRecord).where(EnergyRecord.energy_source == "wind_onshore").order_by(EnergyRecord.timestamp_utc))
    assert rec.value == 3540.87 * 4 and rec.unit == "MW" and rec.original_value == "3,540.87" and rec.original_unit == "MWh"
    assert rec.raw_payload_id is not None and rec.data_origin == "real"
    raw = db.get(RawPayload, rec.raw_payload_id)
    assert raw.outcome == "parsed" and raw.body == read_fixture("smard/generation_en.csv")
    report = db.scalar(select(QualityReport))
    assert report.invalid_record_count == 1 and report.null_value_count >= 1
    assert db.scalar(select(SyncError).where(SyncError.code == "malformed_value")) is not None


def test_ingestion_is_idempotent_and_revisions_update(db, smard_connector, settings):
    body = read_fixture("smard/generation_en.csv")
    run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
             transport=smard_transport(body), sleep=NOOP, now=NOW)
    n = count(db, EnergyRecord)
    second = run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
                      transport=smard_transport(body), sleep=NOOP, now=NOW)
    assert count(db, EnergyRecord) == n
    assert second.records_inserted == 0 and second.records_unchanged == 11
    revised = body.replace(b"3,540.87", b"3,600.00")
    third = run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
                     transport=smard_transport(revised), sleep=NOOP, now=NOW)
    assert third.records_updated == 1 and count(db, EnergyRecord) == n


def test_partial_ingestion_keeps_good_payloads_and_records_bad_ones(db, smard_connector, settings):
    smard_connector.config = {"categories": ["generation", "consumption"]}
    db.commit()
    log = run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
                   transport=smard_transport(read_fixture("smard/generation_en.csv"), read_fixture("smard/bad_columns.csv")),
                   sleep=NOOP, now=NOW)
    assert log.status == "partial"
    outcomes = sorted(r.outcome for r in db.scalars(select(RawPayload)))
    assert outcomes == ["parse_failed", "parsed"]
    assert db.scalar(select(SyncError).where(SyncError.code == "unexpected_columns")) is not None
    assert count(db, EnergyRecord) == 11


def test_provider_outage_fails_sync_after_retries(db, smard_connector, settings):
    log = run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
                   transport=httpx.MockTransport(lambda r: httpx.Response(503)), sleep=NOOP, now=NOW)
    assert log.status == "failed" and log.error_code == "provider_server_error"
    assert log.requests_made == 3 and log.retry_count == 2 and log.requests_failed == 3
    assert db.get(Connector, smard_connector.id).last_failed_sync is not None
    assert count(db, EnergyRecord) == 0
    health = compute_connector_health(db, smard_connector.id, now=NOW)
    assert health["status"] == "failed" and health["request_success_rate"] == 0.0


def test_entsoe_without_token_is_never_reported_as_connected(db, entsoe_connector, settings):
    log = run_sync(db, entsoe_connector.id, settings=settings, sleep=NOOP, now=NOW)
    assert log.status == "failed" and log.error_code == "missing_token" and log.requests_made == 0
    c = db.get(Connector, entsoe_connector.id)
    assert c.status == "awaiting_credentials"
    health = compute_connector_health(db, c.id, now=NOW)
    assert health["status"] == "failed"
    assert any("Awaiting credentials" in r["reason"] for r in health["reasons"])


def test_simulated_fixture_sync_labels_data_and_finds_planted_defects(db, providers, settings):
    c = Connector(provider_id=providers["entsoe"].id, connector_name="sim", connector_type="entsoe_fixture",
                  data_origin="simulated", config={"fixed_window": ["2026-11-13T23:00:00+00:00", "2026-11-20T23:00:00+00:00"]},
                  max_data_lag_minutes=240)
    db.add(c)
    db.commit()
    log = run_sync(db, c.id, settings=settings, sleep=NOOP, now=NOW)
    assert log.status == "partial" and log.records_failed == 1  # planted negative biomass value
    origins = set(db.scalars(select(EnergyRecord.data_origin).distinct()))
    assert origins == {"simulated"}
    report = db.scalar(select(QualityReport))
    wind_off = next(s for s in report.validation_details["series"] if s["series_key"] == "A75::B18::in")
    assert wind_off["missing_periods"][0]["intervals"] == 8
    assert report.validation_details["data_origin"] == "simulated"
    health = compute_connector_health(db, c.id, now=NOW)
    assert any("SIMULATED" in r["reason"] for r in health["reasons"])


def test_healthy_requires_more_than_http_200(db, smard_connector, settings):
    # HTTP 200 but only 2 of 11 expected generation series delivered -> not healthy
    run_sync(db, smard_connector.id, window_start=WS, window_end=WE, settings=settings,
             transport=smard_transport(read_fixture("smard/generation_en.csv")), sleep=NOOP, now=NOW)
    health = compute_connector_health(db, smard_connector.id, now=datetime(2026, 11, 20, 20, tzinfo=UTC))
    assert health["status"] in ("degraded", "failed")
    assert any("Completeness" in r["reason"] for r in health["reasons"]), health["reasons"]


