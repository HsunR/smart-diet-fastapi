"""Real Redis integration: set TEST_REDIS_URL to a disposable Redis instance."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import Header, HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeoutError

from app.api.v1 import food, upload, user as user_api
from app.core.config import Settings, settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.rate_limit import Policy, RateLimitManager
from app.main import app
from app.schemas.food import MealOverview


@pytest.fixture
async def manager():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL to run real Redis integration tests")
    config = Settings(_env_file=None, rate_limit_prefix=f"test:ratelimit:{uuid4().hex}")
    redis = Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    await redis.ping()
    limiter = RateLimitManager(redis, config)
    try:
        yield limiter
    finally:
        # Only delete keys in this test's unique namespace; never FLUSHDB.
        keys = [key async for key in redis.scan_iter(match=f"{config.rate_limit_prefix}:*")]
        if keys:
            await redis.delete(*keys)
        await limiter.close()


@pytest.fixture
async def client(manager, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(app.state, "rate_limits", manager, raising=False)

    async def current_user(authorization: str = Header(default="")):
        if not authorization:
            raise HTTPException(401, "请先登录")
        return SimpleNamespace(id=authorization, age=25, weight=65)

    async def database():
        yield SimpleNamespace()

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = database
    try:
        transport = httpx.ASGITransport(app=app, client=("198.51.100.10", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
            yield value
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def request():
    return Request({"type": "http", "method": "POST", "path": "/api/v1/probe", "headers": [], "app": app})


async def test_atomic_acquisition_across_independent_workers(manager):
    manager.policies["ai"] = Policy(5, 60_000)
    other = RateLimitManager(Redis.from_url(os.environ["TEST_REDIS_URL"]), manager.config)
    other.policies["ai"] = manager.policies["ai"]

    async def attempt(index):
        try:
            await (manager if index % 2 else other).check(request(), "ai", "same-user")
            return 200
        except HTTPException as exc:
            return exc.status_code

    try:
        results = await asyncio.gather(*(attempt(i) for i in range(40)))
        assert results.count(200) == 5
        assert results.count(429) == 35
    finally:
        await other.close()


async def test_identity_and_policy_isolation_and_private_keys(manager):
    manager.policies["ai"] = Policy(1, 60_000)
    await manager.check(request(), "ai", "private-account")
    with pytest.raises(HTTPException) as failure:
        await manager.check(request(), "ai", "private-account")
    assert failure.value.status_code == 429
    assert int(failure.value.headers["Retry-After"]) > 0
    await manager.check(request(), "ai", "other-account")
    await manager.check(request(), "user", "private-account")
    keys = [key async for key in manager.redis.scan_iter(match=f"{manager.config.rate_limit_prefix}:*")]
    assert len(keys) == 3
    assert all(b"private-account" not in key and b"other-account" not in key for key in keys)
    assert all([await manager.redis.pttl(key) > 0 for key in keys])


async def test_weighted_upload_is_atomic_and_does_not_charge_rejections(manager):
    manager.policies["upload"] = Policy(6, 60_000)
    await manager.check(request(), "upload", "user", weight=5)
    with pytest.raises(HTTPException) as failure:
        await manager.check(request(), "upload", "user", weight=2)
    assert failure.value.status_code == 429
    # The denied batch must not consume its first image's remaining permit.
    await manager.check(request(), "upload", "user", weight=1)


async def test_idle_keys_expire_and_quota_refills(manager):
    manager.policies["ai"] = Policy(1, 100)
    await manager.check(request(), "ai", "short-window")
    with pytest.raises(HTTPException):
        await manager.check(request(), "ai", "short-window")
    await asyncio.sleep(0.25)
    assert not [key async for key in manager.redis.scan_iter(match=f"{manager.config.rate_limit_prefix}:ai:*")]
    await manager.check(request(), "ai", "short-window")


async def test_ip_admission_precedes_body_parsing_and_ignores_spoofed_xff(client, manager):
    manager.policies["ip"] = Policy(1, 60_000)
    first = await client.post("/api/v1/users/web/login", content="not-json", headers={"X-Forwarded-For": "1.1.1.1", "Content-Type": "application/json"})
    assert first.status_code == 422
    second = await client.post("/api/v1/users/web/login/", content="not-json", headers={"X-Forwarded-For": "2.2.2.2", "Origin": "https://example.com", "Content-Type": "application/json"})
    assert second.status_code == 429
    assert second.json()["code"] == 429
    assert second.json()["data"] is None
    assert second.headers["retry-after"].isdigit()
    assert second.headers["access-control-expose-headers"] == "Retry-After"
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200
    assert (await client.options("/api/v1/users/me", headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"})).status_code == 200


async def test_login_ip_shared_between_web_and_wechat(client, manager):
    manager.policies["login"] = Policy(1, 60_000)
    assert (await client.post("/api/v1/users/login", json={})).status_code == 422
    assert (await client.post("/api/v1/users/web/login", json={})).status_code == 429


async def test_registration_has_independent_ip_policy(client, manager):
    manager.policies["register"] = Policy(1, 3_600_000)
    assert (await client.post("/api/v1/users/web/register", json={})).status_code == 422
    assert (await client.post("/api/v1/users/web/register", json={})).status_code == 429
    assert (await client.post("/api/v1/users/web/login", json={})).status_code == 422


async def test_account_limit_normalizes_case_and_is_shared_across_ips(client, manager, monkeypatch):
    manager.policies["account"] = Policy(1, 60_000)

    async def invalid_credentials(*args):
        raise HTTPException(400, "账号或密码错误")

    login = AsyncMock(side_effect=invalid_credentials)
    monkeypatch.setattr(user_api.user_service, "login_web_account", login)
    assert (await client.post("/api/v1/users/web/login", json={"account": "Alice", "password": "password123"})).status_code == 400
    transport = httpx.ASGITransport(app=app, client=("203.0.113.25", 4321))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as another:
        result = await another.post("/api/v1/users/web/login", json={"account": "ALICE", "password": "password123"})
    assert result.status_code == 429
    assert login.await_count == 1


async def test_ai_routes_share_quota_before_opening_sse(client, manager, monkeypatch):
    manager.policies["ai"] = Policy(1, 60_000)
    monkeypatch.setattr(food, "owned_images", AsyncMock(return_value=["photo"]))
    recognize = AsyncMock(return_value={"foods": [], "meal_overview": MealOverview(), "dietary_advice": ""})
    monkeypatch.setattr(food, "run_food_recognition", recognize)
    stream_calls = []

    async def stream(*args):
        stream_calls.append(args)
        yield {"type": "done", "data": {}}

    monkeypatch.setattr(food, "recognize_food_stream", stream)
    headers = {"Authorization": "user-a"}
    assert (await client.post("/api/v1/records/recognize", json={"imageUrl": "photo"}, headers=headers)).status_code == 200
    blocked = await client.post("/api/v1/records/recognize/stream", json={"imageUrls": ["photo"]}, headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers["content-type"].startswith("application/json")
    assert blocked.headers["retry-after"].isdigit()
    assert not stream_calls
    allowed = await client.post("/api/v1/records/recognize/stream", json={"imageUrls": ["photo"]}, headers={"Authorization": "user-b"})
    assert allowed.status_code == 200
    assert "data:" in allowed.text
    # Also prove sharing in the reverse direction, and no model call on denial.
    assert (await client.post("/api/v1/records/recognize", json={"imageUrl": "photo"}, headers={"Authorization": "user-b"})).status_code == 429
    assert recognize.await_count == 1


async def test_user_limit_shared_across_routes_but_not_users(client, manager, monkeypatch):
    manager.policies["user"] = Policy(1, 60_000)
    monkeypatch.setattr(food.food_service, "get_records_by_date", AsyncMock(return_value=[]))
    monkeypatch.setattr(food, "record_responses", AsyncMock(return_value=[]))
    headers = {"Authorization": "user-a"}
    assert (await client.get("/api/v1/records?date=2026-10-27", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 429
    assert (await client.get("/api/v1/records?date=2026-10-27", headers={"Authorization": "user-b"})).status_code == 200


async def test_single_and_batch_upload_share_image_quota_before_validation(client, manager, monkeypatch):
    manager.policies["upload"] = Policy(6, 60_000)
    read = AsyncMock(return_value=(b"image", ".jpg", "image/jpeg"))
    save = AsyncMock(return_value={"url": "stored-photo", "filename": "photo.jpg"})
    monkeypatch.setattr(upload, "_read_image", read)
    monkeypatch.setattr(upload, "_save_image", save)
    headers = {"Authorization": "user-a"}
    files = [("files", (f"{i}.jpg", b"photo", "image/jpeg")) for i in range(6)]
    assert (await client.post("/api/v1/upload/images", files=files, headers=headers)).status_code == 200
    denied = await client.post("/api/v1/upload", files={"file": ("a.jpg", b"photo", "image/jpeg")}, headers=headers)
    assert denied.status_code == 429
    assert read.await_count == 6
    assert save.await_count == 6


async def test_redis_outage_fails_closed_but_health_remains_available(client, manager, monkeypatch):
    time = AsyncMock(side_effect=ConnectionError("offline"))
    monkeypatch.setattr(manager.redis, "time", time)
    response = await client.post("/api/v1/users/web/login", json={})
    assert response.status_code == 503
    assert response.json()["code"] == 503
    assert response.headers["retry-after"] == "5"
    assert time.await_count == 1
    assert (await client.get("/health")).status_code == 200


async def test_uncertain_write_is_not_replayed(manager, monkeypatch):
    write = AsyncMock(side_effect=RedisTimeoutError("write outcome unknown"))
    monkeypatch.setattr(manager.redis, "evalsha", write)
    with pytest.raises(HTTPException) as failure:
        await manager.check(request(), "ai", "user")
    assert failure.value.status_code == 503
    write.assert_awaited_once()


async def test_disabled_limits_do_not_access_redis(client, manager, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    time = AsyncMock(side_effect=AssertionError("Redis must not be touched"))
    monkeypatch.setattr(manager.redis, "time", time)
    assert (await client.post("/api/v1/users/web/login", json={})).status_code == 422
    time.assert_not_awaited()


async def test_unauthenticated_requests_do_not_spend_user_or_ai_quota(client, manager):
    assert (await client.post("/api/v1/records/recognize/stream", json={"imageUrls": ["photo"]})).status_code == 401
    keys = [key async for key in manager.redis.scan_iter(match=f"{manager.config.rate_limit_prefix}:*")]
    assert len(keys) == 1
    assert b":ip:" in keys[0]


async def test_missing_initialization_returns_503(client, monkeypatch):
    monkeypatch.setattr(app.state, "rate_limits", None)
    assert (await client.get("/api/v1/users/me", headers={"Authorization": "user"})).status_code == 503


def test_disabled_initialization_does_not_create_redis(monkeypatch):
    from app.core import rate_limit
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    create = AsyncMock()
    monkeypatch.setattr(rate_limit, "create_redis", create)
    assert asyncio.run(rate_limit.init_rate_limits()) is None
    create.assert_not_called()


async def test_initialization_failure_closes_connection(monkeypatch):
    from app.core import rate_limit
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    redis = SimpleNamespace(ping=AsyncMock(side_effect=ConnectionError("offline")), aclose=AsyncMock())
    monkeypatch.setattr(rate_limit, "create_redis", lambda: redis)
    with pytest.raises(ConnectionError):
        await rate_limit.init_rate_limits()
    redis.aclose.assert_awaited_once()
