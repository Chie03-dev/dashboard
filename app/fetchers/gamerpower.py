from datetime import datetime, timezone
from typing import Any, Optional

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetchResult, FetchStatus, FetcherConfig
from app.logging_conf import get_logger

logger = get_logger(__name__)


def _parse_gp_date(s: str) -> Optional[str]:
    if not s or s == "N/A":
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            return None


class GamerPowerFetcher(BaseFetcher):
    """Fetcher for GamerPower free games."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/api/giveaways?platform=pc&sort-by=date"
    
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
            # Use conditional headers for incremental sync
            headers = self._get_conditional_headers()
            response = self.client.get(self.path, headers=headers)
            
            # Handle 304 Not Modified
            if response.status_code == 304:
                logger.info("GamerPower content not modified (304)")
                return FetchResult(
                    status=FetchStatus.SKIPPED,
                    items=[],
                    duration_ms=(datetime.now() - start).total_seconds() * 1000,
                )
            
            # Update conditional state for next request
            self._update_conditional_state(response)
            
            data = response.json()
            
            if not isinstance(data, list):
                return FetchResult(
                    status=FetchStatus.FAILED,
                    error="Invalid response format",
                )
            
            items = []
            for item in data:
                try:
                    if item.get("type") not in (None, "Game"):
                        pass
                    parsed = self.parse_item(item)
                    if parsed:
                        items.append(parsed)
                except Exception as e:
                    logger.warning("GamerPower item parse error: %s", e)
            
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
            logger.error("GamerPower fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, item: Any) -> Optional[dict]:
        if not isinstance(item, dict):
            return None
        return {
            "source": "gamerpower",
            "external_id": str(item.get("id", "")),
            "title": item.get("title", ""),
            "platform": item.get("platforms", ""),
            "url": item.get("open_giveaway_url") or item.get("gamerpower_url"),
            "thumbnail": item.get("thumbnail") or item.get("image"),
            "category": item.get("type") or "Game",
            "end_date": _parse_gp_date(item.get("end_date", "")),
        }


def create_gamerpower_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="gamerpower",
        enabled=True,
        rate_limit=10,
        rate_period=60.0,
        cache_ttl=1800,  # 30 minutes
        extra={"base_url": "https://www.gamerpower.com"},
    )
    return GamerPowerFetcher(config)