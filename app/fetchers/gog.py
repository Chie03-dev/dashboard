from datetime import datetime
from typing import Any

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetcherConfig, FetchResult, FetchStatus
from app.logging_conf import get_logger

logger = get_logger(__name__)


class GOGFetcher(BaseFetcher):
    """Fetcher for GOG free games."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/products"
    
    def fetch(self) -> FetchResult:
        start = datetime.now()
        cache_k = self.get_cache_key("data")
        
        cached = get(cache_k)
        if cached is not None:
            return FetchResult(
                status=FetchStatus.CACHED,
                items=cached,
                cached=True,
            )
        
        try:
            headers = self._get_conditional_headers()
            response = self.client.get(
                self.path,
                headers=headers,
                params={
                    "page": 1,
                    "pageSize": 50,
                    "sortBy": "popularity",
                    "system": "windows",
                    "priceMin": 0,
                    "priceMax": 0,  # Free games only
                },
            )
            
            if response.status_code == 304:
                logger.info("GOG content not modified (304)")
                return FetchResult(
                    status=FetchStatus.SKIPPED,
                    items=[],
                    duration_ms=(datetime.now() - start).total_seconds() * 1000,
                )
            
            self._update_conditional_state(response)
            data = response.json()
            
            items = []
            for product in data.get("products", []):
                try:
                    parsed = self.parse_item(product)
                    if parsed:
                        items.append(parsed)
                except Exception as e:
                    logger.warning("GOG item parse error: %s", e)
            
            set(cache_k, items, self.config.cache_ttl)
            
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return FetchResult(
                status=FetchStatus.SUCCESS,
                items=items,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("GOG fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, product: Any) -> dict | None:
        if not isinstance(product, dict):
            return None
        
        # Check if free
        price = product.get("price", {})
        amount = price.get("amount", 0)
        if amount != 0:
            return None
        
        slug = product.get("slug", "")
        return {
            "source": "gog",
            "external_id": str(product.get("id", "")),
            "title": product.get("title", ""),
            "platform": "PC (GOG)",
            "url": f"https://www.gog.com/game/{slug}" if slug else None,
            "thumbnail": product.get("image") or product.get("gallery", [{}])[0].get("url"),
            "category": "Game",
            "end_date": None,  # GOG free games typically don't expire
        }


def create_gog_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="gog",
        enabled=False,  # Disabled by default
        rate_limit=10,
        rate_period=60.0,
        cache_ttl=3600,  # 1 hour
        extra={"base_url": "https://api.gog.com/v2"},
    )
    return GOGFetcher(config)