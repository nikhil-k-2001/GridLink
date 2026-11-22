"""API test bench: run a real request against an allow-listed provider host (or the in-process simulated
DSO platforms), and keep the redacted request + response excerpt as evidence for an investigation."""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import ApiTest
from app.simulated import dso_api

SECRET_KEYS = re.compile(r"(token|key|secret|password|authorization|apikey|api_key)", re.I)
EXCERPT_LIMIT = 20_000
LOCAL_HOSTS = {"localhost", "127.0.0.1"}


class ApiTestRejected(ValueError):
    pass


def redact(d: dict[str, str]) -> dict[str, str]:
    return {k: ("***REDACTED***" if SECRET_KEYS.search(k) else v) for k, v in (d or {}).items()}


def _excerpt(resp: httpx.Response) -> str:
    ctype = resp.headers.get("content-type", "")
    body = resp.content
    if body[:2] == b"PK":
        try:
            names = zipfile.ZipFile(io.BytesIO(body)).namelist()
            return f"[ZIP archive, {len(body)} bytes] files: {', '.join(names)}"
        except zipfile.BadZipFile:
            return f"[binary, {len(body)} bytes]"
    if "json" in ctype:
        try:
            return json.dumps(resp.json(), indent=2, ensure_ascii=False)[:EXCERPT_LIMIT]
        except ValueError:
            pass
    try:
        return body.decode("utf-8-sig")[:EXCERPT_LIMIT]
    except UnicodeDecodeError:
        return f"[binary {ctype or 'content'}, {len(body)} bytes]"


def check_target(url: str, settings: Settings) -> str:
    """Return 'simulated' or 'remote'; raise when the target is not allowed."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ApiTestRejected("URL must be http(s) with a host")
    if u.hostname in LOCAL_HOSTS or u.hostname in settings.self_hosts:
        if u.path.startswith("/simulated/"):
            return "simulated"
        raise ApiTestRejected("Only the /simulated/ DSO platforms may be called on this API's own host")
    if u.scheme != "https":
        raise ApiTestRejected("External providers must be called over https")
    if u.hostname not in settings.api_test_allowed_hosts:
        raise ApiTestRejected(f"Host '{u.hostname}' is not on the test-bench allowlist ({', '.join(settings.api_test_allowed_hosts)}). "
                              "Add it via API_TEST_ALLOWED_HOSTS if it is a provider you are investigating.")
    return "remote"


def run_test(settings: Settings, *, name: str, method: str, url: str, params: dict[str, str], headers: dict[str, str],
             body: str | None, provider_id: int | None, transport: httpx.BaseTransport | None = None) -> ApiTest:
    target = check_target(url, settings)
    if target == "simulated":
        transport = dso_api.transport()
    test = ApiTest(provider_id=provider_id, name=name, method=method, url=url, params=redact(params),
                   request_headers=redact(headers), request_body=body)
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=20, transport=transport, follow_redirects=False,
                          headers={"User-Agent": "GridLink-API-test-bench/0.1"}) as client:
            resp = client.request(method, url, params=params or None, headers=headers or None,
                                  content=body.encode() if body else None)
        test.status_code = resp.status_code
        test.content_type = resp.headers.get("content-type")
        test.response_headers = {k: v for k, v in resp.headers.items() if k.lower() in
                                 ("content-type", "content-length", "retry-after", "date", "content-disposition", "x-ratelimit-remaining")}
        test.response_size = len(resp.content)
        test.response_excerpt = _excerpt(resp)
        test.verdict = "works" if resp.status_code < 300 else "fails" if resp.status_code >= 400 else "inconclusive"
    except httpx.HTTPError as exc:
        test.error = f"{type(exc).__name__}: {exc}"
        test.verdict = "fails"
    test.duration_ms = int((time.perf_counter() - started) * 1000)
    return test
