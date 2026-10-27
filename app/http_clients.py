import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

import httpx
from prometheus_client import Counter, Histogram

from app.config import FETCH_TIMEOUT

logger = logging.getLogger(__name__)

EXTERNAL_API_LATENCY = Histogram("dashboard_external_api_latency_seconds", "External API latency", ["api"])
EXTERNAL_API_ERRORS = Counter("dashboard_external_api_errors_total", "External API errors", ["api", "error_type"])
EXTERNAL_API_REQUESTS = Counter("dashboard_external_api_requests_total", "External API requests", ["api", "status"])


@dataclass
class TokenBucket:
    rate: int
    per: float
    tokens: float = field(init=False)
    last: float = field(init=False)
    lock: Lock = field(default_factory=Lock, init=False)

    def __post_init__(self):
        self.tokens = float(self.rate)
        self.last = time.monotonic()

    def take(self) -> float:
        with self.lock:
            now = time.monotonic()
            since_last = now - self.last
            self.tokens = min(self.rate, self.tokens + since_last * self.rate / self.per)
            if self.tokens >= 1:
                self.tokens -= 1
                self.last = now
                return 0.0
            wait = (1 - self.tokens) * self.per / self.rate
            self.tokens = 0
            self.last = now
            return wait


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0, half_open_requests: int = 3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"
        self.half_open_successes = 0
        self.lock = Lock()

    def record_success(self):
        with self.lock:
            if self.state == "half-open":
                self.half_open_successes += 1
                if self.half_open_successes >= self.half_open_requests:
                    self.state = "closed"
                    self.failures = 0
                    self.half_open_successes = 0
                    logger.info("Circuit breaker closed after recovery")
            elif self.state == "closed":
                self.failures = 0

    def record_failure(self):
        with self.lock:
            self.failures += 1
            self.last_failure_time = time.monotonic()
            if self.state == "half-open":
                self.state = "open"
                self.half_open_successes = 0
                logger.warning("Circuit breaker reopened after half-open failure")
            elif self.state == "closed" and self.failures >= self.failure_threshold:
                self.state = "open"
                logger.warning("Circuit breaker opened after %d failures", self.failures)

    def can_execute(self) -> bool:
        with self.lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                if self.last_failure_time and (time.monotonic() - self.last_failure_time) >= self.recovery_timeout:
                    self.state = "half-open"
                    self.half_open_successes = 0
                    logger.info("Circuit breaker half-open, allowing test requests")
                    return True
                return False
            return True


class RateLimitedClient:
    def __init__(
        self,
        base_url: str,
        rate_limit: int,
        rate_period: float = 60.0,
        circuit_breaker: Optional[CircuitBreaker] = None,
        timeout: float = FETCH_TIMEOUT,
    ):
        self.base_url = base_url
        self.bucket = TokenBucket(rate_limit, rate_period)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.client = httpx.Client(timeout=timeout)
        self.timeout = timeout

    def _respect_retry_after(self, response: httpx.Response) -> Optional[float]:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return None

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        api_name = self.base_url.replace("https://", "").replace("http://", "").split("/")[0]
        if not self.circuit_breaker.can_execute():
            EXTERNAL_API_ERRORS.labels(api=api_name, error_type="circuit_breaker_open").inc()
            raise httpx.RequestError("Circuit breaker is open", request=httpx.Request(method, self.base_url + path))

        wait = self.bucket.take()
        if wait > 0:
            time.sleep(wait)

        url = self.base_url + path
        max_retries = 3
        for attempt in range(max_retries):
            start = time.perf_counter()
            try:
                response = self.client.request(method, url, **kwargs)
                duration = time.perf_counter() - start
                EXTERNAL_API_LATENCY.labels(api=api_name).observe(duration)
                if response.status_code == 429:
                    EXTERNAL_API_REQUESTS.labels(api=api_name, status="429").inc()
                    retry_after = self._respect_retry_after(response)
                    if retry_after:
                        time.sleep(retry_after)
                    else:
                        time.sleep(2**attempt)
                    continue
                response.raise_for_status()
                EXTERNAL_API_REQUESTS.labels(api=api_name, status=str(response.status_code)).inc()
                self.circuit_breaker.record_success()
                return response
            except httpx.HTTPStatusError as e:
                duration = time.perf_counter() - start
                EXTERNAL_API_LATENCY.labels(api=api_name).observe(duration)
                EXTERNAL_API_REQUESTS.labels(api=api_name, status=str(e.response.status_code)).inc()
                if e.response.status_code >= 500:
                    EXTERNAL_API_ERRORS.labels(api=api_name, error_type="http_5xx").inc()
                    self.circuit_breaker.record_failure()
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue
                raise
            except (httpx.RequestError, httpx.TimeoutException) as e:
                duration = time.perf_counter() - start
                EXTERNAL_API_LATENCY.labels(api=api_name).observe(duration)
                EXTERNAL_API_REQUESTS.labels(api=api_name, status="error").inc()
                EXTERNAL_API_ERRORS.labels(api=api_name, error_type=type(e).__name__).inc()
                self.circuit_breaker.record_failure()
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                raise
        EXTERNAL_API_ERRORS.labels(api=api_name, error_type="max_retries").inc()
        raise httpx.RequestError("Max retries exceeded", request=httpx.Request(method, url))

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


