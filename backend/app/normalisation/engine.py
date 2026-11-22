"""Provider-agnostic normalisation: provider vocabulary -> GridLink standard schema.

Each provider has a mapping file (app/connectors/mappings/<provider>.json) that maps a provider series
key (e.g. "generation::Wind onshore" or "A75::B16::in") to a dataset, metric type, energy source and the
unit the provider is expected to publish. Similar-looking provider fields are never merged implicitly:
only explicitly mapped series are ingested, and an unexpected unit rejects the record instead of being
converted on a guess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.connectors.base import Issue, SourceRecord
from app.normalisation.units import UnitConversionError, convert, normalise_unit_label

METRIC_TYPES = {"generation", "consumption", "residual_load", "day_ahead_price", "asset_production"}
ENERGY_SOURCES = {
    "biomass", "hydro", "wind_offshore", "wind_onshore", "solar", "other_renewable", "nuclear", "lignite",
    "hard_coal", "fossil_gas", "pumped_storage", "other_conventional", "oil", "geothermal", "waste",
    "hydro_run_of_river", "hydro_reservoir", "marine", "total", "all",
}  # fmt: skip


class NormalisedRecord(BaseModel):
    """The GridLink standard energy record. Pydantic enforces the schema contract."""

    model_config = ConfigDict(frozen=True)

    provider_id: int
    dataset_key: str
    series_key: str
    timestamp_utc: datetime
    interval_minutes: int = Field(gt=0, le=1440)
    country_code: str = Field(pattern=r"^[A-Z]{2}$|^EU$")
    bidding_zone: str | None = None
    energy_source: str
    metric_type: str
    value: float | None
    unit: str
    original_value: str | None
    original_unit: str
    transformation: str
    source_record_id: str = Field(min_length=1, max_length=300)
    data_origin: str = Field(pattern=r"^(real|simulated)$")
    payload_index: int = 0
    location: str | None = None
    asset_id: int | None = None
    flags: tuple[str, ...] = ()
    ingestion_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("timestamp_utc")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        return v.astimezone(UTC)

    @field_validator("metric_type")
    @classmethod
    def _metric(cls, v: str) -> str:
        if v not in METRIC_TYPES:
            raise ValueError(f"unknown metric_type '{v}'")
        return v

    @field_validator("energy_source")
    @classmethod
    def _source(cls, v: str) -> str:
        if v not in ENERGY_SOURCES:
            raise ValueError(f"unknown energy_source '{v}'")
        return v


@dataclass
class NormaliseResult:
    records: list[NormalisedRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    rejected: int = 0
    unmapped_series: dict[str, int] = field(default_factory=dict)


def _reject(result: NormaliseResult, code: str, message: str, rec: SourceRecord, **ctx: Any) -> None:
    result.rejected += 1
    result.issues.append(
        Issue(
            stage="normalise",
            code=code,
            message=message,
            context={
                "series": rec.series_key,
                "timestamp_raw": rec.timestamp_raw,
                "raw_value": rec.raw_value,
                "location": rec.location,
                "source_record_id": rec.source_record_id,
                **ctx,
            },
        )
    )


def normalise_records(
    records: list[SourceRecord], mapping: dict[str, Any], *, provider_id: int, data_origin: str
) -> NormaliseResult:
    result = NormaliseResult()
    series_map: dict[str, dict[str, Any]] = mapping["series"]

    for rec in records:
        spec = series_map.get(rec.series_key)
        if spec is None:
            result.unmapped_series[rec.series_key] = result.unmapped_series.get(rec.series_key, 0) + 1
            continue
        if rec.parse_error:
            _reject(result, "malformed_value", rec.parse_error, rec)
            continue
        if rec.timestamp_utc is None:
            _reject(result, "invalid_timestamp", "Record has no resolvable timestamp", rec)
            continue

        expected_unit = normalise_unit_label(spec["unit"])
        if normalise_unit_label(rec.unit) != expected_unit:
            _reject(
                result,
                "unexpected_unit",
                f"Published unit '{rec.unit}' differs from mapped unit '{spec['unit']}' - not converted",
                rec,
                expected_unit=spec["unit"],
            )
            continue

        value: float | None = None
        transformation = "none"
        unit = spec.get("canonical_unit")
        try:
            if rec.value is not None:
                conv = convert(rec.value, rec.unit, spec["metric_type"], rec.interval_minutes)
                value, unit, transformation = conv.value, conv.unit, conv.transformation
            else:
                from app.normalisation.units import canonical_unit

                unit = canonical_unit(spec["metric_type"])
                transformation = "null (provider published no value)"
        except UnitConversionError as exc:
            _reject(result, exc.code, str(exc), rec)
            continue

        try:
            result.records.append(
                NormalisedRecord(
                    provider_id=provider_id,
                    dataset_key=spec["dataset_key"],
                    series_key=rec.series_key,
                    timestamp_utc=rec.timestamp_utc,
                    interval_minutes=rec.interval_minutes,
                    country_code=rec.country_code,
                    bidding_zone=rec.bidding_zone,
                    energy_source=spec["energy_source"],
                    metric_type=spec["metric_type"],
                    value=value,
                    unit=unit,
                    original_value=rec.raw_value,
                    original_unit=rec.unit,
                    transformation=transformation,
                    source_record_id=rec.source_record_id,
                    data_origin=data_origin,
                    payload_index=rec.payload_index,
                    location=rec.location,
                    asset_id=spec.get("asset_id"),
                    flags=rec.flags,
                )
            )
        except ValidationError as exc:
            errs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            _reject(result, "schema_violation", errs, rec)

    for key, count in result.unmapped_series.items():
        result.issues.append(
            Issue(
                stage="normalise",
                code="unmapped_series",
                severity="warning",
                message=f"Series '{key}' is not in the provider mapping; {count} values were not ingested",
                context={"series": key, "count": count},
            )
        )
    return result
