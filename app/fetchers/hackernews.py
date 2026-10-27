from datetime import datetime
from typing import Any, Optional

from app.cache import get, set
from app.config import HN_LIMIT
from app.fetchers.base import BaseFetcher, FetchResult, FetchStatus, FetcherConfig
from app.logging_conf import get_logger

logger = get_logger(__name__)


class HackerNewsFetcher(BaseFetcher):
    """Fetcher for HackerNews top stories."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.top_path = "/v0/topstories.json"
        self.item_path = "/v0/item/{}.json"
    
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
        
        try:
            response = self.client.get(self.top_path)
            ids = response.json() or []
            
            items = []
            for sid in ids[:self.config.extra.get("limit", HN_LIMIT)]:
                try:
                    ir = self.client.get(self.item_path.format(sid))
                    item = ir.json() or {}
                    if not item.get("title"):
                        continue
                    parsed = self.parse_item(item)
                    if parsed:
                        items.append(parsed)
                except Exception as e:
                    logger.warning("HN item %s failed: %s", sid, e)
            
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
            logger.error("HN fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, item: Any) -> Optional[dict]:
        if not isinstance(item, dict):
            return None
        if not item.get("title"):
            return None
        return {
            "source": "hackernews",
            "external_id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "url": item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}",
        }


def create_hn_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="hackernews",
        enabled=True,
        rate_limit=30,
        rate_period=60.0,
        cache_ttl=1800,  # 30 minutes
        extra={"base_url": "https://hacker-news.firebaseio.com", "limit": 15},
    )
    return HackerNewsFetcher(config)