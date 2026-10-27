import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.cache import cache_key, get, set
from app.config import FETCH_TIMEOUT
from app.http_clients import CircuitBreaker, RateLimitedClient
from app.logging_conf import get_logger

logger = get_logger(__name__)


class FetchStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CACHED = "cached"


@dataclass
class FetchResult:
    status: FetchStatus
    items: list[dict] = field(default_factory=list)
    error: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str | None = None
    cached: bool = False
    duration_ms: float = 0.0


@dataclass
class FetcherConfig:
    name: str
    enabled: bool = True
    rate_limit: int = 10
    rate_period: float = 60.0
    timeout: float = FETCH_TIMEOUT
    cache_ttl: int = 3600
    retry_count: int = 3
    retry_base_delay: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    extra: dict = field(default_factory=dict)


@dataclass
class DeadLetterEntry:
    """Entry in the dead letter queue for failed fetches."""
    fetcher_name: str
    error: str
    timestamp: datetime
    attempt: int
    max_retries: int
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


class DeadLetterQueue:
    """Queue for storing failed fetch attempts for later retry."""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._queue: list[DeadLetterEntry] = []
    
    def add(self, entry: DeadLetterEntry):
        if len(self._queue) >= self.max_size:
            # Remove oldest entry
            self._queue.pop(0)
        self._queue.append(entry)
        logger.warning(
            "Added to dead letter queue: %s (attempt %d/%d)",
            entry.fetcher_name,
            entry.attempt,
            entry.max_retries,
        )
    
    def get_all(self) -> list[DeadLetterEntry]:
        return list(self._queue)
    
    def remove(self, entry_id: str) -> bool:
        for i, entry in enumerate(self._queue):
            if entry.id == entry_id:
                self._queue.pop(i)
                return True
        return False
    
    def clear(self):
        self._queue.clear()
    
    def __len__(self):
        return len(self._queue)


# Global dead letter queue
dead_letter_queue = DeadLetterQueue()


class BaseFetcher(ABC):
    """Base class for all data fetchers."""
    
    def __init__(self, config: FetcherConfig):
        self.config = config
        self.client = RateLimitedClient(
            base_url=config.extra.get("base_url", ""),
            rate_limit=config.rate_limit,
            rate_period=config.rate_period,
            circuit_breaker=CircuitBreaker(
                failure_threshold=config.circuit_breaker_threshold,
                recovery_timeout=config.circuit_breaker_timeout,
            ),
            timeout=config.timeout,
        )
        self._etag: str | None = None
        self._last_modified: str | None = None
    
    def _get_conditional_headers(self) -> dict:
        """Get headers for conditional requests (ETag/If-Modified-Since)."""
        headers = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
        return headers
    
    def _update_conditional_state(self, response):
        """Update ETag and Last-Modified from response headers."""
        etag = response.headers.get("ETag") or response.headers.get("etag")
        last_modified = response.headers.get("Last-Modified") or response.headers.get("last-modified")
        if etag:
            self._etag = etag
        if last_modified:
            self._last_modified = last_modified
    
    @abstractmethod
    def fetch(self) -> FetchResult:
        """Fetch data from source. Must be implemented by subclasses."""
    
    @abstractmethod
    def parse_item(self, raw_item: Any) -> dict | None:
        """Parse raw item into standardized format."""
    
    def get_cache_key(self, suffix: str = "") -> str:
        return cache_key("fetcher", self.config.name, suffix)
    
    def get_etag(self) -> str | None:
        return self._etag
    
    def get_last_modified(self) -> str | None:
        return self._last_modified
    
    def set_etag(self, etag: str | None):
        self._etag = etag
    
    def set_last_modified(self, lm: str | None):
        self._last_modified = lm
    
    def compute_content_hash(self, items: list[dict]) -> str:
        content = json.dumps(items, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def is_content_changed(self, new_hash: str) -> bool:
        cache_k = self.get_cache_key("content_hash")
        cached_hash = get(cache_k)
        if cached_hash is None:
            return True
        return cached_hash != new_hash
    
    def store_content_hash(self, hash_val: str):
        cache_k = self.get_cache_key("content_hash")
        set(cache_k, hash_val, self.config.cache_ttl)
    
    def fetch_with_retry(self) -> FetchResult:
        """Fetch with retry logic and dead letter queue integration."""
        last_error = None
        for attempt in range(1, self.config.retry_count + 1):
            try:
                result = self.fetch()
                if result.status == FetchStatus.SUCCESS:
                    # Check if content actually changed
                    if result.items:
                        content_hash = self.compute_content_hash(result.items)
                        if not self.is_content_changed(content_hash):
                            logger.info("Content unchanged for %s, skipping", self.config.name)
                            return FetchResult(
                                status=FetchStatus.SKIPPED,
                                items=[],
                                content_hash=content_hash,
                            )
                        self.store_content_hash(content_hash)
                        result.content_hash = content_hash
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    "Fetch attempt %d/%d failed for %s: %s",
                    attempt,
                    self.config.retry_count,
                    self.config.name,
                    e,
                )
                if attempt < self.config.retry_count:
                    import time
                    delay = self.config.retry_base_delay * (2 ** (attempt - 1))
                    time.sleep(min(delay, 60))
        
        # All retries failed - add to dead letter queue
        from app.fetchers.base import DeadLetterEntry, dead_letter_queue
        entry = DeadLetterEntry(
            fetcher_name=self.config.name,
            error=str(last_error),
            timestamp=datetime.utcnow(),
            attempt=self.config.retry_count,
            max_retries=self.config.retry_count,
            payload={"error": str(last_error)},
        )
        dead_letter_queue.add(entry)
        
        return FetchResult(
            status=FetchStatus.FAILED,
            error=str(last_error),
        )
    
    def close(self):
        self.client.close()


class FetcherRegistry:
    """Registry for managing fetcher plugins."""
    
    def __init__(self):
        self._fetchers: dict[str, BaseFetcher] = {}
        self._configs: dict[str, FetcherConfig] = {}
    
    def register(self, fetcher_class: type[BaseFetcher], config: FetcherConfig):
        """Register a fetcher class with its configuration."""
        if not config.enabled:
            logger.info("Fetcher %s is disabled, skipping registration", config.name)
            return
        self._configs[config.name] = config
        fetcher = fetcher_class(config)
        self._fetchers[config.name] = fetcher
        logger.info("Registered fetcher: %s", config.name)
    
    def get(self, name: str) -> BaseFetcher | None:
        return self._fetchers.get(name)
    
    def get_all(self) -> list[BaseFetcher]:
        return list(self._fetchers.values())
    
    def get_enabled(self) -> list[BaseFetcher]:
        return [f for f in self._fetchers.values() if f.config.enabled]
    
    def get_config(self, name: str) -> FetcherConfig | None:
        return self._configs.get(name)
    
    def run_all(self) -> dict[str, FetchResult]:
        """Run all enabled fetchers with retry logic and return results."""
        results = {}
        for fetcher in self.get_enabled():
            try:
                logger.info("Running fetcher: %s", fetcher.config.name)
                result = fetcher.fetch_with_retry()
                results[fetcher.config.name] = result
            except Exception as e:
                logger.error("Fetcher %s failed: %s", fetcher.config.name, e)
                results[fetcher.config.name] = FetchResult(
                    status=FetchStatus.FAILED,
                    error=str(e),
                )
        return results
    
    def close_all(self):
        for fetcher in self._fetchers.values():
            fetcher.close()
        self._fetchers.clear()
        self._configs.clear()


# Global registry instance
fetcher_registry = FetcherRegistry()