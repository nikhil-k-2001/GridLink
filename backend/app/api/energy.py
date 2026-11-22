from datetime import UTC, datetime, timedelta
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DB, Paging, paginate
from app.models import Connector, Dataset, EnergyRecord, Provider
from app.schemas import EnergyRecordOut, Page

router = APIRouter(tags=["energy-records"])
MAX_RANGE_DAYS = 92
BUCKET_FREQ = {"15min": "15min", "hour": "1h", "day": "1D"}
BUCKET_MINUTES = {"15min": 15, "hour": 60, "day": 1440}


def _range(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=7)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "start/end must include a timezone offset")
    if start >= end:
        raise HTTPException(422, "start must be before end")
    if end - start > timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(422, f"Maximum range is {MAX_RANGE_DAYS} days")
    return start, end


@router.get("/energy-records", response_model=Page[EnergyRecordOut])
def list_records(
    db: DB, paging: Paging,
    country: str | None = None, provider_id: int | None = None, metric_type: str | None = None,
    energy_source: str | None = None, dataset_id: int | None = None,
    start: datetime | None = None, end: datetime | None = None,
    data_origin: Literal["real", "simulated"] | None = None,
):
    stmt = select(EnergyRecord).order_by(EnergyRecord.timestamp_utc.desc(), EnergyRecord.id)
    if start or end:
        s, e = _range(start, end)
        stmt = stmt.where(EnergyRecord.timestamp_utc >= s, EnergyRecord.timestamp_utc < e)
    for col, val in ((EnergyRecord.country_code, country and country.upper()), (EnergyRecord.provider_id, provider_id),
                     (EnergyRecord.metric_type, metric_type), (EnergyRecord.energy_source, energy_source),
                     (EnergyRecord.dataset_id, dataset_id), (EnergyRecord.data_origin, data_origin)):
        if val is not None:
            stmt = stmt.where(col == val)
    items, total = paginate(db, stmt, paging)
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)


