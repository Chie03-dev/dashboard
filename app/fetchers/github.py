from datetime import datetime
from typing import Any

from app.cache import get, set
from app.config import GITHUB_TOKEN
from app.fetchers.base import BaseFetcher, FetcherConfig, FetchResult, FetchStatus
from app.logging_conf import get_logger

logger = get_logger(__name__)


class GitHubFetcher(BaseFetcher):
    """Fetcher for GitHub notifications."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/notifications"
    
    def fetch(self) -> FetchResult:
        start = datetime.now()
        cache_k = self.get_cache_key("data")
        
        # Check cache first
        cached = get(cache_k)
        if cached is not None:
            return FetchResult(
                status=FetchStatus.CACHED,
                items=cached,
                cached=True,
            )
        
        if not self.config.extra.get("github_token"):
            return FetchResult(
                status=FetchStatus.SKIPPED,
                error="GITHUB_TOKEN not configured",
            )
        
        try:
            response = self.client.get(
                self.path,
                headers={
                    "Authorization": f"token {self.config.extra['github_token']}",
                    "Accept": "application/vnd.github+json",
                },
            )
            data = response.json() or []
            
            items = []
            for n in data:
                try:
                    parsed = self.parse_item(n)
                    if parsed:
                        items.append(parsed)
                except Exception as e:
                    logger.warning("GitHub item parse error: %s", e)
            
            # Cache results
            set(cache_k, items, self.config.cache_ttl)
            
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return FetchResult(
                status=FetchStatus.SUCCESS,
                items=items,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("GitHub fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, n: Any) -> dict | None:
        if not isinstance(n, dict):
            return None
        subject = n.get("subject") or {}
        title = subject.get("title") or n.get("id")
        url = subject.get("url")
        if not url:
            repo = n.get("repository") or {}
            url = repo.get("html_url")
        return {
            "source": "github",
            "external_id": str(n.get("id", "")),
            "title": title,
            "url": url,
        }


def create_github_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="github",
        enabled=bool(GITHUB_TOKEN),
        rate_limit=30,
        rate_period=60.0,
        cache_ttl=1800,  # 30 minutes
        extra={"base_url": "https://api.github.com", "github_token": GITHUB_TOKEN},
    )
    return GitHubFetcher(config)