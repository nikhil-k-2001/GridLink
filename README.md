# GridLink — Market Connections Workspace

**Make the data customers need accessible, reliable and usable — across European energy markets.**

GridLink is a working model of the job of a **Technical Product Manager for market connections** at a
renewable-asset-management SaaS. It starts where that job starts — *customers' plants and the data they
need* — and follows the work through: mapping how data can be accessed in each country, chasing providers,
testing APIs, building reusable connectors with engineering, catching data issues before customers do, and
turning each connection into a playbook that makes the next one faster.

> **Live demo:** https://gridlink-web.vercel.app · API docs: https://gridlink-api.vercel.app/docs
>
> **Start here:** [How GridLink maps to the role](docs/role-mapping.md) ·
> [5-minute demo script](docs/demo-script.md) · [First 90 days plan](docs/first-90-days.md)

| What | Status |
|---|---|
| SMARD (Bundesnetzagentur) — German generation, load, DE-LU day-ahead prices | **Real data**, public CSV download |
| ENTSO-E Transparency Platform — prices for FR/ES/IT/NL | Connector built & tested; **live calls need your own token** |
| Customers, plants, plant-level DSO metering (France, Spain) | **Fictional / simulated**, labelled everywhere |
| Facts about real organisations (Enedis, Datadis, e-distribuzione, MaStR, ENTSO-E…) | Each tagged *verified* / *researched* (with URL) / *assumption* |

> GridLink never fabricates credentials or claims a connection that doesn't exist. Without `ENTSOE_API_TOKEN`
> the live ENTSO-E connector shows **Failed — awaiting credentials**.

### The workflow it models

```
Customers & plants ─► Coverage gaps ─► Prioritisation ─► Country access map ─► Relationships & access requests
        ▲                                                                              │
        │                                                                              ▼
  Data issues ◄── Quality & health ◄── Connector (shared pipeline) ◄── Integration spec ◄── API test bench
        │
        └──► Lessons learned & country playbook (the next country is faster)
```

## Quick start

