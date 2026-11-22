"""Seed the GridLink workspace with researched provider profiles, connectors, investigations and
prioritisation candidates. Idempotent: re-running updates nothing that already exists.

Evidence levels used in provider facts:
- verified    tested by GridLink against the live provider (date recorded)
- researched  taken from provider documentation that was read (URL recorded)
- assumption  believed true but NOT yet confirmed - must be verified before relying on it
"""
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import session_factory
from app.models import Connector, Provider, ProviderFact, ProviderInvestigation

CHECKED = datetime(2026, 11, 21, tzinfo=UTC)

PROVIDERS = [
    {
        "slug": "smard", "name": "SMARD (Bundesnetzagentur)", "country_code": "DE",
        "website": "https://www.smard.de/en", "documentation_url": "https://www.smard.de/en/downloadcenter/download-market-data",
        "description": "Electricity market data platform of the German Federal Network Agency: generation by source, "
                       "consumption (grid load, residual load) and wholesale prices.",
        "status": "connected", "authentication_type": "None (public download centre)", "data_formats": ["CSV", "XLSX", "XML"],
        "access_requirements": "Public. No registration. Attribution required under CC BY 4.0.",
        "registration_status": "Not required", "last_investigated_at": CHECKED,
        "notes": "Download centre endpoint is used by the SMARD website itself; it is not a versioned, documented public API.",
        "next_action": "Monitor endpoint stability; add alerting when the CSV header contract changes.",
        "owner": "Data Integration TPM", "licence": "CC BY 4.0", "attribution": "Bundesnetzagentur | SMARD.de",
    },
    {
        "slug": "entsoe", "name": "ENTSO-E Transparency Platform", "country_code": "EU",
        "website": "https://transparency.entsoe.eu/", "documentation_url": "https://transparencyplatform.zendesk.com/",
        "description": "Pan-European transparency data (EU Regulation 543/2013): generation per production type, load, "
                       "day-ahead prices, cross-border flows for all ENTSO-E bidding zones.",
        "status": "access_requested", "authentication_type": "Personal security token (query parameter)",
        "data_formats": ["XML (IEC 62325)", "ZIP"],
        "access_requirements": "Free user account + RESTful API access request; token generated in account settings.",
        "registration_status": "Token not yet configured in this workspace", "last_investigated_at": CHECKED,
        "notes": "Connector is implemented and tested against fixtures; live calls require ENTSOE_API_TOKEN. "
                 "A clearly labelled SIMULATED fixture connector is available meanwhile.",
        "next_action": "Register account, request API access, configure token, run first live sync and compare with SMARD.",
        "owner": "Data Integration TPM", "licence": "ENTSO-E Transparency Platform terms (to verify)",
        "attribution": "ENTSO-E Transparency Platform",
    },
    {
        "slug": "energinet", "name": "Energi Data Service (Energinet)", "country_code": "DK",
        "website": "https://www.energidataservice.dk/", "documentation_url": "https://www.energidataservice.dk/guides/api-guides",
        "description": "Danish TSO open data portal: production, consumption, CO2 emissions and spot prices for DK1/DK2.",
        "status": "discovered", "authentication_type": "None (assumed)", "data_formats": ["JSON", "CSV"],
        "access_requirements": "To verify", "next_action": "Verify API access and licence; map datasets to standard schema.",
        "owner": "Unassigned",
    },
    {
        "slug": "rte-eco2mix", "name": "RTE éCO2mix / ODRÉ", "country_code": "FR",
        "website": "https://www.rte-france.com/en/eco2mix", "documentation_url": "https://odre.opendatasoft.com/",
        "description": "French TSO real-time and consolidated generation mix and consumption, published via open data portal.",
        "status": "discovered", "authentication_type": "To verify (open data portal; RTE Data Portal uses OAuth2)",
        "data_formats": ["JSON", "CSV"], "next_action": "Decide between ODRÉ open data and RTE Data Portal APIs.",
        "owner": "Unassigned",
    },
    {
        "slug": "elexon-bmrs", "name": "Elexon Insights (BMRS)", "country_code": "GB",
        "website": "https://bmrs.elexon.co.uk/", "documentation_url": "https://developer.data.elexon.co.uk/",
        "description": "GB balancing mechanism and generation data (fuel type mix, demand, system prices).",
        "status": "under_investigation", "authentication_type": "None for Insights API (assumed)",
        "data_formats": ["JSON", "CSV", "XML"], "next_action": "Confirm fair-use limits and settlement-period time convention.",
        "owner": "Data Integration TPM",
    },
    {
        "slug": "netztransparenz", "name": "Netztransparenz.de (German TSOs)", "country_code": "DE",
        "website": "https://www.netztransparenz.de/", "documentation_url": "https://www.netztransparenz.de/de-de/Web-API",
        "description": "Joint platform of the four German TSOs: renewable forecasts and actuals, balancing data, EEG data.",
        "status": "discovered", "authentication_type": "OAuth2 client credentials (assumed)", "data_formats": ["CSV", "JSON"],
        "next_action": "Register API client; check whether forecast data complements SMARD actuals.", "owner": "Unassigned",
    },
    {
        "slug": "fingrid", "name": "Fingrid Open Data", "country_code": "FI",
        "website": "https://data.fingrid.fi/en", "documentation_url": "https://data.fingrid.fi/en/instructions",
        "description": "Finnish TSO open data: production, consumption, frequency, cross-border transmission.",
        "status": "discovered", "authentication_type": "API key (assumed, free registration)", "data_formats": ["JSON", "CSV"],
        "next_action": "Verify key issuance and rate limits.", "owner": "Unassigned",
    },
]

