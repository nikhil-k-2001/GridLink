from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.connectors.base import FetchedPayload
from app.connectors.dso_sim import EsDsoSimConnector, FrDsoSimConnector
from app.models import Asset, Connector, DataIssue, EnergyRecord
from app.normalisation.engine import normalise_records
from app.quality.engine import validate_batch
from app.services.coverage import compute_coverage, demand
from app.services.sync import build_http_client, run_sync
from app.simulated import dso_api

NOOP = lambda s: None  # noqa: E731


def fr(settings, plants):
    c = FrDsoSimConnector({}, settings, build_http_client("fr_dso_sim", settings, FrDsoSimConnector.default_transport(), sleep=NOOP))
    c.authenticate()
    for i, (mp, auth) in enumerate(plants, start=1):
        c.add_plant(i, f"Plant {i}", mp, "wind_onshore", 24.0, auth)
    return c


class TestSimulatedPlatforms:
    def test_fr_requires_token_and_consent(self):
        url = "http://localhost:8000/simulated/fr-dso/v5/metering_data/production_load_curve"
        p = {"usage_point_id": "99000000000104", "start": "2026-11-10", "end": "2026-11-11"}
        assert dso_api.handle(httpx.Request("GET", url, params=p)).status_code == 401
        r = dso_api.handle(httpx.Request("GET", url, params=p, headers={"Authorization": "Bearer sim-fr-oauth-token"}))
        assert r.status_code in (403, 429)

    def test_fr_rejects_windows_over_seven_days(self):
        url = "http://x/simulated/fr-dso/v5/metering_data/production_load_curve"
        p = {"usage_point_id": "99000000000101", "start": "2026-11-01", "end": "2026-11-15"}
        codes = {dso_api.handle(httpx.Request("GET", url, params=p, headers={"Authorization": "Bearer sim-fr-oauth-token"})).status_code
                 for _ in range(2)}
        assert 400 in codes


class TestFranceConnector:
    def test_w_interval_end_paris_time_becomes_mw_interval_start_utc(self, settings):
        c = fr(settings, [("99000000000101", "granted")])
        body = (b'{"meter_reading":{"usage_point_id":"99000000000101","reading_type":{"unit":"W"},'
                b'"interval_reading":[{"value":"12000000","date":"2026-11-20 00:30:00","interval_length":"PT30M"}]}}')
        res = c.parse_response(FetchedPayload("u", {}, 200, "application/json", body, {"asset_id": 1, "metering_point_id": "99000000000101",
                                                                                       "asset_name": "P"}), 0)
        rec = res.records[0]
        assert rec.timestamp_utc == datetime(2026, 11, 19, 23, 0, tzinfo=UTC)  # 00:30 CET end -> 00:00 CET start -> 23:00 UTC
        norm = c.normalise_data(res.records, 1).records[0]
        assert norm.value == pytest.approx(12.0) and norm.unit == "MW" and norm.asset_id == 1 and norm.metric_type == "asset_production"

    def test_only_authorised_plants_are_requested_and_blocks_do_not_overlap(self, settings):
        c = fr(settings, [("99000000000101", "granted"), ("99000000000105", "requested")])
        start = datetime(2026, 11, 1, 12, tzinfo=UTC)
        payloads = c.fetch_data(start, start + timedelta(days=10))
        params = [p.request_params for p in payloads]
        assert {p["usage_point_id"] for p in params} == {"99000000000101"}
        days = sorted((date.fromisoformat(p["start"]), date.fromisoformat(p["end"])) for p in params)
        assert all(a[1] <= b[0] for a, b in zip(days, days[1:], strict=False))  # end exclusive == next start

    def test_revoked_consent_becomes_authorisation_denied(self, settings):
        c = fr(settings, [("99000000000104", "granted")])
        payloads = c.fetch_data(datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 11, tzinfo=UTC))
        issues = [i for p in payloads for i in c.parse_response(p, 0).issues]
        assert issues and issues[0].code == "authorisation_denied" and issues[0].context["metering_point_id"] == "99000000000104"


class TestSpainConnector:
    def parse(self, settings, rows):
        import json

        c = EsDsoSimConnector({}, settings)
        c.add_plant(7, "Solar", "ES0000SIM0000000202ZZ", "solar", 40.0, "granted")
        meta = {"asset_id": 7, "metering_point_id": "ES0000SIM0000000202ZZ", "asset_name": "Solar"}
        return c, c.parse_response(FetchedPayload("u", {}, 200, "application/json", json.dumps(rows).encode(), meta), 0)

    def test_hour_ending_labels_and_24h(self, settings):
        rows = [{"cups": "ES0000SIM0000000202ZZ", "date": "2026/11/20", "time": "01:00", "generationEnergyKWh": 5000, "obtainMethod": "Real"},
                {"cups": "ES0000SIM0000000202ZZ", "date": "2026/11/20", "time": "24:00", "generationEnergyKWh": 0, "obtainMethod": "Real"}]
        c, res = self.parse(settings, rows)
        assert res.records[0].timestamp_utc == datetime(2026, 11, 19, 23, tzinfo=UTC)  # 00:00-01:00 CET
        assert res.records[1].timestamp_utc == datetime(2026, 11, 20, 22, tzinfo=UTC)  # 23:00-24:00 CET
        assert c.normalise_data(res.records, 1).records[0].value == pytest.approx(5.0)  # 5000 kWh in 1 h = 5 MW

    def test_estimated_values_are_flagged_not_dropped(self, settings):
        rows = [{"cups": "ES0000SIM0000000202ZZ", "date": "2026/11/20", "time": "12:00", "generationEnergyKWh": 9000, "obtainMethod": "Estimada"}]
        _, res = self.parse(settings, rows)
        assert res.records[0].flags == ("estimated",) and res.issues[0].code == "estimated_values"


