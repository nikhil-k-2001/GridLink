from datetime import UTC, datetime

import pandas as pd
import pytest

from app.normalisation.timestamps import TimestampError, duration_to_minutes, localise_series, to_utc
from app.normalisation.units import UnitConversionError, convert


class TestUnitConversion:
    def test_kw_to_mw(self):
        assert convert(1_250_000, "kW", "generation", 60).value == pytest.approx(1250)

    def test_energy_per_quarter_hour_to_average_power(self):
        c = convert(1159.0, "MWh", "generation", 15)
        assert c.value == pytest.approx(4636.0)
        assert "per 15min" in c.transformation

    def test_hourly_energy_equals_power(self):
        assert convert(1000, "MWh", "consumption", 60).value == pytest.approx(1000)

    def test_entsoe_maw_is_mw(self):
        c = convert(42, "MAW", "generation", 15)
        assert (c.value, c.unit, c.transformation) == (42, "MW", "none")

    def test_price_units(self):
        assert convert(0.25, "EUR/kWh", "day_ahead_price", 15).value == pytest.approx(250)
        assert convert(25, "ct/kWh", "day_ahead_price", 15).value == pytest.approx(250)
        assert convert(80, "€/MWh", "day_ahead_price", 15).unit == "EUR/MWh"

    def test_unknown_unit_is_rejected_not_guessed(self):
        with pytest.raises(UnitConversionError) as e:
            convert(1, "MVA", "generation", 15)
        assert e.value.code == "unexpected_unit"

    def test_power_unit_for_price_is_rejected(self):
        with pytest.raises(UnitConversionError):
            convert(1, "MW", "day_ahead_price", 15)


class TestTimestamps:
    def test_iso_z(self):
        assert to_utc("2026-11-20T10:00:00Z") == datetime(2026, 11, 20, 10, tzinfo=UTC)

    def test_offset(self):
        assert to_utc("2026-11-20T11:00:00+01:00") == datetime(2026, 11, 20, 10, tzinfo=UTC)

    def test_naive_requires_timezone(self):
        with pytest.raises(TimestampError):
            to_utc("2026-11-20 11:00")

    def test_naive_local_winter_and_summer(self):
        assert to_utc("2026-11-20 11:00", "Europe/Berlin") == datetime(2026, 11, 20, 10, tzinfo=UTC)
        assert to_utc("2026-07-01 12:00", "Europe/Berlin") == datetime(2026, 7, 1, 10, tzinfo=UTC)

    def test_ambiguous_fallback_raises_without_context(self):
        with pytest.raises(TimestampError, match="Ambiguous"):
            to_utc("2026-10-25 02:30", "Europe/Berlin")

    def test_nonexistent_spring_forward_raises(self):
        with pytest.raises(TimestampError, match="Non-existent"):
            to_utc("2026-03-29 02:30", "Europe/Berlin")

    def test_series_infers_dst_fallback_from_order(self):
        naive = pd.Series(pd.to_datetime(["2026-10-25 01:45", "2026-10-25 02:00", "2026-10-25 02:45",
                                          "2026-10-25 02:00", "2026-10-25 02:45", "2026-10-25 03:00"]))
        out = [t.strftime("%H:%M") for t in localise_series(naive, "Europe/Berlin")]
        assert out == ["23:45", "00:00", "00:45", "01:00", "01:45", "02:00"]

    def test_iso_durations(self):
        assert duration_to_minutes("PT15M") == 15
        assert duration_to_minutes("PT60M") == 60
        with pytest.raises(TimestampError):
            duration_to_minutes("PT7M")
