import os
import json
import redis
from typing import Optional, Any
from functools import wraps

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
)

CACHE_TTL = 300


def get_cache(key: str) -> Optional[Any]:
    try:
        data = redis_client.get(key)
        if data is not None:
            return json.loads(data)
    except Exception:
        pass
    return None


def set_cache(key: str, value: Any, ttl: int = CACHE_TTL) -> bool:
    try:
        redis_client.setex(key, ttl, json.dumps(value, default=str, ensure_ascii=False))
        return True
    except Exception:
        return False


def delete_cache(key: str) -> bool:
    try:
        redis_client.delete(key)
        return True
    except Exception:
        return False


def clear_cache_pattern(pattern: str) -> bool:
    try:
        keys = list(redis_client.scan_iter(match=pattern, count=500))
        if keys:
            redis_client.delete(*keys)
        return True
    except Exception:
        return False


def build_cache_key(prefix: str, **kwargs) -> str:
    if not kwargs:
        return prefix
    items = [f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None]
    return f"{prefix}:{':'.join(items)}" if items else prefix


def cached(key_prefix: str, ttl: int = CACHE_TTL):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache_key = build_cache_key(key_prefix, **kwargs)
            cached_data = get_cache(cache_key)
            if cached_data is not None:
                return cached_data

            result = await func(*args, **kwargs)
            set_cache(cache_key, result, ttl)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache_key = build_cache_key(key_prefix, **kwargs)
            cached_data = get_cache(cache_key)
            if cached_data is not None:
                return cached_data

            result = func(*args, **kwargs)
            set_cache(cache_key, result, ttl)
            return result

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator