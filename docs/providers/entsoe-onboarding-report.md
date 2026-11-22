# Provider onboarding report: ENTSO-E Transparency Platform

| Field | Value |
|---|---|
| Country | EU |
| Status | access requested |
| Website | https://transparency.entsoe.eu/ |
| Documentation | https://transparencyplatform.zendesk.com/ |
| Authentication | Personal security token (query parameter) |
| Licence | ENTSO-E Transparency Platform terms (to verify) |
| Owner | Data Integration TPM |
| Report author | Data Integration TPM |
| Last updated | 2026-11-21 18:03 UTC |
| Template completion | 100.0% |

## Summary of findings

ENTSO-E is the strategic pan-European source. Connector, XML parser and error handling are built and tested on fixtures; access is blocked on obtaining a personal security token.

## 1. Provider overview

The ENTSO-E Transparency Platform publishes data mandated by EU Regulation 543/2013 for all member TSOs.

## 2. Country and market

All ENTSO-E bidding zones. First target: DE-LU (EIC 10Y1001A1001A82H).

## 3. Available datasets

- A75 Actual generation per production type (16.1.B&C)
- A65 Actual total load (6.1.A)
- A44 Day-ahead prices (12.1.D)
- Cross-border flows, outages, capacities (later)

## 4. API documentation

RESTful API guide on the Transparency Platform help centre (https://transparencyplatform.zendesk.com/). Pages returned HTTP 403 to automated fetches; read manually.

## 5. Authentication requirements

Personal security token passed as `securityToken` query parameter. GridLink reads it from ENTSOE_API_TOKEN and redacts it from all stored URLs and logs.

## 6. Registration process

1. Create a Transparency Platform account
2. Request RESTful API access (email to the Transparency Platform service desk - to verify)
3. Generate token in account settings

## 7. Access requirements

Free account; token per user; respect request limits (to verify: ~400 req/min).

## 8. Sample API requests

GET https://web-api.tp.entsoe.eu/api?documentType=A75&processType=A16&in_Domain=10Y1001A1001A82H&periodStart=202611200000&periodEnd=202611210000&securityToken=<token>

## 9. Sample response

<GL_MarketDocument> ... <TimeSeries><MktPSRType><psrType>B16</psrType></MktPSRType><Period><resolution>PT15M</resolution><Point><position>1</position><quantity>0</quantity></Point>... </Period></TimeSeries></GL_MarketDocument>

## 10. Data format

IEC 62325 XML. Positional points per Period; curveType A01 (every point) or A03 (repeats omitted). Errors and 'no data' come as Acknowledgement_MarketDocument (reason 999).

## 11. Known limitations

- Token required for every call
- Request rate and range limits (to verify)
- A75 mixes generation (inBiddingZone) and pumped-storage consumption (outBiddingZone)

## 12. Data quality issues

- Missing positions (A01) = missing data
- Late TSO submissions
- Definitions differ from SMARD (e.g. total load vs grid load)

## 13. Commercial or licensing considerations

Reuse governed by Transparency Platform terms and conditions (to verify before commercial use).

## 14. Integration complexity

Medium. XML parsing, curve types, multiple document types and token management. Effort: ~2 weeks including live validation.

## 15. Next steps

1. Obtain token
2. Live sync DE-LU A75/A65/A44
3. Reconcile against SMARD for the same window
4. Extend to FR, NL, AT bidding zones

## Evidence register

| Evidence | Category | Statement | Source |
|---|---|---|---|
| verified | access | API returns HTTP 401 when no security token is supplied. | https://web-api.tp.entsoe.eu/api |
| assumption | access | Token is obtained by registering, requesting RESTful API access from the Transparency Platform team, then generating it in account settings. | https://transparencyplatform.zendesk.com/ |
| assumption | limits | Request limit of roughly 400 requests per minute per user; exceeding it may block access temporarily. | https://transparencyplatform.zendesk.com/ |
| assumption | limits | A single request may cover at most one year; large queries return 'too many documents' errors. | - |
| assumption | format | Responses are IEC 62325 XML; omitted positions under curveType A03 repeat the previous value. | - |
| assumption | units | Generation and load quantities are MW (MAW); prices EUR/MWh. | - |
| verified | documentation | Help-centre pages returned HTTP 403 to automated fetches on 2026-11-21; facts above need manual verification in a browser. | https://transparencyplatform.zendesk.com/ |

_verified_ = tested by GridLink; _researched_ = from provider documentation; _assumption_ = not yet confirmed.

_Exported from GridLink on 2026-11-21 18:20 UTC._