from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.base import SourceRecord
from app.normalisation.engine import NormaliseResult, normalise_records
from app.normalisation.timestamps import to_utc
from app.quality.engine import validate_batch

MAPPING = {
    "series": {
        "a::solar": {"dataset_key": "a_solar", "metric_type": "generation", "energy_source": "solar", "unit": "MW", "frequency": "PT60M"},
        "b::production": {"dataset_key": "b_solar", "metric_type": "generation", "energy_source": "solar", "unit": "kW", "frequency": "PT60M"},
        "p::price": {"dataset_key": "p", "metric_type": "day_ahead_price", "energy_source": "all", "unit": "EUR/MWh", "frequency": "PT60M"},
        "c::load": {"dataset_key": "c", "metric_type": "consumption", "energy_source": "total", "unit": "MW", "frequency": "PT15M"},
    },
    "validation": {"non_negative_metrics": ["generation", "consumption"], "max_mw": {"generation": 90000}, "price_range": [-500, 5000]},
}
NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


def rec(series, ts, value, unit="MW", interval=60, rid=None, country="DE", raw=None):
    return SourceRecord(series_key=series, timestamp_utc=ts, timestamp_raw=str(ts), interval_minutes=interval,
                        raw_value=raw if raw is not None else (None if value is None else str(value)), value=value, unit=unit,
                        country_code=country, bidding_zone=None, source_record_id=rid or f"{series}:{ts.isoformat()}")


def test_provider_a_and_b_examples_normalise_to_the_same_record():
    a = rec("a::solar", to_utc("2026-11-20T10:00:00Z"), 1250, "MW")
    b = rec("b::production", to_utc("2026-11-20 11:00", "Europe/Berlin"), 1_250_000, "kW")
    out = normalise_records([a, b], MAPPING, provider_id=1, data_origin="real")
    ra, rb = out.records
    assert ra.timestamp_utc == rb.timestamp_utc == datetime(2026, 11, 20, 10, tzinfo=UTC)
    assert ra.value == rb.value == 1250 and ra.unit == rb.unit == "MW"
    assert rb.original_value == "1250000" and rb.original_unit == "kW" and "kW->MW" in rb.transformation


def test_unexpected_unit_rejected_and_never_silently_converted():
    out = normalise_records([rec("a::solar", NOW, 5, "GW")], MAPPING, provider_id=1, data_origin="real")
    assert out.records == [] and out.rejected == 1 and out.issues[0].code == "unexpected_unit"


def test_null_is_kept_as_null_with_provenance():
    out = normalise_records([rec("a::solar", NOW, None, raw="-")], MAPPING, provider_id=1, data_origin="real")
    assert out.records[0].value is None and out.records[0].original_value == "-"


def test_schema_violation_invalid_country():
    out = normalise_records([rec("a::solar", NOW, 1, country="Germany")], MAPPING, provider_id=1, data_origin="real")
    assert out.rejected == 1 and out.issues[0].code == "schema_violation"


def _validate(records, start, end, **kw):
    norm = normalise_records(records, MAPPING, provider_id=1, data_origin="real")
    return validate_batch(norm, MAPPING, start, end, 0, now=NOW, **kw)


def test_duplicates_detected_and_conflicts_flagged():
    t = datetime(2026, 11, 20, 0, tzinfo=UTC)
    v = _validate([rec("a::solar", t, 1), rec("a::solar", t, 1), rec("a::solar", t, 2)], t, t + timedelta(hours=1))
    assert v.duplicate_count == 2 and v.conflicting_duplicates == 1 and len(v.valid) == 1


def test_missing_intervals_and_completeness():
    t0 = datetime(2026, 11, 20, 0, tzinfo=UTC)
    recs = [rec("c::load", t0 + timedelta(minutes=15 * i), 50000, interval=15) for i in range(8) if i not in (3, 4)]
    v = _validate(recs, t0, t0 + timedelta(hours=2))
    s = v.series[0]
    assert (s.expected, s.present, s.completeness) == (8, 6, 75.0)
    assert s.missing_periods == [{"start": "2026-11-20T00:45:00+00:00", "end": "2026-11-20T01:15:00+00:00", "intervals": 2}]
    assert v.overall_status == "fail"


def test_null_values_count_as_missing():
    t0 = datetime(2026, 11, 20, 0, tzinfo=UTC)
    v = _validate([rec("a::solar", t0, 1), rec("a::solar", t0 + timedelta(hours=1), None)], t0, t0 + timedelta(hours=2))
    assert v.null_count == 1 and v.series[0].completeness == 50.0


def test_expected_series_without_data_is_reported():
    t0 = datetime(2026, 11, 20, 0, tzinfo=UTC)
    v = _validate([rec("a::solar", t0, 1)], t0, t0 + timedelta(hours=1), expected_series=["a::solar", "c::load"])
    assert any(i.code == "missing_series" for i in v.issues)
    assert v.checks["completeness"]["missing_series"] == ["c::load"]


@pytest.mark.parametrize("series,value,code", [
    ("a::solar", -10, "negative_value"),
    ("a::solar", 150000, "out_of_range"),
    ("p::price", 9000, "out_of_range"),
])
def test_validity_rules(series, value, code):
    t0 = datetime(2026, 11, 20, 0, tzinfo=UTC)
    v = _validate([rec(series, t0, value, unit="EUR/MWh" if series.startswith("p") else "MW")], t0, t0 + timedelta(hours=1))
    assert v.invalid_count == 1 and v.checks["validity"]["by_rule"] == {code: 1}


def test_negative_price_is_valid():
    t0 = datetime(2026, 11, 20, 0, tzinfo=UTC)
    v = _validate([rec("p::price", t0, -80, unit="EUR/MWh")], t0, t0 + timedelta(hours=1))
    assert v.invalid_count == 0


def test_future_and_misaligned_timestamps_are_invalid():
    future = NOW + timedelta(days=1)
    v = _validate([rec("a::solar", future, 1), rec("a::solar", datetime(2026, 11, 20, 0, 7, tzinfo=UTC), 1)],
                  NOW - timedelta(days=2), NOW)
    assert v.checks["validity"]["by_rule"] == {"future_timestamp": 1, "misaligned_timestamp": 1}


def test_invalid_country_code_is_consistency_failure():
    from app.normalisation.engine import NormalisedRecord

    r = NormalisedRecord(provider_id=1, dataset_key="a_solar", series_key="a::solar", timestamp_utc=NOW - timedelta(hours=2),
                         interval_minutes=60, country_code="ZZ", energy_source="solar", metric_type="generation", value=1,
                         unit="MW", original_value="1", original_unit="MW", transformation="none", source_record_id="x",
                         data_origin="real")
    v = validate_batch(NormaliseResult(records=[r]), MAPPING, NOW - timedelta(hours=3), NOW, 0, now=NOW)
    assert v.checks["consistency"]["invalid_country_codes"] == 1


def test_freshness_statuses():
    t_old = NOW - timedelta(hours=10)
    v = _validate([rec("a::solar", t_old, 1)], t_old, NOW, lag_by_series={"a::solar": 180})
    assert v.series[0].freshness_status == "stale"
    v = _validate([rec("a::solar", NOW - timedelta(hours=4), 1)], NOW - timedelta(hours=5), NOW, lag_by_series={"a::solar": 120})
    assert v.series[0].freshness_status == "delayed"
    v = _validate([rec("a::solar", NOW - timedelta(hours=1), 1)], NOW - timedelta(hours=2), NOW, lag_by_series={"a::solar": 120})
    assert v.series[0].freshness_status == "fresh"
