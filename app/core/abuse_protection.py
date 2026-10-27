"""fastapi-limiter integration; Redis owns quotas and AI concurrency leases."""

import asyncio
from contextlib import suppress
import hashlib
from inspect import isawaitable
import logging
import math
from types import SimpleNamespace
from uuid import uuid4

import anyio
from fastapi import Depends, HTTPException, Request, Response
from fastapi_limiter.depends import RateLimiter
from pyrate_limiter import Limiter, Rate, RateItem, RedisBucket
from pyrate_limiter.buckets.redis_bucket import LuaScript
from pyrate_limiter.limiter import SingleBucketFactory
from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
LEASE_SECONDS = 120
_POLICY_SCOPE = SimpleNamespace(routes=())

# Keep the library's sliding-window/weighted admission algorithm unchanged.
# Add server time, atomic log pruning and idle expiry; register_script handles NOSCRIPT.
_RATE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local delta = now - tonumber(ARGV[1])
ARGV[1] = now
for i=1,tonumber(ARGV[4]) do
    local offset = 5 + (i - 1) * 3
    ARGV[offset] = tonumber(ARGV[offset]) + delta
end
local cutoff = tonumber(ARGV[5])
for i=2,tonumber(ARGV[4]) do
    cutoff = math.min(cutoff, tonumber(ARGV[5 + (i - 1) * 3]))
