import json
from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.base import ConnectorError, FetchedPayload
from app.connectors.energinet import EnerginetConnector
from app.connectors.entsoe import EntsoeConnector
from app.connectors.http import RetryingClient
from app.services.sync import build_http_client
from tests.conftest import read_fixture

RT = {"records": [{"Minutes1UTC": "2026-11-22T10:00:00", "SolarPower": 1059.87, "OffshoreWindPower": 2337.53, "OnshoreWindPower": None},
                  {"Minutes1UTC": "2026-11-22T10:01:00", "SolarPower": 1010.72, "OffshoreWindPower": 2311.21, "OnshoreWindPower": 1107.4}]}
PRICES = {"records": [{"TimeUTC": "2026-11-22T22:45:00", "PriceArea": "DE", "DayAheadPriceEUR": 181.19},
                      {"TimeUTC": "2026-11-22T22:45:00", "PriceArea": "DK1", "DayAheadPriceEUR": 181.19},
                      {"TimeUTC": "2026-11-22T22:45:00", "PriceArea": "DK2", "DayAheadPriceEUR": -3.5}]}


def parse(settings, body, dataset):
    c = EnerginetConnector({}, settings)
    return c, c.parse_response(FetchedPayload("u", {}, 200, "application/json", json.dumps(body).encode(), {"dataset": dataset}), 0)


def test_realtime_minutes_are_utc_mw_and_nulls_stay_null(settings):
    c, res = parse(settings, RT, "realtime")
    solar = [r for r in res.records if r.series_key == "realtime::SolarPower"]
    assert solar[0].timestamp_utc == datetime(2026, 11, 22, 10, 0, tzinfo=UTC) and solar[0].interval_minutes == 1
    onshore = [r for r in res.records if r.series_key == "realtime::OnshoreWindPower"]
    assert onshore[0].value is None and onshore[0].parse_error is None
    norm = c.normalise_data(res.records, 1)
    assert norm.rejected == 0 and {r.energy_source for r in norm.records} == {"solar", "wind_onshore", "wind_offshore"}


def test_price_areas_map_to_countries_and_zones(settings):
    c, res = parse(settings, PRICES, "day_ahead_price")
    by = {r.series_key: r for r in res.records}
    assert by["price::DE"].country_code == "DE" and by["price::DE"].bidding_zone == "DE-LU"
    assert by["price::DK1"].country_code == "DK" and by["price::DK2"].value == -3.5  # negative prices are valid
    assert all(r.unit == "EUR/MWh" for r in c.normalise_data(res.records, 1).records)


def test_missing_records_key_is_a_schema_error(settings):
    with pytest.raises(ConnectorError) as e:
        parse(settings, {"error": "x"}, "realtime")
    assert e.value.code == "unexpected_schema"


def test_fetch_requests_utc_window_columns_and_price_filter(settings):
    seen = []

    def handler(req):
        seen.append(req.url)
        return httpx.Response(200, json=RT if "PowerSystemRightNow" in str(req.url) else PRICES)

    c = EnerginetConnector({}, settings, build_http_client("energinet_api", settings, httpx.MockTransport(handler), sleep=lambda s: None))
    c.fetch_data(datetime(2026, 11, 22, 10, tzinfo=UTC), datetime(2026, 11, 22, 12, tzinfo=UTC))
    rt, pr = seen
    assert rt.params["timezone"] == "utc" and rt.params["start"] == "2026-11-22T10:00" and "SolarPower" in rt.params["columns"]
    assert json.loads(pr.params["filter"]) == {"PriceArea": ["DK1", "DK2", "DE"]}
    assert pr.params["end"] == "2026-11-24T00:00"  # day-ahead: look 36 h ahead


def test_rate_limit_wait_read_from_body():
    calls = iter([httpx.Response(429, json={"statusCode": 429, "message": "Rate limit is exceeded. Try again in 36 seconds."}),
                  httpx.Response(200)])
    sleeps = []
    c = RetryingClient(httpx.Client(transport=httpx.MockTransport(lambda r: next(calls))), max_retries=2, backoff_max=60, sleep=sleeps.append)
    assert c.request("GET", "https://x").status_code == 200 and sleeps == [36.0]


class TestEntsoeZones:
    def test_one_request_per_zone_with_eic_codes(self, settings):
        settings.entsoe_api_token = "11111111-2222-3333-4444-555555555555"
        seen = []

        def handler(req):
            seen.append((req.url.params["in_Domain"], req.url.params["documentType"]))
            return httpx.Response(200, content=read_fixture("entsoe/a44_a03.xml"))

        c = EntsoeConnector({"areas": ["FR", "IT-SUD"], "datasets": ["day_ahead_price"]}, settings,
                            build_http_client("entsoe_api", settings, httpx.MockTransport(handler), sleep=lambda s: None))
        payloads = c.fetch_data(datetime(2026, 11, 20, tzinfo=UTC), datetime(2026, 11, 21, tzinfo=UTC))
        assert seen == [("10YFR-RTE------C", "A44"), ("10Y1001A1001A788", "A44")]
        recs = [r for i, p in enumerate(payloads) for r in c.parse_response(p, i).records]
        assert {(r.series_key, r.bidding_zone, r.country_code) for r in recs} == {
            ("A44::price@FR", "FR", "FR"), ("A44::price@IT-SUD", "IT-SUD", "IT")}
        norm = c.normalise_data(recs, 1)
        assert norm.rejected == 0 and len({r.dataset_key for r in norm.records}) == 2

    def test_unknown_zone_is_rejected(self, settings):
        with pytest.raises(ConnectorError) as e:
            EntsoeConnector({"areas": ["XX"]}, settings)
        assert e.value.code == "unknown_area"

    def test_de_lu_keeps_original_series_keys(self, settings):
        c = EntsoeConnector({}, settings)
        assert c.areas == ["DE-LU"] and "A44::price" in c.mapping["series"] and not any("@" in k for k in c.mapping["series"])
