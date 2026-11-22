# GridLink API reference

Interactive OpenAPI docs: `http://localhost:8000/docs` · machine-readable spec: [`openapi.json`](openapi.json).

Conventions: list endpoints accept `limit` (1–500, default 50) and `offset` and return `{items, total, limit, offset}`; validation errors return HTTP 422 with field details; missing resources 404; conflicts (duplicate slug, sync already running, paused connector) 409; disabled optional features (AI without key) 503. All timestamps are ISO 8601 with offset.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health |
| GET | `/settings/status` | Settings Status |
| GET | `/overview` | Overview |
| POST | `/ai/assist` | Ai Assist |
| GET | `/providers` | List Providers — query: `country, status, q, limit, offset` |
| POST | `/providers` | Create Provider |
| GET | `/providers/{provider_id}` | Get Provider |
| PATCH | `/providers/{provider_id}` | Update Provider |
| POST | `/providers/{provider_id}/facts` | Add Fact |
| DELETE | `/providers/{provider_id}/facts/{fact_id}` | Delete Fact |
| GET | `/datasets` | List Datasets — query: `provider_id, metric_type, active, limit, offset` |
| GET | `/connectors/types` | Connector Types |
| GET | `/connectors` | List Connectors — query: `provider_id, include_health, limit, offset` |
| POST | `/connectors` | Create Connector |
| GET | `/connectors/{connector_id}` | Get Connector |
| PATCH | `/connectors/{connector_id}` | Update Connector |
| POST | `/connectors/{connector_id}/sync` | Sync Connector |
| GET | `/connectors/{connector_id}/health` | Connector Health |
| GET | `/connectors/{connector_id}/logs` | Connector Logs — query: `status_filter, limit, offset` |
| GET | `/connectors/{connector_id}/errors` | Connector Errors — query: `sync_log_id, stage, severity, limit, offset` |
| GET | `/connectors/{connector_id}/payloads` | Connector Payloads — query: `limit, offset` |
| GET | `/energy-records` | List Records — query: `country, provider_id, metric_type, energy_source, dataset_id, start, end, data_origin, limit, offset` |
| GET | `/energy-records/summary` | Summary — query: `metric_type, country, provider_id, energy_source, start, end, bucket, include_simulated` |
| GET | `/energy-records/facets` | Facets |
| GET | `/quality-reports` | List Reports — query: `connector_id, overall_status, limit, offset` |
| GET | `/quality-reports/{report_id}` | Get Report |
| GET | `/integration-opportunities` | List Opportunities — query: `country, decision_status` |
| POST | `/integration-opportunities` | Create Opportunity |
| GET | `/integration-opportunities/{opp_id}` | Get Opportunity |
| PATCH | `/integration-opportunities/{opp_id}` | Update Opportunity |
| DELETE | `/integration-opportunities/{opp_id}` | Delete Opportunity |
| GET | `/prioritisation/weights` | Read Weights |
| PUT | `/prioritisation/weights` | Write Weights |
| GET | `/investigations/template` | Template |
| GET | `/investigations` | List Investigations — query: `provider_id` |
| POST | `/investigations` | Create Investigation |
| GET | `/investigations/export.csv` | Export All Csv |
| GET | `/investigations/{inv_id}` | Get Investigation |
| PUT | `/investigations/{inv_id}` | Update Investigation |
| GET | `/investigations/{inv_id}/export` | Export Investigation — query: `format` |
