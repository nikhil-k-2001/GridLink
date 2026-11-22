"""Deterministic synthetic production profiles: the same plant and timestamp always give the same value,
so re-syncing a window is idempotent, while different plants look different."""
import hashlib
import math
from datetime import datetime


def _seed(*parts: str) -> float:
    h = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def production_mw(metering_point_id: str, technology: str, capacity_mw: float, ts_utc: datetime) -> float:
    """Average power (MW) for the interval starting at ts_utc."""
    phase = _seed(metering_point_id) * 2 * math.pi
    hours = ts_utc.timestamp() / 3600
    if technology == "solar":
        # crude clear-sky curve around 12:00 UTC (+/- longitude is ignored), winter-scaled, with daily cloudiness
        hod = (ts_utc.hour + ts_utc.minute / 60) - 12.0
        day_len = 9.0
        if abs(hod) > day_len / 2:
            return 0.0
        clear = math.cos(math.pi * hod / day_len) ** 1.5
        cloud = 0.35 + 0.6 * _seed(metering_point_id, ts_utc.strftime("%Y-%m-%d"))
        return round(capacity_mw * 0.55 * clear * cloud, 4)
    # wind: smooth multi-day variation, capped by capacity
    v = 0.45 + 0.30 * math.sin(hours / 19 + phase) + 0.15 * math.sin(hours / 5.3 + 2 * phase) + 0.05 * math.sin(hours / 1.7)
    return round(max(0.0, min(1.0, v)) * capacity_mw * 0.95, 4)
