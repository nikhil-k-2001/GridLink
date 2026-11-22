from app.models import Connector


def make_provider(client, **kw):
    body = {"name": "Test Provider", "country_code": "NL", "status": "discovered", **kw}
    return client.post("/providers", json=body)


def test_create_and_list_providers_with_pagination(client):
    for i in range(3):
        assert make_provider(client, name=f"Provider {i}").status_code == 201
    r = client.get("/providers?limit=2&offset=0").json()
    assert r["total"] == 3 and len(r["items"]) == 2
    assert client.get("/providers?country=NL").json()["total"] == 3


def test_provider_validation_errors(client):
    assert make_provider(client, country_code="Netherlands").status_code == 422
    assert make_provider(client, status="live").status_code == 422
    assert make_provider(client, website="not a url").status_code == 422
    assert make_provider(client).status_code == 201
    assert make_provider(client).status_code == 409  # duplicate slug
    assert client.get("/providers/999").status_code == 404


def test_provider_facts_evidence_levels(client):
    pid = make_provider(client).json()["id"]
    ok = client.post(f"/providers/{pid}/facts", json={"category": "access", "statement": "No auth", "evidence_level": "verified"})
    assert ok.status_code == 201
    bad = client.post(f"/providers/{pid}/facts", json={"category": "access", "statement": "x", "evidence_level": "rumour"})
    assert bad.status_code == 422
    assert client.get(f"/providers/{pid}").json()["facts"][0]["evidence_level"] == "verified"


def test_connector_create_rejects_unknown_type(client):
    pid = make_provider(client).json()["id"]
    assert client.post("/connectors", json={"provider_id": pid, "connector_name": "x conn", "connector_type": "ftp"}).status_code == 422
    r = client.post("/connectors", json={"provider_id": pid, "connector_name": "fixture conn", "connector_type": "entsoe_fixture"})
    assert r.status_code == 201 and r.json()["data_origin"] == "simulated"
    assert r.json()["health"]["status"] == "failed"  # never synced


def test_sync_endpoint_validation(client, db, smard_connector):
    assert client.post("/connectors/999/sync").status_code == 404
    r = client.post(f"/connectors/{smard_connector.id}/sync",
                    json={"window_start": "2026-11-20T10:00:00", "window_end": "2026-11-20T11:00:00Z"})
    assert r.status_code == 422  # naive timestamp rejected
    db.get(Connector, smard_connector.id).status = "paused"
    db.commit()
    assert client.post(f"/connectors/{smard_connector.id}/sync").status_code == 409


def test_entsoe_sync_via_api_reports_missing_token(client, entsoe_connector):
    r = client.post(f"/connectors/{entsoe_connector.id}/sync").json()
    assert r["status"] == "failed" and r["error_code"] == "missing_token"
    logs = client.get(f"/connectors/{entsoe_connector.id}/logs").json()
    assert logs["total"] == 1
    errs = client.get(f"/connectors/{entsoe_connector.id}/errors").json()
    assert errs["items"][0]["stage"] == "authenticate"


def test_energy_summary_with_simulated_data(client, providers):
    cid = client.post("/connectors", json={"provider_id": providers["entsoe"].id, "connector_name": "sim conn",
                                           "connector_type": "entsoe_fixture",
                                           "config": {"fixed_window": ["2026-11-13T23:00:00+00:00", "2026-11-20T23:00:00+00:00"]}}).json()["id"]
    assert client.post(f"/connectors/{cid}/sync").json()["status"] == "partial"
    q = "metric_type=generation&start=2026-11-14T00:00:00Z&end=2026-11-15T00:00:00Z&bucket=hour"
    s = client.get(f"/energy-records/summary?{q}").json()
    solar = next(x for x in s["series"] if x["energy_source"] == "solar")
    assert len(solar["points"]) == 24 and solar["unit"] == "MW" and solar["data_origin"] == "simulated"
    assert any(w["type"] == "simulated" for w in s["warnings"])
    assert s["provenance"][0]["data_origins"] == ["simulated"]
    real_only = client.get(f"/energy-records/summary?{q}&include_simulated=false").json()
    assert real_only["series"] == []
    assert client.get("/energy-records/summary?start=2026-01-01T00:00:00Z&end=2026-11-01T00:00:00Z").status_code == 422
    recs = client.get("/energy-records?limit=5&data_origin=simulated").json()
    assert recs["limit"] == 5 and len(recs["items"]) == 5


def test_prioritisation_scoring_ranking_and_weights(client):
    pid = make_provider(client).json()["id"]
    base = {"provider_id": pid, "customer_value": 5, "data_importance": 5, "commercial_opportunity": 1,
            "strategic_relevance": 5, "technical_effort": 1, "access_complexity": 1}
    a = client.post("/integration-opportunities", json={**base, "title": "Easy win"}).json()
    assert a["priority_score"] == 25.0  # (1*1*1)/(0.2*0.2)
    b = client.post("/integration-opportunities", json={**base, "title": "Hard one", "technical_effort": 5, "access_complexity": 5}).json()
    assert b["priority_score"] == 1.0
    listing = client.get("/integration-opportunities").json()
    assert [o["title"] for o in listing["items"]] == ["Easy win", "Hard one"]
    assert "not an objective market valuation" in listing["disclaimer"]
    assert client.post("/integration-opportunities", json={**base, "title": "bad", "customer_value": 6}).status_code == 422
    w = client.put("/prioritisation/weights", json={"commercial_opportunity": 1}).json()
    assert w["commercial_opportunity"] == 1
    assert client.get("/integration-opportunities").json()["items"][0]["priority_score"] == 5.0  # CO 0.2 now counts
    upd = client.patch(f"/integration-opportunities/{b['id']}", json={"rationale": "Needs OAuth", "decision_status": "deferred"}).json()
    assert upd["decision_status"] == "deferred"


def test_investigation_template_and_exports(client):
    pid = make_provider(client, name="Doc Provider").json()["id"]
    inv = client.post("/investigations", json={"provider_id": pid, "overview": "Overview text", "next_steps": "Do X"}).json()
    assert inv["completion"] == round(100 * 2 / 15, 1)
    assert client.post("/investigations", json={"provider_id": pid}).status_code == 409
    assert len(client.get("/investigations/template").json()) == 15
    md = client.get(f"/investigations/{inv['id']}/export?format=md")
    assert md.status_code == 200 and "# Provider onboarding report: Doc Provider" in md.text and "## 15. Next steps" in md.text
    csv = client.get(f"/investigations/{inv['id']}/export?format=csv")
    assert csv.text.splitlines()[0].startswith("provider,country")
    assert client.get(f"/investigations/{inv['id']}/export?format=pdf").status_code == 422


def test_settings_never_expose_secrets_and_ai_is_optional(client):
    s = client.get("/settings/status").json()
    assert "entsoe_api_token" not in s and s["entsoe_token_configured"] is False
    r = client.post("/ai/assist", json={"task": "summarise_documentation", "text": "docs"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]


def test_overview(client, smard_connector):
    o = client.get("/overview").json()
    assert o["connector_status_counts"]["failed"] == 1 and o["connectors"][0]["name"] == "SMARD test"
