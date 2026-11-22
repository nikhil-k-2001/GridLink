"""Persistence of normalised records. Idempotent: (provider_id, source_record_id) is the natural key.

Re-ingesting a window inserts nothing new; a value revised by the provider updates the stored value and
keeps the audit fields (original value/unit/transformation, raw payload) of the latest delivery.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models import EnergyRecord
from app.normalisation.engine import NormalisedRecord


@dataclass
class SaveResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def saved(self) -> int:
        return self.inserted + self.updated


def upsert_energy_records(
    db: Session,
    records: list[NormalisedRecord],
    *,
    connector_id: int,
    dataset_ids: dict[str, int],
    raw_payload_ids: dict[int, int] | None = None,
    chunk_size: int = 1000,
) -> SaveResult:
    result = SaveResult()
    raw_payload_ids = raw_payload_ids or {}
    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        keys = [(r.provider_id, r.source_record_id) for r in chunk]
        existing = {
            (row.provider_id, row.source_record_id): row
            for row in db.scalars(
                select(EnergyRecord).where(tuple_(EnergyRecord.provider_id, EnergyRecord.source_record_id).in_(keys))
            )
        }
        for r in chunk:
            row = existing.get((r.provider_id, r.source_record_id))
            if row is None:
                db.add(
                    EnergyRecord(
                        provider_id=r.provider_id,
                        dataset_id=dataset_ids.get(r.dataset_key),
                        connector_id=connector_id,
                        raw_payload_id=raw_payload_ids.get(r.payload_index),
                        timestamp_utc=r.timestamp_utc,
                        interval_minutes=r.interval_minutes,
                        country_code=r.country_code,
                        bidding_zone=r.bidding_zone,
                        energy_source=r.energy_source,
                        metric_type=r.metric_type,
                        value=r.value,
                        unit=r.unit,
                        original_value=r.original_value,
                        original_unit=r.original_unit,
                        transformation=r.transformation,
                        source_record_id=r.source_record_id,
                        data_origin=r.data_origin,
                        ingestion_timestamp=r.ingestion_timestamp,
                    )
                )
                result.inserted += 1
            elif row.value != r.value or row.original_value != r.original_value:
                row.value = r.value
                row.original_value = r.original_value
                row.original_unit = r.original_unit
                row.transformation = r.transformation
                row.raw_payload_id = raw_payload_ids.get(r.payload_index, row.raw_payload_id)
                row.ingestion_timestamp = r.ingestion_timestamp
                result.updated += 1
            else:
                result.unchanged += 1
        db.flush()
    return result
