import json
import logging
import os
from typing import Any, Optional

import redis

from app.config import REDIS_URL

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None
_redis_available = False


def get_redis() -> Optional[redis.Redis]:
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client

    url = REDIS_URL
    if not url:
        logger.info("REDIS_URL not set; caching disabled")
        return None

    try:
        _redis_client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected at %s", url)
    except Exception as e:
        logger.warning("Redis unavailable; falling back to no cache: %s", e)
        _redis_client = None
        _redis_available = False
    return _redis_client


def is_available() -> bool:
    return _redis_available


def get(key: str) -> Optional[Any]:
    client = get_redis()
    if not client:
        return None
    try:
        val = client.get(key)
        if val is None:
            return None
        return json.loads(val)
    except Exception as e:
        logger.warning("Redis GET failed for %s: %s", key, e)
        return None


def set(key: str, value: Any, ttl: int) -> bool:
    client = get_redis()
    if not client:
        return False
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning("Redis SET failed for %s: %s", key, e)
        return False


def delete(key: str) -> bool:
    client = get_redis()
    if not client:
        return False
    try:
        client.delete(key)
        return True
    except Exception as e:
        logger.warning("Redis DELETE failed for %s: %s", key, e)
        return False


def clear_pattern(pattern: str) -> int:
    client = get_redis()
    if not client:
        return 0
    try:
        keys = client.keys(pattern)
        if keys:
            return client.delete(*keys)
        return 0
    except Exception as e:
        logger.warning("Redis CLEAR PATTERN failed for %s: %s", pattern, e)
        return 0


def cache_key(prefix: str, *parts: str, tenant_id: str = "default") -> str:
    return f"{prefix}:{tenant_id}:{':'.join(parts)}"