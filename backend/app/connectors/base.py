"""Connector contract.

A connector only knows how to talk to ONE provider: authenticate, fetch raw payloads and parse them into
`SourceRecord`s that still use the provider's own vocabulary. Everything after that (mapping to the
standard schema, unit conversion, validation, persistence, health) is provider-agnostic and lives in the
common layers. Adding a provider = one connector class + one mapping file.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from app.config import Settings
from app.connectors.http import RetryingClient

MAPPINGS_DIR = Path(__file__).parent / "mappings"


@dataclass
class AuthResult:
    ok: bool
    method: str  # "none" | "security_token" | "fixture"
    message: str
    code: str | None = None  # e.g. "missing_token", "invalid_token"


@dataclass
class FetchedPayload:
    request_url: str  # redacted
    request_params: dict[str, Any]
    http_status: int | None
    content_type: str | None
    body: bytes
    meta: dict[str, Any] = field(default_factory=dict)  # e.g. {"category": "generation"}


@dataclass
class Issue:
    stage: str
    code: str
    message: str
    severity: str = "error"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceRecord:
    """One observation in the provider's own terms, before normalisation."""

    series_key: str  # key into the provider mapping, e.g. "generation::Wind onshore"
    timestamp_utc: datetime | None  # resolved interval start (connector resolves source tz/DST)
    timestamp_raw: str  # exactly as published
    interval_minutes: int
    raw_value: str | None  # exactly as published ("-" , "1,234.5", ...)
    value: float | None  # parsed numeric value; None when the provider published no value
    unit: str  # unit as published
    country_code: str
    bidding_zone: str | None
    source_record_id: str
    payload_index: int = 0
    location: str | None = None  # row / XML path for audit
    parse_error: str | None = None


@dataclass
class ParseResult:
    records: list[SourceRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


class ConnectorError(Exception):
    """A provider-specific failure that aborts (part of) a sync with a human-readable reason."""

    def __init__(self, stage: str, code: str, message: str, retryable: bool = False, http_status: int | None = None):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status


def load_mapping(name: str) -> dict[str, Any]:
    return json.loads((MAPPINGS_DIR / f"{name}.json").read_text(encoding="utf-8"))


class BaseConnector(ABC):
    connector_type: ClassVar[str]
    provider_slug: ClassVar[str]
    mapping_name: ClassVar[str]
    data_origin: ClassVar[str] = "real"

    def __init__(self, config: dict[str, Any], settings: Settings, http: RetryingClient | None = None):
        self.config = config or {}
        self.settings = settings
        self.http = http
        self.mapping = load_mapping(self.mapping_name)

    # --- provider-specific -------------------------------------------------------------------------
    @abstractmethod
    def authenticate(self) -> AuthResult: ...

    @abstractmethod
    def fetch_data(self, window_start: datetime, window_end: datetime) -> list[FetchedPayload]: ...

    @abstractmethod
    def parse_response(self, payload: FetchedPayload, payload_index: int) -> ParseResult: ...

    # --- provider-agnostic defaults ----------------------------------------------------------------
    def normalise_data(self, records: list[SourceRecord], provider_id: int):
        from app.normalisation.engine import normalise_records

        return normalise_records(records, self.mapping, provider_id=provider_id, data_origin=self.data_origin)

    def validate_data(self, normalised, window_start: datetime, window_end: datetime, expected_lag_minutes: int,
                      now: datetime | None = None):
        from app.quality.engine import validate_batch

        return validate_batch(
            normalised,
            self.mapping,
            window_start,
            window_end,
            expected_lag_minutes,
            expected_series=self.expected_series(),
            publishes_ahead_series=self.publishes_ahead_series(),
            lag_by_series=self.lag_by_series(),
            now=now,
        )

    def save_records(self, db, records, connector_id: int, dataset_ids: dict[str, int]):
        from app.services.repository import upsert_energy_records

        return upsert_energy_records(db, records, connector_id=connector_id, dataset_ids=dataset_ids)

    def get_health(self, db, connector_id: int):
        from app.services.health import compute_connector_health

        return compute_connector_health(db, connector_id)

    # --- quality expectations (override per provider) ---------------------------------------------
    def expected_series(self) -> list[str]:
        """Series that MUST be present; a missing one is a completeness failure. Default: none."""
        return []

    def series_category(self, series_key: str) -> str | None:
        return None

    def _category_cfg(self) -> dict[str, dict[str, Any]]:
        return {}

    def publishes_ahead_series(self) -> set[str]:
        cfg = self._category_cfg()
        return {k for k in self.mapping["series"] if cfg.get(self.series_category(k) or "", {}).get("publishes_ahead")}

    def lag_by_series(self) -> dict[str, int]:
        cfg = self._category_cfg()
        out = {}
        for k in self.mapping["series"]:
            lag = cfg.get(self.series_category(k) or "", {}).get("max_data_lag_minutes")
            if lag:
                out[k] = int(lag)
        return out

    # --- helpers -----------------------------------------------------------------------------------
    def active_series(self) -> dict[str, dict[str, Any]]:
        return {k: v for k, v in self.mapping["series"].items() if v.get("active", True)}


CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}


def register(cls: type[BaseConnector]) -> type[BaseConnector]:
    CONNECTOR_REGISTRY[cls.connector_type] = cls
    return cls


def get_connector_class(connector_type: str) -> type[BaseConnector]:
    # Import side effect registers built-in connectors.
    from app.connectors import entsoe, smard  # noqa: F401

    try:
        return CONNECTOR_REGISTRY[connector_type]
    except KeyError as exc:
        raise ValueError(f"Unknown connector type '{connector_type}'. Known: {sorted(CONNECTOR_REGISTRY)}") from exc
