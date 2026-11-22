"""Energi Data Service (Energinet, Danish TSO) — REAL public data, no key.

Verified on 2026-11-22:
- GET https://api.energidataservice.dk/dataset/<name>?start=..&end=..&timezone=utc&columns=..&sort=..&limit=0
  returns {"records": [...]} ; start inclusive, end exclusive, times in UTC with timezone=utc.
- PowerSystemRightNow: 1-minute values (MW) published within ~1 minute. The provider notes they are upscaled
  real-time SCADA measurements, errors "will generally not be corrected" — fine for operations, not statistics.
- DayAheadPrices: 15-minute prices (EUR/MWh) for DK1, DK2 and DE (among others). Elspotprices (hourly) ended
  2025-09-30 with the move to 15-minute day-ahead products.
- Rate limiting answers HTTP 429 with the wait time only in the body ("Try again in 36 seconds").
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

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

BASE_URL = "https://api.energidataservice.dk/dataset"


def _fmt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


@register
class EnerginetConnector(BaseConnector):
    """Energi Data Service (Denmark): real-time 1-minute wind & solar, 15-minute day-ahead prices."""

    connector_type = "energinet_api"
    provider_slug = "energinet"
    mapping_name = "energinet"

    def datasets(self) -> list[str]:
        return [d for d in (self.config.get("datasets") or list(self.mapping["datasets"])) if d in self.mapping["datasets"]]

    def series_category(self, series_key: str) -> str | None:
        return "realtime" if series_key.startswith("realtime::") else "day_ahead_price"

    def _category_cfg(self):
        return self.mapping["datasets"]

    def expected_series(self) -> list[str]:
        out = []
        if "realtime" in self.datasets():
            out += [f"realtime::{c}" for c in self.mapping["datasets"]["realtime"]["columns"]]
        if "day_ahead_price" in self.datasets():
            out += [f"price::{a}" for a in self.mapping["datasets"]["day_ahead_price"]["areas"]]
        return out

    def authenticate(self) -> AuthResult:
        return AuthResult(ok=True, method="none", message="Public API, no authentication")

    def fetch_data(self, window_start: datetime, window_end: datetime) -> list[FetchedPayload]:
        if self.http is None:
            raise ConnectorError("fetch", "no_http_client", "Connector has no HTTP client configured")
        payloads = []
        for key in self.datasets():
            cfg = self.mapping["datasets"][key]
            end = window_end + timedelta(hours=36) if cfg.get("publishes_ahead") else window_end
            params = {"start": _fmt(window_start), "end": _fmt(end), "timezone": "utc", "limit": "0",
                      "sort": f"{cfg['time_column']} asc"}
            if key == "realtime":
                params["columns"] = ",".join([cfg["time_column"], *cfg["columns"]])
            else:
                params["columns"] = f"{cfg['time_column']},PriceArea,DayAheadPriceEUR"
                params["filter"] = json.dumps({"PriceArea": cfg["areas"]})
            url = f"{self.config.get('base_url', BASE_URL)}/{cfg['dataset']}"
            try:
                resp = self.http.request("GET", url, params=params)
            except HTTPRequestFailed as exc:
                raise ConnectorError("fetch", exc.code, f"Energi Data Service {cfg['dataset']}: {exc.message}", True, exc.status) from exc
            if resp.status_code >= 400:
                raise ConnectorError("fetch", "provider_http_error",
                                     f"Energi Data Service {cfg['dataset']} returned HTTP {resp.status_code}: {resp.text[:200]}",
                                     http_status=resp.status_code)
            payloads.append(FetchedPayload(request_url=str(resp.request.url), request_params=params, http_status=resp.status_code,
                                           content_type=resp.headers.get("content-type"), body=resp.content, meta={"dataset": key}))
        return payloads

    def parse_response(self, payload: FetchedPayload, payload_index: int) -> ParseResult:
        try:
            data = json.loads(payload.body)
            records = data["records"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ConnectorError("parse", "unexpected_schema", f"Energi Data Service response has no 'records': {exc}") from exc
        key = payload.meta["dataset"]
        cfg = self.mapping["datasets"][key]
        out = ParseResult()
        if not records:
            out.issues.append(Issue("parse", "no_data", f"{cfg['dataset']}: no records in window", "warning"))
            return out
        minutes = cfg["interval_minutes"]
        for i, r in enumerate(records):
            raw_ts = r.get(cfg["time_column"])
            try:
                ts = datetime.fromisoformat(raw_ts).replace(tzinfo=UTC)  # timezone=utc: naive values are UTC
            except (TypeError, ValueError):
                ts = None
            if key == "realtime":
                fields = [(f"realtime::{c}", r.get(c), "MW", "DK", None) for c in cfg["columns"]]
            else:
                area = r.get("PriceArea")
                info = self.mapping["price_areas"].get(area, {"country_code": "DK", "bidding_zone": area})
                fields = [(f"price::{area}", r.get("DayAheadPriceEUR"), "EUR/MWh", info["country_code"], info["bidding_zone"])]
            for series_key, raw, unit, country, zone in fields:
                value, err = None, None
                if raw is not None:
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        err = f"'{raw}' is not numeric"
                stamp = ts.strftime("%Y-%m-%dT%H:%MZ") if ts else f"raw:{raw_ts}"
                out.records.append(SourceRecord(
                    series_key=series_key, timestamp_utc=ts, timestamp_raw=str(raw_ts), interval_minutes=minutes,
                    raw_value=None if raw is None else str(raw), value=value, unit=unit, country_code=country, bidding_zone=zone,
                    source_record_id=f"energinet:{series_key}:{minutes}:{stamp}", payload_index=payload_index,
                    location=f"{cfg['dataset']} record {i + 1}", parse_error=err))
        return out