FACTS = {
    "smard": [
        ("access", "Download centre POST endpoint returns CSV without authentication.", "verified",
         "https://www.smard.de/en/downloadcenter/download-market-data"),
        ("format", "CSV is semicolon-separated with UTF-8 BOM; English: 'Nov 18, 2026 7:00 PM' and 1,234.56; "
                   "German: '18.11.2026 19:00' and 1.234,56.", "verified", None),
        ("format", "Requesting several data categories at once returns a ZIP of CSV files.", "verified", None),
        ("time", "Timestamps are Europe/Berlin local time; DST fall-back hours repeat.", "verified", None),
        ("units", "Generation and consumption are published as MWh per interval (energy), not MW (power).", "verified", None),
        ("quality", "'-' denotes no published value (e.g. nuclear since 15 Apr 2023); it is not zero.", "verified", None),
        ("access", "Wholesale prices require region 'DE-LU'; region 'DE' returns 'No data for submitted query'.", "verified", None),
        ("quality", "On 2026-11-21 most DE-LU quarter-hour prices from 2026-11-20 were published as '-' while the "
                    "following delivery day was complete.", "verified", None),
        ("licensing", "Market data is licensed CC BY 4.0; attribution 'Bundesnetzagentur | SMARD.de'.", "researched",
         "https://www.smard.de/en/datennutzung"),
        ("licensing", "BNetzA is reviewing licensing of wholesale price data (HEDWIG proceedings) - treat price reuse as "
                      "under review.", "researched", "https://www.smard.de/en/datennutzung"),
        ("limits", "No published rate limit or automated-download restriction was found; GridLink throttles to be "
                   "polite. Absence of a restriction is not proof there is none.", "assumption", None),
        ("stability", "The download endpoint is undocumented as a public API and may change without notice.", "assumption", None),
    ],
    "entsoe": [
        ("access", "API returns HTTP 401 when no security token is supplied.", "verified", "https://web-api.tp.entsoe.eu/api"),
        ("access", "Token is obtained by registering, requesting RESTful API access from the Transparency Platform "
                   "team, then generating it in account settings.", "assumption",
         "https://transparencyplatform.zendesk.com/"),
        ("limits", "Request limit of roughly 400 requests per minute per user; exceeding it may block access temporarily.",
         "assumption", "https://transparencyplatform.zendesk.com/"),
        ("limits", "A single request may cover at most one year; large queries return 'too many documents' errors.",
         "assumption", None),
        ("format", "Responses are IEC 62325 XML; omitted positions under curveType A03 repeat the previous value.",
         "assumption", None),
        ("units", "Generation and load quantities are MW (MAW); prices EUR/MWh.", "assumption", None),
        ("documentation", "Help-centre pages returned HTTP 403 to automated fetches on 2026-11-21; facts above need "
                          "manual verification in a browser.", "verified", "https://transparencyplatform.zendesk.com/"),
    ],
}

for slug in ("energinet", "rte-eco2mix", "elexon-bmrs", "netztransparenz", "fingrid"):
    FACTS[slug] = [("access", "Access model and licence have not yet been verified by GridLink.", "assumption", None)]

