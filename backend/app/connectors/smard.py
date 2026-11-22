"""SMARD (Bundesnetzagentur) connector - real public CSV downloads.

Verified behaviour of the SMARD download centre (see docs/providers/smard-onboarding.md):
- POST {smard_download_url} with a JSON `request_form`; no authentication.
- Response is a semicolon-separated CSV with a UTF-8 BOM; multiple data categories in one request return a
  ZIP archive instead, so GridLink requests one category at a time (and still accepts ZIP).
- English CSVs use "Nov 18, 2026 7:00 PM" timestamps and 1,234.56 numbers; German CSVs use
  "18.11.2026 19:00" and 1.234,56.
- Timestamps are Europe/Berlin local time (DST fall-back hours repeat).
- "-" means the provider published no value (e.g. nuclear since April 2023) - it is not zero.
- Wholesale prices require region "DE-LU" (bidding zone); region "DE" returns "No data for submitted query".
Data licence: CC BY 4.0, attribution "Bundesnetzagentur | SMARD.de".
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import UTC, datetime, timedelta

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
from app.normalisation.timestamps import localise_series

HEADER_RE = re.compile(r"^(?P<name>.+?)\s*\[(?P<unit>[^\]]+)\]\s*(?P<resolution>.*)$")
LANG_PROFILES = {
    "en": {
        "start": "Start date",
        "end": "End date",
        "ts_format": "%b %d, %Y %I:%M %p",
        "number_re": re.compile(r"^-?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$"),
        "thousands": ",",
        "decimal": ".",
    },
    "de": {
        "start": "Datum von",
        "end": "Datum bis",
        "ts_format": "%d.%m.%Y %H:%M",
        "number_re": re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+)(,\d+)?$"),
        "thousands": ".",
        "decimal": ",",
    },
}
RESOLUTION_MINUTES = {"quarterhour": 15, "hour": 60, "day": 1440}
NO_DATA_MARKER = "No data for submitted query"


def parse_number(text: str, profile: dict) -> float:
    if not profile["number_re"].match(text):
        raise ValueError(f"'{text}' is not a valid number in {profile['decimal']!r}-decimal format")
    return float(text.replace(profile["thousands"], "").replace(profile["decimal"], "."))


def detect_separator(header_line: str) -> str:
    try:
        return csv.Sniffer().sniff(header_line, delimiters=";,\t").delimiter
    except csv.Error:
        return ";"


def split_csv_files(body: bytes) -> list[tuple[str, str]]:
    """Return [(filename, text)] for a plain CSV body or a ZIP archive of CSVs."""
    if body[:2] == b"PK":
        out = []
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".csv"):
                    out.append((name, zf.read(name).decode("utf-8-sig")))
        return out
    return [("response.csv", body.decode("utf-8-sig"))]


@register
class SmardConnector(BaseConnector):
    connector_type = "smard_csv"
    provider_slug = "smard"
    mapping_name = "smard"

    @property
    def resolution(self) -> str:
        return self.config.get("resolution", "quarterhour")

    @property
    def language(self) -> str:
        return self.config.get("language", "en")

    def categories(self) -> list[str]:
        wanted = self.config.get("categories") or list(self.mapping["categories"])
        return [c for c in wanted if c in self.mapping["categories"]]

    def series_category(self, series_key: str) -> str | None:
        return series_key.split("::", 1)[0]

    def _category_cfg(self):
        return self.mapping["categories"]

    def expected_series(self) -> list[str]:
        cats = set(self.categories())
        return [k for k in self.active_series() if self.series_category(k) in cats]

    def authenticate(self) -> AuthResult:
        return AuthResult(ok=True, method="none", message="SMARD public downloads require no authentication")

    def _module_ids(self, category: str) -> list[int]:
        active = {s["module_id"] for k, s in self.active_series().items() if k.startswith(f"{category}::")}
        return [m for m in self.mapping["categories"][category]["module_ids"] if m in active]

    def fetch_data(self, window_start: datetime, window_end: datetime) -> list[FetchedPayload]:
        if self.http is None:
            raise ConnectorError("fetch", "no_http_client", "Connector has no HTTP client configured")
        payloads: list[FetchedPayload] = []
        max_days = int(self.config.get("max_days_per_request", 7))
        chunk_start = window_start
        while chunk_start < window_end:
            chunk_end = min(window_end, chunk_start + timedelta(days=max_days))
            for category in self.categories():
                cat = self.mapping["categories"][category]
                # Day-ahead prices are published for the next delivery day: look ahead on the final chunk.
                to = chunk_end + timedelta(hours=36) if cat.get("publishes_ahead") and chunk_end == window_end else chunk_end
                form = {
                    "format": "CSV",
                    "moduleIds": self._module_ids(category),
                    "region": cat["region"],
                    "timestamp_from": int(chunk_start.timestamp() * 1000),
                    "timestamp_to": int(to.timestamp() * 1000),
                    "type": "discrete",
                    "language": self.language,
                    "resolution": self.resolution,
                }
                if not form["moduleIds"]:
                    continue
                url = self.settings.smard_download_url
                try:
                    resp = self.http.request("POST", url, json={"request_form": [form]})
                except HTTPRequestFailed as exc:
                    raise ConnectorError("fetch", exc.code, f"SMARD {category}: {exc.message}", True, exc.status) from exc
                if resp.status_code >= 400:
                    raise ConnectorError(
                        "fetch",
                        "provider_http_error",
                        f"SMARD download centre returned HTTP {resp.status_code} for {category}: {resp.text[:200]}",
                        http_status=resp.status_code,
                    )
                payloads.append(
                    FetchedPayload(
                        request_url=url,
                        request_params=form,
                        http_status=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        body=resp.content,
                        meta={"category": category},
                    )
                )
            chunk_start = chunk_end
        return payloads

    def parse_response(self, payload: FetchedPayload, payload_index: int) -> ParseResult:
        category = payload.meta["category"]
        result = ParseResult()
        try:
            files = split_csv_files(payload.body)
        except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
            raise ConnectorError("parse", "malformed_payload", f"SMARD response is not a readable CSV/ZIP: {exc}") from exc
        for filename, text in files:
            self._parse_csv(text, category, payload_index, filename, result)
        return result

    def _parse_csv(self, text: str, category: str, payload_index: int, filename: str, result: ParseResult) -> None:
        cat_cfg = self.mapping["categories"][category]
        aliases = self.mapping["column_aliases"][category]
        missing_tokens = set(self.mapping.get("missing_value_tokens", ["-"]))
        if not text.strip():
            result.issues.append(Issue("parse", "empty_payload", f"{filename} is empty"))
            return
        header_line = text.splitlines()[0]
        sep = detect_separator(header_line)
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
        cols = list(df.columns)

        lang = next((k for k, p in LANG_PROFILES.items() if len(cols) >= 2 and cols[0].strip() == p["start"]), None)
        if lang is None:
            raise ConnectorError(
                "parse",
                "unexpected_columns",
                f"{filename}: first columns {cols[:2]} are not SMARD start/end date columns",
            )
        profile = LANG_PROFILES[lang]
        if cols[1].strip() != profile["end"]:
            raise ConnectorError("parse", "unexpected_columns", f"{filename}: expected '{profile['end']}' as column 2")

        # "No data" rows: SMARD returns the header plus marker rows when nothing is published.
        no_data = df[cols[0]].str.strip() == NO_DATA_MARKER
        if no_data.any():
            result.issues.append(
                Issue("parse", "no_data", f"{filename}: provider returned '{NO_DATA_MARKER}'", severity="warning",
                      context={"category": category, "region": cat_cfg["region"]})
            )
            df = df[~no_data]
        if df.empty:
            return

        interval = RESOLUTION_MINUTES.get(self.resolution, 15)
        naive = pd.to_datetime(df[cols[0]].str.strip(), format=profile["ts_format"], errors="coerce")
        bad_ts = naive.isna()
        utc_index: dict[int, datetime] = {}
        good = naive[~bad_ts]
        try:
            localised = localise_series(good, self.mapping["source_timezone"])
            utc_index = {i: ts.to_pydatetime() for i, ts in localised.items()}
        except Exception as exc:  # ambiguous times that cannot be inferred, non-existent times
            result.issues.append(
                Issue("parse", "timestamp_ambiguity", f"{filename}: could not resolve local timestamps: {exc}")
            )
            from app.normalisation.timestamps import TimestampError, to_utc

            for i, ts in good.items():
                try:
                    utc_index[i] = to_utc(ts.to_pydatetime(), self.mapping["source_timezone"])
                except TimestampError:
                    pass

        for col in cols[2:]:
            m = HEADER_RE.match(col.strip())
            if not m:
                result.issues.append(
                    Issue("parse", "unexpected_columns", f"{filename}: column '{col}' does not match 'Name [unit]'",
                          severity="warning")
                )
                continue
            name, unit = m.group("name").strip(), m.group("unit").strip()
            series_key = aliases.get(name, f"{category}::{name}")
            for row_pos, (idx, raw) in enumerate(df[col].items()):
                raw_text = raw.strip()
                ts_raw = df.at[idx, cols[0]]
                ts_utc = utc_index.get(idx)
                value: float | None = None
                parse_error = None
                if raw_text in missing_tokens:
                    value = None
                else:
                    try:
                        value = parse_number(raw_text, profile)
                    except ValueError as exc:
                        parse_error = str(exc)
                rid_ts = ts_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ") if ts_utc else f"raw:{ts_raw}"
                result.records.append(
                    SourceRecord(
                        series_key=series_key,
                        timestamp_utc=ts_utc,
                        timestamp_raw=ts_raw,
                        interval_minutes=interval,
                        raw_value=raw_text,
                        value=value,
                        unit=unit,
                        country_code=self.mapping["country_code"],
                        bidding_zone=cat_cfg.get("bidding_zone"),
                        source_record_id=f"smard:{series_key}:{interval}:{rid_ts}",
                        payload_index=payload_index,
                        location=f"{filename} row {row_pos + 2} col '{col}'",
                        parse_error=parse_error,
                    )
                )
        if bad_ts.any():
            result.issues.append(
                Issue("parse", "invalid_timestamp", f"{filename}: {int(bad_ts.sum())} rows have unparseable timestamps",
                      context={"examples": df.loc[bad_ts, cols[0]].head(3).tolist()})
            )
