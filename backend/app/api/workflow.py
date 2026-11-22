"""Market-connections workflow API: customers & plants, coverage, country access maps & playbooks,
provider relationships, data issues, the API test bench and the weekly cockpit."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, get_or_404
from app.config import get_settings
from app.models import (
    AUTH_STATUSES,
    COUNTRY_STATUSES,
    DATA_NEEDS,
    ISSUE_STATUSES,
    PLAYBOOK_STEPS,
    REQUEST_STATUSES,
    ROUTE_STATUSES,
    ROUTE_TYPES,
    AccessRequest,
    AccessRoute,
    ApiTest,
    Asset,
    AssetAuthorisation,
    Connector,
    Contact,
    CountryProfile,
    Customer,
    DataIssue,
    Interaction,
    PlaybookStep,
    Provider,
    ProviderFact,
)
from app.services import api_tests
from app.services.coverage import (
    compute_coverage,
    country_summaries,
    demand,
    follow_ups,
    lead_times,
    playbook_progress,
)
from app.services.health import compute_connector_health
from app.simulated import dso_api

router = APIRouter()


def row(obj, *exclude: str) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name not in exclude}


# =================================================================================== customers & plants
class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    segment: str | None = None
    account_owner: str | None = None
    notes: str | None = None


class AssetIn(BaseModel):
    customer_id: int
    name: str = Field(min_length=2, max_length=200)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    bidding_zone: str = Field(min_length=2, max_length=32)
    technology: Literal["solar", "wind_onshore", "wind_offshore"]
    capacity_mw: float = Field(gt=0, le=5000)
    dso_provider_id: int | None = None
    metering_point_id: str | None = Field(default=None, max_length=64)
    data_needs: list[Literal[DATA_NEEDS]] = ["production_metering", "day_ahead_price"]  # type: ignore[valid-type]


class AuthorisationIn(BaseModel):
    status: Literal[AUTH_STATUSES]  # type: ignore[valid-type]
    method: str | None = None
    notes: str | None = None


@router.get("/customers", tags=["customers & plants"])
def list_customers(db: DB):
    out = []
    for c in db.scalars(select(Customer).order_by(Customer.name)):
        out.append({**row(c), "plants": len(c.assets), "capacity_mw": round(sum(a.capacity_mw for a in c.assets), 1),
                    "countries": sorted({a.country_code for a in c.assets})})
    return out


@router.post("/customers", status_code=201, tags=["customers & plants"])
def create_customer(body: CustomerIn, db: DB):
    c = Customer(**body.model_dump())
    db.add(c)
    db.commit()
    return row(c)


@router.get("/assets", tags=["customers & plants"])
def list_assets(db: DB, country: str | None = None, customer_id: int | None = None):
    stmt = select(Asset).order_by(Asset.country_code, Asset.name)
    if country:
        stmt = stmt.where(Asset.country_code == country.upper())
    if customer_id:
        stmt = stmt.where(Asset.customer_id == customer_id)
    return [{**row(a), "customer": a.customer.name, "dso": a.dso.name if a.dso else None,
             "authorisations": [{**row(x), "provider": x.provider.name} for x in a.authorisations]} for a in db.scalars(stmt)]


@router.post("/assets", status_code=201, tags=["customers & plants"])
def create_asset(body: AssetIn, db: DB):
    get_or_404(db, Customer, body.customer_id, "Customer")
    if body.dso_provider_id:
        get_or_404(db, Provider, body.dso_provider_id, "Provider")
    a = Asset(**body.model_dump(), is_fictional=False)
    db.add(a)
    db.commit()
    return row(a)


@router.put("/assets/{asset_id}/authorisations/{provider_id}", tags=["customers & plants"])
def set_authorisation(asset_id: int, provider_id: int, body: AuthorisationIn, db: DB):
    get_or_404(db, Asset, asset_id, "Asset")
    get_or_404(db, Provider, provider_id, "Provider")
    auth = db.scalar(select(AssetAuthorisation).where(AssetAuthorisation.asset_id == asset_id,
                                                      AssetAuthorisation.provider_id == provider_id))
    now = datetime.now(UTC)
    if auth is None:
        auth = AssetAuthorisation(asset_id=asset_id, provider_id=provider_id)
        db.add(auth)
    auth.status, auth.method, auth.notes = body.status, body.method or auth.method, body.notes or auth.notes
    if body.status == "requested":
        auth.requested_at = now
    if body.status == "granted":
        auth.granted_at = now
    db.commit()
    return row(auth)


@router.get("/coverage", tags=["customers & plants"])
def coverage(db: DB):
    return compute_coverage(db)


# =================================================================================== countries
class CountryPatch(BaseModel):
    status: Literal[COUNTRY_STATUSES] | None = None  # type: ignore[valid-type]
    owner: str | None = None
    summary: str | None = None
    lessons_learned: str | None = None
    dso_landscape: str | None = None


class RouteIn(BaseModel):
    data_need: Literal[DATA_NEEDS]  # type: ignore[valid-type]
    holder_name: str = Field(min_length=2, max_length=200)
    provider_id: int | None = None
    route_type: Literal[ROUTE_TYPES]  # type: ignore[valid-type]
    status: Literal[ROUTE_STATUSES] = "to_investigate"  # type: ignore[valid-type]
    is_fallback: bool = False
    effort: Literal["low", "medium", "high"] | None = None
    requires_owner_authorisation: bool = False
    blockers: str | None = None
    notes: str | None = None
    evidence_level: Literal["verified", "researched", "assumption"] = "assumption"
    source_url: str | None = None


class RoutePatch(BaseModel):
    status: Literal[ROUTE_STATUSES] | None = None  # type: ignore[valid-type]
    blockers: str | None = None
    notes: str | None = None
    evidence_level: Literal["verified", "researched", "assumption"] | None = None
    effort: Literal["low", "medium", "high"] | None = None


class StepPatch(BaseModel):
    status: Literal["todo", "in_progress", "done", "blocked", "n/a"]
    notes: str | None = None


@router.get("/playbook/template", tags=["countries"])
def playbook_template():
    return [{"key": k, "title": t, "description": d, "number": i} for i, (k, t, d) in enumerate(PLAYBOOK_STEPS, start=1)]


@router.get("/countries", tags=["countries"])
def list_countries(db: DB):
    return {"countries": country_summaries(db, compute_coverage(db)), "lead_times": lead_times(db)}


@router.get("/countries/{code}", tags=["countries"])
def get_country(code: str, db: DB):
    c = db.get(CountryProfile, code.upper())
    if c is None:
        raise HTTPException(404, f"Country {code} not profiled")
    cov = compute_coverage(db)
    steps = {s.step_key: s for s in db.scalars(select(PlaybookStep).where(PlaybookStep.country_code == c.country_code))}
    routes = db.scalars(select(AccessRoute).where(AccessRoute.country_code == c.country_code)
                        .order_by(AccessRoute.data_need, AccessRoute.is_fallback, AccessRoute.id))
    providers = db.scalars(select(Provider).where(Provider.country_code == c.country_code).order_by(Provider.name))
    reqs = db.scalars(select(AccessRequest).where(AccessRequest.country_code == c.country_code).order_by(AccessRequest.opened_at.desc()))
    return {
        "profile": row(c),
        "routes": [{**row(r), "provider": r.provider.name if r.provider else None} for r in routes],
        "playbook": [{"key": k, "title": t, "description": d, "number": i,
                      **({kk: vv for kk, vv in row(steps[k]).items() if kk in ("status", "notes", "started_at", "completed_at")}
                         if k in steps else {"status": "todo"})} for i, (k, t, d) in enumerate(PLAYBOOK_STEPS, start=1)],
        "playbook_progress": playbook_progress(db, c.country_code),
        "providers": [{"id": p.id, "name": p.name, "status": p.status} for p in providers],
        "requests": [{**row(r), "provider": r.provider.name} for r in reqs],
        "plants": [a for a in cov["assets"] if a["country_code"] == c.country_code],
        "coverage": cov["by_country"].get(c.country_code),
        "lead_times": lead_times(db)["by_country"].get(c.country_code),
    }


@router.patch("/countries/{code}", tags=["countries"])
def patch_country(code: str, body: CountryPatch, db: DB):
    c = db.get(CountryProfile, code.upper())
    if c is None:
        raise HTTPException(404, "Country not profiled")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return row(c)


@router.post("/countries/{code}/routes", status_code=201, tags=["countries"])
def add_route(code: str, body: RouteIn, db: DB):
    if db.get(CountryProfile, code.upper()) is None:
        raise HTTPException(404, "Country not profiled")
    r = AccessRoute(country_code=code.upper(), **body.model_dump())
    db.add(r)
    db.commit()
    return row(r)


@router.patch("/routes/{route_id}", tags=["countries"])
def patch_route(route_id: int, body: RoutePatch, db: DB):
    r = get_or_404(db, AccessRoute, route_id, "Route")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    return row(r)


@router.patch("/countries/{code}/playbook/{step_key}", tags=["countries"])
def patch_step(code: str, step_key: str, body: StepPatch, db: DB):
    if step_key not in {k for k, _, _ in PLAYBOOK_STEPS}:
        raise HTTPException(404, "Unknown playbook step")
    if db.get(CountryProfile, code.upper()) is None:
        raise HTTPException(404, "Country not profiled")
    s = db.scalar(select(PlaybookStep).where(PlaybookStep.country_code == code.upper(), PlaybookStep.step_key == step_key))
    if s is None:
        s = PlaybookStep(country_code=code.upper(), step_key=step_key)
        db.add(s)
    now = datetime.now(UTC)
    if body.status == "in_progress" and s.started_at is None:
        s.started_at = now
    if body.status == "done":
        s.completed_at = now
        s.started_at = s.started_at or now
    s.status = body.status
    if body.notes is not None:
        s.notes = body.notes
    db.commit()
    return row(s)


# =================================================================================== relationships
class ContactIn(BaseModel):
    provider_id: int
    role: str = Field(min_length=2, max_length=200)
    name: str | None = None
    email: str | None = None
    language: str | None = None
    notes: str | None = None


class RequestIn(BaseModel):
    provider_id: int
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    data_need: Literal[DATA_NEEDS]  # type: ignore[valid-type]
    subject: str = Field(min_length=3, max_length=300)
    status: Literal[REQUEST_STATUSES] = "draft"  # type: ignore[valid-type]
    owner: str | None = None
    due_date: datetime | None = None
    fallback_route_id: int | None = None
    notes: str | None = None


class RequestPatch(BaseModel):
    status: Literal[REQUEST_STATUSES] | None = None  # type: ignore[valid-type]
    owner: str | None = None
    due_date: datetime | None = None
    fallback_route_id: int | None = None
    notes: str | None = None


class InteractionIn(BaseModel):
    provider_id: int
    access_request_id: int | None = None
    contact_id: int | None = None
    occurred_at: datetime | None = None
    channel: Literal["email", "call", "meeting", "portal", "ticket", "linkedin"]
    direction: Literal["outbound", "inbound"]
    summary: str = Field(min_length=3)
    next_follow_up: datetime | None = None


@router.get("/contacts", tags=["relationships"])
def list_contacts(db: DB, provider_id: int | None = None):
    stmt = select(Contact).order_by(Contact.provider_id, Contact.role)
    if provider_id:
        stmt = stmt.where(Contact.provider_id == provider_id)
    return [{**row(c), "provider": c.provider.name} for c in db.scalars(stmt)]


@router.post("/contacts", status_code=201, tags=["relationships"])
def add_contact(body: ContactIn, db: DB):
    get_or_404(db, Provider, body.provider_id, "Provider")
    c = Contact(**body.model_dump(), is_placeholder=False)
    db.add(c)
    db.commit()
    return row(c)


@router.get("/access-requests", tags=["relationships"])
def list_requests(db: DB, status: str | None = None, country: str | None = None, provider_id: int | None = None):
    stmt = select(AccessRequest).order_by(AccessRequest.opened_at.desc())
    if status:
        stmt = stmt.where(AccessRequest.status == status)
    if country:
        stmt = stmt.where(AccessRequest.country_code == country.upper())
    if provider_id:
        stmt = stmt.where(AccessRequest.provider_id == provider_id)
    return [{**row(r), "provider": r.provider.name, "interactions": len(r.interactions)} for r in db.scalars(stmt)]


@router.post("/access-requests", status_code=201, tags=["relationships"])
def create_request(body: RequestIn, db: DB):
    get_or_404(db, Provider, body.provider_id, "Provider")
    r = AccessRequest(**body.model_dump())
    db.add(r)
    db.commit()
    return row(r)


@router.patch("/access-requests/{request_id}", tags=["relationships"])
def patch_request(request_id: int, body: RequestPatch, db: DB):
    r = get_or_404(db, AccessRequest, request_id, "Access request")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    if body.status in ("granted", "rejected") and r.closed_at is None:
        r.closed_at = datetime.now(UTC)
    db.commit()
    return row(r)


@router.get("/interactions", tags=["relationships"])
def list_interactions(db: DB, provider_id: int | None = None, access_request_id: int | None = None, limit: int = 100):
    stmt = select(Interaction).order_by(Interaction.occurred_at.desc()).limit(min(limit, 500))
    if provider_id:
        stmt = stmt.where(Interaction.provider_id == provider_id)
    if access_request_id:
        stmt = stmt.where(Interaction.access_request_id == access_request_id)
    providers = {p.id: p.name for p in db.scalars(select(Provider))}
    contacts = {c.id: c.role for c in db.scalars(select(Contact))}
    return [{**row(i), "provider": providers.get(i.provider_id), "contact": contacts.get(i.contact_id)} for i in db.scalars(stmt)]


@router.post("/interactions", status_code=201, tags=["relationships"])
def log_interaction(body: InteractionIn, db: DB):
    get_or_404(db, Provider, body.provider_id, "Provider")
    data = body.model_dump()
    data["occurred_at"] = data["occurred_at"] or datetime.now(UTC)
    i = Interaction(**data)
    db.add(i)
    if body.access_request_id:
        r = get_or_404(db, AccessRequest, body.access_request_id, "Access request")
        if body.direction == "outbound" and r.status == "draft":
            r.status = "sent"
        if body.direction == "inbound" and r.status in ("sent", "awaiting_reply", "stalled"):
            r.status = "in_review"
    db.commit()
    return row(i)


@router.get("/follow-ups", tags=["relationships"])
def get_follow_ups(db: DB):
    return follow_ups(db)


# =================================================================================== data issues
class IssueIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    severity: Literal["low", "medium", "high"] = "medium"
    connector_id: int | None = None
    provider_id: int | None = None
    affected_asset_ids: list[int] = []
    hypotheses: str | None = None


class IssuePatch(BaseModel):
    status: Literal[ISSUE_STATUSES] | None = None  # type: ignore[valid-type]
    severity: Literal["low", "medium", "high"] | None = None
    hypotheses: str | None = None
    root_cause: str | None = None
    provider_contacted: bool | None = None
    customer_update: str | None = None
    resolution: str | None = None


def _issue_out(db, i: DataIssue) -> dict[str, Any]:
    assets = list(db.scalars(select(Asset).where(Asset.id.in_(i.affected_asset_ids or [-1]))))
    conn = db.get(Connector, i.connector_id) if i.connector_id else None
    prov = db.get(Provider, i.provider_id) if i.provider_id else None
    return {**row(i), "connector": conn.connector_name if conn else None, "provider": prov.name if prov else None,
            "affected_assets": [{"id": a.id, "name": a.name, "customer": a.customer.name, "capacity_mw": a.capacity_mw} for a in assets],
            "affected_customers": sorted({a.customer.name for a in assets}),
            "affected_mw": round(sum(a.capacity_mw for a in assets), 1)}


@router.get("/issues", tags=["data issues"])
def list_issues(db: DB, status: str | None = None, severity: str | None = None, connector_id: int | None = None,
                include_resolved: bool = True):
    stmt = select(DataIssue).order_by(DataIssue.status == "resolved", DataIssue.detected_at.desc())
    if status:
        stmt = stmt.where(DataIssue.status == status)
    if not include_resolved:
        stmt = stmt.where(DataIssue.status != "resolved")
    if severity:
        stmt = stmt.where(DataIssue.severity == severity)
    if connector_id:
        stmt = stmt.where(DataIssue.connector_id == connector_id)
    return [_issue_out(db, i) for i in db.scalars(stmt)]


@router.get("/issues/{issue_id}", tags=["data issues"])
def get_issue(issue_id: int, db: DB):
    return _issue_out(db, get_or_404(db, DataIssue, issue_id, "Issue"))


@router.post("/issues", status_code=201, tags=["data issues"])
def create_issue(body: IssueIn, db: DB):
    i = DataIssue(code="manual", source="manual", **body.model_dump())
    db.add(i)
    db.commit()
    return _issue_out(db, i)


@router.patch("/issues/{issue_id}", tags=["data issues"])
def patch_issue(issue_id: int, body: IssuePatch, db: DB):
    i = get_or_404(db, DataIssue, issue_id, "Issue")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") == "resolved" and not (data.get("resolution") or i.resolution):
        raise HTTPException(422, "Document the resolution before closing the issue")
    for k, v in data.items():
        setattr(i, k, v)
    if data.get("status") == "resolved":
        i.resolved_at = datetime.now(UTC)
    elif data.get("status"):
        i.resolved_at = None
    db.commit()
    return _issue_out(db, i)


# =================================================================================== API test bench
class ApiTestIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    provider_id: int | None = None
    method: Literal["GET", "POST"] = "GET"
    url: str = Field(min_length=8, max_length=2000)
    params: dict[str, str] = {}
    headers: dict[str, str] = {}
    body: str | None = Field(default=None, max_length=20000)


class ApiTestPatch(BaseModel):
    name: str | None = None
    verdict: Literal["works", "partial", "fails", "inconclusive"] | None = None
    notes: str | None = None


class PromoteIn(BaseModel):
    statement: str = Field(min_length=5)
    category: str = "access"


@router.post("/api-tests/run", status_code=201, tags=["api test bench"])
def run_api_test(body: ApiTestIn, db: DB):
    if body.provider_id:
        get_or_404(db, Provider, body.provider_id, "Provider")
    try:
        test = api_tests.run_test(get_settings(), name=body.name, method=body.method, url=body.url, params=body.params,
                                  headers=body.headers, body=body.body, provider_id=body.provider_id)
    except api_tests.ApiTestRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(test)
    db.commit()
    return row(test)


@router.get("/api-tests", tags=["api test bench"])
def list_api_tests(db: DB, provider_id: int | None = None):
    stmt = select(ApiTest).order_by(ApiTest.created_at.desc()).limit(200)
    if provider_id:
        stmt = stmt.where(ApiTest.provider_id == provider_id)
    providers = {p.id: p.name for p in db.scalars(select(Provider))}
    return [{**row(t), "provider": providers.get(t.provider_id)} for t in db.scalars(stmt)]


@router.get("/api-tests/allowlist", tags=["api test bench"])
def api_test_allowlist():
    return {"hosts": get_settings().api_test_allowed_hosts, "simulated_base": "http://localhost:8000/simulated",
            "simulated_tokens": dso_api.SIM_TOKENS}


@router.patch("/api-tests/{test_id}", tags=["api test bench"])
def patch_api_test(test_id: int, body: ApiTestPatch, db: DB):
    t = get_or_404(db, ApiTest, test_id, "API test")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    return row(t)


@router.post("/api-tests/{test_id}/promote", status_code=201, tags=["api test bench"])
def promote_api_test(test_id: int, body: PromoteIn, db: DB):
    t = get_or_404(db, ApiTest, test_id, "API test")
    if not t.provider_id:
        raise HTTPException(422, "Link the test to a provider before recording a verified fact")
    f = ProviderFact(provider_id=t.provider_id, category=body.category, statement=body.statement, evidence_level="verified",
                     source_url=t.url[:500], checked_at=t.created_at)
    db.add(f)
    db.commit()
    return {"fact_id": f.id, "provider_id": t.provider_id}


# =================================================================================== simulated platforms over HTTP
@router.api_route("/simulated/{path:path}", methods=["GET", "POST"], include_in_schema=False)
async def simulated_platform(path: str, request: Request):
    body = await request.body()
    req = httpx.Request(request.method, str(request.url), headers=list(request.headers.items()), content=body)
    resp = dso_api.handle(req)
    return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))


# =================================================================================== cockpit
@router.get("/cockpit", tags=["cockpit"])
def cockpit(db: DB):
    now = datetime.now(UTC)
    cov = compute_coverage(db, now)
    fus = follow_ups(db, now)
    issues = [_issue_out(db, i) for i in db.scalars(select(DataIssue).where(DataIssue.status != "resolved")
                                                     .order_by(DataIssue.detected_at.desc()))]
    sev = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (sev.get(i["severity"], 3), -i["affected_mw"]))
    pending_auth = [{"asset": a["name"], "customer": a["customer"], "country_code": a["country_code"], "status": n["status"]}
                    for a in cov["assets"] for n in a["needs"]
                    if n["need"] == "production_metering" and n["status"] in ("awaiting_authorisation", "authorisation_not_requested")]
    connectors = []
    for c in db.scalars(select(Connector).order_by(Connector.id)):
        h = compute_connector_health(db, c.id, now)
        connectors.append({"id": c.id, "name": c.connector_name, "status": h["status"], "data_origin": c.data_origin,
                           "reason": next((r["reason"] for r in h["reasons"] if r["level"] != "info"), None)})
    gaps = {}
    for a in cov["assets"]:
        for n in a["needs"]:
            if n["status"] != "covered":
                g = gaps.setdefault((a["country_code"], n["need"]), {"country_code": a["country_code"], "need": n["need"],
                                                                     "plants": 0, "capacity_mw": 0.0, "customers": set()})
                g["plants"] += 1
                g["capacity_mw"] += a["capacity_mw"]
                g["customers"].add(a["customer"])
    biggest = sorted(({**g, "capacity_mw": round(g["capacity_mw"], 1), "customers": sorted(g["customers"])} for g in gaps.values()),
                     key=lambda g: -g["capacity_mw"])[:6]
    return {
        "generated_at": now, "coverage": cov["totals"], "by_need": cov["by_need"], "by_country": cov["by_country"],
        "biggest_gaps": biggest,
        "follow_ups": {"overdue": [f for f in fus if f["overdue"]], "upcoming": [f for f in fus if not f["overdue"]][:5]},
        "issues": {"open": len(issues), "high": sum(1 for i in issues if i["severity"] == "high"), "top": issues[:5]},
        "authorisations_pending": pending_auth,
        "connectors": connectors, "lead_times": lead_times(db),
        "demand_for": {f"{g['country_code']}:{g['need']}": demand(cov, g["country_code"], g["need"]) for g in biggest},
    }
