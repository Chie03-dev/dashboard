from datetime import datetime
from typing import Any

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetcherConfig, FetchResult, FetchStatus
from app.logging_conf import get_logger

logger = get_logger(__name__)


class OpenMeteoFetcher(BaseFetcher):
    """Fetcher for Open-Meteo weather."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.path = "/v1/forecast"
    
    def fetch(self) -> FetchResult:
        start = datetime.now()
        
        lat = self.config.extra.get("latitude", 40.7128)
        lon = self.config.extra.get("longitude", -74.0060)
        cache_k = self.get_cache_key(f"weather_{lat}_{lon}")
        
        # Check cache first
        cached = get(cache_k)
        if cached is not None:
            return FetchResult(
                status=FetchStatus.CACHED,
                items=[cached],
                cached=True,
            )
        
        try:
            response = self.client.get(
                self.path,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code,wind_speed_10m",
                },
            )
            data = response.json() or {}
            cur = data.get("current") or {}
            
            item = {
                "temperature": cur.get("temperature_2m"),
                "wind": cur.get("wind_speed_10m"),
                "code": cur.get("weather_code"),
                "latitude": lat,
                "longitude": lon,
            }
            
            # Cache results
            set(cache_k, item, self.config.cache_ttl)
            
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return FetchResult(
                status=FetchStatus.SUCCESS,
                items=[item],
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("Open-Meteo fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, item: Any) -> dict | None:
        return item


def create_openmeteo_fetcher(latitude: float = 40.7128, longitude: float = -74.0060) -> BaseFetcher:
    config = FetcherConfig(
        name="openmeteo",
        enabled=True,
        rate_limit=60,
        rate_period=60.0,
        cache_ttl=600,  # 10 minutes
        extra={
            "base_url": "https://api.open-meteo.com",
            "latitude": latitude,
            "longitude": longitude,
        },
    )
    return OpenMeteoFetcher(config)