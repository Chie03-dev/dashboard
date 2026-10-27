from app.fetchers.base import BaseFetcher, FetchResult, FetchStatus, FetcherConfig, FetcherRegistry, fetcher_registry, dead_letter_queue
from app.fetchers.gamerpower import GamerPowerFetcher
from app.fetchers.epic import EpicFetcher
from app.fetchers.hackernews import HackerNewsFetcher
from app.fetchers.github import GitHubFetcher
from app.fetchers.cheapshark import CheapSharkFetcher
from app.fetchers.openmeteo import OpenMeteoFetcher
from app.fetchers.steam import SteamFetcher
from app.fetchers.gog import GOGFetcher
from app.fetchers.reddit import RedditFetcher

# Register all fetchers
fetcher_registry.register(GamerPowerFetcher, FetcherConfig(
    name="gamerpower",
    enabled=True,
    rate_limit=10,
    rate_period=60.0,
    cache_ttl=1800,
    extra={"base_url": "https://www.gamerpower.com"},
))

fetcher_registry.register(EpicFetcher, FetcherConfig(
    name="epic",
    enabled=True,
    rate_limit=10,
    rate_period=60.0,
    cache_ttl=1800,
    extra={"base_url": "https://store-site-backend-static.ak.epicgames.com"},
))

fetcher_registry.register(HackerNewsFetcher, FetcherConfig(
    name="hackernews",
    enabled=True,
    rate_limit=30,
    rate_period=60.0,
    cache_ttl=1800,
    extra={"base_url": "https://hacker-news.firebaseio.com", "limit": 15},
))

fetcher_registry.register(GitHubFetcher, FetcherConfig(
    name="github",
    enabled=bool(__import__("app.config", fromlist=["GITHUB_TOKEN"]).GITHUB_TOKEN),
    rate_limit=30,
    rate_period=60.0,
    cache_ttl=1800,
    extra={"base_url": "https://api.github.com", "github_token": __import__("app.config", fromlist=["GITHUB_TOKEN"]).GITHUB_TOKEN},
))

fetcher_registry.register(CheapSharkFetcher, FetcherConfig(
    name="cheapshark",
    enabled=True,
    rate_limit=10,
    rate_period=60.0,
    cache_ttl=3600,
    extra={"base_url": "https://www.cheapshark.com", "limit": 12},
))

fetcher_registry.register(OpenMeteoFetcher, FetcherConfig(
    name="openmeteo",
    enabled=True,
    rate_limit=60,
    rate_period=60.0,
    cache_ttl=600,
    extra={"base_url": "https://api.open-meteo.com", "latitude": 40.7128, "longitude": -74.0060},
))

# New fetchers (disabled by default, enable via config)
fetcher_registry.register(SteamFetcher, FetcherConfig(
    name="steam",
    enabled=False,  # Requires Steam API key
    rate_limit=20,
    rate_period=60.0,
    cache_ttl=3600,
    extra={"base_url": "https://store.steampowered.com"},
))

fetcher_registry.register(GOGFetcher, FetcherConfig(
    name="gog",
    enabled=False,
    rate_limit=10,
    rate_period=60.0,
    cache_ttl=3600,
    extra={"base_url": "https://api.gog.com/v2"},
))

fetcher_registry.register(RedditFetcher, FetcherConfig(
    name="reddit",
    enabled=False,  # Requires Reddit OAuth
    rate_limit=30,
    rate_period=60.0,
    cache_ttl=1800,
    extra={"base_url": "https://www.reddit.com", "subreddits": ["GameDealsFree", "FreeGameFindings", "Freeware"]},
))

__all__ = [
    "BaseFetcher",
    "FetchResult",
    "FetchStatus",
    "FetcherConfig",
    "FetcherRegistry",
    "fetcher_registry",
    "dead_letter_queue",
    "GamerPowerFetcher",
    "EpicFetcher",
    "HackerNewsFetcher",
    "GitHubFetcher",
    "CheapSharkFetcher",
    "OpenMeteoFetcher",
    "SteamFetcher",
    "GOGFetcher",
    "RedditFetcher",
]