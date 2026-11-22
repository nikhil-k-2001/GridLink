"""The fictional portfolio GridLink is demonstrated on.

Customers, plants, metering-point IDs and the consent state held by the simulated DSO platforms are
INVENTED. They exist so the market-connections workflow (demand -> access -> authorisation -> data ->
issues) can be shown end to end without real customer data. Everything derived from them is stored with
data_origin = "simulated" and is labelled in the UI.

Data holder state ("dso_consent") deliberately differs from GridLink's own records in places, because in
real life the data holder is the source of truth and the two drift apart.
"""
from dataclasses import dataclass

CUSTOMERS = [
    {"key": "aurelia", "name": "Aurelia Wind Partners", "segment": "Asset manager (wind)", "account_owner": "Sales – DACH & France"},
    {"key": "helio", "name": "Helio Invest Fund II", "segment": "Infrastructure fund (solar)", "account_owner": "Sales – Southern Europe"},
    {"key": "brightwater", "name": "Brightwater Energy", "segment": "Independent power producer", "account_owner": "Sales – Benelux & Italy"},
]


@dataclass(frozen=True)
class SimPlant:
    customer: str
    name: str
    country: str
    zone: str
    technology: str
    capacity_mw: float
    metering_point_id: str
    dso: str | None  # provider slug of the data holder
    dso_consent: str  # what the (simulated) data holder records: granted | revoked | none
    gridlink_auth: str  # what GridLink believes: granted | requested | not_requested
    fault: str | None = None  # injected data problem


PLANTS = [
    # France – simulated Enedis-like consent-based API, 30-min average power in W, interval-END local timestamps
    SimPlant("aurelia", "Plaine de Beauce Wind", "FR", "FR", "wind_onshore", 24.0, "99000000000101", "enedis", "granted", "granted"),
    SimPlant("aurelia", "Côte d'Opale Wind", "FR", "FR", "wind_onshore", 18.0, "99000000000102", "enedis", "granted", "granted", "gap_36h"),
    SimPlant("helio", "Provence Solar I", "FR", "FR", "solar", 12.0, "99000000000103", "enedis", "granted", "granted"),
    SimPlant("helio", "Provence Solar II", "FR", "FR", "solar", 9.5, "99000000000104", "enedis", "revoked", "granted"),
    SimPlant("helio", "Aquitaine Solar", "FR", "FR", "solar", 15.0, "99000000000105", "enedis", "none", "requested"),
    # Spain – simulated Datadis-like API, hourly kWh, hour-ENDING "01:00".."24:00" local time
    SimPlant("aurelia", "Sierra de Gredos Wind", "ES", "ES", "wind_onshore", 30.0, "ES0000SIM0000000201ZZ", "datadis", "granted", "granted"),
    SimPlant("helio", "Extremadura Solar", "ES", "ES", "solar", 40.0, "ES0000SIM0000000202ZZ", "datadis", "granted", "granted", "estimated"),
    SimPlant("helio", "Murcia Solar", "ES", "ES", "solar", 22.0, "ES0000SIM0000000203ZZ", "datadis", "granted", "granted", "duplicates"),
    SimPlant("aurelia", "Navarra Wind", "ES", "ES", "wind_onshore", 26.0, "ES0000SIM0000000204ZZ", "datadis", "none", "not_requested"),
    # Germany – no plant-level connector yet (≈860 DSOs); market prices come from real SMARD data
    SimPlant("aurelia", "Uckermark Wind", "DE", "DE-LU", "wind_onshore", 21.0, "SIM-DE-MALO-301", None, "none", "not_requested"),
    SimPlant("brightwater", "Lausitz Solar", "DE", "DE-LU", "solar", 35.0, "SIM-DE-MALO-302", None, "none", "not_requested"),
    SimPlant("brightwater", "Emsland Wind", "DE", "DE-LU", "wind_onshore", 16.8, "SIM-DE-MALO-303", None, "none", "not_requested"),
    # Italy – DSO portal only (no API confirmed): blocked on a manual-export route
    SimPlant("helio", "Puglia Solar", "IT", "IT-SUD", "solar", 28.0, "IT-SIM-POD-401", "e-distribuzione", "none", "requested"),
    SimPlant("helio", "Sicilia Solar", "IT", "IT-SICI", "solar", 19.0, "IT-SIM-POD-402", "e-distribuzione", "none", "requested"),
    SimPlant("brightwater", "Campania Wind", "IT", "IT-SUD", "wind_onshore", 33.0, "IT-SIM-POD-403", "e-distribuzione", "none", "not_requested"),
    # Netherlands – demand exists, country not started
    SimPlant("brightwater", "Flevoland Wind", "NL", "NL", "wind_onshore", 12.0, "SIM-NL-EAN-501", None, "none", "not_requested"),
]

PLANTS_BY_MP = {p.metering_point_id: p for p in PLANTS}
