import logging

from app.cache import cache_key, get, set
from app.config import CACHE_TTL_WEATHER
from app.http_clients import get_openmeteo_client

logger = logging.getLogger(__name__)

WEATHER_PATH = "/v1/forecast"


def fetch_weather(lat=40.7128, lon=-74.0060):
    out = {}
    cache_k = cache_key("weather", f"{lat},{lon}")
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for weather")
        return cached
    try:
        client = get_openmeteo_client()
        r = client.get(
            WEATHER_PATH,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m",
            },
        )
        data = r.json() or {}
        cur = data.get("current") or {}
        out = {
            "temperature": cur.get("temperature_2m"),
            "wind": cur.get("wind_speed_10m"),
            "code": cur.get("weather_code"),
            "latitude": lat,
            "longitude": lon,
        }
        set(cache_k, out, CACHE_TTL_WEATHER)
    except Exception as e:
        logger.error("weather fetch failed: %s", e)
    return out
