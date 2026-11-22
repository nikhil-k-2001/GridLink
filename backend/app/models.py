"""SQLAlchemy ORM models.

Design notes
- Every normalised record keeps its provenance: provider, dataset, raw payload, the original value
  and unit, and the transformation applied. Raw payloads are retained so transformations can be audited.
- `(provider_id, source_record_id)` is unique: re-ingesting the same window is idempotent.
- `data_origin` distinguishes real provider data from clearly-labelled simulated fixtures.
- Enumerations are stored as constrained strings so new values only need a migration, not a type change.
"""
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC)


PROVIDER_STATUSES = (
    "discovered",
    "under_investigation",
    "access_requested",
    "access_granted",
    "integration_in_progress",
    "connected",
    "blocked",
)
EVIDENCE_LEVELS = ("verified", "researched", "assumption")
CONNECTOR_STATUSES = ("active", "paused", "awaiting_credentials", "disabled")
SYNC_STATUSES = ("running", "success", "partial", "failed")
DATA_ORIGINS = ("real", "simulated")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (CheckConstraint(_in("status", PROVIDER_STATUSES), name="ck_providers_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str] = mapped_column(String(8), index=True)  # ISO 3166-1 alpha-2, or "EU"
    website: Mapped[str | None] = mapped_column(String(500))
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="discovered", index=True)
    authentication_type: Mapped[str | None] = mapped_column(String(100))
    data_formats: Mapped[list | None] = mapped_column(JSONType, default=list)
    access_requirements: Mapped[str | None] = mapped_column(Text)
    registration_status: Mapped[str | None] = mapped_column(String(100))
    last_investigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(120))
    attribution: Mapped[str | None] = mapped_column(String(300))
    licence: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    datasets: Mapped[list["Dataset"]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    connectors: Mapped[list["Connector"]] = relationship(back_populates="provider", cascade="all, delete-orphan")
    facts: Mapped[list["ProviderFact"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class ProviderFact(Base):
    """A single claim about a provider and how strongly we know it (verified / researched / assumption)."""

    __tablename__ = "provider_facts"
    __table_args__ = (CheckConstraint(_in("evidence_level", EVIDENCE_LEVELS), name="ck_facts_evidence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64))  # access, format, licensing, limits, quality...
    statement: Mapped[str] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(String(16))
    source_url: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    provider: Mapped[Provider] = relationship(back_populates="facts")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("provider_id", "dataset_key", name="uq_datasets_provider_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    dataset_key: Mapped[str] = mapped_column(String(100))
    dataset_name: Mapped[str] = mapped_column(String(200))
    metric_type: Mapped[str] = mapped_column(String(64))  # generation | consumption | day_ahead_price ...
    energy_source: Mapped[str | None] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(32))  # CSV | XML | JSON
    unit: Mapped[str] = mapped_column(String(32))  # unit as published by the provider
    frequency: Mapped[str] = mapped_column(String(16))  # PT15M | PT60M | P1D
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    provider: Mapped[Provider] = relationship(back_populates="datasets")


class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (CheckConstraint(_in("status", CONNECTOR_STATUSES), name="ck_connectors_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    connector_name: Mapped[str] = mapped_column(String(200), unique=True)
    connector_type: Mapped[str] = mapped_column(String(64))  # registry key, e.g. "smard_csv"
    status: Mapped[str] = mapped_column(String(32), default="active")
    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    config: Mapped[dict] = mapped_column(JSONType, default=dict)
    expected_update_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_data_lag_minutes: Mapped[int] = mapped_column(Integer, default=360)
    sync_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    provider: Mapped[Provider] = relationship(back_populates="connectors")
    sync_logs: Mapped[list["SyncLog"]] = relationship(back_populates="connector", cascade="all, delete-orphan")


class SyncLog(Base):
    __tablename__ = "sync_logs"
    __table_args__ = (
        CheckConstraint(_in("status", SYNC_STATUSES), name="ck_sync_logs_status"),
        Index("ix_sync_logs_connector_started", "connector_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | scheduled | test
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_saved: Mapped[int] = mapped_column(Integer, default=0)  # inserted + updated
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    requests_failed: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)

    connector: Mapped[Connector] = relationship(back_populates="sync_logs")
    errors: Mapped[list["SyncError"]] = relationship(back_populates="sync_log", cascade="all, delete-orphan")


class SyncError(Base):
    """Individual problems found during a sync: HTTP failures, parse errors, rejected records."""

    __tablename__ = "sync_errors"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    sync_log_id: Mapped[int] = mapped_column(ForeignKey("sync_logs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(32))  # authenticate | fetch | parse | normalise | validate | save
    severity: Mapped[str] = mapped_column(String(16), default="error")  # error | warning
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sync_log: Mapped[SyncLog] = relationship(back_populates="errors")


class RawPayload(Base):
    """Exact bytes received from a provider. Never discarded without an ingestion outcome."""

    __tablename__ = "raw_payloads"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    sync_log_id: Mapped[int] = mapped_column(ForeignKey("sync_logs.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    request_url: Mapped[str] = mapped_column(Text)  # credentials are redacted before storage
    request_params: Mapped[dict] = mapped_column(JSONType, default=dict)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    outcome: Mapped[str] = mapped_column(String(32), default="received")  # received | parsed | parse_failed


class EnergyRecord(Base):
    __tablename__ = "energy_records"
    __table_args__ = (
        UniqueConstraint("provider_id", "source_record_id", name="uq_energy_records_provider_source"),
        CheckConstraint(_in("data_origin", DATA_ORIGINS), name="ck_energy_records_origin"),
        Index("ix_energy_records_query", "country_code", "metric_type", "timestamp_utc"),
        Index("ix_energy_records_provider_ts", "provider_id", "timestamp_utc"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), index=True)
    connector_id: Mapped[int | None] = mapped_column(ForeignKey("connectors.id", ondelete="SET NULL"))
    raw_payload_id: Mapped[int | None] = mapped_column(ForeignKey("raw_payloads.id", ondelete="SET NULL"))
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # interval start, UTC
    interval_minutes: Mapped[int] = mapped_column(Integer)
    country_code: Mapped[str] = mapped_column(String(8))
    bidding_zone: Mapped[str | None] = mapped_column(String(32))
    energy_source: Mapped[str] = mapped_column(String(64))
    metric_type: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float)  # null = provider published "no value"
    unit: Mapped[str] = mapped_column(String(32))  # canonical unit
    original_value: Mapped[str | None] = mapped_column(String(64))  # exactly as published
    original_unit: Mapped[str | None] = mapped_column(String(32))
    transformation: Mapped[str | None] = mapped_column(String(200))
    source_record_id: Mapped[str] = mapped_column(String(300))
    data_origin: Mapped[str] = mapped_column(String(16), default="real")
    ingestion_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityReport(Base):
    __tablename__ = "quality_reports"
    __table_args__ = (Index("ix_quality_reports_connector_created", "connector_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id", ondelete="CASCADE"))
    sync_log_id: Mapped[int | None] = mapped_column(ForeignKey("sync_logs.id", ondelete="CASCADE"), index=True)
    completeness_score: Mapped[float | None] = mapped_column(Float)  # 0..100
    freshness_status: Mapped[str] = mapped_column(String(16))  # fresh | delayed | stale | unknown
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_record_count: Mapped[int] = mapped_column(Integer, default=0)
    null_value_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_interval_count: Mapped[int] = mapped_column(Integer, default=0)
    overall_status: Mapped[str] = mapped_column(String(16))  # pass | warn | fail
    validation_details: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationOpportunity(Base):
    __tablename__ = "integration_opportunities"
    __table_args__ = tuple(
        CheckConstraint(f"{c} BETWEEN 1 AND 5", name=f"ck_opp_{c}")
        for c in (
            "customer_value",
            "data_importance",
            "commercial_opportunity",
            "strategic_relevance",
            "technical_effort",
            "access_complexity",
        )
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    customer_value: Mapped[int] = mapped_column(Integer)
    data_importance: Mapped[int] = mapped_column(Integer)
    commercial_opportunity: Mapped[int] = mapped_column(Integer)
    strategic_relevance: Mapped[int] = mapped_column(Integer)
    technical_effort: Mapped[int] = mapped_column(Integer)
    access_complexity: Mapped[int] = mapped_column(Integer)
    estimated_weeks: Mapped[float | None] = mapped_column(Float)
    priority_score: Mapped[float] = mapped_column(Float, default=0)
    rationale: Mapped[str | None] = mapped_column(Text)
    decision_status: Mapped[str] = mapped_column(String(32), default="proposed")
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    provider: Mapped[Provider] = relationship()


INVESTIGATION_SECTIONS = (
    ("overview", "Provider overview"),
    ("country_market", "Country and market"),
    ("available_datasets", "Available datasets"),
    ("api_documentation", "API documentation"),
    ("authentication_method", "Authentication requirements"),
    ("registration_process", "Registration process"),
    ("access_requirements", "Access requirements"),
    ("sample_requests", "Sample API requests"),
    ("sample_response", "Sample response"),
    ("data_format", "Data format"),
    ("limitations", "Known limitations"),
    ("data_quality_issues", "Data quality issues"),
    ("licensing", "Commercial or licensing considerations"),
    ("integration_complexity", "Integration complexity"),
    ("next_steps", "Next steps"),
)


class ProviderInvestigation(Base):
    __tablename__ = "provider_investigations"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), unique=True)
    author: Mapped[str | None] = mapped_column(String(120))
    findings: Mapped[str | None] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    country_market: Mapped[str | None] = mapped_column(Text)
    available_datasets: Mapped[str | None] = mapped_column(Text)
    api_documentation: Mapped[str | None] = mapped_column(Text)
    authentication_method: Mapped[str | None] = mapped_column(Text)
    registration_process: Mapped[str | None] = mapped_column(Text)
    access_requirements: Mapped[str | None] = mapped_column(Text)
    sample_requests: Mapped[str | None] = mapped_column(Text)
    sample_response: Mapped[str | None] = mapped_column(Text)
    data_format: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    data_quality_issues: Mapped[str | None] = mapped_column(Text)
    licensing: Mapped[str | None] = mapped_column(Text)
    integration_complexity: Mapped[str | None] = mapped_column(Text)
    next_steps: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    provider: Mapped[Provider] = relationship()


class AppSetting(Base):
    """Small key/value store for non-secret, user-editable configuration (e.g. prioritisation weights)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
