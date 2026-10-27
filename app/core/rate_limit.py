"""Framework-owned token buckets, with application identity and policy wiring."""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from math import ceil
from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request, Response
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import BucketFactory, Duration, Limiter, Rate, RateItem, RedisStateStore, StateBucket, TokenBucket
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings, settings
from app.core.dependencies import get_current_user
from app.core.redis import create_redis
from app.models.user import User

logger = logging.getLogger(__name__)

# Published fastapi-limiter 0.2.0 scans app.routes and adds positional indices.
# FastAPI 0.162 uses _IncludedRouter objects without .path. Give the library a
# stable, empty route view: our named policies explicitly define sharing, so
# route order (or route insertion on a rolling deploy) must not change keys.
_LIMITER_ROUTE_VIEW = SimpleNamespace(routes=())


@dataclass(frozen=True)
class Policy:
    limit: int
    interval: Duration | int


class RedisBucketFactory(BucketFactory):
    """One ephemeral framework bucket per attempt; Redis owns state and TTLs.

    A single shared RedisBucket would pool ALL identities regardless of item
    name. Binding the store to the hashed identity guarantees isolation without
    retaining a growing Python bucket cache or starting background leakers.
    """

    def __init__(self, redis: Redis, key: str, policy: Policy, weight: int):
        self.redis = redis
        self.weight = weight
        self.bucket = StateBucket(
            [Rate(policy.limit, policy.interval)],
            algorithm=TokenBucket(),
            store=RedisStateStore(redis, key),
        )
        self.item: RateItem | None = None

    async def wrap_item(self, name: str, weight: int = 1) -> RateItem:
        # A common clock keeps workers/hosts consistent. The framework's Lua
        # script owns the atomic decision, write, and expiry (no custom Lua).
        seconds, micros = await self.redis.time()
        self.item = RateItem(name, seconds * 1000 + micros // 1000, self.weight)
        return self.item

    def get(self, item: RateItem) -> StateBucket:
        return self.bucket

    def owned_buckets(self) -> list[StateBucket]:
        return [self.bucket]


class RateLimitManager:
    def __init__(self, redis: Redis, config: Settings):
        self.redis = redis
        self.config = config
        self.policies = {
            "ip": Policy(config.rate_limit_ip_per_minute, Duration.MINUTE),
            "user": Policy(config.rate_limit_user_per_minute, Duration.MINUTE),
            "login": Policy(config.rate_limit_login_per_minute, Duration.MINUTE),
            "account": Policy(config.rate_limit_account_per_minute, Duration.MINUTE),
            "register": Policy(config.rate_limit_register_per_hour, Duration.HOUR),
            "upload": Policy(config.rate_limit_upload_images_per_minute, Duration.MINUTE),
            "ai": Policy(config.rate_limit_ai_per_minute, Duration.MINUTE),
        }

    async def check(self, request: Request, name: str, identity: str, weight: int = 1) -> None:
        policy = self.policies[name]
        digest = hmac.new(self.config.jwt_secret.encode(), identity.encode(), hashlib.sha256).hexdigest()
        key = f"{self.config.rate_limit_prefix}:{name}:{policy.limit}:{int(policy.interval)}:{digest}"
        factory = RedisBucketFactory(self.redis, key, policy, weight)
        limiter = Limiter(factory)

        async def identifier(_: Request) -> str:
            return digest

        async def exceeded(_: Request, response: Response) -> None:
            assert factory.item is not None
            wait_ms = factory.bucket.waiting(factory.item)
            retry_after = max(1, ceil(wait_ms / 1000))
            raise HTTPException(
                status_code=429,
                detail=f"操作过于频繁，请在 {retry_after} 秒后重试",
                headers={"Retry-After": str(retry_after)},
            )

        dependency = RateLimiter(limiter=limiter, identifier=identifier, callback=exceeded, blocking=False)
        scoped_request = Request({**request.scope, "app": _LIMITER_ROUTE_VIEW}, receive=request.receive)
        try:
            await dependency(scoped_request, Response())
        except RedisError:
            # Never replay an uncertain write, or substitute per-process quotas.
            logger.warning("Rate limit storage unavailable (policy=%s)", name)
            raise HTTPException(status_code=503, detail="限流服务暂不可用，请稍后重试", headers={"Retry-After": "5"}) from None
        finally:
            limiter.close()

    async def close(self) -> None:
        await self.redis.aclose()


async def init_rate_limits() -> RateLimitManager | None:
    if not settings.rate_limit_enabled:
        return None
    redis = create_redis()
    try:
        await redis.ping()
    except BaseException:
        await redis.aclose()
        raise
    return RateLimitManager(redis, settings)


async def check_rate_limit(request: Request, name: str, identity: str, weight: int = 1) -> None:
    if not settings.rate_limit_enabled:
        return
    manager = getattr(request.app.state, "rate_limits", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="限流服务尚未就绪，请稍后重试", headers={"Retry-After": "5"})
    await manager.check(request, name, identity, weight)


async def get_rate_limited_user(request: Request, user: User = Depends(get_current_user)) -> User:
    await check_rate_limit(request, "user", str(user.id))
    return user


async def require_ai_rate_limit(request: Request, user: User = Depends(get_rate_limited_user)) -> None:
    # Both recognition endpoints share this policy, before SSE headers are sent.
    await check_rate_limit(request, "ai", str(user.id))


def rate_limit_response(exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": exc.detail, "data": None},
        headers=exc.headers,
    )


class RateLimitMiddleware:
    """Coarse IP/auth admission before JSON/multipart parsing or database work."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        root = scope.get("root_path", "").rstrip("/")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        path = path.rstrip("/")
        if not path.startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        # Only ASGI's trusted client address; never trust arbitrary XFF headers.
        # Configure Uvicorn's forwarded-allow-ips for actual reverse proxies.
        identity = request.client.host if request.client else "unknown"
        try:
            await check_rate_limit(request, "ip", identity)
            if scope["method"] == "POST":
                if path in {"/api/v1/users/login", "/api/v1/users/web/login"}:
                    await check_rate_limit(request, "login", identity)
                elif path == "/api/v1/users/web/register":
                    await check_rate_limit(request, "register", identity)
        except HTTPException as exc:
            await rate_limit_response(exc)(scope, receive, send)
            return
        await self.app(scope, receive, send)
