# Provider onboarding report: SMARD (Bundesnetzagentur)

| Field | Value |
|---|---|
| Country | DE |
| Status | connected |
| Website | https://www.smard.de/en |
| Documentation | https://www.smard.de/en/downloadcenter/download-market-data |
| Authentication | None (public download centre) |
| Licence | CC BY 4.0 |
| Owner | Data Integration TPM |
| Report author | Data Integration TPM |
| Last updated | 2026-11-21 18:03 UTC |
| Template completion | 100.0% |

## Summary of findings

SMARD is integrated via its public download centre. Data is real, free (CC BY 4.0) and covers the core German datasets at 15-minute resolution. Main risks: undocumented endpoint, local-time timestamps, energy-vs-power units and gaps published as '-'.

## 1. Provider overview

SMARD is operated by the Bundesnetzagentur (German Federal Network Agency) and publishes electricity market data for Germany and neighbouring bidding zones.

## 2. Country and market

Germany (control area DE) for generation/consumption; DE-LU bidding zone for day-ahead prices.

## 3. Available datasets

- Actual generation by source (12 sources; nuclear discontinued since 15 Apr 2023)
- Grid load, residual load, pumped-storage consumption
- Day-ahead price DE-LU and neighbours
- Forecasts, cross-border flows, balancing (not yet integrated)

## 4. API documentation

No formal API documentation. The download centre UI issues a POST request to /nip-download-manager/nip/download/market-data. An undocumented JSON chart API (/app/chart_data/...) also exists but is not used.

## 5. Authentication requirements

None.

## 6. Registration process

None required.

## 7. Access requirements

Public internet access. Attribution 'Bundesnetzagentur | SMARD.de'.

## 8. Sample API requests

POST https://www.smard.de/nip-download-manager/nip/download/market-data
{"request_form":[{"format":"CSV","moduleIds":[1004067,1004068],"region":"DE","timestamp_from":1795201200000,"timestamp_to":1795287600000,"type":"discrete","language":"en","resolution":"quarterhour"}]}

## 9. Sample response

Start date;End date;Wind onshore [MWh] Original resolutions;Photovoltaics [MWh] Original resolutions
Nov 20, 2026 7:00 PM;Nov 20, 2026 7:15 PM;3,540.87;0.00

## 10. Data format

Semicolon CSV, UTF-8 BOM, locale-dependent numbers and dates; ZIP when several categories are requested. Module IDs: generation 100xxxx, consumption 500xxxx, prices 800xxxx.

## 11. Known limitations

- Undocumented endpoint, no versioning or SLA
- Local time (Europe/Berlin) with DST ambiguity
- Header text is the only schema; a rename breaks mapping (detected as 'unmapped series')
- Region semantics differ per category (DE vs DE-LU)

## 12. Data quality issues

- '-' for unpublished values (must not become 0)
- Recent intervals published with delay
- Values revised after first publication (handled as updates, not duplicates)
- Observed multi-hour '-' gap in DE-LU quarter-hour prices on 2026-11-20

## 13. Commercial or licensing considerations

CC BY 4.0 for market data. Wholesale price licensing is under review by BNetzA - confirm before commercial redistribution of prices.

## 14. Integration complexity

Low-medium. No auth, but locale parsing, DST handling and MWh->MW conversion are required. Effort: ~1 week including tests.

## 15. Next steps

1. Add header-contract monitoring alert
2. Add forecast datasets
3. Legal review of price reuse

## Evidence register

| Evidence | Category | Statement | Source |
|---|---|---|---|
| verified | access | Download centre POST endpoint returns CSV without authentication. | https://www.smard.de/en/downloadcenter/download-market-data |
| verified | format | CSV is semicolon-separated with UTF-8 BOM; English: 'Nov 18, 2026 7:00 PM' and 1,234.56; German: '18.11.2026 19:00' and 1.234,56. | - |
| verified | format | Requesting several data categories at once returns a ZIP of CSV files. | - |
| verified | time | Timestamps are Europe/Berlin local time; DST fall-back hours repeat. | - |
| verified | units | Generation and consumption are published as MWh per interval (energy), not MW (power). | - |
| verified | quality | '-' denotes no published value (e.g. nuclear since 15 Apr 2023); it is not zero. | - |
| verified | access | Wholesale prices require region 'DE-LU'; region 'DE' returns 'No data for submitted query'. | - |
| verified | quality | On 2026-11-21 most DE-LU quarter-hour prices from 2026-11-20 were published as '-' while the following delivery day was complete. | - |
| researched | licensing | Market data is licensed CC BY 4.0; attribution 'Bundesnetzagentur \| SMARD.de'. | https://www.smard.de/en/datennutzung |
| researched | licensing | BNetzA is reviewing licensing of wholesale price data (HEDWIG proceedings) - treat price reuse as under review. | https://www.smard.de/en/datennutzung |
| assumption | limits | No published rate limit or automated-download restriction was found; GridLink throttles to be polite. Absence of a restriction is not proof there is none. | - |
| assumption | stability | The download endpoint is undocumented as a public API and may change without notice. | - |

_verified_ = tested by GridLink; _researched_ = from provider documentation; _assumption_ = not yet confirmed.

_Exported from GridLink on 2026-11-21 18:20 UTC._