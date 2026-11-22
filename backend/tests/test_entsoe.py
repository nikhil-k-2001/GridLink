from datetime import UTC, datetime

import httpx
import pytest

from app.connectors.base import ConnectorError, FetchedPayload
from app.connectors.entsoe import EntsoeConnector, EntsoeFixtureConnector, redact_token
from app.services.sync import build_http_client
from tests.conftest import read_fixture

TOKEN = "11111111-2222-3333-4444-555555555555"


def parse(settings, name):
    c = EntsoeConnector({"area": "DE-LU"}, settings)
    return c, c.parse_response(FetchedPayload("u", {}, 200, "application/xml", read_fixture(f"entsoe/{name}"), {}), 0)


def test_a75_parses_generation_and_separates_pumped_storage_consumption(settings):
    c, res = parse(settings, "a75_small.xml")
    keys = {r.series_key for r in res.records}
    assert keys == {"A75::B16::in", "A75::B10::out"}
    norm = c.normalise_data(res.records, provider_id=1)
    out = [r for r in norm.records if r.series_key == "A75::B10::out"]
    assert out[0].metric_type == "consumption" and out[0].energy_source == "pumped_storage"


def test_a01_missing_position_is_not_invented(settings):
    _, res = parse(settings, "a75_small.xml")
    solar = sorted((r for r in res.records if r.series_key == "A75::B16::in"), key=lambda r: r.timestamp_utc)
    assert [r.timestamp_utc.minute for r in solar] == [0, 15, 45]  # position 3 omitted -> missing interval


def test_non_numeric_quantity_becomes_rejection(settings):
    c, res = parse(settings, "a75_small.xml")
    norm = c.normalise_data(res.records, provider_id=1)
    assert norm.rejected == 1 and norm.issues[0].code == "malformed_value"


def test_a03_curve_carries_previous_value_forward(settings):
    c, res = parse(settings, "a44_a03.xml")
    vals = [(r.timestamp_utc, r.value) for r in sorted(res.records, key=lambda r: r.timestamp_utc)]
    assert [v for _, v in vals] == [-5.5, -5.5, 80.1, 80.1]
    assert vals[0][0] == datetime(2026, 11, 20, 23, 0, tzinfo=UTC)
    norm = c.normalise_data(res.records, provider_id=1)
    assert norm.records[0].unit == "EUR/MWh" and norm.records[0].value == -5.5  # negative prices are valid


def test_acknowledgement_no_data_is_a_warning(settings):
    _, res = parse(settings, "ack_no_data.xml")
    assert res.records == [] and res.issues[0].code == "no_data" and res.issues[0].severity == "warning"


def test_malformed_xml_raises(settings):
    with pytest.raises(ConnectorError) as e:
        parse(settings, "malformed.xml")
    assert e.value.code == "malformed_xml"


class TestAuthentication:
    def test_missing_token(self, settings):
        auth = EntsoeConnector({}, settings).authenticate()
        assert not auth.ok and auth.code == "missing_token"

    def test_bad_format(self, settings):
        settings.entsoe_api_token = "bad token!"
        assert EntsoeConnector({}, settings).authenticate().code == "invalid_token_format"

    def test_valid_token_present(self, settings):
        settings.entsoe_api_token = TOKEN
        assert EntsoeConnector({}, settings).authenticate().ok

    def test_http_401_maps_to_invalid_token(self, settings):
        settings.entsoe_api_token = TOKEN
        http = build_http_client("entsoe_api", settings, httpx.MockTransport(lambda r: httpx.Response(401, text="Unauthorized")),
                                 sleep=lambda s: None)
        c = EntsoeConnector({"datasets": ["generation"]}, settings, http)
        with pytest.raises(ConnectorError) as e:
            c.fetch_data(datetime(2026, 11, 20, tzinfo=UTC), datetime(2026, 11, 21, tzinfo=UTC))
        assert e.value.code == "invalid_token" and e.value.http_status == 401

    def test_token_is_sent_and_redacted(self, settings):
        settings.entsoe_api_token = TOKEN
        seen = {}

        def handler(request):
            seen["token"] = request.url.params.get("securityToken")
            seen["doc"] = request.url.params.get("documentType")
            return httpx.Response(200, content=read_fixture("entsoe/a75_small.xml"))

        http = build_http_client("entsoe_api", settings, httpx.MockTransport(handler), sleep=lambda s: None)
        payloads = EntsoeConnector({"datasets": ["generation"]}, settings, http).fetch_data(
            datetime(2026, 11, 20, tzinfo=UTC), datetime(2026, 11, 21, tzinfo=UTC))
        assert seen == {"token": TOKEN, "doc": "A75"}
        assert TOKEN not in payloads[0].request_url and "REDACTED" in payloads[0].request_url
        assert redact_token(f"x?a=1&securityToken={TOKEN}&b=2") == "x?a=1&securityToken=REDACTED&b=2"

    def test_400_no_matching_data_is_not_a_failure(self, settings):
        settings.entsoe_api_token = TOKEN
        http = build_http_client("entsoe_api", settings, httpx.MockTransport(
            lambda r: httpx.Response(400, content=read_fixture("entsoe/ack_no_data.xml"))), sleep=lambda s: None)
        payloads = EntsoeConnector({"datasets": ["generation"]}, settings, http).fetch_data(
            datetime(2026, 11, 20, tzinfo=UTC), datetime(2026, 11, 21, tzinfo=UTC))
        assert len(payloads) == 1


def test_simulated_fixture_connector_is_labelled(settings):
    c = EntsoeFixtureConnector({}, settings)
    assert c.data_origin == "simulated" and c.authenticate().method == "fixture"
    payloads = c.fetch_data(datetime(2026, 11, 13, tzinfo=UTC), datetime(2026, 11, 21, tzinfo=UTC))
    assert all(p.request_url.startswith("fixture://") for p in payloads)
    assert all(b"SIMULATED" in p.body for p in payloads)
