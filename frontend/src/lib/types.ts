export interface Page<T> { items: T[]; total: number; limit: number; offset: number }

export const PROVIDER_STATUSES = ["discovered", "under_investigation", "access_requested", "access_granted",
  "integration_in_progress", "connected", "blocked"] as const;
export type ProviderStatus = (typeof PROVIDER_STATUSES)[number];
export type HealthStatus = "healthy" | "warning" | "degraded" | "failed";
export type EvidenceLevel = "verified" | "researched" | "assumption";

export interface ProviderFact { id: number; category: string; statement: string; evidence_level: EvidenceLevel;
  source_url: string | null; checked_at: string | null }
export interface Dataset { id: number; provider_id: number; dataset_key: string; dataset_name: string; metric_type: string;
  energy_source: string | null; format: string; unit: string; frequency: string; description: string | null; is_active: boolean }
export interface Provider {
  id: number; slug: string; name: string; country_code: string; website: string | null; documentation_url: string | null;
  description: string | null; status: ProviderStatus; authentication_type: string | null; data_formats: string[] | null;
  access_requirements: string | null; registration_status: string | null; last_investigated_at: string | null;
  notes: string | null; next_action: string | null; owner: string | null; licence: string | null; attribution: string | null;
  created_at: string; updated_at: string; dataset_count: number; connector_count: number;
}
export interface ProviderDetail extends Provider { facts: ProviderFact[]; datasets: Dataset[] }

export interface HealthReason { level: HealthStatus | "info"; reason: string }
export interface ConnectorHealth {
  connector_id: number; status: HealthStatus; reasons: HealthReason[]; data_origin: "real" | "simulated";
  last_successful_sync: string | null; last_failed_sync: string | null; last_sync_status: string | null;
  sync_success_rate: number | null; request_success_rate: number | null; http_error_rate: number | null;
  retry_count: number; syncs_considered: number; completeness: number | null;
  freshness: { status: string; max_lag_minutes: number; metrics: Record<string, { latest: string; lag_minutes: number; status: string }> };
  failed_records_last_sync: number; records_fetched_last_sync: number;
  recent_errors: { id: number; sync_log_id: number; stage: string; code: string; message: string; created_at: string }[];
  computed_at: string;
}
export interface Connector {
  id: number; provider_id: number; provider_name: string | null; country_code: string | null; connector_name: string;
  connector_type: string; status: string; data_origin: "real" | "simulated"; config: Record<string, unknown>;
  expected_update_minutes: number; max_data_lag_minutes: number; sync_interval_minutes: number | null;
  last_successful_sync: string | null; last_failed_sync: string | null; created_at: string; health: ConnectorHealth | null;
}
export interface SyncLog {
  id: number; connector_id: number; trigger: string; started_at: string; completed_at: string | null;
  window_start: string | null; window_end: string | null; records_fetched: number; records_saved: number;
  records_inserted: number; records_updated: number; records_unchanged: number; records_failed: number;
  requests_made: number; requests_failed: number; retry_count: number; status: "running" | "success" | "partial" | "failed";
  error_code: string | null; error_message: string | null; details: Record<string, unknown>;
}
export interface SyncError { id: number; sync_log_id: number; stage: string; severity: "error" | "warning"; code: string;
  message: string; context: Record<string, unknown>; created_at: string }
export interface RawPayload { id: number; sync_log_id: number; request_url: string; request_params: Record<string, unknown>;
  http_status: number | null; content_type: string | null; sha256: string; size_bytes: number; received_at: string; outcome: string }

export interface SeriesQuality { series_key: string; dataset_key: string; interval_minutes: number; expected: number; present: number;
  nulls: number; completeness: number; latest: string | null; freshness: string; lag_minutes: number | null;
  missing_periods: { start: string; end: string; intervals: number }[] }
export interface QualityReport {
  id: number; connector_id: number; connector_name: string | null; sync_log_id: number | null; completeness_score: number | null;
  freshness_status: string; duplicate_count: number; invalid_record_count: number; null_value_count: number;
  missing_interval_count: number; overall_status: "pass" | "warn" | "fail"; created_at: string;
  validation_details: {
    completeness: { score: number | null; missing_intervals: number; null_values: number; missing_series: string[] };
    consistency: { duplicates: number; conflicting_duplicates: number; unexpected_units: number; invalid_country_codes: number;
      inconsistent_categories: number; unmapped_series: Record<string, number> };
    validity: { invalid_records: number; rejected_in_normalisation: number; by_rule: Record<string, number> };
    freshness: { status: string };
    series: SeriesQuality[]; window: { start: string; end: string }; data_origin: "real" | "simulated";
  };
}

export interface SummarySeries {
  key: string; provider_id: number; provider_name: string; energy_source: string; data_origin: "real" | "simulated";
  unit: string; source_interval_minutes: number[]; bidding_zone: string | null;
  dataset: { id: number; name: string; published_unit: string; frequency: string; description: string | null } | null;
  coverage: { first: string; last: string; records: number; null_values: number };
  points: { t: string; v: number | null }[];
}
export interface Summary {
  metric_type: string; bucket: string; start: string; end: string; series: SummarySeries[];
  provenance: { provider_id: number; provider_name: string; licence: string | null; attribution: string | null; website: string | null;
    data_origins: string[]; datasets: { id: number; name: string; published_unit: string; frequency: string }[];
    connectors: { id: number; name: string; last_successful_sync: string | null }[] }[];
  warnings: { type: string; message: string }[];
}

export interface Opportunity {
  id: number; provider_id: number; provider_name: string | null; country_code: string | null; title: string;
  customer_value: number; data_importance: number; commercial_opportunity: number; strategic_relevance: number;
  technical_effort: number; access_complexity: number; estimated_weeks: number | null; priority_score: number; rank: number | null;
  rationale: string | null; decision_status: string; decision_notes: string | null; created_at: string; updated_at: string;
}
export interface Weights { customer_value: number; data_importance: number; strategic_relevance: number;
  commercial_opportunity: number; technical_effort: number; access_complexity: number }

export interface Investigation {
  id: number; provider_id: number; provider_name: string | null; author: string | null; findings: string | null;
  completion: number; created_at: string; updated_at: string; [section: string]: string | number | null;
}
export interface TemplateSection { key: string; title: string; number: number }

export interface Overview {
  connectors: { id: number; name: string; provider: string; country_code: string; data_origin: string; status: HealthStatus;
    completeness: number | null; freshness: string; last_successful_sync: string | null; reasons: HealthReason[] }[];
  connector_status_counts: Record<HealthStatus, number>;
  records: { total: number; by_origin: Record<string, number> };
  datasets: number; providers: { total: number; by_status: Record<string, number> };
  syncs_last_7d: Record<string, number>; errors_last_7d: number; quality_reports_by_status: Record<string, number>;
  recent_syncs: { id: number; connector_id: number; status: string; started_at: string; records_saved: number;
    records_failed: number; error_code: string | null }[];
  generated_at: string;
}
