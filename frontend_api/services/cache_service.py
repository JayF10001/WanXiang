from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

try:
    import redis
except Exception:  # pragma: no cover - optional dependency fallback
    redis = None

from ..core.config import settings


logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self) -> None:
        self._redis_client = None
        self._lock = threading.Lock()
        self._memory_cache: dict[str, tuple[Any, float]] = {}
        self.mode = "memory"
        self.connection_label = "memory-fallback"
        self._init_redis()

    def _init_redis(self) -> None:
        if redis is None:
            logger.warning("frontend_api cache: redis dependency unavailable, using memory fallback")
            return

        redis_url = str(settings.redis_url or "").strip()
        if not redis_url:
            return

        try:
            client = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            client.ping()
            self._redis_client = client
            self.mode = "redis"
            self.connection_label = redis_url
            logger.info("frontend_api cache: connected to Redis %s", redis_url)
        except Exception:
            logger.warning("frontend_api cache: Redis unavailable, using memory fallback", exc_info=True)
            self._redis_client = None

    def get(self, key: str) -> Any | None:
        if self._redis_client is not None:
            try:
                raw = self._redis_client.get(key)
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception:
                logger.warning("frontend_api cache: redis get failed for key=%s", key, exc_info=True)

        with self._lock:
            cached = self._memory_cache.get(key)
            if not cached:
                return None
            value, expires_at = cached
            if expires_at and expires_at < time.time():
                self._memory_cache.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> bool:
        expires_at = time.time() + max(1, ttl_seconds)

        if self._redis_client is not None:
            try:
                self._redis_client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False, default=str))
                return True
            except Exception:
                logger.warning("frontend_api cache: redis set failed for key=%s", key, exc_info=True)

        with self._lock:
            self._memory_cache[key] = (value, expires_at)
        return True


cache_service = CacheService()
