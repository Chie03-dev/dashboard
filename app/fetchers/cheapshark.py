from datetime import datetime
from typing import Any, Optional

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetchResult, FetchStatus, FetcherConfig
from app.logging_conf import get_logger

logger = get_logger(__name__)


class CheapSharkFetcher(BaseFetcher):
    """Fetcher for CheapShark deals."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/api/1.0/deals"
    
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
            limit = self.config.extra.get("limit", 12)
            response = self.client.get(
                self.path,
                params={"storeID": "1", "pageSize": limit, "sortBy": "DealRating"},
                headers={"User-Agent": "dashboard/1.0"},
            )
            data = response.json() or []
            
            items = []
            for d in data:
                items.append({
                    "title": d.get("title"),
                    "salePrice": d.get("salePrice"),
                    "normalPrice": d.get("normalPrice"),
                    "savings": d.get("savings"),
                    "thumb": d.get("thumb"),
                    "url": "https://www.cheapshark.com/redirect?dealID=" + str(d.get("dealID")),
                })
            
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
            logger.error("CheapShark fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, item: Any) -> Optional[dict]:
        # Already parsed in fetch
        return item


def create_cheapshark_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="cheapshark",
        enabled=True,
        rate_limit=10,
        rate_period=60.0,
        cache_ttl=3600,  # 1 hour
        extra={"base_url": "https://www.cheapshark.com", "limit": 12},
    )
    return CheapSharkFetcher(config)