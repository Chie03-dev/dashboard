import logging

import httpx

from app.config import FETCH_TIMEOUT

logger = logging.getLogger(__name__)

DEALS_URL = "https://www.cheapshark.com/api/1.0/deals"


def fetch_deals(limit=12):
    out = []
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT) as c:
            r = c.get(DEALS_URL, params={"storeID": "1", "pageSize": limit, "sortBy": "DealRating"}, headers={"User-Agent": "dashboard/1.0"})
            r.raise_for_status()
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
    except Exception as e:
        logger.error("deals fetch failed: %s", e)
    return out
