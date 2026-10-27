from datetime import datetime
from typing import Any

from app.cache import get, set
from app.fetchers.base import BaseFetcher, FetcherConfig, FetchResult, FetchStatus
from app.logging_conf import get_logger

logger = get_logger(__name__)


class RedditFetcher(BaseFetcher):
    """Fetcher for Reddit free game posts (r/GameDealsFree, r/FreeGameFindings)."""
    
    def __init__(self, config: FetcherConfig):
        super().__init__(config)
        self.subreddits = config.extra.get("subreddits", ["GameDealsFree", "FreeGameFindings"])
        self.path = "/r/{}/new.json"
    
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
        
        all_items = []
        
        try:
            for subreddit in self.subreddits:
                path = self.path.format(subreddit)
                headers = self._get_conditional_headers()
                headers["User-Agent"] = "Mozilla/5.0 (compatible; dashboard/1.0; +https://github.com/Chie03-dev/dashboard)"
                
                response = self.client.get(
                    path,
                    headers=headers,
                    params={"limit": 25, "raw_json": 1},
                )
                
                if response.status_code == 304:
                    logger.info("Reddit r/%s content not modified (304)", subreddit)
                    continue
                elif response.status_code == 403:
                    logger.warning("Reddit r/%s blocked (403), trying with different UA", subreddit)
                    # Try with a more browser-like UA
                    headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    response = self.client.get(
                        path,
                        headers=headers,
                        params={"limit": 25, "raw_json": 1},
                    )
                
                if response.status_code == 304:
                    logger.info("Reddit r/%s content not modified (304)", subreddit)
                    continue
                elif response.status_code == 429:
                    logger.warning("Reddit r/%s rate limited (429)", subreddit)
                    continue
                elif response.status_code != 200:
                    logger.warning("Reddit r/%s returned %d", subreddit, response.status_code)
                    continue
                
                self._update_conditional_state(response)
                data = response.json()
                
                for post in data.get("data", {}).get("children", []):
                    try:
                        post_data = post.get("data", {})
                        parsed = self.parse_item(post_data, subreddit)
                        if parsed:
                            all_items.append(parsed)
                    except Exception as e:
                        logger.warning("Reddit post parse error: %s", e)
            
            set(cache_k, all_items, self.config.cache_ttl)
            
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return FetchResult(
                status=FetchStatus.SUCCESS,
                items=all_items,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            logger.error("Reddit fetch failed: %s", e)
            return FetchResult(
                status=FetchStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms,
            )
    
    def parse_item(self, post: Any, subreddit: str) -> dict | None:
        if not isinstance(post, dict):
            return None
        
        # Filter for free game posts
        title = post.get("title", "").lower()
        if not any(kw in title for kw in ["free", "100% off", "giveaway", "freebie"]):
            return None
        
        # Skip stickied/announcement posts
        if post.get("stickied"):
            return None
        
        url = post.get("url", "")
        # Prefer direct links to store pages
        if "reddit.com" in url:
            url = f"https://reddit.com{post.get('permalink', '')}"
        
        return {
            "source": f"reddit/{subreddit}",
            "external_id": post.get("id", ""),
            "title": post.get("title", ""),
            "platform": "PC",
            "url": url,
            "thumbnail": post.get("thumbnail") if post.get("thumbnail", "").startswith("http") else None,
            "category": "Game",
            "end_date": None,
            "metadata": {
                "score": post.get("score"),
                "subreddit": subreddit,
                "author": post.get("author"),
            },
        }


def create_reddit_fetcher() -> BaseFetcher:
    config = FetcherConfig(
        name="reddit",
        enabled=False,  # Disabled by default - requires Reddit OAuth
        rate_limit=30,
        rate_period=60.0,
        cache_ttl=1800,  # 30 minutes
        extra={
            "base_url": "https://www.reddit.com",
            "subreddits": ["GameDealsFree", "FreeGameFindings", "Freeware"],
        },
    )
    return RedditFetcher(config)