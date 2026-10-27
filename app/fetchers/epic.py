from datetime import datetime
from typing import Any

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetcherConfig, FetchResult, FetchStatus
from app.logging_conf import get_logger

logger = get_logger(__name__)


def _epic_slug(el: dict) -> str | None:
    for key in ("catalogNs",):
        mappings = (el.get(key) or {}).get("mappings") or []
        for m in mappings:
            if m.get("pageSlug"):
                return m["pageSlug"]
    for m in el.get("offerMappings") or []:
        if m.get("pageSlug"):
            return m["pageSlug"]
    return None


def _flatten_promos(groups: list) -> list:
    out = []
    for g in groups or []:
        for po in (g.get("promotionalOffers") or []):
            out.append(po)
    return out


class EpicFetcher(BaseFetcher):
    """Fetcher for Epic Games free games."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
    
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
            response = self.client.get(self.path)
            data = response.json()
            
            elements = (((data.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []
            items = []
            
            for el in elements:
                try:
                    parsed = self.parse_item(el)
                    if parsed:
                        items.append(parsed)
                except Exception as e:
                    logger.warning("Epic item parse error: %s", e)
            
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
            logger.error("Epic fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, el: Any) -> dict | None:
        if not isinstance(el, dict):
            return None
        
        try:
            price = ((el.get("price") or {}).get("totalPrice") or {}).get("discountPrice")
            price = 0 if price is None else price
            promos = el.get("promotions") or {}
            current = _flatten_promos(promos.get("promotionalOffers"))
            upcoming = _flatten_promos(promos.get("upcomingPromotionalOffers"))
            has_100 = any(
                (po.get("discountSetting") or {}).get("discountPercentage") == 100
                for po in (current + upcoming)
            )
            if not (price == 0 or has_100):
                return None

            end = None
            hundred_current = [po for po in current if (po.get("discountSetting") or {}).get("discountPercentage") == 100]
            hundred_upcoming = [po for po in upcoming if (po.get("discountSetting") or {}).get("discountPercentage") == 100]
            candidates = hundred_current or (current if price == 0 else []) or hundred_upcoming
            if candidates:
                end = candidates[0].get("endDate")
            if not end:
                for lo in (el.get("price") or {}).get("lineOffers") or []:
                    for r in lo.get("appliedRules") or []:
                        if r.get("endDate"):
                            end = r["endDate"]
                            break
                    if end:
                        break
            if not end:
                end = el.get("expiryDate")
            if end:
                try:
                    dt = datetime.fromisoformat(str(end))
                    end = dt.isoformat()
                except Exception:
                    pass

            slug = _epic_slug(el)
            url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else None
            thumbnail = None
            for ki in el.get("keyImages") or []:
                if ki.get("type") in ("OfferImageTall", "Thumbnail", "OfferImageWide"):
                    thumbnail = ki.get("url")
                    break
            offer_type = el.get("offerType") or "BASE_GAME"
            category_map = {"BASE_GAME": "Game", "ADD_ON": "DLC", "BUNDLE": "Bundle"}
            category = category_map.get(offer_type, offer_type)
            
            return {
                "source": "epic",
                "external_id": str(el.get("id", "")),
                "title": el.get("title", ""),
                "platform": "PC (Epic)",
                "url": url,
                "thumbnail": thumbnail,
                "category": category,
                "end_date": end,
            }
        except Exception as e:
            logger.warning("Epic parse error: %s", e)
            return None


def create_epic_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="epic",
        enabled=True,
        rate_limit=10,
        rate_period=60.0,
        cache_ttl=1800,  # 30 minutes
        extra={"base_url": "https://store-site-backend-static.ak.epicgames.com"},
    )
    return EpicFetcher(config)