@router.get("/energy-records/summary")
def summary(
    db: DB,
    metric_type: str = Query("generation"),
    country: str | None = "DE",
    provider_id: list[int] | None = Query(None),
    energy_source: list[str] | None = Query(None),
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: Literal["15min", "hour", "day"] = "hour",
    include_simulated: bool = True,
):
    """Time series aggregated per (provider, energy source) with provenance and comparability warnings.

    Values are canonical (MW average power, or EUR/MWh), so bucket aggregation is a time-weighted mean of
    equal-length intervals. Null (unpublished) values are excluded from means and reported as coverage gaps.
    """
    s, e = _range(start, end)
    q = (select(EnergyRecord.provider_id, EnergyRecord.dataset_id, EnergyRecord.connector_id,
                EnergyRecord.energy_source, EnergyRecord.timestamp_utc, EnergyRecord.interval_minutes,
                EnergyRecord.value, EnergyRecord.unit, EnergyRecord.data_origin, EnergyRecord.bidding_zone)
         .where(EnergyRecord.metric_type == metric_type, EnergyRecord.timestamp_utc >= s, EnergyRecord.timestamp_utc < e))
    if country:
        q = q.where(EnergyRecord.country_code == country.upper())
    if provider_id:
        q = q.where(EnergyRecord.provider_id.in_(provider_id))
    if energy_source:
        q = q.where(EnergyRecord.energy_source.in_(energy_source))
    if not include_simulated:
        q = q.where(EnergyRecord.data_origin == "real")
    rows = db.execute(q).all()

    providers = {p.id: p for p in db.scalars(select(Provider))}
    datasets = {d.id: d for d in db.scalars(select(Dataset))}
    connectors = {c.id: c for c in db.scalars(select(Connector))}
    warnings: list[dict] = []
    series_out, provenance = [], {}
    missing_by_provider: dict[str, list[tuple[str, int]]] = {}
    simulated_providers: set[str] = set()

    if rows:
        df = pd.DataFrame(rows, columns=["provider_id", "dataset_id", "connector_id", "energy_source", "ts", "interval",
                                         "value", "unit", "origin", "zone"])
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        for (pid, src, origin), g in df.groupby(["provider_id", "energy_source", "origin"], sort=True):
            intervals = sorted(g["interval"].unique().tolist())
            units = sorted(g["unit"].unique().tolist())
            vals = g.set_index("ts")["value"].astype("float64").sort_index()
            nulls = int(vals.isna().sum())
            agg = vals.resample(BUCKET_FREQ[bucket]).mean()
            if BUCKET_MINUTES[bucket] < max(intervals):
                warnings.append({"type": "granularity", "message": f"{providers[pid].name} {src} is published at "
                                 f"{max(intervals)}-min resolution; a {bucket} bucket cannot add detail."})
            ds = datasets.get(int(g["dataset_id"].dropna().iloc[0])) if g["dataset_id"].notna().any() else None
            series_out.append({
                "key": f"{providers[pid].slug}:{src}:{origin}",
                "provider_id": int(pid), "provider_name": providers[pid].name, "energy_source": src,
                "data_origin": origin, "unit": units[0] if len(units) == 1 else units,
                "source_interval_minutes": intervals,
                "bidding_zone": next(iter(g["zone"].dropna().unique()), None),
                "dataset": {"id": ds.id, "name": ds.dataset_name, "published_unit": ds.unit,
                            "frequency": ds.frequency, "description": ds.description} if ds else None,
                "coverage": {"first": vals.index.min().isoformat(), "last": vals.index.max().isoformat(),
                             "records": int(len(vals)), "null_values": nulls},
                "points": [{"t": t.isoformat(), "v": None if pd.isna(v) else round(float(v), 3)} for t, v in agg.items()],
            })
            if len(units) > 1:
                warnings.append({"type": "unit", "message": f"Mixed units {units} for {src}; series not comparable."})
            if nulls:
                missing_by_provider.setdefault(providers[pid].name, []).append((src, nulls))
            if origin == "simulated":
                simulated_providers.add(providers[pid].name)
            prov = provenance.setdefault(int(pid), {
                "provider_id": int(pid), "provider_name": providers[pid].name, "licence": providers[pid].licence,
                "attribution": providers[pid].attribution, "website": providers[pid].website, "data_origins": set(),
                "datasets": {}, "connectors": {}})
            prov["data_origins"].add(origin)
            if ds:
                prov["datasets"][ds.id] = {"id": ds.id, "name": ds.dataset_name, "published_unit": ds.unit,
                                           "frequency": ds.frequency}
            for cid in g["connector_id"].dropna().unique():
                c = connectors.get(int(cid))
                if c:
                    prov["connectors"][c.id] = {"id": c.id, "name": c.connector_name,
                                                "last_successful_sync": c.last_successful_sync}

        for name, items in missing_by_provider.items():
            total = sum(n for _, n in items)
            detail = ", ".join(f"{src} ({n})" for src, n in items[:6]) + (" …" if len(items) > 6 else "")
            warnings.append({"type": "missing", "message": f"{name}: {total} intervals across {len(items)} series were "
                             f"published without a value and are shown as gaps, not zero — {detail}."})
        for name in sorted(simulated_providers):
            warnings.append({"type": "simulated", "message": f"{name}: series shown dashed / labelled are SIMULATED fixture "
                             "data, not real market data."})

        # cross-provider comparability
        by_provider = df.groupby("provider_id")
        if by_provider.ngroups > 1:
            spans = {pid: (g["ts"].min(), g["ts"].max()) for pid, g in by_provider}
            starts = [a for a, _ in spans.values()]
            ends = [b for _, b in spans.values()]
            if max(starts) - min(starts) > timedelta(hours=1) or max(ends) - min(ends) > timedelta(hours=1):
                warnings.append({"type": "coverage", "message": "Providers cover different time ranges: "
                                 + "; ".join(f"{providers[p].name} {a:%Y-%m-%d %H:%M}–{b:%Y-%m-%d %H:%M} UTC"
                                             for p, (a, b) in spans.items())})
            if df["interval"].nunique() > 1:
                warnings.append({"type": "granularity", "message": "Providers publish at different resolutions: "
                                 + ", ".join(f"{providers[p].name} {sorted(g['interval'].unique().tolist())} min"
                                             for p, g in by_provider)})
            warnings.append({"type": "definition", "message": f"Multiple providers report '{metric_type}'. Similar names do "
                             "not guarantee identical definitions (e.g. net vs gross generation, grid load vs total "
                             "load); check dataset descriptions before comparing."})

    for p in provenance.values():
        p["data_origins"] = sorted(p["data_origins"])
        p["datasets"] = list(p["datasets"].values())
        p["connectors"] = list(p["connectors"].values())
    # de-duplicate warnings
    seen, uniq = set(), []
    for w in warnings:
        if w["message"] not in seen:
            seen.add(w["message"])
            uniq.append(w)
    return {"metric_type": metric_type, "bucket": bucket, "start": s, "end": e, "series": series_out,
            "provenance": list(provenance.values()), "warnings": uniq}


@router.get("/energy-records/facets")
def facets(db: DB):
    rows = db.execute(select(EnergyRecord.country_code, EnergyRecord.metric_type, EnergyRecord.energy_source,
                             EnergyRecord.provider_id, EnergyRecord.data_origin, func.count(),
                             func.min(EnergyRecord.timestamp_utc), func.max(EnergyRecord.timestamp_utc))
                      .group_by(EnergyRecord.country_code, EnergyRecord.metric_type, EnergyRecord.energy_source,
                                EnergyRecord.provider_id, EnergyRecord.data_origin)).all()
    return [{"country_code": r[0], "metric_type": r[1], "energy_source": r[2], "provider_id": r[3],
             "data_origin": r[4], "records": r[5], "first": r[6], "last": r[7]} for r in rows]
