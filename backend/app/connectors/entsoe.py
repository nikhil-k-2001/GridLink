"""ENTSO-E Transparency Platform connector.

- Authentication: a personal security token, passed as the `securityToken` query parameter. GridLink
  reads it from the ENTSOE_API_TOKEN environment variable only. Without a token the connector reports
  `awaiting_credentials` and never pretends to be connected. (Verified: the API returns HTTP 401 without
  a token.)
- Responses are IEC 62325 XML documents: GL_MarketDocument (generation A75, load A65),
  Publication_MarketDocument (prices A44) or Acknowledgement_MarketDocument (errors / "no data").
- Points are positional within a Period; with curveType A03 omitted positions repeat the previous value.

`EntsoeFixtureConnector` replays local XML fixtures through exactly the same parser. Its records are
stored with data_origin = "simulated" and are labelled as such everywhere in the UI.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from app.normalisation.timestamps import TimestampError, duration_to_minutes, to_utc

TOKEN_RE = re.compile(r"^[A-Za-z0-9-]{20,64}$")
FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "entsoe_simulated"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _children(el: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in el if _local(c.tag) == name]


def _text(el: ET.Element | None, path: str) -> str | None:
    cur = el
    for part in path.split("/"):
        if cur is None:
            return None
        cur = _child(cur, part)
    return cur.text.strip() if cur is not None and cur.text else None


def redact_token(url: str) -> str:
    return re.sub(r"(securityToken=)[^&]+", r"\1REDACTED", url)


def fmt_period(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%d%H%M")


def parse_acknowledgement(root: ET.Element) -> tuple[str | None, str]:
    reason = _child(root, "Reason")
    return _text(reason, "code"), _text(reason, "text") or "No reason given"


@register
class EntsoeConnector(BaseConnector):
    connector_type = "entsoe_api"
    provider_slug = "entsoe"
    mapping_name = "entsoe"

    def __init__(self, config, settings, http=None):
        super().__init__(config, settings, http)
        # One series per zone: prices of different zones at the same time are not duplicates of each other.
        for area in self.areas:
            if area == "DE-LU":
                continue
            if area not in self.mapping["areas"]:
                raise ConnectorError("fetch", "unknown_area", f"No EIC code mapped for area '{area}'")
            for key, spec in list(self.mapping["series"].items()):
                if "@" not in key:
                    self.mapping["series"][self.series_key(key, area)] = {
                        **spec, "dataset_key": f"{spec['dataset_key']}_{area.lower().replace('-', '_')}",
                        "dataset_name": f"{spec.get('dataset_name', key)} ({area})"}

    @property
    def area(self) -> str:
        return self.areas[0]

    @property
    def areas(self) -> list[str]:
        return list(self.config.get("areas") or [self.config.get("area", "DE-LU")])

    @staticmethod
    def series_key(base: str, area: str) -> str:
        """DE-LU keeps the original keys (backwards compatible); other zones get an @zone suffix."""
        return base if area == "DE-LU" else f"{base}@{area}"

    def request_kinds(self) -> list[str]:
        return self.config.get("datasets") or list(self.mapping["requests"])

    def series_category(self, series_key: str) -> str | None:
        return {"A75": "generation", "A65": "load", "A44": "day_ahead_price"}.get(series_key.split("::", 1)[0])

    def _category_cfg(self):
        return self.mapping["requests"]

    def authenticate(self) -> AuthResult:
        token = self.settings.entsoe_api_token
        if not token:
            return AuthResult(
                ok=False,
                method="security_token",
                code="missing_token",
                message="No ENTSO-E security token configured. Register on the Transparency Platform, request "
                "RESTful API access, then set ENTSOE_API_TOKEN in backend/.env.",
            )
        if not TOKEN_RE.match(token.strip()):
            return AuthResult(False, "security_token", "ENTSOE_API_TOKEN has an unexpected format", "invalid_token_format")
        return AuthResult(ok=True, method="security_token", message="Security token present (validated on first request)")

    # ---------------------------------------------------------------------------------------------
    def _params(self, kind: str, start: datetime, end: datetime, area: str | None = None) -> dict[str, str]:
        req = self.mapping["requests"][kind]
        eic = self.mapping["areas"][area or self.area]["eic"]
        params = {"documentType": req["documentType"], "periodStart": fmt_period(start), "periodEnd": fmt_period(end)}
        if "processType" in req:
            params["processType"] = req["processType"]
        for p in req.get("area_params", [req.get("area_param")]):
            if p:
                params[p] = eic
        return params

    def fetch_data(self, window_start: datetime, window_end: datetime) -> list[FetchedPayload]:
        if self.http is None:
            raise ConnectorError("fetch", "no_http_client", "Connector has no HTTP client configured")
        token = (self.settings.entsoe_api_token or "").strip()
        payloads = []
        max_days = int(self.config.get("max_days_per_request", 7))
        start = window_start
        while start < window_end:
            end = min(window_end, start + timedelta(days=max_days))
            for kind, area in [(k, a) for k in self.request_kinds() for a in self.areas]:
                params = self._params(kind, start, end, area)
                try:
                    resp = self.http.request("GET", self.settings.entsoe_base_url, params={**params, "securityToken": token})
                except HTTPRequestFailed as exc:
                    raise ConnectorError("fetch", exc.code, f"ENTSO-E {kind}: {exc.message}", True, exc.status) from exc
                if resp.status_code == 401:
                    raise ConnectorError(
                        "authenticate", "invalid_token",
                        "ENTSO-E rejected the security token (HTTP 401). Check that RESTful API access was granted "
                        "for your account and that ENTSOE_API_TOKEN is correct.",
                        http_status=401,
                    )
                if resp.status_code >= 400:
                    reason = resp.text[:300]
                    try:
                        code, reason = parse_acknowledgement(ET.fromstring(resp.content))
                        reason = f"[{code}] {reason}"
                    except ET.ParseError:
                        pass
                    if "No matching data" in reason:
                        # A valid 'no data' answer: record it, do not treat as a transport failure.
                        payloads.append(self._payload(params, resp, kind, area))
                        continue
                    raise ConnectorError("fetch", "provider_http_error",
                                         f"ENTSO-E {kind} returned HTTP {resp.status_code}: {reason}", http_status=resp.status_code)
                payloads.append(self._payload(params, resp, kind, area))
            start = end
        return payloads

    def _payload(self, params, resp, kind, area="DE-LU") -> FetchedPayload:
        return FetchedPayload(
            request_url=redact_token(str(resp.request.url)) if resp.request else self.settings.entsoe_base_url,
            request_params=params,
            http_status=resp.status_code,
            content_type=resp.headers.get("content-type"),
            body=resp.content,
            meta={"kind": kind, "area": area},
        )

    # ---------------------------------------------------------------------------------------------
    def parse_response(self, payload: FetchedPayload, payload_index: int) -> ParseResult:
        result = ParseResult()
        try:
            root = ET.fromstring(payload.body)
        except ET.ParseError as exc:
            raise ConnectorError("parse", "malformed_xml", f"ENTSO-E response is not well-formed XML: {exc}") from exc

        doc = _local(root.tag)
        if doc == "Acknowledgement_MarketDocument":
            code, text = parse_acknowledgement(root)
            result.issues.append(Issue("parse", "no_data" if code == "999" else "provider_acknowledgement",
                                       f"ENTSO-E acknowledgement [{code}]: {text}", severity="warning",
                                       context={"kind": payload.meta.get("kind"), "reason_code": code}))
            return result
        if doc not in ("GL_MarketDocument", "Publication_MarketDocument"):
            raise ConnectorError("parse", "unexpected_document", f"Unexpected ENTSO-E document type '{doc}'")

        doc_type = _text(root, "type")
        area = payload.meta.get("area", self.area)
        country = self.mapping["areas"].get(area, {}).get("country_code", "DE")
        for ts_i, ts in enumerate(_children(root, "TimeSeries")):
            if doc_type == "A75":
                psr = _text(ts, "MktPSRType/psrType") or "UNKNOWN"
                direction = "out" if _child(ts, "outBiddingZone_Domain.mRID") is not None else "in"
                series_key = f"A75::{psr}::{direction}"
                unit = _text(ts, "quantity_Measure_Unit.name") or "?"
                value_tag = "quantity"
            elif doc_type == "A65":
                series_key, unit, value_tag = "A65::total", _text(ts, "quantity_Measure_Unit.name") or "?", "quantity"
            elif doc_type == "A44":
                cur, meas = _text(ts, "currency_Unit.name") or "?", _text(ts, "price_Measure_Unit.name") or "?"
                series_key, unit, value_tag = "A44::price", f"{cur}/{'MWh' if meas == 'MWH' else meas}", "price.amount"
            else:
                result.issues.append(Issue("parse", "unsupported_document_type", f"documentType {doc_type} not supported"))
                return result
            curve = _text(ts, "curveType") or "A01"
            for period in _children(ts, "Period"):
                self._parse_period(period, self.series_key(series_key, area), unit, value_tag, curve, country,
                                   payload_index, ts_i, result, area)
        return result

    def _parse_period(self, period, series_key, unit, value_tag, curve, country, payload_index, ts_i, result, area="DE-LU"):
        start_raw = _text(period, "timeInterval/start")
        end_raw = _text(period, "timeInterval/end")
        res_raw = _text(period, "resolution") or ""
        try:
            start = to_utc(start_raw or "")
            end = to_utc(end_raw or "")
            minutes = duration_to_minutes(res_raw)
        except TimestampError as exc:
            result.issues.append(Issue("parse", "invalid_period", f"TimeSeries {ts_i}: {exc}"))
            return
        n_slots = int((end - start).total_seconds() // 60 // minutes)
        points: dict[int, tuple[str | None, float | None, str | None]] = {}
        for pt in _children(period, "Point"):
            pos_raw = _text(pt, "position")
            raw = _text(pt, value_tag)
            try:
                pos = int(pos_raw or "")
            except ValueError:
                result.issues.append(Issue("parse", "malformed_point", f"Point with invalid position '{pos_raw}'"))
                continue
            try:
                points[pos] = (raw, float(raw) if raw is not None else None, None)
            except ValueError:
                points[pos] = (raw, None, f"'{raw}' is not numeric")

        last: tuple[str | None, float | None, str | None] | None = None
        for pos in range(1, n_slots + 1):
            if pos in points:
                last = points[pos]
                raw, val, err = points[pos]
                transform_note = None
            elif curve == "A03" and last is not None:
                raw, val, err = last  # A03: value holds until the next published position
                transform_note = "A03 carry-forward"
            else:
                continue  # genuinely missing position -> shows up as a missing interval
            ts = start + timedelta(minutes=minutes * (pos - 1))
            result.records.append(
                SourceRecord(
                    series_key=series_key,
                    timestamp_utc=ts,
                    timestamp_raw=f"{start_raw}+{res_raw}*{pos - 1}",
                    interval_minutes=minutes,
                    raw_value=raw,
                    value=val,
                    unit=unit,
                    country_code=country,
                    bidding_zone=area,
                    source_record_id=f"entsoe:{series_key}:{area}:{minutes}:{ts.strftime('%Y-%m-%dT%H:%MZ')}",
                    payload_index=payload_index,
                    location=f"TimeSeries[{ts_i}] position {pos}" + (f" ({transform_note})" if transform_note else ""),
                    parse_error=err,
                )
            )


@register
class EntsoeFixtureConnector(EntsoeConnector):
    """Replays local, clearly-labelled SIMULATED ENTSO-E XML documents. Used when no token is available."""

    connector_type = "entsoe_fixture"
    data_origin = "simulated"

    def authenticate(self) -> AuthResult:
        return AuthResult(ok=True, method="fixture", message="Simulated fixtures - no provider connection is made")

    def fetch_data(self, window_start: datetime, window_end: datetime) -> list[FetchedPayload]:
        fixture_dir = Path(self.config.get("fixture_dir") or FIXTURE_DIR)
        files = self.config.get("files") or sorted(p.name for p in fixture_dir.glob("*.xml"))
        if not files:
            raise ConnectorError("fetch", "no_fixtures", f"No fixture files found in {fixture_dir}")
        return [
            FetchedPayload(
                request_url=f"fixture://entsoe_simulated/{name}",
                request_params={"fixture": name},
                http_status=None,
                content_type="application/xml",
                body=(fixture_dir / name).read_bytes(),
                meta={"kind": name.split("_")[0], "fixture": True},
            )
            for name in files
        ]
