"""Two SIMULATED DSO metering platforms, implemented as a plain request handler.

They are *modelled loosely* on publicly described behaviour of French and Spanish DSO data platforms
(consent per metering point, J+1 availability, local time conventions). Paths, field names and error
codes are ILLUSTRATIVE, not copies of any real API. They exist to exercise the connector, quality and
issue workflow realistically:

fr-dso  30-minute average power in W; timestamps are interval END in Europe/Paris local time;
        bearer token; 403 when the metering point has no (or revoked) consent; max 7 days per call;
        every 6th call is rate-limited (429 + Retry-After).
es-dso  hourly energy in kWh; hour-ENDING labels "01:00".."24:00" in Europe/Madrid local time;
        some readings flagged "Estimada" (estimated); one plant returns duplicate rows.

The same handler is used in-process by the connectors (httpx.MockTransport) and over HTTP under
/simulated/... so the API test bench can call it like any external API.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.simulated.profiles import production_mw
from app.simulated.world import PLANTS_BY_MP

SIM_TOKENS = {"fr-dso": "sim-fr-oauth-token", "es-dso": "sim-es-token"}
_calls = {"fr-dso": 0, "es-dso": 0}
PARIS, MADRID = ZoneInfo("Europe/Paris"), ZoneInfo("Europe/Madrid")


def _json(status: int, body, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body).encode(), headers={"content-type": "application/json", **(headers or {})})


def _authorised(request: httpx.Request, platform: str) -> bool:
    return request.headers.get("authorization", "") == f"Bearer {SIM_TOKENS[platform]}"


def _available_until(tz: ZoneInfo, now: datetime) -> datetime:
    """Data is published J+1: complete up to the start of today (local)."""
    local_midnight = datetime.combine(now.astimezone(tz).date(), time(0), tzinfo=tz)
    return local_midnight.astimezone(UTC)


def handle(request: httpx.Request, now: datetime | None = None) -> httpx.Response:
    now = now or datetime.now(UTC)
    path = request.url.path.removeprefix("/simulated")
    if path.startswith("/fr-dso/v5/metering_data/production_load_curve"):
        return _fr(request, now)
    if path.startswith("/es-dso/api-private/api/get-production-data"):
        return _es(request, now)
    return _json(404, {"error": "not_found", "message": f"No simulated endpoint at {path}"})


# --------------------------------------------------------------------------------------------------
def _fr(request: httpx.Request, now: datetime) -> httpx.Response:
    if not _authorised(request, "fr-dso"):
        return _json(401, {"error": "invalid_token", "error_description": "Bearer token missing or invalid"})
    _calls["fr-dso"] += 1
    if _calls["fr-dso"] % 6 == 0:
        return _json(429, {"error": "too_many_requests"}, {"Retry-After": "1"})
    q = request.url.params
    mp, start_s, end_s = q.get("usage_point_id"), q.get("start"), q.get("end")
    if not (mp and start_s and end_s):
        return _json(400, {"error": "invalid_request", "error_description": "usage_point_id, start, end are required"})
    try:
        start_d, end_d = date.fromisoformat(start_s), date.fromisoformat(end_s)
    except ValueError:
        return _json(400, {"error": "invalid_request", "error_description": "dates must be YYYY-MM-DD"})
    if (end_d - start_d).days > 7 or end_d <= start_d:
        return _json(400, {"error": "invalid_request", "error_description": "end must be after start and at most 7 days later"})
    plant = PLANTS_BY_MP.get(mp)
    if plant is None or plant.dso != "enedis":
        return _json(404, {"error": "usage_point_not_found"})
    if plant.dso_consent != "granted":
        return _json(403, {"error": "SIM-CONSENT-403", "error_description": f"No valid consent for usage point {mp} ({plant.dso_consent})"})

    t = datetime.combine(start_d, time(0), tzinfo=PARIS).astimezone(UTC)
    stop = min(datetime.combine(end_d, time(0), tzinfo=PARIS).astimezone(UTC), _available_until(PARIS, now))
    gap_start = _available_until(PARIS, now) - timedelta(days=3)
    readings = []
    while t < stop:
        if not (plant.fault == "gap_36h" and gap_start <= t < gap_start + timedelta(hours=36)):
            watts = production_mw(mp, plant.technology, plant.capacity_mw, t) * 1_000_000
            end_local = (t + timedelta(minutes=30)).astimezone(PARIS)
            readings.append({"value": str(int(round(watts))), "date": end_local.strftime("%Y-%m-%d %H:%M:%S"),
                             "interval_length": "PT30M", "measure_type": "B"})
        t += timedelta(minutes=30)
    return _json(200, {"meter_reading": {
        "usage_point_id": mp, "start": start_s, "end": end_s, "quality": "BRUT",
        "reading_type": {"measurement_kind": "power", "unit": "W", "aggregate": "average"},
        "interval_reading": readings}})


# --------------------------------------------------------------------------------------------------
def _es(request: httpx.Request, now: datetime) -> httpx.Response:
    if not _authorised(request, "es-dso"):
        return _json(401, {"status": 401, "message": "Unauthorized"})
    _calls["es-dso"] += 1
    q = request.url.params
    cups, start_s, end_s = q.get("cups"), q.get("startDate"), q.get("endDate")
    if not (cups and start_s and end_s):
        return _json(400, {"status": 400, "message": "cups, startDate and endDate (YYYY/MM/DD) are required"})
    try:
        start_d = datetime.strptime(start_s, "%Y/%m/%d").date()
        end_d = datetime.strptime(end_s, "%Y/%m/%d").date()
    except ValueError:
        return _json(400, {"status": 400, "message": "Dates must be YYYY/MM/DD"})
    plant = PLANTS_BY_MP.get(cups)
    if plant is None or plant.dso != "datadis":
        return _json(404, {"status": 404, "message": "CUPS not found"})
    if plant.dso_consent != "granted":
        return _json(403, {"status": 403, "message": f"Not authorised for CUPS {cups} (simulated)"})

    t = datetime.combine(start_d, time(0), tzinfo=MADRID).astimezone(UTC)
    stop = min(datetime.combine(end_d + timedelta(days=1), time(0), tzinfo=MADRID).astimezone(UTC), _available_until(MADRID, now))
    rows = []
    while t < stop:
        end_local = (t + timedelta(hours=1)).astimezone(MADRID)
        start_local_date = t.astimezone(MADRID).date()
        label = "24:00" if end_local.hour == 0 else end_local.strftime("%H:00")
        day = start_local_date if label == "24:00" else end_local.date()
        mw = sum(production_mw(cups, plant.technology, plant.capacity_mw, t + timedelta(minutes=15 * k)) for k in range(4)) / 4
        estimated = plant.fault == "estimated" and t.hour in (9, 10, 11) and t.day % 2 == 0
        row = {"cups": cups, "date": day.strftime("%Y/%m/%d"), "time": label,
               "generationEnergyKWh": round(mw * 1000, 3), "obtainMethod": "Estimada" if estimated else "Real"}
        rows.append(row)
        if plant.fault == "duplicates" and t.hour == 12:
            rows.append(dict(row))
        t += timedelta(hours=1)
    return _json(200, rows)


def transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: handle(req))