end
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', '(' .. cutoff)
local function admit()
""" + LuaScript.PUT_ITEM + """
end
local result = admit()
if result[1] < 0 then
    redis.call('PEXPIRE', KEYS[1], math.max(1, tonumber(ARGV[1]) - cutoff + 1))
end
-- Translate the blocking timestamp back to the caller's clock for library Retry-After.
if result[2] >= 0 then result[2] = result[2] - delta end
return result
"""
_ACQUIRE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
for i,key in ipairs(KEYS) do
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
    if redis.call('ZCARD', key) >= tonumber(ARGV[i + 2]) then return 0 end
end
for _,key in ipairs(KEYS) do
    redis.call('ZADD', key, now + tonumber(ARGV[2]), ARGV[1])
    redis.call('PEXPIRE', key, ARGV[2])
end
return 1
"""
_RENEW_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
for _,key in ipairs(KEYS) do
    local expiry = redis.call('ZSCORE', key, ARGV[1])
    if not expiry or tonumber(expiry) <= now then return 0 end
end
for _,key in ipairs(KEYS) do
    redis.call('ZADD', key, now + tonumber(ARGV[2]), ARGV[1])
    redis.call('PEXPIRE', key, ARGV[2])
end
return 1
"""
_RELEASE_SCRIPT = """
for _,key in ipairs(KEYS) do redis.call('ZREM', key, ARGV[1]) end
return 1
"""


class RateLimited(HTTPException):
    def __init__(self, retry_after: int):
        super().__init__(429, "请求过于频繁，请稍后再试", headers={"Retry-After": str(max(1, retry_after))})


def unavailable() -> HTTPException:
    return HTTPException(503, "请求保护服务暂不可用，请稍后再试", headers={"Retry-After": "5"})


class _BucketConnection:
    """Supply RedisBucket with its registered, expiring Lua script."""

    def __init__(self, redis: Redis, script):
        self.redis, self.script = redis, script

    async def evalsha(self, sha, numkeys, *arguments):
        return await self.script(keys=list(arguments[:numkeys]), args=list(arguments[numkeys:]), client=self.redis)


class AbuseProtection:
    def __init__(self, redis: Redis, prefix: str):
        self.redis, self.prefix = redis, prefix
        self.rate_script = redis.register_script(_RATE_SCRIPT)
        self.acquire_script = redis.register_script(_ACQUIRE_SCRIPT)
        self.renew_script = redis.register_script(_RENEW_SCRIPT)
        self.release_script = redis.register_script(_RELEASE_SCRIPT)

    def key(self, policy: str, subject: str) -> str:
        return f"{self.prefix}:rate:{policy}:{hashlib.sha256(subject.encode()).hexdigest()}"

    def _limiter(self, policy: str, subject: str, rates: list[Rate]):
        # Each identity owns a distinct bucket. No route indexes or plaintext IPs/accounts in keys.
        bucket = RedisBucket(rates, _BucketConnection(self.redis, self.rate_script), self.key(policy, subject), "")
        # Redis script handles pruning; no per-request background leaker threads.
        return Limiter(SingleBucketFactory(bucket, schedule_leak=False)), bucket

    @staticmethod
    async def _reject(bucket, weight: int = 1):
        wait_ms = bucket.waiting(RateItem("retry", bucket.now(), weight))
        if isawaitable(wait_ms):
            wait_ms = await wait_ms
        if wait_ms < 0:
            wait_ms = max(rate.interval for rate in bucket.rates)
        raise RateLimited(math.ceil(wait_ms / 1000))

    async def check_request(self, request: Request, policy: str, subject: str, maximum: int, seconds: int):
        limiter, bucket = self._limiter(policy, subject, [Rate(maximum, seconds * 1000)])

        async def identifier(request):
            return self.key(policy, subject)

        async def callback(request, response):
            await self._reject(bucket)

        try:
            # Checks run before routing and share a named policy across several endpoints.
            # 0.2.0 enumerates app.routes (incompatible with FastAPI's included routers).
            # Give it a route-free view: bucket isolation is already policy + identity.
            policy_request = Request({**request.scope, "app": _POLICY_SCOPE})
            await RateLimiter(limiter, identifier=identifier, callback=callback)(policy_request, Response())
        except RedisError as exc:
            logger.error("Rate limit Redis operation failed (%s)", type(exc).__name__)
            raise unavailable() from exc

    async def consume(self, policy: str, subject: str, rates: list[Rate], weight: int = 1):
        limiter, bucket = self._limiter(policy, subject, rates)
        try:
            if not await limiter.try_acquire_async(subject, weight=weight, blocking=False):
                await self._reject(bucket, weight)
        except RedisError as exc:
            logger.error("Quota Redis operation failed (%s)", type(exc).__name__)
            raise unavailable() from exc

    async def acquire(self, user_id: str):
        root = f"{self.prefix}:{{ai}}"
        keys = [f"{root}:user:{user_id}", f"{root}:global"]
        token = uuid4().hex
        try:
            if not await self.acquire_script(keys=keys, args=[
                token, LEASE_SECONDS * 1000, settings.recognition_user_concurrency, settings.recognition_global_concurrency,
            ]):
                raise RateLimited(5)
        except RedisError as exc:
            logger.error("AI lease Redis operation failed (%s)", type(exc).__name__)
            raise unavailable() from exc
        return Lease(self, keys, token)

    async def renew(self, keys: list[str], token: str) -> bool:
        return bool(await self.renew_script(keys=keys, args=[token, LEASE_SECONDS * 1000]))

    async def release(self, keys: list[str], token: str):
        await self.release_script(keys=keys, args=[token])


class Lease:
    def __init__(self, store: AbuseProtection, keys: list[str], token: str):
        self.store, self.keys, self.token = store, keys, token
        self.request_task = asyncio.current_task()
        self.heartbeat = asyncio.create_task(self._keep_alive())

    async def _keep_alive(self):
        try:
            while True:
                await asyncio.sleep(LEASE_SECONDS / 4)
                if not await self.store.renew(self.keys, self.token):
                    raise RuntimeError("AI lease expired")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("AI concurrency lease lost (%s); cancelling request", type(exc).__name__)
            self.request_task.cancel()

    async def close(self):
        self.heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await self.heartbeat
        try:
            await self.store.release(self.keys, self.token)
        except RedisError as exc:
            logger.warning("AI lease release failed (%s); lease will expire", type(exc).__name__)


def get_protection(request: Request) -> AbuseProtection:
    return request.app.state.abuse_protection


async def limit_login_account(request: Request, account: str):
    await get_protection(request).check_request(
        request, "login-account", account.strip().lower(), settings.login_account_per_15_minutes, 900,
    )


async def limit_upload(request: Request, user_id, count: int):
    await get_protection(request).consume(
        "upload-images", str(user_id), [Rate(settings.upload_user_images_per_day, 86400_000)], weight=count,
    )


async def guard_recognition(request: Request, user: User = Depends(get_current_user)) -> User:
    protection = get_protection(request)
    minute, day = settings.recognition_user_per_minute, settings.recognition_user_per_day
    # Eliminate redundant windows to satisfy the library's strictly increasing rate list.
    rates = [Rate(day, 86400_000)] if day <= minute else [Rate(minute, 60_000)]
    if minute < day < minute * 1440:
        rates.append(Rate(day, 86400_000))
    await protection.consume("recognition", str(user.id), rates)
    request.state.ai_lease = await protection.acquire(str(user.id))
    return user


class AbuseProtectionMiddleware:
    """IP checks precede body parsing; leases cover the complete SSE response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            path = scope.get("path", "").rstrip("/")
            root = scope.get("root_path", "").rstrip("/")
            if root and path.startswith(root + "/"):
                path = path[len(root):]
            if scope["method"] == "POST":
                rule = None
                if path in ("/api/v1/users/login", "/api/v1/users/web/login"):
                    rule = ("login-ip", settings.login_ip_per_minute, 60)
                elif path == "/api/v1/users/web/register":
                    rule = ("register-ip", settings.register_ip_per_hour, 3600)
                elif path in ("/api/v1/upload", "/api/v1/upload/images"):
                    rule = ("upload-ip", settings.upload_ip_per_minute, 60)
                elif path in ("/api/v1/records/recognize", "/api/v1/records/recognize/stream"):
                    rule = ("recognition-ip", settings.recognition_ip_per_minute, 60)
                elif path == "/api/v1/upload/access":
                    rule = ("image-access-ip", 120, 60)
                if rule:
                    request = Request(scope)
                    peer = scope.get("client")
                    await get_protection(request).check_request(request, rule[0], peer[0] if peer else "unknown", rule[1], rule[2])
            await self.app(scope, receive, send)
        except HTTPException as exc:
            await JSONResponse(
                {"code": exc.status_code, "message": exc.detail, "data": None},
                status_code=exc.status_code, headers=exc.headers,
            )(scope, receive, send)
        finally:
            lease = scope.get("state", {}).pop("ai_lease", None)
            if lease:
                with anyio.CancelScope(shield=True):
                    await lease.close()