_gamerpower_client: Optional[RateLimitedClient] = None
_epic_client: Optional[RateLimitedClient] = None
_hn_client: Optional[RateLimitedClient] = None
_github_client: Optional[RateLimitedClient] = None
_cheapshark_client: Optional[RateLimitedClient] = None
_openmeteo_client: Optional[RateLimitedClient] = None


def get_gamerpower_client() -> RateLimitedClient:
    global _gamerpower_client
    if _gamerpower_client is None:
        from app.config import RATE_LIMIT_GAMERPOWER
        _gamerpower_client = RateLimitedClient(
            base_url="https://www.gamerpower.com",
            rate_limit=RATE_LIMIT_GAMERPOWER,
            rate_period=60.0,
        )
    return _gamerpower_client


def get_epic_client() -> RateLimitedClient:
    global _epic_client
    if _epic_client is None:
        from app.config import RATE_LIMIT_EPIC
        _epic_client = RateLimitedClient(
            base_url="https://store-site-backend-static.ak.epicgames.com",
            rate_limit=RATE_LIMIT_EPIC,
            rate_period=60.0,
        )
    return _epic_client


def get_hn_client() -> RateLimitedClient:
    global _hn_client
    if _hn_client is None:
        from app.config import RATE_LIMIT_HN
        _hn_client = RateLimitedClient(
            base_url="https://hacker-news.firebaseio.com",
            rate_limit=RATE_LIMIT_HN,
            rate_period=60.0,
        )
    return _hn_client


def get_github_client() -> RateLimitedClient:
    global _github_client
    if _github_client is None:
        from app.config import RATE_LIMIT_GITHUB
        _github_client = RateLimitedClient(
            base_url="https://api.github.com",
            rate_limit=RATE_LIMIT_GITHUB,
            rate_period=60.0,
        )
    return _github_client


def get_cheapshark_client() -> RateLimitedClient:
    global _cheapshark_client
    if _cheapshark_client is None:
        from app.config import RATE_LIMIT_CHEAPSHARK
        _cheapshark_client = RateLimitedClient(
            base_url="https://www.cheapshark.com",
            rate_limit=RATE_LIMIT_CHEAPSHARK,
            rate_period=60.0,
        )
    return _cheapshark_client


def get_openmeteo_client() -> RateLimitedClient:
    global _openmeteo_client
    if _openmeteo_client is None:
        from app.config import RATE_LIMIT_OPENMETEO
        _openmeteo_client = RateLimitedClient(
            base_url="https://api.open-meteo.com",
            rate_limit=RATE_LIMIT_OPENMETEO,
            rate_period=60.0,
        )
    return _openmeteo_client


def close_all_clients():
    global _gamerpower_client, _epic_client, _hn_client, _github_client, _cheapshark_client, _openmeteo_client
    for client in [_gamerpower_client, _epic_client, _hn_client, _github_client, _cheapshark_client, _openmeteo_client]:
        if client:
            client.close()