Prerequisites: Docker, Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make db                 # PostgreSQL 16 on localhost:5434 (docker compose)
cp backend/.env.example backend/.env
make backend-install migrate seed    # `python -m app.seed --reset` rebuilds the demo workspace
make api                # http://localhost:8000  (OpenAPI: /docs)
```

In a second terminal:

```bash
cp frontend/.env.example frontend/.env.local
make frontend-install web   # http://localhost:3000
```

Then open **Connectors** and press **Sync** on each connector (or `curl -X POST localhost:8000/connectors/{id}/sync`).
The SMARD sync downloads the last 7 days of real data (~10k records) in a few seconds; the two simulated DSO
connectors fetch plant data and raise the planted data issues (gap, revoked consent, estimated values, duplicates).

Without `make`: see the commands inside the [`Makefile`](Makefile).

### Optional configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `ENTSOE_API_TOKEN` | Your personal ENTSO-E security token → enables the live ENTSO-E connector |
| `GEMINI_API_KEY` | Gemini Developer API (free tier) → AI error summaries / dataset explanations. Optional. |
| `SCHEDULER_ENABLED=true` | Background syncs every `sync_interval_minutes` per connector (APScheduler). Default: manual. |

---

## Modules

| Area | Page | What it does |
|---|---|---|
| This week | **Cockpit** `/` | Coverage, overdue follow-ups, data issues by customer impact, biggest gaps, access lead time |
| Demand | **Customers & plants** `/coverage` | Every plant × data need with one status, a reason and a next step; rollups per customer and country |
| Demand | **Prioritisation** `/prioritisation` | Transparent, editable scoring; customer value backed by live demand (plants, MW, customers waiting) |
| Access | **Country access maps** `/countries` | Market actors, routes per data need with fallbacks and blockers, 10-step playbook, lessons learned |
| Access | **Providers** `/providers` | Directory with status workflow and an evidence register (verified / researched / assumption) |
| Access | **Relationships** `/relationships` | Access requests, interaction log, follow-ups (overdue first), contacts by role |
| Access | **API test bench** `/api-bench` | Allow-listed real and simulated API calls, redacted evidence, promote results to verified facts |
| Access | **Onboarding docs** `/documentation` | 15-section integration spec per provider, Markdown/CSV export |
| Data | **Connectors** `/connectors` | One contract for all providers; sync history, errors, raw payloads, missing periods |
| Data | **Data quality** `/quality` | Completeness, consistency, freshness, validity and reliability after every sync |
| Data | **Data issues** `/issues` | Auto-raised issues with affected customers/MW, hypotheses, root cause, customer update, resolution |
| Data | **Energy explorer** `/explorer` | Normalised market data with provenance and comparability warnings |

Example exported reports: [SMARD](docs/providers/smard-onboarding-report.md) · [ENTSO-E](docs/providers/entsoe-onboarding-report.md)

## Architecture

Full write-up with diagram: **[docs/architecture.md](docs/architecture.md)**. API reference: **[docs/api.md](docs/api.md)**.

```
authenticate → fetch (raw bytes stored) → parse (provider vocabulary) → normalise (mapping file) → validate → save (idempotent) → quality report → health
└──────── provider-specific ────────┘   └──────────────────────── provider-agnostic ────────────────────────┘
```

```
backend/
  app/connectors/        base contract, HTTP client (retry/backoff), smard.py, entsoe.py, mappings/*.json
  app/normalisation/     units (MWh/interval → MW, kW → MW, ct/kWh → EUR/MWh), timestamps (DST-safe), engine
  app/quality/           completeness, consistency, validity, freshness checks
  app/services/          sync orchestrator, repository (upsert), health, prioritisation, report export, AI
  app/api/               FastAPI routers
  alembic/               migrations
  fixtures/              SIMULATED ENTSO-E XML (generated by scripts/generate_entsoe_fixtures.py)
  app/simulated/         fictional portfolio + simulated DSO platforms (also served at /simulated/...)
  tests/                 100 tests + provider failure fixtures
frontend/                Next.js 16 · TypeScript strict · Tailwind · shadcn/ui · Recharts · Lucide
docs/                    architecture, API reference, OpenAPI spec, onboarding reports
```

### Key design decisions

* **Energy ≠ power.** SMARD publishes MWh per 15 min, ENTSO-E publishes MW. GridLink stores average MW and keeps the
  original value, unit and transformation on every record.
* **Missing ≠ zero.** SMARD's `-` is stored as `null` and counted as missing; zeros (solar at night) stay zeros.
* **Similar names ≠ same metric.** Every provider series is mapped explicitly; unknown columns are reported, not guessed.
  Pumped-storage *generation* and *consumption* are kept apart in both providers.
* **HTTP 200 ≠ healthy.** Health combines sync outcomes, request reliability, completeness (overall *and* per series),
  validity and freshness, and explains every downgrade.
* **Idempotent, auditable ingestion.** Natural key `(provider_id, source_record_id)`; raw payloads retained with outcome;
  provider revisions are counted as updates.

---

## Data sources, access and usage restrictions

| Provider | Access | Format | Licence / attribution | Evidence |
|---|---|---|---|---|
| SMARD | Public, no registration. Download-centre endpoint used by the website itself (not a versioned API). | Semicolon CSV, UTF-8 BOM; ZIP for multi-category requests | **CC BY 4.0**, attribute *"Bundesnetzagentur \| SMARD.de"*. BNetzA states licensing of **wholesale prices** is under review. | Endpoint behaviour verified 2026-11-21; licence read on smard.de/en/datennutzung |
| ENTSO-E | Free account + RESTful API access request + personal security token | IEC 62325 XML | Transparency Platform terms (to verify before commercial use) | HTTP 401 without token verified; rate limits and token steps from prior knowledge — help-centre pages returned 403 to automated fetches, **verify manually** |
| Gemini (optional) | Free-tier API key | JSON | Google AI terms | Free-tier rate limits apply; GridLink degrades gracefully (HTTP 503 with message) |

GridLink assumes no provider offers unlimited access: it throttles requests (SMARD 4 req/s max, ENTSO-E 2 req/s),
chunks windows to 7 days, honours `Retry-After`, and syncs manually by default.

Real-world findings captured during the build (see the SMARD report): prices require region `DE-LU` not `DE`;
on 2026-11-20 most DE-LU quarter-hour prices were published as `-`; SMARD revises recent values after first publication.

---

## Testing

```bash
cd backend && uv run pytest        # 100 tests, SQLite in-memory, no network
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

Covered: CSV parsing (EN/DE number formats, ZIP, bad columns, no-data marker), XML parsing (A75 in/out, A44, A01 gaps,
A03 carry-forward, acknowledgement documents, malformed XML), token authentication (missing, malformed, HTTP 401,
redaction), timestamp normalisation (offsets, naive rejection, DST fall-back inference, DST gap), unit conversion,
missing records, duplicate & conflicting-duplicate detection, validity rules, freshness, API failures (5xx exhaustion,
timeouts, network errors, 4xx no-retry, 429 Retry-After), idempotent ingestion and revisions, partial ingestion,
connector health calculations, and the REST API (validation, pagination, 404/409/422/503).

---

## Deployment

The live demo runs entirely on free tiers:

| Part | Where | Notes |
|---|---|---|
| Web (Next.js) | Vercel project `gridlink-web`, root `frontend/` | `NEXT_PUBLIC_API_URL=https://gridlink-api.vercel.app` (baked in at build time) |
| API (FastAPI) | Vercel project `gridlink-api`, root `backend/`, functions in `fra1` | Zero-config FastAPI (`[tool.vercel] entrypoint = "app.main:app"`), 60 s max duration |
| Database | Supabase Postgres (Frankfurt) via the Vercel Marketplace | Injects `POSTGRES_URL` (pooled) and `POSTGRES_URL_NON_POOLING` (migrations) |
| Daily refresh | Vercel Cron → `GET /cron/daily-sync` at 06:00 UTC | Protected by `CRON_SECRET`; refreshes SMARD and the simulated DSO connectors (also keeps the free database active) |

On first start with `AUTO_SETUP=true` the API runs Alembic migrations and seeds the demo workspace under a
Postgres advisory lock (taken on the direct connection, never through the transaction pooler). `/health`
reports the setup state. Pushing to `main` redeploys both projects.

Any PostgreSQL 14+ works elsewhere: set `DATABASE_URL` (or `POSTGRES_URL`), optionally a direct
`POSTGRES_URL_NON_POOLING` / `DATABASE_URL_UNPOOLED`, and run `docker build -t gridlink-api backend` for a container
deployment. Secrets are only ever read from the environment and are redacted from stored URLs.

> The public demo has no login: anyone can sync connectors or edit records. That is deliberate for a portfolio
> demo; a real deployment would add SSO and roles first.

## Known limitations / next steps

* Plant-level data comes from simulated DSO platforms; going live means a provider contract (e.g. Enedis) and owner consent per plant.
* No authentication or roles in the web app ("administrators" = anyone with access). Add SSO before sharing.
* Sync runs synchronously inside the request (seconds for SMARD). Large backfills should move to a job queue.
* ENTSO-E has only been exercised against fixtures and mocked HTTP; the first live sync with a real token must be
  reconciled against SMARD for the same window.
* SMARD's endpoint is undocumented; a header-contract change will surface as `unmapped_series` / `unexpected_columns`
  (visible in health), but there is no alert channel yet.
* Some German CSV header aliases beyond "Wind Onshore"/"Photovoltaik" are assumed; unknown ones are reported, not ingested.
* Quality reports are computed at ingestion; health recomputes freshness live.

Data attribution: **Bundesnetzagentur | SMARD.de** (CC BY 4.0).
