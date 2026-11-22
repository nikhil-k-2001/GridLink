"""Plant-level metering connectors for two SIMULATED DSO platforms (see app/simulated/dso_api.py).

What they demonstrate:
- Data access is per metering point and depends on the plant owner's authorisation held by the DSO.
  GridLink only requests data for plants it believes are authorised; a 403 means GridLink's records and
  the data holder disagree -> an `authorisation_denied` issue, not a silent gap.
- Each platform has its own conventions (W vs kWh, 30-min vs hourly, interval-end vs hour-ending labels,
  local time zones, estimated readings). The connectors only translate; normalisation, validation,
  persistence and health are the shared pipeline.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.connectors.base import (
    AuthResult,
    BaseConnector,
    ConnectorError,
    FetchedPayload,
    Issue,
    ParseResult,
    SourceRecord,
    register,
)
from app.connectors.http import HTTPRequestFailed
from app.normalisation.timestamps import duration_to_minutes, localise_series
from app.simulated import dso_api


class SimDsoConnector(BaseConnector):
    data_origin = "simulated"
    platform: str = ""
    default_base_url: str = ""
    max_days: int = 7

    @classmethod
    def default_transport(cls):
        return dso_api.transport()

    def __init__(self, config, settings, http=None):
        super().__init__(config, settings, http)
        self.plants: list[dict[str, Any]] = []

    # --- context ----------------------------------------------------------------------------------
    def prepare(self, db, connector_row) -> None:
        from app.models import Asset, AssetAuthorisation

        auths = {a.asset_id: a for a in db.query(AssetAuthorisation).filter(AssetAuthorisation.provider_id == connector_row.provider_id)}
        for a in db.query(Asset).filter(Asset.dso_provider_id == connector_row.provider_id).order_by(Asset.id):
            self.add_plant(a.id, a.name, a.metering_point_id, a.technology, a.capacity_mw,
                                auths[a.id].status if a.id in auths else "not_requested")

    def add_plant(self, asset_id, name, mp, technology, capacity_mw, auth_status):
        self.plants.append({"asset_id": asset_id, "name": name, "mp": mp, "technology": technology,
                            "capacity_mw": capacity_mw, "auth": auth_status})
        self.mapping["series"][f"asset::{mp}"] = {
            "dataset_key": f"{self.mapping['provider']}_sim_asset_production", "dataset_name": f"Plant production ({self.platform}, simulated)",
            "metric_type": "asset_production", "energy_source": technology, "unit": self.mapping["published_unit"],
            "frequency": self.mapping["frequency"], "asset_id": asset_id, "max_value": round(capacity_mw * 1.05, 3),
            "description": f"Metered production of {name}. Published as {self.mapping['published_unit']} per "
                           f"{self.mapping['frequency']}; stored as average MW.",
        }

    def authorised_plants(self) -> list[dict[str, Any]]:
        return [p for p in self.plants if p["auth"] == "granted"]

    def expected_series(self) -> list[str]:
        return [f"asset::{p['mp']}" for p in self.authorised_plants()]

    def series_category(self, series_key: str) -> str | None:
        return "production"

    def _category_cfg(self):
        return self.mapping["requests"]

    def authenticate(self) -> AuthResult:
        token = self.config.get("client_token", dso_api.SIM_TOKENS[self.platform])
        if not token:
            return AuthResult(False, "oauth2_simulated", "No client token configured", "missing_token")
        self._token = token
        return AuthResult(True, "oauth2_simulated", "Simulated platform credentials (no real provider is contacted)")

    # --- fetch ------------------------------------------------------------------------------------
    def _request(self, path: str, params: dict[str, str], plant: dict[str, Any]) -> FetchedPayload:
        base = self.config.get("base_url", self.default_base_url)
        try:
            resp = self.http.request("GET", f"{base}{path}", params=params, headers={"Authorization": f"Bearer {self._token}"})
        except HTTPRequestFailed as exc:
            raise ConnectorError("fetch", exc.code, f"{self.platform}: {exc.message}", True, exc.status) from exc
        if resp.status_code == 401:
            raise ConnectorError("authenticate", "invalid_token", f"{self.platform} rejected the client token (HTTP 401)", http_status=401)
        meta = {"asset_id": plant["asset_id"], "metering_point_id": plant["mp"], "asset_name": plant["name"]}
        if resp.status_code >= 400:
            meta["error_status"] = resp.status_code
        return FetchedPayload(request_url=str(resp.request.url), request_params=params, http_status=resp.status_code,
                              content_type=resp.headers.get("content-type"), body=resp.content, meta=meta)

    def fetch_data(self, window_start: datetime, window_end: datetime) -> list[FetchedPayload]:
        """One request per plant per block of local calendar days; blocks never overlap."""
        if self.http is None:
            raise ConnectorError("fetch", "no_http_client", "Connector has no HTTP client configured")
        tz = ZoneInfo(self.mapping["source_timezone"])
        first, last = window_start.astimezone(tz).date(), window_end.astimezone(tz).date()  # inclusive local dates
        payloads = []
        for plant in self.authorised_plants():
            day = first
            while day <= last:
                block_last = min(last, day + timedelta(days=self.max_days - 1))
                payloads.append(self._request(*self.request_for(plant, day, block_last), plant))
                day = block_last + timedelta(days=1)
        return payloads

    def request_for(self, plant, first_day, last_day) -> tuple[str, dict[str, str]]:
        """Build (path, params) for an inclusive range of local calendar days."""
        raise NotImplementedError

    # --- parse ------------------------------------------------------------------------------------
    def parse_response(self, payload: FetchedPayload, payload_index: int) -> ParseResult:
        m = payload.meta
        if "error_status" in m:
            try:
                body = json.loads(payload.body)
            except ValueError:
                body = {"raw": payload.body[:200].decode(errors="replace")}
            code = "authorisation_denied" if m["error_status"] == 403 else "provider_http_error"
            msg = (f"{m['asset_name']} ({m['metering_point_id']}): data holder refused access — GridLink records the "
                   f"authorisation as granted, the provider does not" if code == "authorisation_denied"
                   else f"{m['asset_name']}: HTTP {m['error_status']}")
            return ParseResult(issues=[Issue("fetch", code, msg, context={**m, "provider_response": body})])
        try:
            data = json.loads(payload.body)
        except ValueError as exc:
            raise ConnectorError("parse", "malformed_json", f"{self.platform}: response is not JSON: {exc}") from exc
        return self.parse_json(data, payload_index, m)

    def parse_json(self, data, payload_index: int, meta: dict[str, Any]) -> ParseResult:
        raise NotImplementedError

    def _records(self, ends_naive: pd.Series, minutes: int, raw_values, values, unit, mp, payload_index, labels, flags):
        tz = self.mapping["source_timezone"]
        out = ParseResult()
        try:
            ends = localise_series(ends_naive.reset_index(drop=True), tz)
        except Exception as exc:
            raise ConnectorError("parse", "timestamp_ambiguity", f"Cannot resolve local timestamps: {exc}") from exc
        for i, end in enumerate(ends):
            start = end.to_pydatetime() - timedelta(minutes=minutes)
            out.records.append(SourceRecord(
                series_key=f"asset::{mp}", timestamp_utc=start.astimezone(UTC), timestamp_raw=labels[i],
                interval_minutes=minutes, raw_value=raw_values[i], value=values[i][0], unit=unit,
                country_code=self.mapping["country_code"], bidding_zone=None,
                source_record_id=f"{self.platform}:{mp}:{minutes}:{start.astimezone(UTC):%Y-%m-%dT%H:%MZ}",
                payload_index=payload_index, location=f"{mp} reading {i + 1}", parse_error=values[i][1], flags=flags[i]))
        return out


def _num(raw) -> tuple[float | None, str | None]:
    try:
        return float(raw), None
    except (TypeError, ValueError):
        return None, f"'{raw}' is not numeric"


@register
class FrDsoSimConnector(SimDsoConnector):
    """France DSO metering (SIMULATED, Enedis-like consent model): 30-min W, interval-end Paris time."""

    connector_type = "fr_dso_sim"
    provider_slug = "enedis"
    mapping_name = "fr_dso_sim"
    platform = "fr-dso"
    default_base_url = "http://localhost:8000/simulated/fr-dso"

    def request_for(self, plant, first_day, last_day):
        # this API's `end` is exclusive
        return "/v5/metering_data/production_load_curve", {
            "usage_point_id": plant["mp"], "start": first_day.isoformat(), "end": (last_day + timedelta(days=1)).isoformat()}

    def parse_json(self, data, payload_index, meta):
        mr = data.get("meter_reading") or {}
        readings = mr.get("interval_reading")
        if readings is None:
            raise ConnectorError("parse", "unexpected_schema", "fr-dso response has no meter_reading.interval_reading")
        if not readings:
            return ParseResult(issues=[Issue("parse", "no_data", f"{meta['asset_name']}: no readings in window", "warning", meta)])
        unit = (mr.get("reading_type") or {}).get("unit", "?")
        minutes = duration_to_minutes(readings[0].get("interval_length", "PT30M"))
        ends = pd.Series(pd.to_datetime([r.get("date") for r in readings], format="%Y-%m-%d %H:%M:%S", errors="coerce"))
        if ends.isna().any():
            raise ConnectorError("parse", "invalid_timestamp", f"{meta['asset_name']}: unparseable reading dates")
        return self._records(ends, minutes, [r.get("value") for r in readings], [_num(r.get("value")) for r in readings],
                             unit, mr.get("usage_point_id", meta["metering_point_id"]), payload_index,
                             [r.get("date") for r in readings], [()] * len(readings))


@register
class EsDsoSimConnector(SimDsoConnector):
    """Spain DSO metering (SIMULATED, Datadis-like): hourly kWh, hour-ending labels in Madrid time."""

    connector_type = "es_dso_sim"
    provider_slug = "datadis"
    mapping_name = "es_dso_sim"
    platform = "es-dso"
    default_base_url = "http://localhost:8000/simulated/es-dso"

    def request_for(self, plant, first_day, last_day):
        # this API's endDate is inclusive
        return "/api-private/api/get-production-data", {
            "cups": plant["mp"], "startDate": first_day.strftime("%Y/%m/%d"), "endDate": last_day.strftime("%Y/%m/%d")}

    def parse_json(self, data, payload_index, meta):
        if not isinstance(data, list):
            raise ConnectorError("parse", "unexpected_schema", "es-dso response is not a list of readings")
        if not data:
            return ParseResult(issues=[Issue("parse", "no_data", f"{meta['asset_name']}: no readings in window", "warning", meta)])
        ends = []
        for r in data:
            d = datetime.strptime(r["date"], "%Y/%m/%d")
            h = int(r["time"].split(":")[0])  # "24:00" = midnight at the end of that day
            ends.append(d + timedelta(hours=h))
        flags = [("estimated",) if r.get("obtainMethod") == "Estimada" else () for r in data]
        res = self._records(pd.Series(pd.to_datetime(ends)), 60, [str(r.get("generationEnergyKWh")) for r in data],
                            [_num(r.get("generationEnergyKWh")) for r in data], "kWh", data[0].get("cups", meta["metering_point_id"]),
                            payload_index, [f"{r['date']} {r['time']}" for r in data], flags)
        est = sum(1 for f in flags if f)
        if est:
            res.issues.append(Issue("parse", "estimated_values", f"{meta['asset_name']}: {est} hourly values are estimates "
                                    "(obtainMethod=Estimada), not meter readings", "warning", {**meta, "count": est}))
        return res