def test_regression_plants_sharing_a_dataset_are_not_duplicates(settings):
    """Bug found during development: logical duplicates were keyed on dataset, so plant 2 looked like a copy of plant 1."""
    c = fr(settings, [("99000000000101", "granted"), ("99000000000103", "granted")])
    payloads = c.fetch_data(datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 12, tzinfo=UTC))
    recs = [r for i, p in enumerate(payloads) for r in c.parse_response(p, i).records]
    norm = normalise_records(recs, c.mapping, provider_id=1, data_origin="simulated")
    v = validate_batch(norm, c.mapping, datetime(2026, 11, 10, tzinfo=UTC), datetime(2026, 11, 12, tzinfo=UTC), 2880,
                       now=datetime(2026, 11, 20, tzinfo=UTC))
    assert v.duplicate_count == 0 and {r.series_key for r in v.valid} == {"asset::99000000000101", "asset::99000000000103"}


class TestWorkflowEndToEnd:
    def sync_dsos(self, db, settings, now):
        ids = [c.id for c in db.scalars(select(Connector).where(Connector.connector_type.in_(["fr_dso_sim", "es_dso_sim"])))]
        return [run_sync(db, i, settings=settings, sleep=NOOP, now=now) for i in ids]

    def test_dso_syncs_raise_the_planted_issues(self, workspace, settings):
        now = datetime.now(UTC)
        logs = self.sync_dsos(workspace, settings, now)
        assert {log.status for log in logs} <= {"success", "partial"}
        codes = {i.code for i in workspace.scalars(select(DataIssue).where(DataIssue.source == "auto"))}
        assert {"authorisation_denied", "incomplete_data", "estimated_values", "duplicate_records"} <= codes
        denied = workspace.scalar(select(DataIssue).where(DataIssue.code == "authorisation_denied"))
        names = {a.name for a in workspace.scalars(select(Asset).where(Asset.id.in_(denied.affected_asset_ids)))}
        assert names == {"Provence Solar II"}
        gap = workspace.scalar(select(DataIssue).where(DataIssue.code == "incomplete_data", DataIssue.connector_id == logs[0].connector_id))
        assert "Côte d'Opale Wind" in gap.title and "Provence Solar II" not in gap.title  # denied plant not double-reported
        assert workspace.scalar(select(EnergyRecord).where(EnergyRecord.asset_id.is_not(None))).data_origin == "simulated"

    def test_issues_are_deduplicated_across_syncs(self, workspace, settings):
        now = datetime.now(UTC)
        self.sync_dsos(workspace, settings, now)
        n = len(list(workspace.scalars(select(DataIssue))))
        self.sync_dsos(workspace, settings, now)
        assert len(list(workspace.scalars(select(DataIssue)))) == n

    def test_coverage_statuses_explain_every_gap(self, workspace, settings):
        self.sync_dsos(workspace, settings, datetime.now(UTC))
        cov = compute_coverage(workspace)
        st = {(a["name"], n["need"]): n["status"] for a in cov["assets"] for n in a["needs"]}
        assert st[("Plaine de Beauce Wind", "production_metering")] == "covered"
        assert st[("Provence Solar II", "production_metering")] == "access_denied"
        assert st[("Aquitaine Solar", "production_metering")] == "awaiting_authorisation"
        assert st[("Navarra Wind", "production_metering")] == "authorisation_not_requested"
        assert st[("Campania Wind", "production_metering")] == "route_blocked"
        assert st[("Puglia Solar", "day_ahead_price")] == "route_blocked"
        assert st[("Flevoland Wind", "production_metering")] == "no_route"
        assert all(n["reason"] for a in cov["assets"] for n in a["needs"])

    def test_demand_feeds_customer_value(self, workspace):
        d = demand(compute_coverage(workspace), "IT", "production_metering")
        assert d["plants"] == 3 and d["capacity_mw"] == 80.0 and len(d["customers"]) == 2 and d["suggested_customer_value"] == 5

    def test_sync_failure_issue_auto_resolves(self, workspace, settings):
        c = workspace.scalar(select(Connector).where(Connector.connector_type == "es_dso_sim"))
        c.config = {"client_token": "wrong"}
        workspace.commit()
        assert run_sync(workspace, c.id, settings=settings, sleep=NOOP).status == "failed"
        issue = workspace.scalar(select(DataIssue).where(DataIssue.code == "sync_failed"))
        assert issue.status == "open" and issue.severity == "high"
        c.config = {}
        workspace.commit()
        run_sync(workspace, c.id, settings=settings, sleep=NOOP)
        workspace.refresh(issue)
        assert issue.status == "resolved" and "closed automatically" in issue.resolution
