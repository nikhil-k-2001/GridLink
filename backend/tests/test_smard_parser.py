import io
import zipfile
from datetime import UTC, datetime

import pytest

from app.connectors.base import ConnectorError, FetchedPayload
from app.connectors.smard import SmardConnector
from tests.conftest import read_fixture


def parse(settings, body: bytes, category="generation"):
    c = SmardConnector({}, settings)
    return c, c.parse_response(FetchedPayload("u", {}, 200, "text/csv", body, {"category": category}), 0)


def test_english_csv_parses_thousands_separators_and_local_time(settings):
    _, res = parse(settings, read_fixture("smard/generation_en.csv"))
    wind = [r for r in res.records if r.series_key == "generation::Wind onshore"]
    assert wind[0].value == pytest.approx(3540.87)
    assert wind[0].timestamp_utc == datetime(2026, 11, 20, 18, 0, tzinfo=UTC)  # 19:00 CET
    assert wind[0].unit == "MWh"
    assert wind[0].interval_minutes == 15


def test_german_csv_parses_decimal_comma_and_maps_to_same_series(settings):
    _, en = parse(settings, read_fixture("smard/generation_en.csv"))
    _, de = parse(settings, read_fixture("smard/generation_de.csv"))
    de_wind = [r for r in de.records if r.series_key == "generation::Wind onshore"]
    assert de_wind[0].value == pytest.approx(3540.87)
    # identical source ids => idempotent across CSV languages
    assert de_wind[0].source_record_id == next(r for r in en.records if r.series_key == de_wind[0].series_key).source_record_id


def test_dash_is_missing_not_zero(settings):
    _, res = parse(settings, read_fixture("smard/generation_en.csv"))
    third = [r for r in res.records if r.series_key == "generation::Wind onshore"][2]
    assert third.raw_value == "-" and third.value is None and third.parse_error is None
    pv = [r for r in res.records if r.series_key == "generation::Photovoltaics"]
    assert pv[0].value == 0.0  # a real zero stays zero


def test_malformed_value_is_flagged_not_converted(settings):
    _, res = parse(settings, read_fixture("smard/generation_en.csv"))
    bad = [r for r in res.records if r.raw_value == "n/a"]
    assert len(bad) == 1 and bad[0].value is None and "not a valid number" in bad[0].parse_error


def test_dst_fallback_rows_get_distinct_utc_timestamps(settings):
    _, res = parse(settings, read_fixture("smard/dst_fallback_en.csv"))
    ts = [r.timestamp_utc for r in res.records]
    assert len(set(ts)) == len(ts) == 10
    assert ts == sorted(ts)
    assert ts[1] == datetime(2026, 10, 25, 0, 0, tzinfo=UTC)  # first 02:00 = CEST
    assert ts[5] == datetime(2026, 10, 25, 1, 0, tzinfo=UTC)  # second 02:00 = CET


def test_no_data_marker_is_reported(settings):
    _, res = parse(settings, read_fixture("smard/no_data.csv"), "day_ahead_price")
    assert res.records == []
    assert res.issues[0].code == "no_data"


def test_unexpected_columns_raise(settings):
    with pytest.raises(ConnectorError) as e:
        parse(settings, read_fixture("smard/bad_columns.csv"))
    assert e.value.code == "unexpected_columns"


def test_zip_payload_is_unpacked(settings):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Realisierte_Erzeugung.csv", read_fixture("smard/generation_en.csv"))
    _, res = parse(settings, buf.getvalue())
    assert len(res.records) == 12


def test_unmapped_column_is_reported_by_normaliser(settings):
    body = "﻿Start date;End date;Fusion [MWh] Original resolutions\nNov 20, 2026 7:00 PM;x;5.00\n".encode()
    c, res = parse(settings, body)
    norm = c.normalise_data(res.records, provider_id=1)
    assert norm.records == []
    assert norm.unmapped_series == {"generation::Fusion": 1}
    assert norm.issues[0].code == "unmapped_series"
