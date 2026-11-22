"""Seed the market-connections workflow: providers per country, country access maps, playbooks,
relationships, fictional customers & plants, plant connectors and demand-linked priorities.

Honesty rules applied here
- Real organisations are named, but every claim about them carries an evidence level and, where it was
  read, the URL. Facts not confirmed on 2026-11-22 are labelled "assumption".
- Customers, plants, metering IDs and plant data are FICTIONAL / SIMULATED.
- Contacts are roles or shared channels, never invented named people or e-mail addresses.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import (
    PLAYBOOK_STEPS,
    AccessRequest,
    AccessRoute,
    Asset,
    AssetAuthorisation,
    Connector,
    Contact,
    CountryProfile,
    Customer,
    DataIssue,
    IntegrationOpportunity,
    Interaction,
    PlaybookStep,
    Provider,
    ProviderFact,
)
from app.schemas import PrioritisationWeights
from app.services.prioritisation import priority_score
from app.simulated.world import CUSTOMERS, PLANTS

CHECKED = datetime(2026, 11, 22, tzinfo=UTC)

PROVIDERS = [
    {"slug": "enedis", "name": "Enedis — Data Connect", "country_code": "FR", "status": "access_requested",
     "website": "https://www.enedis.fr/", "documentation_url": "https://datahub-enedis.fr/services-api/data-connect/",
     "description": "French DSO. Data Connect is a REST/JSON API through which customers (incl. producers) share Linky meter data "
                    "with a service provider after consenting in their Enedis account.",
     "authentication_type": "OAuth2 customer consent + prior contract", "data_formats": ["JSON"],
     "access_requirements": "Professional legal entity; contract with Enedis before production use; consent per customer.",
     "registration_status": "Contract in review", "owner": "Data Integration TPM",
     "next_action": "Chase signed contract; plan migration from simulated connector to live API."},
    {"slug": "datadis", "name": "Datadis (Spanish DSO data platform)", "country_code": "ES", "status": "integration_in_progress",
     "website": "https://datadis.es/", "description": "Shared platform through which Spanish distributors expose metering data to "
     "supply-point holders and authorised third parties.", "authentication_type": "Account + authorisation by supply-point holder (to verify)",
     "data_formats": ["JSON"], "access_requirements": "To verify — public site is JavaScript-rendered and private API docs returned 403.",
     "registration_status": "Third-party access granted (simulated)", "owner": "Data Integration TPM",
     "next_action": "Resolve estimated-value and duplicate-row handling with engineering; document in runbook."},
    {"slug": "e-distribuzione", "name": "e-distribuzione", "country_code": "IT", "status": "blocked",
     "website": "https://www.e-distribuzione.it/", "description": "Largest Italian electricity DSO (distribution and metering). "
     "Producers can view produced and injected energy readings in the online client area.",
     "authentication_type": "Client-area login (no third-party API found)", "data_formats": ["Portal export"],
     "access_requirements": "No third-party API confirmed. Options: owner delegates client-area access, or manual exports.",
     "registration_status": "Request stalled", "owner": "Data Integration TPM",
     "next_action": "Escalate via customer's account manager; in parallel test O&M/SCADA export fallback with Helio Invest."},
    {"slug": "mastr", "name": "Marktstammdatenregister (BNetzA)", "country_code": "DE", "status": "access_requested",
     "website": "https://www.marktstammdatenregister.de/MaStR",
     "documentation_url": "https://www.marktstammdatenregister.de/MaStRHilfe/subpages/webdienst.html",
     "description": "German register of all generation units, operated by the Bundesnetzagentur. Public bulk export daily; SOAP web "
                    "service with API key.", "authentication_type": "None for bulk download; API key for SOAP web service",
     "data_formats": ["XML (ZIP)", "SOAP"], "licence": "Datenlizenz Deutschland – Namensnennung 2.0",
     "access_requirements": "Bulk export public. Web service needs a registered 'Webdienst-Benutzer' key; 100,000 calls/day.",
     "registration_status": "Web-service user requested", "owner": "Data Integration TPM",
     "next_action": "Use daily bulk export to validate plant capacity & commissioning dates against customer data."},
    {"slug": "de-direct-marketers", "name": "Direct marketers (DE) — production data feeds", "country_code": "DE",
     "status": "under_investigation", "description": "Most German renewable plants sell via a direct marketer, which receives "
     "quarter-hourly production data. A bilateral feed may be faster than integrating hundreds of DSOs.",
     "authentication_type": "Bilateral agreement + plant-owner authorisation", "data_formats": ["CSV", "SFTP", "API (varies)"],
     "owner": "Data Integration TPM", "next_action": "Ask Aurelia & Brightwater which direct marketers they use; shortlist two."},
    {"slug": "nl-dsos", "name": "Dutch regional DSOs (Liander, Stedin, Enexis)", "country_code": "NL", "status": "discovered",
     "description": "Regional grid operators in the Netherlands. Central metering-data arrangements not yet verified.",
     "authentication_type": "To investigate", "data_formats": [], "owner": "Unassigned",
     "next_action": "Map the access process (central metering hub?) before contacting individual DSOs."},
]

FACTS = {
    "enedis": [
        ("access", "Data Connect is an API for consumers and producers with a Linky meter to share their data with a service provider.",
         "researched", "https://datahub-enedis.fr/services-api/data-connect/"),
        ("access", "Consent is given by the customer in their Enedis account (OAuth 2.0) and can be revoked there.", "researched",
         "https://datahub-enedis.fr/services-api/data-connect/parcours-client/"),
        ("access", "Open to professional legal entities; requires a prior contract.", "researched",
         "https://datahub-enedis.fr/fournisseurs-de-services/"),
        ("format", "Load-curve history available for 24 months, J+1/J+2 freshness, REST JSON.", "researched",
         "https://datahub-enedis.fr/fournisseurs-de-services/"),
        ("licensing", "Listed as 'Non facturé' (no charge) in Enedis' service comparison table — verify for Data Connect specifically.",
         "assumption", "https://datahub-enedis.fr/fournisseurs-de-services/"),
        ("format", "Exact interval length of production curves not confirmed (catalogue page returned 403).", "assumption", None),
    ],
    "datadis": [
        ("documentation", "Public site is JavaScript-rendered and the private API page returned 403 to automated reads on 2026-11-22.",
         "verified", "https://datadis.es/"),
        ("access", "Third parties access data after authorisation by the supply-point holder.", "assumption", None),
        ("format", "Hourly values labelled by hour-ending ('01:00'..'24:00') in local time; estimated values flagged.", "assumption", None),
    ],
    "e-distribuzione": [
        ("access", "Largest Italian DSO for distribution and metering, serving 31.5+ million customers.", "researched",
         "https://www.e-distribuzione.it/"),
        ("access", "Producers can view produced and injected energy readings in the online client area.", "researched",
         "https://www.e-distribuzione.it/a-chi-ci-rivolgiamo/produttori.html"),
        ("access", "No public or third-party API for producer metering data was found on the pages reviewed.", "researched",
         "https://www.e-distribuzione.it/a-chi-ci-rivolgiamo/produttori.html"),
    ],
    "mastr": [
        ("access", "Operated by the Bundesnetzagentur.", "researched", "https://www.marktstammdatenregister.de/MaStR"),
        ("format", "Full public export ('Gesamtdatenauszug') as XML in ZIP, updated daily around 05:00.", "researched",
         "https://www.marktstammdatenregister.de/MaStR/Datendownload"),
        ("licensing", "Bulk export licensed under Datenlizenz Deutschland – Namensnennung 2.0.", "researched",
         "https://www.marktstammdatenregister.de/MaStR/Datendownload"),
        ("limits", "SOAP web service requires a registered web-service user key; non-network-operators limited to 100,000 calls/day.",
         "researched", "https://www.marktstammdatenregister.de/MaStRHilfe/subpages/webdienst.html"),
        ("documentation", "Help page's production WSDL link points to the test host — confirm the correct WSDL before building.",
         "researched", "https://www.marktstammdatenregister.de/MaStRHilfe/subpages/webdienst.html"),
    ],
    "de-direct-marketers": [("access", "Direct marketers receive quarter-hourly production data for the plants they market.", "assumption", None)],
    "nl-dsos": [("access", "A central metering-data access arrangement may exist; not verified.", "assumption", None)],
}

IT_ZONES = ["IT-NORD", "IT-CNOR", "IT-CSUD", "IT-SUD", "IT-CALA", "IT-SICI", "IT-SARD"]
COUNTRIES = [
    {"country_code": "DE", "name": "Germany", "bidding_zones": ["DE-LU"], "tso": "50Hertz, Amprion, TenneT DE, TransnetBW",
     "market_operator": "EPEX SPOT / day-ahead via SDAC", "languages": ["German"], "status": "partially_connected",
     "dso_landscape": "Several hundred DSOs (often quoted as ~860 — verify). Production metering sits with the DSO or metering-point "
                      "operator; direct marketers also receive 15-min data. Plant master data is public in MaStR.",
     "summary": "Market prices live from SMARD (real). Plant metering is the hard part: no single DSO platform. Investigating direct "
                "marketers as an aggregation route.",
     "lessons_learned": "- SMARD prices need region DE-LU, not DE.\n- SMARD uses Berlin local time and MWh per interval — convert to MW.\n"
                        "- '-' means unpublished, never zero; SMARD revises recent values.\n"
                        "- With hundreds of DSOs, look for an aggregator (direct marketer) before going DSO by DSO."},
    {"country_code": "FR", "name": "France", "bidding_zones": ["FR"], "tso": "RTE", "market_operator": "EPEX SPOT / SDAC",
     "languages": ["French"], "status": "access_in_progress",
     "dso_landscape": "Enedis operates most of the distribution network (share to verify); local distribution companies (ELD) cover the rest. "
                      "Enedis Data Connect gives consent-based API access.",
     "summary": "Consent-based route identified and tested on a simulated platform. Contract in review. One plant's consent was revoked at "
                "the DSO while our records still said granted.",
     "lessons_learned": "- Consent lives at the DSO: re-check our authorisation records against provider responses every sync.\n"
                        "- Interval-END timestamps in local time — shift to interval start before storing.\n"
                        "- Start the contract early: it, not the API, is the critical path."},
    {"country_code": "ES", "name": "Spain", "bidding_zones": ["ES"], "tso": "Red Eléctrica (REE)", "market_operator": "OMIE",
     "languages": ["Spanish"], "status": "partially_connected",
     "dso_landscape": "Several large DSOs plus many small ones; metering data shared through the Datadis platform (details to verify).",
     "summary": "Plant metering connected (simulated platform). Prices still blocked on the ENTSO-E token; OMIE files are a fallback.",
     "lessons_learned": "- Hour-ending labels ('24:00') and DST: convert with sequence-aware localisation.\n"
                        "- Estimated readings exist and are revised later — flag, don't drop.\n"
                        "- Duplicate rows from the provider: de-duplicate on natural key, report count."},
    {"country_code": "IT", "name": "Italy", "bidding_zones": IT_ZONES, "tso": "Terna", "market_operator": "GME",
     "languages": ["Italian"], "status": "blocked",
     "dso_landscape": "e-distribuzione is the largest DSO (31.5m+ customers); several local DSOs. No third-party API for producer "
                      "metering confirmed — client-area access only.",
     "summary": "Highest unmet demand (3 plants, 80 MW, 2 customers) and no API route. Pursuing owner-delegated access and an O&M/SCADA "
                "export fallback in parallel.",
     "lessons_learned": "- Seven bidding zones: map each plant to its zone before talking about prices.\n"
                        "- When the official channel stalls, go through the customer: owners have portal access we can be delegated."},
    {"country_code": "NL", "name": "Netherlands", "bidding_zones": ["NL"], "tso": "TenneT NL", "market_operator": "EPEX SPOT / SDAC",
     "languages": ["Dutch", "English"], "status": "not_started",
     "dso_landscape": "Regional DSOs (Liander, Stedin, Enexis and smaller). Central metering-data arrangements to verify.",
     "summary": "One plant today (Brightwater). Start with landscape mapping when demand grows.", "lessons_learned": ""},
]

ROUTES = [  # country, need, holder, provider slug, type, status, fallback, effort, owner_auth, blockers, evidence, url, notes
    ("DE", "day_ahead_price", "SMARD (Bundesnetzagentur)", "smard", "public_download", "in_use", False, "low", False, None, "verified",
     "https://www.smard.de/en/downloadcenter/download-market-data", "Live. CC BY 4.0."),
    ("DE", "production_metering", "DSO / metering-point operator per plant", None, "email_request", "investigating", False, "high", True,
     "Hundreds of DSOs, no common API; per-DSO contracts", "assumption", None, None),
    ("DE", "production_metering", "Direct marketer data feed", "de-direct-marketers", "third_party", "investigating", True, "medium", True,
     None, "assumption", None, "One agreement can cover many plants across DSOs."),
    ("DE", "plant_master_data", "Marktstammdatenregister bulk export", "mastr", "public_download", "available", False, "low", False, None,
     "researched", "https://www.marktstammdatenregister.de/MaStR/Datendownload", "Validate capacity and commissioning dates."),
    ("FR", "production_metering", "Enedis Data Connect", "enedis", "authorised_api", "testing", False, "medium", True,
     "Contract required before production access", "researched", "https://datahub-enedis.fr/services-api/data-connect/",
     "Tested against simulated platform; live after contract."),
    ("FR", "production_metering", "Owner export from Enedis customer account", "enedis", "portal_export", "available", True, "low", True,
     None, "assumption", None, "Manual, monthly — acceptable stop-gap only."),
    ("FR", "day_ahead_price", "ENTSO-E Transparency Platform (A44)", "entsoe", "authorised_api", "blocked", False, "low", False,
     "Waiting for ENTSO-E API token", "verified", "https://web-api.tp.entsoe.eu/api", "HTTP 401 without token verified."),
    ("ES", "production_metering", "Datadis", "datadis", "authorised_api", "in_use", False, "medium", True, None, "assumption",
     "https://datadis.es/", "Connected via simulated platform."),
    ("ES", "day_ahead_price", "ENTSO-E Transparency Platform (A44)", "entsoe", "authorised_api", "blocked", False, "low", False,
     "Waiting for ENTSO-E API token", "verified", None, None),
    ("ES", "day_ahead_price", "OMIE public market results", None, "public_download", "to_investigate", True, "low", False, None,
     "assumption", None, "Check licence and file format."),
    ("IT", "production_metering", "e-distribuzione client area", "e-distribuzione", "portal_export", "blocked", False, "high", True,
     "No third-party API; needs owner login delegation or manual export", "researched",
     "https://www.e-distribuzione.it/a-chi-ci-rivolgiamo/produttori.html", None),
    ("IT", "production_metering", "Customer O&M / SCADA export", None, "file_delivery", "investigating", True, "medium", True, None,
     "assumption", None, "Inverter/turbine SCADA is not revenue metering — reconcile against DSO readings monthly."),
    ("IT", "day_ahead_price", "ENTSO-E Transparency Platform (A44)", "entsoe", "authorised_api", "blocked", False, "low", False,
     "Waiting for ENTSO-E API token", "verified", None, "7 bidding zones."),
    ("IT", "day_ahead_price", "GME market results", None, "public_download", "to_investigate", True, "low", False, None, "assumption", None, None),
    ("NL", "production_metering", "Regional DSOs", "nl-dsos", "email_request", "to_investigate", False, "high", True, None, "assumption", None, None),
    ("NL", "day_ahead_price", "ENTSO-E Transparency Platform (A44)", "entsoe", "authorised_api", "blocked", False, "low", False,
     "Waiting for ENTSO-E API token", "verified", None, None),
]

PLAYBOOK = {
    "DE": ["done", "done", "done", "in_progress", "todo", "done", "done", "in_progress", "done", "in_progress"],
    "FR": ["done", "done", "done", "done", "in_progress", "in_progress", "done", "done", "in_progress", "todo"],
    "ES": ["done", "done", "done", "done", "done", "done", "done", "done", "done", "in_progress"],
    "IT": ["done", "done", "in_progress", "in_progress", "todo", "blocked", "todo", "todo", "todo", "todo"],
    "NL": ["done", "todo", "todo", "todo", "todo", "todo", "todo", "todo", "todo", "todo"],
}

CONTACTS = [  # provider slug, role, language, notes
    ("enedis", "Data Connect partner onboarding (contact form)", "French", "Replies in ~1 week; contract questions go via the same channel."),
    ("datadis", "Third-party access support (web form)", "Spanish", None),
    ("e-distribuzione", "Producer services — client-area support", "Italian", "Phone line routes API questions to client-area support."),
    ("e-distribuzione", "Helio Invest — asset manager for Italian plants (customer side)", "Italian/English",
     "Customer contact who owns the client-area logins — key to the delegation route."),
    ("entsoe", "Transparency Platform service desk", "English", None),
    ("mastr", "MaStR web-service support (BNetzA)", "German", None),
    ("de-direct-marketers", "Aurelia Wind Partners — commercial manager (customer side)", "German/English", "Knows which direct marketer each plant uses."),
]

# provider slug, country, need, subject, status, opened_days_ago, due_in_days, closed_days_ago, interactions
REQUESTS = [
    ("entsoe", "EU", "day_ahead_price", "RESTful API access for GridLink account", "awaiting_reply", 12, -2, None, [
        (12, "email", "outbound", "Requested RESTful API access for our account, explained use case (price data for 4 bidding zones).", 7),
        (5, "email", "outbound", "Follow-up: no reply yet; asked for expected processing time.", -1)]),
    ("enedis", "FR", "production_metering", "Data Connect partner contract for producer load curves", "in_review", 34, 10, None, [
        (34, "portal", "outbound", "Submitted partner onboarding form describing producer use case and consent flow.", 7),
        (27, "email", "inbound", "Received contract draft and technical documentation link.", 5),
        (20, "meeting", "outbound", "Call with onboarding team: clarified producer (injection) curves are in scope; sandbox first.", 10),
        (6, "email", "outbound", "Returned signed contract; asked for production credentials timeline.", 2)]),
    ("enedis", "FR", "production_metering", "Data Connect sandbox credentials", "granted", 50, None, 41, [
        (50, "portal", "outbound", "Requested sandbox access.", 7), (41, "email", "inbound", "Sandbox credentials issued.", None)]),
    ("datadis", "ES", "production_metering", "Third-party access to production data for Aurelia & Helio plants", "granted", 61, None, 40, [
        (61, "portal", "outbound", "Registered as third party; asked owners to authorise their supply points.", 10),
        (52, "email", "outbound", "Sent owners a step-by-step authorisation guide (Spanish + English).", 7),
        (40, "portal", "inbound", "3 of 4 supply points authorised; Navarra Wind not yet requested by owner.", None)]),
    ("e-distribuzione", "IT", "production_metering", "Third-party API access for producer metering data", "stalled", 45, -15, None, [
        (45, "email", "outbound", "Asked whether a third-party API exists for producer metering data.", 14),
        (30, "email", "outbound", "Follow-up with plant list and expected data volumes.", 10),
        (18, "call", "outbound", "Routed to client-area support: no third-party API offering. Suggested owner client-area access.", 14),
        (8, "email", "outbound", "Asked Helio Invest to delegate client-area access for Puglia & Sicilia as fallback.", -4)]),
    ("mastr", "DE", "plant_master_data", "MaStR web-service user (API key)", "sent", 3, 11, None, [
        (3, "portal", "outbound", "Registered web-service user; awaiting key.", 7)]),
    ("de-direct-marketers", "DE", "production_metering", "Identify direct marketers for German plants", "awaiting_reply", 9, 5, None, [
        (9, "email", "outbound", "Asked Aurelia & Brightwater which direct marketer serves each plant and whether they can share 15-min data.", 3)]),
]

OPPORTUNITIES = [  # slug, title, country, need, cv, di, co, sr, te, ac, weeks, rationale
    ("e-distribuzione", "Italy plant metering (owner delegation / SCADA fallback)", "IT", "production_metering", 4, 5, 4, 4, 4, 5, 8,
     "Largest unmet plant demand; no API — process and relationship heavy."),
    ("entsoe", "ENTSO-E prices for FR, ES, IT, NL", None, "day_ahead_price", 5, 5, 4, 5, 2, 2, 1,
     "One token unlocks prices for every non-German plant; connector already built."),
    ("enedis", "France: switch to live Enedis Data Connect", "FR", "production_metering", 4, 5, 3, 4, 2, 3, 3,
     "Connector and consent flow proven on simulation; blocked only by contract."),
    ("de-direct-marketers", "Germany plant metering via direct marketers", "DE", "production_metering", 4, 5, 4, 5, 3, 3, 6,
     "Avoids integrating hundreds of DSOs one by one."),
    ("mastr", "MaStR plant master data (DE)", "DE", "plant_master_data", 2, 3, 2, 3, 1, 1, 1,
     "Cheap, public; validates customer-provided capacity data."),
    ("nl-dsos", "Netherlands plant metering", "NL", "production_metering", 2, 4, 2, 2, 4, 4, 6, "Single plant today — revisit when demand grows."),
]


def seed_workflow(db) -> None:
    now = datetime.now(UTC)
    by_slug = {p.slug: p for p in db.scalars(select(Provider))}
    for data in PROVIDERS:
        if data["slug"] not in by_slug:
            p = Provider(**data, last_investigated_at=CHECKED)
            db.add(p)
            by_slug[p.slug] = p
    db.flush()
    for slug, facts in FACTS.items():
        if not db.scalar(select(ProviderFact).where(ProviderFact.provider_id == by_slug[slug].id)):
            for cat, stmt, level, url in facts:
                db.add(ProviderFact(provider_id=by_slug[slug].id, category=cat, statement=stmt, evidence_level=level,
                                    source_url=url, checked_at=CHECKED))

    for c in COUNTRIES:
        if db.get(CountryProfile, c["country_code"]) is None:
            db.add(CountryProfile(**c, owner="Data Integration TPM"))
    db.flush()
    if not db.scalar(select(AccessRoute)):
        for cc, need, holder, slug, rtype, status, fb, effort, oa, blockers, ev, url, notes in ROUTES:
            db.add(AccessRoute(country_code=cc, data_need=need, holder_name=holder, provider_id=by_slug[slug].id if slug else None,
                               route_type=rtype, status=status, is_fallback=fb, effort=effort, requires_owner_authorisation=oa,
                               blockers=blockers, evidence_level=ev, source_url=url, notes=notes))
    if not db.scalar(select(PlaybookStep)):
        for cc, statuses in PLAYBOOK.items():
            for i, ((key, _, _), st) in enumerate(zip(PLAYBOOK_STEPS, statuses, strict=True)):
                db.add(PlaybookStep(country_code=cc, step_key=key, status=st,
                                    started_at=now - timedelta(days=60 - 4 * i) if st != "todo" else None,
                                    completed_at=now - timedelta(days=55 - 4 * i) if st == "done" else None))

    if not db.scalar(select(Contact)):
        for slug, role, lang, notes in CONTACTS:
            db.add(Contact(provider_id=by_slug[slug].id, role=role, language=lang, notes=notes, is_placeholder=True))
    db.flush()
    if not db.scalar(select(AccessRequest)):
        contacts = {c.provider_id: c.id for c in db.scalars(select(Contact))}
        for slug, cc, need, subject, status, opened, due, closed, interactions in REQUESTS:
            r = AccessRequest(provider_id=by_slug[slug].id, country_code=cc, data_need=need, subject=subject, status=status,
                              owner="Data Integration TPM", opened_at=now - timedelta(days=opened),
                              due_date=now + timedelta(days=due) if due is not None else None,
                              closed_at=now - timedelta(days=closed) if closed is not None else None)
            db.add(r)
            db.flush()
            for ago, channel, direction, summary, follow in interactions:
                db.add(Interaction(provider_id=r.provider_id, access_request_id=r.id, contact_id=contacts.get(r.provider_id),
                                   occurred_at=now - timedelta(days=ago), channel=channel, direction=direction, summary=summary,
                                   next_follow_up=(now - timedelta(days=ago) + timedelta(days=follow)) if follow is not None else None))
        it_fallback = db.scalar(select(AccessRoute).where(AccessRoute.country_code == "IT", AccessRoute.is_fallback.is_(True),
                                                          AccessRoute.data_need == "production_metering"))
        stalled = db.scalar(select(AccessRequest).where(AccessRequest.status == "stalled"))
        if it_fallback and stalled:
            stalled.fallback_route_id = it_fallback.id

    # customers, plants and authorisations (fictional)
    if not db.scalar(select(Customer)):
        cust = {}
        for c in CUSTOMERS:
            cust[c["key"]] = Customer(name=c["name"], segment=c["segment"], account_owner=c["account_owner"], is_fictional=True,
                                      notes="Fictional customer used to demonstrate the workflow.")
            db.add(cust[c["key"]])
        db.flush()
        methods = {"enedis": "Online consent in owner's Enedis account (OAuth)", "datadis": "Authorisation by supply-point holder",
                   "e-distribuzione": "Client-area delegation (requested)"}
        for p in PLANTS:
            needs = ["production_metering", "day_ahead_price"] + (["plant_master_data"] if p.country == "DE" else [])
            a = Asset(customer_id=cust[p.customer].id, name=p.name, country_code=p.country, bidding_zone=p.zone,
                      technology=p.technology, capacity_mw=p.capacity_mw, metering_point_id=p.metering_point_id,
                      dso_provider_id=by_slug[p.dso].id if p.dso else None, data_needs=needs, is_fictional=True,
                      commissioned_year=2012 + sum(map(ord, p.name)) % 11)
            db.add(a)
            db.flush()
            if p.dso:
                db.add(AssetAuthorisation(asset_id=a.id, provider_id=by_slug[p.dso].id, status=p.gridlink_auth, method=methods.get(p.dso),
                                          requested_at=now - timedelta(days=30) if p.gridlink_auth != "not_requested" else None,
                                          granted_at=now - timedelta(days=25) if p.gridlink_auth == "granted" else None))

    for name, ctype, slug in (("France DSO metering — SIMULATED (Enedis-like)", "fr_dso_sim", "enedis"),
                              ("Spain DSO metering — SIMULATED (Datadis-like)", "es_dso_sim", "datadis")):
        if not db.scalar(select(Connector).where(Connector.connector_name == name)):
            db.add(Connector(provider_id=by_slug[slug].id, connector_name=name, connector_type=ctype, data_origin="simulated",
                             config={"lookback_days": 7}, max_data_lag_minutes=2880, status="active"))

    if not db.scalar(select(IntegrationOpportunity).where(IntegrationOpportunity.data_need.is_not(None))):
        db.query(IntegrationOpportunity).delete()
        w = PrioritisationWeights()
        for slug, title, cc, need, cv, di, co, sr, te, ac, weeks, why in OPPORTUNITIES:
            o = IntegrationOpportunity(provider_id=by_slug[slug].id, title=title, country_code=cc, data_need=need, customer_value=cv,
                                       data_importance=di, commercial_opportunity=co, strategic_relevance=sr, technical_effort=te,
                                       access_complexity=ac, estimated_weeks=weeks, rationale=why)
            o.priority_score = priority_score(o, w)
            db.add(o)

    if not db.scalar(select(DataIssue).where(DataIssue.source == "manual")):
        smard = by_slug.get("smard")
        conn = db.scalar(select(Connector).where(Connector.connector_type == "smard_csv"))
        db.add(DataIssue(title="SMARD: most DE-LU quarter-hour prices for 20 Nov published as '-'", code="manual", source="manual",
                         status="investigating", severity="medium", provider_id=smard.id if smard else None,
                         connector_id=conn.id if conn else None, detected_at=datetime(2026, 11, 21, 18, tzinfo=UTC),
                         period_start=datetime(2026, 11, 20, 0, tzinfo=UTC), period_end=datetime(2026, 11, 21, 0, tzinfo=UTC),
                         affected_asset_ids=[], hypotheses="Our parsing (ruled out: raw CSV shows '-') · provider publication "
                         "delay · price-licensing change on SMARD (HEDWIG review) · 15-min MTU migration side effect",
                         root_cause="Provider-side: values absent in the raw CSV downloaded directly from SMARD.",
                         provider_contacted=False, evidence={"raw_check": "Downloaded CSV directly; rows contain '-'"},
                         customer_update="German revenue estimates for 20 Nov use gaps, not zeros. Cross-check with ENTSO-E once the token "
                                         "is available."))
    db.commit()
