"""Unit conversion into GridLink's canonical units.

Canonical units
- generation / consumption / load metrics: MW (average power over the interval)
- prices: EUR/MWh

Energy-per-interval values (e.g. SMARD publishes MWh per quarter hour) are NOT the same quantity as
average power (e.g. ENTSO-E publishes MW). They are converted explicitly using the interval length and
the transformation is recorded on every record. Unknown units are rejected, never guessed.
"""
from dataclasses import dataclass

POWER_FACTORS_TO_MW = {"W": 1e-6, "kW": 1e-3, "MW": 1.0, "GW": 1e3, "MAW": 1.0}  # MAW = ENTSO-E code for MW
ENERGY_FACTORS_TO_MWH = {"Wh": 1e-6, "kWh": 1e-3, "MWh": 1.0, "GWh": 1e3}
PRICE_FACTORS_TO_EUR_MWH = {"EUR/MWh": 1.0, "€/MWh": 1.0, "EUR/kWh": 1000.0, "ct/kWh": 10.0, "EUR/MWH": 1.0}

CANONICAL_UNIT_BY_METRIC = {
    "generation": "MW",
    "consumption": "MW",
    "residual_load": "MW",
    "asset_production": "MW",
    "day_ahead_price": "EUR/MWh",
}


class UnitConversionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Converted:
    value: float
    unit: str
    transformation: str


def canonical_unit(metric_type: str) -> str:
    try:
        return CANONICAL_UNIT_BY_METRIC[metric_type]
    except KeyError as exc:
        raise UnitConversionError("unknown_metric", f"No canonical unit defined for metric '{metric_type}'") from exc


def normalise_unit_label(unit: str) -> str:
    u = unit.strip()
    return {"MWH": "MWh", "KWH": "kWh", "KW": "kW", "mw": "MW", "Mw": "MW"}.get(u, u)


def convert(value: float, source_unit: str, metric_type: str, interval_minutes: int) -> Converted:
    target = canonical_unit(metric_type)
    unit = normalise_unit_label(source_unit)

    if target == "MW":
        if unit in POWER_FACTORS_TO_MW:
            f = POWER_FACTORS_TO_MW[unit]
            return Converted(value * f, "MW", "none" if f == 1.0 else f"{unit}->MW x{f:g}")
        if unit in ENERGY_FACTORS_TO_MWH:
            if interval_minutes <= 0:
                raise UnitConversionError("invalid_interval", "Energy->power conversion needs a positive interval")
            hours = interval_minutes / 60.0
            f = ENERGY_FACTORS_TO_MWH[unit]
            return Converted(
                value * f / hours,
                "MW",
                f"{unit} per {interval_minutes}min -> average MW (x{f:g} / {hours:g}h)",
            )
        raise UnitConversionError("unexpected_unit", f"Unit '{source_unit}' cannot be converted to MW")

    if target == "EUR/MWh":
        if unit in PRICE_FACTORS_TO_EUR_MWH:
            f = PRICE_FACTORS_TO_EUR_MWH[unit]
            return Converted(value * f, "EUR/MWh", "none" if f == 1.0 else f"{unit}->EUR/MWh x{f:g}")
        raise UnitConversionError("unexpected_unit", f"Unit '{source_unit}' cannot be converted to EUR/MWh")

    raise UnitConversionError("unknown_metric", f"Unsupported canonical unit {target}")
