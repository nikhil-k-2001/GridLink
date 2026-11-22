"""Data coverage: for every plant and every data need, is the data actually arriving — and if not, why?

This is the view a market-connections TPM is accountable for. Each (plant, need) pair gets exactly one
status with a human-readable reason that points to the next action:

covered                     data is arriving within the expected lag
stale                       we had data, it stopped arriving
access_denied               we believe we're authorised but the data holder refuses (open issue)
awaiting_authorisation      authorisation requested from the plant owner, not yet granted
authorisation_not_requested a route exists but nobody has asked the owner yet
authorisation_refused       owner refused / revoked at our side
no_connector                data holder known, no connector built yet
route_blocked               a route is known but blocked (token, contract, no API) — see blockers
no_route                    nobody has found a way to get this data yet (see country access map)
simulated_only              only SIMULATED data exists for this need (demo) — not real coverage
"""
from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AccessRequest,
    AccessRoute,
    Asset,
    AssetAuthorisation,
    Connector,
    CountryProfile,
    DataIssue,
    EnergyRecord,
    PlaybookStep,
)

COVERED = {"covered"}
IN_PROGRESS = {"awaiting_authorisation", "authorisation_not_requested", "no_connector"}
GAP = {"no_route", "route_blocked", "access_denied", "authorisation_refused", "stale"}
ROUTE_RANK = ["in_use", "available", "testing", "investigating", "to_investigate", "blocked", "rejected"]
PRICE_FRESH = timedelta(days=2)


def _aware(dt):
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=UTC))


def _best_route(routes: list[AccessRoute]) -> AccessRoute | None:
    if not routes:
        return None
    return sorted(routes, key=lambda r: (r.is_fallback, ROUTE_RANK.index(r.status) if r.status in ROUTE_RANK else 99))[0]


def _route_dict(r: AccessRoute | None):
    if r is None:
        return None
    return {"id": r.id, "holder": r.holder_name, "route_type": r.route_type, "status": r.status, "is_fallback": r.is_fallback,
            "blockers": r.blockers}


