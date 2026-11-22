"""HTTP client wrapper: timeouts, exponential backoff with jitter, Retry-After, rate limiting and
per-sync request statistics. Shared by every connector so reliability behaviour is uniform."""
from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

import httpx

log = logging.getLogger("gridlink.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class RequestStats:
    requests: int = 0  # attempts actually sent
    failures: int = 0  # attempts that failed (transport error or retryable/4xx/5xx status)
    retries: int = 0
    rate_limited: int = 0
    statuses: list[int] = field(default_factory=list)


class HTTPRequestFailed(Exception):
    def __init__(self, code: str, message: str, status: int | None = None, attempts: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.attempts = attempts


_BODY_WAIT = re.compile(r"(?:try again|retry) in (\d+(?:\.\d+)?) ?s", re.I)


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """Retry-After header (seconds or HTTP date); some providers only say it in the body
    (e.g. Energi Data Service: "Rate limit is exceeded. Try again in 36 seconds.")."""
    header = resp.headers.get("Retry-After")
    if not header:
        m = _BODY_WAIT.search(resp.text[:500]) if resp.content else None
        return float(m.group(1)) if m else None
    try:
        return max(0.0, float(header))
    except ValueError:
        try:
            dt = parsedate_to_datetime(header)
            return max(0.0, dt.timestamp() - time.time())
        except (TypeError, ValueError):
            return None


class RetryingClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        min_interval_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        redact: Callable[[str], str] | None = None,
    ):
        self.client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "GridLink/0.1 (data-integration)"})
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.min_interval = min_interval_seconds
        self.sleep = sleep
        self.redact = redact or (lambda s: s)
        self.stats = RequestStats()
        self._last_request_at: float | None = None

    def _backoff(self, attempt: int) -> float:
        delay = min(self.backoff_max, self.backoff_base * (2**attempt))
        return delay + random.uniform(0, delay * 0.1)

    def _throttle(self) -> None:
        if self.min_interval and self._last_request_at is not None:
            wait = self.min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                self.sleep(wait)
        self._last_request_at = time.monotonic()

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send with retries. Returns the final response for non-retryable statuses (including 4xx) so the
        connector can translate provider-specific error bodies; raises HTTPRequestFailed when retries are
        exhausted on timeouts, transport errors or retryable statuses."""
        last_error: HTTPRequestFailed | None = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                self.stats.retries += 1
            self._throttle()
            self.stats.requests += 1
            safe_url = self.redact(url)
            try:
                resp = self.client.request(method, url, **kwargs)
            except httpx.TimeoutException:
                self.stats.failures += 1
                last_error = HTTPRequestFailed("timeout", f"Request timed out: {method} {safe_url}", attempts=attempt + 1)
                log.warning("http timeout", extra={"url": safe_url, "attempt": attempt + 1})
                if attempt < self.max_retries:
                    self.sleep(self._backoff(attempt))
                continue
            except httpx.TransportError as exc:
                self.stats.failures += 1
                last_error = HTTPRequestFailed(
                    "network_error", f"Network error contacting provider: {type(exc).__name__}", attempts=attempt + 1
                )
                log.warning("http transport error", extra={"url": safe_url, "attempt": attempt + 1, "error": str(exc)})
                if attempt < self.max_retries:
                    self.sleep(self._backoff(attempt))
                continue

            self.stats.statuses.append(resp.status_code)
            if resp.status_code in RETRYABLE_STATUS:
                self.stats.failures += 1
                if resp.status_code == 429:
                    self.stats.rate_limited += 1
                code = "rate_limited" if resp.status_code == 429 else "provider_server_error"
                last_error = HTTPRequestFailed(
                    code, f"Provider returned HTTP {resp.status_code}", status=resp.status_code, attempts=attempt + 1
                )
                log.warning("http retryable status", extra={"url": safe_url, "status": resp.status_code, "attempt": attempt + 1})
                if attempt < self.max_retries:
                    wait = _retry_after_seconds(resp)
                    self.sleep(min(self.backoff_max, wait) if wait is not None else self._backoff(attempt))
                continue

            if resp.status_code >= 400:
                self.stats.failures += 1
            return resp

        assert last_error is not None
        raise last_error