INVESTIGATIONS = {
    "smard": {
        "author": "Data Integration TPM",
        "findings": "SMARD is integrated via its public download centre. Data is real, free (CC BY 4.0) and covers the "
                    "core German datasets at 15-minute resolution. Main risks: undocumented endpoint, local-time "
                    "timestamps, energy-vs-power units and gaps published as '-'.",
        "overview": "SMARD is operated by the Bundesnetzagentur (German Federal Network Agency) and publishes electricity "
                    "market data for Germany and neighbouring bidding zones.",
        "country_market": "Germany (control area DE) for generation/consumption; DE-LU bidding zone for day-ahead prices.",
        "available_datasets": "- Actual generation by source (12 sources; nuclear discontinued since 15 Apr 2023)\n"
                              "- Grid load, residual load, pumped-storage consumption\n- Day-ahead price DE-LU and neighbours\n"
                              "- Forecasts, cross-border flows, balancing (not yet integrated)",
        "api_documentation": "No formal API documentation. The download centre UI issues a POST request to "
                             "/nip-download-manager/nip/download/market-data. An undocumented JSON chart API "
                             "(/app/chart_data/...) also exists but is not used.",
        "authentication_method": "None.",
        "registration_process": "None required.",
        "access_requirements": "Public internet access. Attribution 'Bundesnetzagentur | SMARD.de'.",
        "sample_requests": "POST https://www.smard.de/nip-download-manager/nip/download/market-data\n"
                           '{"request_form":[{"format":"CSV","moduleIds":[1004067,1004068],"region":"DE",'
                           '"timestamp_from":1795201200000,"timestamp_to":1795287600000,"type":"discrete",'
                           '"language":"en","resolution":"quarterhour"}]}',
        "sample_response": "Start date;End date;Wind onshore [MWh] Original resolutions;Photovoltaics [MWh] Original resolutions\n"
                           "Nov 20, 2026 7:00 PM;Nov 20, 2026 7:15 PM;3,540.87;0.00",
        "data_format": "Semicolon CSV, UTF-8 BOM, locale-dependent numbers and dates; ZIP when several categories are "
                       "requested. Module IDs: generation 100xxxx, consumption 500xxxx, prices 800xxxx.",
        "limitations": "- Undocumented endpoint, no versioning or SLA\n- Local time (Europe/Berlin) with DST ambiguity\n"
                       "- Header text is the only schema; a rename breaks mapping (detected as 'unmapped series')\n"
                       "- Region semantics differ per category (DE vs DE-LU)",
        "data_quality_issues": "- '-' for unpublished values (must not become 0)\n- Recent intervals published with delay\n"
                               "- Values revised after first publication (handled as updates, not duplicates)\n"
                               "- Observed multi-hour '-' gap in DE-LU quarter-hour prices on 2026-11-20",
        "licensing": "CC BY 4.0 for market data. Wholesale price licensing is under review by BNetzA - confirm before "
                     "commercial redistribution of prices.",
        "integration_complexity": "Low-medium. No auth, but locale parsing, DST handling and MWh->MW conversion are required. "
                                  "Effort: ~1 week including tests.",
        "next_steps": "1. Add header-contract monitoring alert\n2. Add forecast datasets\n3. Legal review of price reuse",
    },
    "entsoe": {
        "author": "Data Integration TPM",
        "findings": "ENTSO-E is the strategic pan-European source. Connector, XML parser and error handling are built and "
                    "tested on fixtures; access is blocked on obtaining a personal security token.",
        "overview": "The ENTSO-E Transparency Platform publishes data mandated by EU Regulation 543/2013 for all member TSOs.",
        "country_market": "All ENTSO-E bidding zones. First target: DE-LU (EIC 10Y1001A1001A82H).",
        "available_datasets": "- A75 Actual generation per production type (16.1.B&C)\n- A65 Actual total load (6.1.A)\n"
                              "- A44 Day-ahead prices (12.1.D)\n- Cross-border flows, outages, capacities (later)",
        "api_documentation": "RESTful API guide on the Transparency Platform help centre (https://transparencyplatform.zendesk.com/). "
                             "Pages returned HTTP 403 to automated fetches; read manually.",
        "authentication_method": "Personal security token passed as `securityToken` query parameter. GridLink reads it from "
                                 "ENTSOE_API_TOKEN and redacts it from all stored URLs and logs.",
        "registration_process": "1. Create a Transparency Platform account\n2. Request RESTful API access (email to the "
                                "Transparency Platform service desk - to verify)\n3. Generate token in account settings",
        "access_requirements": "Free account; token per user; respect request limits (to verify: ~400 req/min).",
        "sample_requests": "GET https://web-api.tp.entsoe.eu/api?documentType=A75&processType=A16&in_Domain=10Y1001A1001A82H"
                           "&periodStart=202611200000&periodEnd=202611210000&securityToken=<token>",
        "sample_response": "<GL_MarketDocument> ... <TimeSeries><MktPSRType><psrType>B16</psrType></MktPSRType>"
                           "<Period><resolution>PT15M</resolution><Point><position>1</position><quantity>0</quantity></Point>"
                           "... </Period></TimeSeries></GL_MarketDocument>",
        "data_format": "IEC 62325 XML. Positional points per Period; curveType A01 (every point) or A03 (repeats omitted). "
                       "Errors and 'no data' come as Acknowledgement_MarketDocument (reason 999).",
        "limitations": "- Token required for every call\n- Request rate and range limits (to verify)\n"
                       "- A75 mixes generation (inBiddingZone) and pumped-storage consumption (outBiddingZone)",
        "data_quality_issues": "- Missing positions (A01) = missing data\n- Late TSO submissions\n"
                               "- Definitions differ from SMARD (e.g. total load vs grid load)",
        "licensing": "Reuse governed by Transparency Platform terms and conditions (to verify before commercial use).",
        "integration_complexity": "Medium. XML parsing, curve types, multiple document types and token management. "
                                  "Effort: ~2 weeks including live validation.",
        "next_steps": "1. Obtain token\n2. Live sync DE-LU A75/A65/A44\n3. Reconcile against SMARD for the same window\n"
                      "4. Extend to FR, NL, AT bidding zones",
    },
    "elexon-bmrs": {
        "author": "Data Integration TPM",
        "overview": "Elexon operates the GB balancing and settlement code; Insights Solution exposes BMRS data.",
        "country_market": "Great Britain (not part of SDAC since Brexit - prices not comparable with EU day-ahead).",
        "authentication_method": "Believed to require no key for the Insights API (to verify).",
        "data_quality_issues": "Settlement periods (48 per day, 30-min) in UK local time - conversion needed.",
        "next_steps": "Verify licence and fair-use policy.",
    },
}

