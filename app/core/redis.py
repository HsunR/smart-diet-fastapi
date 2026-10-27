"""Application-owned async Redis connection pool."""

from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.core.config import settings


def create_redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        password=settings.redis_password.get_secret_value() or None,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
        max_connections=100,
        # A timed-out write may already have consumed quota. Do not replay it.
        retry=Retry(NoBackoff(), 0),
    )
