"""Pydantic API schemas (request validation + response shapes)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models import EVIDENCE_LEVELS, PROVIDER_STATUSES

T = TypeVar("T")

ProviderStatus = Literal[PROVIDER_STATUSES]  # type: ignore[valid-type]
EvidenceLevel = Literal[EVIDENCE_LEVELS]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# --- providers -------------------------------------------------------------------------------------
class ProviderFactIn(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1)
    evidence_level: EvidenceLevel
    source_url: HttpUrl | None = None


class ProviderFactOut(ORM):
    id: int
    category: str
    statement: str
    evidence_level: str
    source_url: str | None
    checked_at: datetime | None


class ProviderBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country_code: str = Field(pattern=r"^([A-Z]{2}|EU)$", description="ISO 3166-1 alpha-2 or EU")
    website: HttpUrl | None = None
    documentation_url: HttpUrl | None = None
    description: str | None = None
    status: ProviderStatus = "discovered"
    authentication_type: str | None = None
    data_formats: list[str] = []
    access_requirements: str | None = None
    registration_status: str | None = None
    last_investigated_at: datetime | None = None
    notes: str | None = None
    next_action: str | None = None
    owner: str | None = None
    licence: str | None = None
    attribution: str | None = None


class ProviderCreate(ProviderBase):
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9-]{2,64}$")


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    country_code: str | None = Field(default=None, pattern=r"^([A-Z]{2}|EU)$")
    website: HttpUrl | None = None
    documentation_url: HttpUrl | None = None
    description: str | None = None
    status: ProviderStatus | None = None
    authentication_type: str | None = None
    data_formats: list[str] | None = None
    access_requirements: str | None = None
    registration_status: str | None = None
    last_investigated_at: datetime | None = None
    notes: str | None = None
    next_action: str | None = None
    owner: str | None = None
    licence: str | None = None
    attribution: str | None = None


class DatasetOut(ORM):
    id: int
    provider_id: int
    dataset_key: str
    dataset_name: str
    metric_type: str
    energy_source: str | None
    format: str
    unit: str
    frequency: str
    description: str | None
    is_active: bool


class ProviderOut(ORM):
    id: int
    slug: str
    name: str
    country_code: str
    website: str | None
    documentation_url: str | None
    description: str | None
    status: str
    authentication_type: str | None
    data_formats: list[str] | None
    access_requirements: str | None
    registration_status: str | None
    last_investigated_at: datetime | None
    notes: str | None
    next_action: str | None
    owner: str | None
    licence: str | None
    attribution: str | None
    created_at: datetime
    updated_at: datetime
    dataset_count: int = 0
    connector_count: int = 0


class ProviderDetail(ProviderOut):
    facts: list[ProviderFactOut] = []
    datasets: list[DatasetOut] = []


# --- connectors ------------------------------------------------------------------------------------
class ConnectorCreate(BaseModel):
    provider_id: int
    connector_name: str = Field(min_length=3, max_length=200)
    connector_type: str
    config: dict[str, Any] = {}
    expected_update_minutes: int = Field(default=60, ge=1, le=10080)
    max_data_lag_minutes: int = Field(default=360, ge=1, le=20160)
    sync_interval_minutes: int | None = Field(default=None, ge=15, le=10080)


class ConnectorUpdate(BaseModel):
    status: Literal["active", "paused", "disabled"] | None = None
    config: dict[str, Any] | None = None
    max_data_lag_minutes: int | None = Field(default=None, ge=1, le=20160)
    sync_interval_minutes: int | None = Field(default=None, ge=15, le=10080)


class ConnectorOut(ORM):
    id: int
    provider_id: int
    provider_name: str | None = None
    country_code: str | None = None
    connector_name: str
    connector_type: str
    status: str
    data_origin: str
    config: dict[str, Any]
    expected_update_minutes: int
    max_data_lag_minutes: int
    sync_interval_minutes: int | None
    last_successful_sync: datetime | None
    last_failed_sync: datetime | None
    created_at: datetime
    health: dict[str, Any] | None = None


class SyncRequest(BaseModel):
    window_start: datetime | None = None
    window_end: datetime | None = None

    @field_validator("window_start", "window_end")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("timestamps must include a timezone offset (e.g. 2026-11-20T00:00:00Z)")
        return v


class SyncErrorOut(ORM):
    id: int
    sync_log_id: int
    stage: str
    severity: str
    code: str
    message: str
    context: dict[str, Any]
    created_at: datetime


class SyncLogOut(ORM):
    id: int
    connector_id: int
    trigger: str
    started_at: datetime
    completed_at: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    records_fetched: int
    records_saved: int
    records_inserted: int
    records_updated: int
    records_unchanged: int
    records_failed: int
    requests_made: int
    requests_failed: int
    retry_count: int
    status: str
    error_code: str | None
    error_message: str | None
    details: dict[str, Any]


class RawPayloadOut(ORM):
    id: int
    sync_log_id: int
    request_url: str
    request_params: dict[str, Any]
    http_status: int | None
    content_type: str | None
    sha256: str
    size_bytes: int
    received_at: datetime
    outcome: str


class QualityReportOut(ORM):
    id: int
    connector_id: int
    connector_name: str | None = None
    sync_log_id: int | None
    completeness_score: float | None
    freshness_status: str
    duplicate_count: int
    invalid_record_count: int
    null_value_count: int
    missing_interval_count: int
    overall_status: str
    validation_details: dict[str, Any]
    created_at: datetime


# --- energy records --------------------------------------------------------------------------------
class EnergyRecordOut(ORM):
    id: int
    provider_id: int
    dataset_id: int | None
    connector_id: int | None
    raw_payload_id: int | None
    timestamp_utc: datetime
    interval_minutes: int
    country_code: str
    bidding_zone: str | None
    energy_source: str
    metric_type: str
    value: float | None
    unit: str
    original_value: str | None
    original_unit: str | None
    transformation: str | None
    source_record_id: str
    data_origin: str
    ingestion_timestamp: datetime


# --- prioritisation --------------------------------------------------------------------------------
Score = Field(ge=1, le=5)


class OpportunityBase(BaseModel):
    provider_id: int
    title: str = Field(min_length=3, max_length=200)
    customer_value: int = Score
    data_importance: int = Score
    commercial_opportunity: int = Score
    strategic_relevance: int = Score
    technical_effort: int = Score
    access_complexity: int = Score
    estimated_weeks: float | None = Field(default=None, ge=0, le=520)
    rationale: str | None = None
    decision_status: Literal["proposed", "approved", "in_progress", "deferred", "rejected", "done"] = "proposed"
    decision_notes: str | None = None


class OpportunityCreate(OpportunityBase):
    pass


class OpportunityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    customer_value: int | None = Field(default=None, ge=1, le=5)
    data_importance: int | None = Field(default=None, ge=1, le=5)
    commercial_opportunity: int | None = Field(default=None, ge=1, le=5)
    strategic_relevance: int | None = Field(default=None, ge=1, le=5)
    technical_effort: int | None = Field(default=None, ge=1, le=5)
    access_complexity: int | None = Field(default=None, ge=1, le=5)
    estimated_weeks: float | None = Field(default=None, ge=0, le=520)
    rationale: str | None = None
    decision_status: Literal["proposed", "approved", "in_progress", "deferred", "rejected", "done"] | None = None
    decision_notes: str | None = None


class OpportunityOut(ORM):
    id: int
    provider_id: int
    provider_name: str | None = None
    country_code: str | None = None
    title: str
    customer_value: int
    data_importance: int
    commercial_opportunity: int
    strategic_relevance: int
    technical_effort: int
    access_complexity: int
    estimated_weeks: float | None
    priority_score: float
    rank: int | None = None
    rationale: str | None
    decision_status: str
    decision_notes: str | None
    created_at: datetime
    updated_at: datetime


class PrioritisationWeights(BaseModel):
    customer_value: float = Field(default=1.0, ge=0, le=3)
    data_importance: float = Field(default=1.0, ge=0, le=3)
    strategic_relevance: float = Field(default=1.0, ge=0, le=3)
    commercial_opportunity: float = Field(default=0.0, ge=0, le=3)
    technical_effort: float = Field(default=1.0, ge=0, le=3)
    access_complexity: float = Field(default=1.0, ge=0, le=3)


# --- investigations --------------------------------------------------------------------------------
class InvestigationBase(BaseModel):
    author: str | None = None
    findings: str | None = None
    overview: str | None = None
    country_market: str | None = None
    available_datasets: str | None = None
    api_documentation: str | None = None
    authentication_method: str | None = None
    registration_process: str | None = None
    access_requirements: str | None = None
    sample_requests: str | None = None
    sample_response: str | None = None
    data_format: str | None = None
    limitations: str | None = None
    data_quality_issues: str | None = None
    licensing: str | None = None
    integration_complexity: str | None = None
    next_steps: str | None = None


class InvestigationCreate(InvestigationBase):
    provider_id: int


class InvestigationUpdate(InvestigationBase):
    pass


class InvestigationOut(InvestigationBase, ORM):
    id: int
    provider_id: int
    provider_name: str | None = None
    created_at: datetime
    updated_at: datetime
    completion: float = 0


class AIRequest(BaseModel):
    task: Literal["summarise_errors", "explain_dataset", "summarise_documentation"]
    connector_id: int | None = None
    dataset_id: int | None = None
    text: str | None = Field(default=None, max_length=20000)
