import logging

import httpx

from app.config import FETCH_TIMEOUT

logger = logging.getLogger(__name__)

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather(lat=40.7128, lon=-74.0060):
    out = {}
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT) as c:
            r = c.get(
                WEATHER_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code,wind_speed_10m",
                },
            )
            r.raise_for_status()
            data = r.json() or {}
            cur = data.get("current") or {}
            out = {
                "temperature": cur.get("temperature_2m"),
                "wind": cur.get("wind_speed_10m"),
                "code": cur.get("weather_code"),
                "latitude": lat,
                "longitude": lon,
            }
    except Exception as e:
        logger.error("weather fetch failed: %s", e)
    return out