def seed() -> None:
    with session_factory()() as db:
        by_slug = {p.slug: p for p in db.scalars(select(Provider))}
        for data in PROVIDERS:
            if data["slug"] not in by_slug:
                p = Provider(**data)
                db.add(p)
                by_slug[p.slug] = p
        db.flush()

        for slug, facts in FACTS.items():
            p = by_slug[slug]
            if not db.scalar(select(ProviderFact).where(ProviderFact.provider_id == p.id)):
                for cat, stmt, level, url in facts:
                    db.add(ProviderFact(provider_id=p.id, category=cat, statement=stmt, evidence_level=level,
                                        source_url=url, checked_at=CHECKED))

        connectors = [
            ("SMARD Germany – generation, consumption & prices", "smard_csv", "smard", "real",
             {"lookback_days": 7, "resolution": "quarterhour", "language": "en"}, 1440, 360),
            ("ENTSO-E DE-LU – live API", "entsoe_api", "entsoe", "real",
             {"area": "DE-LU", "lookback_days": 3, "datasets": ["generation", "load", "day_ahead_price"]}, 240, 60),
            ("ENTSO-E DE-LU – SIMULATED fixtures", "entsoe_fixture", "entsoe", "simulated",
             {"area": "DE-LU", "fixed_window": ["2026-11-13T23:00:00+00:00", "2026-11-20T23:00:00+00:00"]}, 240, None),
        ]
        for name, ctype, slug, origin, cfg, lag, interval in connectors:
            if not db.scalar(select(Connector).where(Connector.connector_name == name)):
                db.add(Connector(provider_id=by_slug[slug].id, connector_name=name, connector_type=ctype,
                                 data_origin=origin, config=cfg, max_data_lag_minutes=lag,
                                 sync_interval_minutes=interval,
                                 status="awaiting_credentials" if ctype == "entsoe_api" else "active"))

        for slug, fields in INVESTIGATIONS.items():
            p = by_slug[slug]
            if not db.scalar(select(ProviderInvestigation).where(ProviderInvestigation.provider_id == p.id)):
                db.add(ProviderInvestigation(provider_id=p.id, **fields))

        db.commit()
        from app.seed_workflow import seed_workflow

        seed_workflow(db)
    print("seed complete")


def reset() -> None:
    """Delete ALL data (keeps the schema). Used to rebuild the demo workspace."""
    from app.db import Base, get_engine

    with get_engine().begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.exec_driver_sql(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    print("all tables truncated")


if __name__ == "__main__":
    import sys

    if "--reset" in sys.argv:
        reset()
    seed()
