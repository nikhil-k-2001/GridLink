import httpx
import pytest

from app.connectors.http import HTTPRequestFailed, RetryingClient


def client(handler, retries=3):
    sleeps = []
    c = RetryingClient(httpx.Client(transport=httpx.MockTransport(handler)), max_retries=retries, backoff_base=1.0,
                       sleep=sleeps.append)
    return c, sleeps


def test_retries_server_errors_with_exponential_backoff():
    calls = iter([503, 502, 200])
    c, sleeps = client(lambda r: httpx.Response(next(calls)))
    assert c.request("GET", "https://x").status_code == 200
    assert c.stats.requests == 3 and c.stats.retries == 2 and c.stats.failures == 2
    assert 1.0 <= sleeps[0] < 1.2 and 2.0 <= sleeps[1] < 2.3  # base * 2^attempt + jitter


def test_honours_retry_after_on_429():
    calls = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)])
    c, sleeps = client(lambda r: next(calls))
    c.request("GET", "https://x")
    assert sleeps == [7.0] and c.stats.rate_limited == 1


def test_gives_up_after_max_retries():
    c, sleeps = client(lambda r: httpx.Response(500), retries=2)
    with pytest.raises(HTTPRequestFailed) as e:
        c.request("GET", "https://x")
    assert e.value.code == "provider_server_error" and e.value.attempts == 3 and len(sleeps) == 2


def test_timeouts_are_retried():
    state = {"n": 0}

    def handler(r):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ReadTimeout("slow", request=r)
        return httpx.Response(200)

    c, _ = client(handler)
    assert c.request("GET", "https://x").status_code == 200 and c.stats.retries == 1


def test_client_errors_are_not_retried():
    c, sleeps = client(lambda r: httpx.Response(400, text="bad"))
    assert c.request("GET", "https://x").status_code == 400
    assert c.stats.requests == 1 and sleeps == [] and c.stats.failures == 1


def test_network_error_exhaustion():
    def handler(r):
        raise httpx.ConnectError("down", request=r)

    c, _ = client(handler, retries=1)
    with pytest.raises(HTTPRequestFailed) as e:
        c.request("GET", "https://x")
    assert e.value.code == "network_error"
