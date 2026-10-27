from datetime import datetime
from typing import Any

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetcherConfig, FetchResult, FetchStatus
from app.logging_conf import get_logger

logger = get_logger(__name__)


class SteamFetcher(BaseFetcher):
    """Fetcher for Steam free games / free weekends."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/api/FeaturedCategories/1/15/1"
    
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
            response = self.client.get(self.path, headers=headers)
            
            if response.status_code == 304:
                logger.info("Steam content not modified (304)")
                return FetchResult(
                    status=FetchStatus.SKIPPED,
                    items=[],
                    duration_ms=(datetime.now() - start).total_seconds() * 1000,
                )
            
            self._update_conditional_state(response)
            data = response.json()
            
            items = []
            # Parse Steam featured categories for free games
            for category in data.get("categories", []):
                if category.get("id") in (1, 2, 3, 19):  # Free to Play, Free Weekend, etc.
                    for item in category.get("items", []):
                        parsed = self.parse_item(item)
                        if parsed:
                            items.append(parsed)
            
            set(cache_k, items, self.config.cache_ttl)
            
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return FetchResult(
                status=FetchStatus.SUCCESS,
                items=items,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("Steam fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, item: Any) -> dict | None:
        if not isinstance(item, dict):
            return None
        
        # Check if actually free (price = 0)
        price = item.get("price", {})
        final_price = price.get("final", 0)
        if final_price != 0:
            return None
        
        return {
            "source": "steam",
            "external_id": str(item.get("id", "")),
            "title": item.get("name", ""),
            "platform": "PC (Steam)",
            "url": f"https://store.steampowered.com/app/{item.get('id', '')}",
            "thumbnail": item.get("header_image") or item.get("capsule_image"),
            "category": "Game",
            "end_date": item.get("release_date", {}).get("date"),
        }


def create_steam_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="steam",
        enabled=False,  # Disabled by default, requires Steam API key
        rate_limit=20,
        rate_period=60.0,
        cache_ttl=3600,  # 1 hour
        extra={"base_url": "https://store.steampowered.com"},
    )
    return SteamFetcher(config)