def compute_coverage(db: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    assets = list(db.scalars(select(Asset).order_by(Asset.country_code, Asset.name)))
    routes_by: dict[tuple[str, str], list[AccessRoute]] = {}
    for r in db.scalars(select(AccessRoute)):
        routes_by.setdefault((r.country_code, r.data_need), []).append(r)
    auths = {(a.asset_id, a.provider_id): a for a in db.scalars(select(AssetAuthorisation))}
    connectors = list(db.scalars(select(Connector)))
    latest_by_asset = {aid: (_aware(ts), origin) for aid, ts, origin in db.execute(
        select(EnergyRecord.asset_id, func.max(EnergyRecord.timestamp_utc), func.min(EnergyRecord.data_origin))
        .where(EnergyRecord.asset_id.is_not(None), EnergyRecord.value.is_not(None)).group_by(EnergyRecord.asset_id))}
    price_by_zone: dict[str, dict[str, datetime]] = {}
    for zone, origin, ts in db.execute(
            select(EnergyRecord.bidding_zone, EnergyRecord.data_origin, func.max(EnergyRecord.timestamp_utc))
            .where(EnergyRecord.metric_type == "day_ahead_price", EnergyRecord.value.is_not(None))
            .group_by(EnergyRecord.bidding_zone, EnergyRecord.data_origin)):
        price_by_zone.setdefault(zone or "", {})[origin] = _aware(ts)
    denied_assets: set[int] = set()
    for issue in db.scalars(select(DataIssue).where(DataIssue.code == "authorisation_denied", DataIssue.status != "resolved")):
        denied_assets |= set(issue.affected_asset_ids or [])

    rows = []
    for a in assets:
        items = []
        for need in a.data_needs or []:
            route = _best_route(routes_by.get((a.country_code, need), []))
            item: dict[str, Any] = {"need": need, "route": _route_dict(route), "latest": None, "data_origin": None}
            if need == "production_metering":
                conns = [c for c in connectors if a.dso_provider_id and c.provider_id == a.dso_provider_id and c.status == "active"]
                auth = auths.get((a.id, a.dso_provider_id)) if a.dso_provider_id else None
                latest, origin = latest_by_asset.get(a.id, (None, None))
                item["authorisation"] = auth.status if auth else ("not_requested" if a.dso_provider_id else None)
                lag_limit = timedelta(minutes=max((c.max_data_lag_minutes for c in conns), default=2880))
                if latest is not None:
                    item["latest"], item["data_origin"] = latest, origin
                if a.id in denied_assets:
                    item["status"], item["reason"] = "access_denied", "Data holder refuses access although our records say authorised — see open issue"
                elif latest is not None and now - latest <= lag_limit + timedelta(minutes=60):
                    item["status"] = "covered"
                    item["reason"] = f"Metered data arriving ({'SIMULATED' if origin == 'simulated' else 'real'})"
                elif latest is not None:
                    item["status"], item["reason"] = "stale", f"Last value {latest:%d %b %H:%M} UTC — beyond expected lag"
                elif auth and auth.status in ("refused", "revoked", "expired"):
                    item["status"], item["reason"] = "authorisation_refused", f"Owner authorisation {auth.status}"
                elif auth and auth.status == "requested":
                    item["status"], item["reason"] = "awaiting_authorisation", "Waiting for the plant owner to authorise access"
                elif a.dso_provider_id and conns and (auth is None or auth.status == "not_requested"):
                    item["status"], item["reason"] = "authorisation_not_requested", "Connector ready — ask the owner for authorisation"
                elif route and route.status == "blocked" and not conns:
                    item["status"] = "route_blocked"
                    item["reason"] = f"{route.holder_name}: {route.blockers or 'blocked'}"
                elif a.dso_provider_id and not conns:
                    item["status"] = "no_connector"
                    item["reason"] = f"Data holder known; route: {route.holder_name} ({route.status.replace('_', ' ')})" if route else "Data holder known; no connector"
                elif a.dso_provider_id:
                    item["status"], item["reason"] = "stale", "Authorised and connected, but no data received yet"
                else:
                    item["status"] = "no_route"
                    item["reason"] = (f"Best route: {route.holder_name} — {route.status.replace('_', ' ')}"
                                      + (f" ({route.blockers})" if route.blockers else "")) if route else "No access route identified"
            elif need == "day_ahead_price":
                found = price_by_zone.get(a.bidding_zone, {})
                real, sim = found.get("real"), found.get("simulated")
                if real and now - real <= PRICE_FRESH:
                    item.update(status="covered", reason=f"Real prices for {a.bidding_zone}", latest=real, data_origin="real")
                elif real:
                    item.update(status="stale", reason=f"Prices for {a.bidding_zone} stopped at {real:%d %b}", latest=real, data_origin="real")
                elif sim:
                    item.update(status="simulated_only", reason=f"Only SIMULATED prices for {a.bidding_zone}", latest=sim, data_origin="simulated")
                elif route and route.status == "blocked":
                    item["status"] = "route_blocked"
                    item["reason"] = f"{route.holder_name}: {route.blockers or 'blocked'}"
                else:
                    item["status"] = "no_connector" if route and route.status in ("available", "testing", "in_use") else "no_route"
                    item["reason"] = (f"Route: {route.holder_name} — {route.status.replace('_', ' ')}"
                                      + (f" ({route.blockers})" if route.blockers else "")) if route else f"No price source for {a.bidding_zone}"
            else:
                item["status"] = "no_connector" if route else "no_route"
                item["reason"] = f"Route: {route.holder_name} ({route.status.replace('_', ' ')})" if route else "No route identified"
            items.append(item)
        rows.append({"asset_id": a.id, "name": a.name, "customer_id": a.customer_id, "customer": a.customer.name,
                     "country_code": a.country_code, "bidding_zone": a.bidding_zone, "technology": a.technology,
                     "capacity_mw": a.capacity_mw, "metering_point_id": a.metering_point_id,
                     "dso": a.dso.name if a.dso else None, "is_fictional": a.is_fictional, "needs": items})

    def rollup(pairs: list[tuple[dict, dict]]) -> dict[str, Any]:
        n = len(pairs)
        cov = [p for p in pairs if p[1]["status"] in COVERED]
        mw = sum(p[0]["capacity_mw"] for p in pairs)
        return {"pairs": n, "covered": len(cov), "in_progress": sum(1 for p in pairs if p[1]["status"] in IN_PROGRESS),
                "gaps": sum(1 for p in pairs if p[1]["status"] in GAP or p[1]["status"] == "simulated_only"),
                "pct": round(100 * len(cov) / n, 1) if n else None,
                "mw_pct": round(100 * sum(p[0]["capacity_mw"] for p in cov) / mw, 1) if mw else None}

    pairs = [(r, i) for r in rows for i in r["needs"]]
    group = lambda key: {k: rollup([p for p in pairs if key(p) == k]) for k in sorted({key(p) for p in pairs})}  # noqa: E731
    return {
        "computed_at": now, "assets": rows, "totals": {**rollup(pairs), "plants": len(rows), "capacity_mw": round(sum(r["capacity_mw"] for r in rows), 1)},
        "by_need": group(lambda p: p[1]["need"]), "by_country": group(lambda p: p[0]["country_code"]),
        "by_customer": group(lambda p: p[0]["customer"]),
        "status_counts": {s: sum(1 for p in pairs if p[1]["status"] == s) for s in sorted({p[1]["status"] for p in pairs})},
    }


def demand(coverage: dict[str, Any], country: str | None, need: str | None) -> dict[str, Any]:
    """Uncovered demand for a (country, need) — the evidence behind 'customer value'."""
    gaps = [(r, i) for r in coverage["assets"] for i in r["needs"]
            if i["status"] not in COVERED and (country is None or r["country_code"] == country) and (need is None or i["need"] == need)]
    mw = round(sum(r["capacity_mw"] for r, _ in gaps), 1)
    customers = sorted({r["customer"] for r, _ in gaps})
    score = 1 if mw == 0 else 2 if mw < 25 else 3 if mw < 50 else 4 if mw < 100 else 5
    if len(customers) >= 2:
        score = min(5, score + 1)
    return {"plants": len(gaps), "capacity_mw": mw, "customers": customers, "suggested_customer_value": score}


def lead_times(db: Session) -> dict[str, Any]:
    closed = [r for r in db.scalars(select(AccessRequest).where(AccessRequest.status == "granted", AccessRequest.closed_at.is_not(None)))]
    by_country: dict[str, list[float]] = {}
    for r in closed:
        by_country.setdefault(r.country_code, []).append((_aware(r.closed_at) - _aware(r.opened_at)).days)
    all_days = [d for v in by_country.values() for d in v]
    return {"median_days_to_grant": statistics.median(all_days) if all_days else None, "samples": len(all_days),
            "by_country": {k: {"median_days": statistics.median(v), "samples": len(v)} for k, v in by_country.items()}}


def follow_ups(db: Session, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    out = []
    for r in db.scalars(select(AccessRequest).where(AccessRequest.status.not_in(["granted", "rejected"]))):
        last = max(r.interactions, key=lambda i: _aware(i.occurred_at), default=None)
        next_fu = _aware(last.next_follow_up) if last and last.next_follow_up else None
        due = _aware(r.due_date)
        overdue = (next_fu is not None and next_fu < now) or (due is not None and due < now)
        out.append({"request_id": r.id, "provider_id": r.provider_id, "provider": r.provider.name, "country_code": r.country_code,
                    "subject": r.subject, "status": r.status, "owner": r.owner,
                    "last_contact": _aware(last.occurred_at) if last else None,
                    "days_since_contact": (now - _aware(last.occurred_at)).days if last else None,
                    "next_follow_up": next_fu, "due_date": due, "overdue": overdue,
                    "days_open": (now - _aware(r.opened_at)).days})
    return sorted(out, key=lambda x: (not x["overdue"], x["next_follow_up"] or x["due_date"] or now))


def playbook_progress(db: Session, country: str) -> dict[str, Any]:
    steps = list(db.scalars(select(PlaybookStep).where(PlaybookStep.country_code == country)))
    relevant = [s for s in steps if s.status != "n/a"]
    done = sum(1 for s in relevant if s.status == "done")
    return {"done": done, "total": len(relevant), "pct": round(100 * done / len(relevant)) if relevant else 0,
            "blocked": sum(1 for s in relevant if s.status == "blocked")}


def country_summaries(db: Session, coverage: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in db.scalars(select(CountryProfile).order_by(CountryProfile.name)):
        plants = [r for r in coverage["assets"] if r["country_code"] == c.country_code]
        routes = list(db.scalars(select(AccessRoute).where(AccessRoute.country_code == c.country_code)))
        open_req = db.scalar(select(func.count()).select_from(AccessRequest).where(
            AccessRequest.country_code == c.country_code, AccessRequest.status.not_in(["granted", "rejected"])))
        out.append({"country_code": c.country_code, "name": c.name, "status": c.status, "owner": c.owner,
                    "bidding_zones": c.bidding_zones, "plants": len(plants),
                    "capacity_mw": round(sum(p["capacity_mw"] for p in plants), 1),
                    "customers": sorted({p["customer"] for p in plants}),
                    "coverage": coverage["by_country"].get(c.country_code),
                    "routes": {s: sum(1 for r in routes if r.status == s) for s in {r.status for r in routes}},
                    "open_requests": open_req or 0, "playbook": playbook_progress(db, c.country_code)})
    return out
