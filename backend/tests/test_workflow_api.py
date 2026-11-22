from datetime import UTC, datetime, timedelta

import httpx

from app.config import Settings
from app.services import api_tests


def pid(client, q):
    return client.get(f"/providers?q={q}").json()["items"][0]["id"]


def test_countries_and_playbook(client, workspace):
    data = client.get("/countries").json()
    codes = {c["country_code"] for c in data["countries"]}
    assert codes == {"DE", "FR", "ES", "IT", "NL"}
    it = client.get("/countries/IT").json()
    assert it["profile"]["status"] == "blocked" and len(it["playbook"]) == 10
    assert any(r["is_fallback"] for r in it["routes"])
    r = client.patch("/countries/IT/playbook/test", json={"status": "done", "notes": "SCADA export sample validated"}).json()
    assert r["status"] == "done" and r["completed_at"]
    assert client.patch("/countries/IT/playbook/unknown", json={"status": "done"}).status_code == 404
    assert data["lead_times"]["samples"] == 2


def test_access_request_lifecycle_and_follow_ups(client, workspace):
    p = pid(client, "Dutch")
    req = client.post("/access-requests", json={"provider_id": p, "country_code": "NL", "data_need": "production_metering",
                                               "subject": "Metering data for Flevoland Wind"}).json()
    assert req["status"] == "draft"
    due = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    client.post("/interactions", json={"provider_id": p, "access_request_id": req["id"], "channel": "email", "direction": "outbound",
                                       "summary": "Asked for the metering access process", "next_follow_up": due})
    assert next(r for r in client.get("/access-requests").json() if r["id"] == req["id"])["status"] == "sent"
    fu = next(f for f in client.get("/follow-ups").json() if f["request_id"] == req["id"])
    assert fu["overdue"] is True
    client.post("/interactions", json={"provider_id": p, "access_request_id": req["id"], "channel": "email", "direction": "inbound",
                                       "summary": "They replied with a form"})
    assert next(r for r in client.get("/access-requests").json() if r["id"] == req["id"])["status"] == "in_review"
    closed = client.patch(f"/access-requests/{req['id']}", json={"status": "granted"}).json()
    assert closed["closed_at"]


def test_issue_cannot_close_without_resolution(client, workspace):
    i = client.post("/issues", json={"title": "Missing November data for Puglia", "severity": "high"}).json()
    assert client.patch(f"/issues/{i['id']}", json={"status": "resolved"}).status_code == 422
    ok = client.patch(f"/issues/{i['id']}", json={"status": "resolved", "resolution": "Backfilled from monthly export"}).json()
    assert ok["status"] == "resolved" and ok["resolved_at"]


def test_coverage_and_cockpit_endpoints(client, workspace):
    cov = client.get("/coverage").json()
    assert cov["totals"]["plants"] == 16 and cov["totals"]["pairs"] == 35
    ck = client.get("/cockpit").json()
    assert ck["follow_ups"]["overdue"] and ck["biggest_gaps"] and "lead_times" in ck
    opp = next(o for o in client.get("/integration-opportunities").json()["items"] if o["title"].startswith("ENTSO-E prices"))
    # no SMARD sync in the test DB, so German plants also lack prices: all 16 plants
    assert opp["demand"]["plants"] == 16 and len(opp["demand"]["customers"]) == 3


class TestApiTestBench:
    def test_allowlist(self):
        s = Settings(database_url="sqlite://")
        assert api_tests.check_target("http://localhost:8000/simulated/fr-dso/x", s) == "simulated"
        assert api_tests.check_target("https://web-api.tp.entsoe.eu/api", s) == "remote"
        for bad in ("http://169.254.169.254/", "http://localhost:5434/", "https://evil.example.com/", "ftp://smard.de/",
                    "http://web-api.tp.entsoe.eu/api"):
            try:
                api_tests.check_target(bad, s)
                raise AssertionError(bad)
            except api_tests.ApiTestRejected:
                pass

    def test_secrets_are_redacted(self):
        t = api_tests.run_test(Settings(database_url="sqlite://"), name="x", method="GET", url="https://web-api.tp.entsoe.eu/api",
                               params={"securityToken": "abc", "documentType": "A44"}, headers={"Authorization": "Bearer x"},
                               body=None, provider_id=None, transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no")))
        assert t.params == {"securityToken": "***REDACTED***", "documentType": "A44"}
        assert t.request_headers == {"Authorization": "***REDACTED***"} and t.status_code == 401 and t.verdict == "fails"

    def test_run_simulated_and_promote_to_verified_fact(self, client, workspace):
        p = pid(client, "Enedis")
        t = client.post("/api-tests/run", json={"name": "FR consent check", "provider_id": p,
                                                "url": "http://localhost:8000/simulated/fr-dso/v5/metering_data/production_load_curve",
                                                "params": {"usage_point_id": "99000000000101", "start": "2026-11-18", "end": "2026-11-19"},
                                                "headers": {"Authorization": "Bearer sim-fr-oauth-token"}}).json()
        assert t["status_code"] in (200, 429) and t["request_headers"]["Authorization"] == "***REDACTED***"
        assert client.post("/api-tests/run", json={"name": "x", "url": "https://example.com/"}).status_code == 422
        f = client.post(f"/api-tests/{t['id']}/promote", json={"statement": "Simulated FR API returns 30-min W values"}).json()
        facts = client.get(f"/providers/{p}").json()["facts"]
        assert any(x["id"] == f["fact_id"] and x["evidence_level"] == "verified" for x in facts)
