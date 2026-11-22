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
  data_need: string | null; demand: { plants: number; capacity_mw: number; customers: string[]; suggested_customer_value: number } | null;
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

// ---------------------------------------------------------------- market-connections workflow
export type DataNeed = "production_metering" | "day_ahead_price" | "plant_master_data";
export const NEED_LABEL: Record<string, string> = {
  production_metering: "Plant metering", day_ahead_price: "Day-ahead price", plant_master_data: "Plant master data",
};
export interface RouteRef { id: number; holder: string; route_type: string; status: string; is_fallback: boolean; blockers: string | null }
export interface NeedCoverage { need: DataNeed; status: string; reason: string; route: RouteRef | null; latest: string | null;
  data_origin: string | null; authorisation?: string | null }
export interface PlantCoverage { asset_id: number; name: string; customer_id: number; customer: string; country_code: string;
  bidding_zone: string; technology: string; capacity_mw: number; metering_point_id: string | null; dso: string | null;
  is_fictional: boolean; needs: NeedCoverage[] }
export interface Rollup { pairs: number; covered: number; in_progress: number; gaps: number; pct: number | null; mw_pct: number | null }
export interface Coverage { computed_at: string; assets: PlantCoverage[]; totals: Rollup & { plants: number; capacity_mw: number };
  by_need: Record<string, Rollup>; by_country: Record<string, Rollup>; by_customer: Record<string, Rollup>; status_counts: Record<string, number> }
export interface Demand { plants: number; capacity_mw: number; customers: string[]; suggested_customer_value: number }

export interface FollowUp { request_id: number; provider_id: number; provider: string; country_code: string; subject: string;
  status: string; owner: string | null; last_contact: string | null; days_since_contact: number | null; next_follow_up: string | null;
  due_date: string | null; overdue: boolean; days_open: number }
export interface Issue { id: number; title: string; code: string; status: string; severity: "low" | "medium" | "high"; source: string;
  connector_id: number | null; connector: string | null; provider_id: number | null; provider: string | null; sync_log_id: number | null;
  detected_at: string; resolved_at: string | null; affected_asset_ids: number[]; period_start: string | null; period_end: string | null;
  evidence: Record<string, unknown>; hypotheses: string | null; root_cause: string | null; provider_contacted: boolean;
  customer_update: string | null; resolution: string | null; updated_at: string;
  affected_assets: { id: number; name: string; customer: string; capacity_mw: number }[]; affected_customers: string[]; affected_mw: number }
export interface Cockpit {
  generated_at: string; coverage: Coverage["totals"]; by_need: Record<string, Rollup>; by_country: Record<string, Rollup>;
  biggest_gaps: { country_code: string; need: string; plants: number; capacity_mw: number; customers: string[] }[];
  follow_ups: { overdue: FollowUp[]; upcoming: FollowUp[] };
  issues: { open: number; high: number; top: Issue[] };
  authorisations_pending: { asset: string; customer: string; country_code: string; status: string }[];
  connectors: { id: number; name: string; status: HealthStatus; data_origin: string; reason: string | null }[];
  lead_times: LeadTimes; demand_for: Record<string, Demand>;
}
export interface LeadTimes { median_days_to_grant: number | null; samples: number; by_country: Record<string, { median_days: number; samples: number }> }
export interface CountrySummary { country_code: string; name: string; status: string; owner: string | null; bidding_zones: string[];
  plants: number; capacity_mw: number; customers: string[]; coverage: Rollup | null; routes: Record<string, number>;
  open_requests: number; playbook: { done: number; total: number; pct: number; blocked: number } }
export interface AccessRoute { id: number; country_code: string; data_need: DataNeed; provider_id: number | null; provider: string | null;
  holder_name: string; route_type: string; status: string; is_fallback: boolean; effort: string | null;
  requires_owner_authorisation: boolean; blockers: string | null; notes: string | null; evidence_level: EvidenceLevel; source_url: string | null }
export interface PlaybookItem { key: string; title: string; description: string; number: number; status: string; notes?: string | null;
  started_at?: string | null; completed_at?: string | null }
export interface AccessRequest { id: number; provider_id: number; provider: string; country_code: string; data_need: DataNeed; subject: string;
  status: string; owner: string | null; opened_at: string; due_date: string | null; closed_at: string | null;
  fallback_route_id: number | null; notes: string | null; interactions?: number }
export interface CountryDetail {
  profile: { country_code: string; name: string; bidding_zones: string[]; tso: string | null; market_operator: string | null;
    dso_landscape: string | null; status: string; owner: string | null; summary: string | null; lessons_learned: string | null;
    languages: string[]; updated_at: string };
  routes: AccessRoute[]; playbook: PlaybookItem[]; playbook_progress: CountrySummary["playbook"];
  providers: { id: number; name: string; status: string }[]; requests: AccessRequest[]; plants: PlantCoverage[];
  coverage: Rollup | null; lead_times: { median_days: number; samples: number } | null;
}
export interface Contact { id: number; provider_id: number; provider: string; role: string; name: string | null; email: string | null;
  language: string | null; notes: string | null; is_placeholder: boolean }
export interface Interaction { id: number; provider_id: number; provider: string; access_request_id: number | null; contact_id: number | null;
  contact: string | null; occurred_at: string; channel: string; direction: "inbound" | "outbound"; summary: string; next_follow_up: string | null }
export interface ApiTest { id: number; provider_id: number | null; provider: string | null; name: string; method: string; url: string;
  params: Record<string, string>; request_headers: Record<string, string>; request_body: string | null; status_code: number | null;
  duration_ms: number | null; content_type: string | null; response_headers: Record<string, string>; response_excerpt: string | null;
  response_size: number | null; error: string | null; verdict: string; notes: string | null; created_at: string }
