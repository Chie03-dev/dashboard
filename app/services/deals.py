import logging

from app.cache import cache_key, get, set
from app.config import CACHE_TTL_DEALS
from app.http_clients import get_cheapshark_client

logger = logging.getLogger(__name__)

DEALS_PATH = "/api/1.0/deals"


def fetch_deals(limit=12):
    out = []
    cache_k = cache_key("deals", "cheapshark", str(limit))
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for deals")
        return cached
    try:
        client = get_cheapshark_client()
        r = client.get(DEALS_PATH, params={"storeID": "1", "pageSize": limit, "sortBy": "DealRating"}, headers={"User-Agent": "dashboard/1.0"})
        data = r.json() or []
        for d in data:
            out.append({
                "title": d.get("title"),
                "salePrice": d.get("salePrice"),
                "normalPrice": d.get("normalPrice"),
                "savings": d.get("savings"),
                "thumb": d.get("thumb"),
                "url": "https://www.cheapshark.com/redirect?dealID=" + str(d.get("dealID")),
            })
        set(cache_k, out, CACHE_TTL_DEALS)
    except Exception as e:
        logger.error("deals fetch failed", error=str(e))
    return out
