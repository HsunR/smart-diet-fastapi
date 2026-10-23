from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import BadRequest
from app.models.user import User
from app.services import user as user_service


@pytest.mark.parametrize("code", ["mock", "mock_other", "unverified-code"])
@pytest.mark.parametrize("allow_mock", [False, True])
async def test_missing_wechat_config_never_falls_back_for_real_codes(
    client, db_session, monkeypatch, code, allow_mock,
):
    monkeypatch.setattr(settings, "allow_mock_login", allow_mock)
    monkeypatch.setattr(settings, "wechat_appid", "")
    monkeypatch.setattr(settings, "wechat_secret", "")
    response = await client.post("/api/v1/users/login", json={"code": code})
    if allow_mock and code.startswith("mock"):
        assert response.status_code == 200
        assert response.json()["data"]["token"]
    else:
        assert response.status_code == (400 if code.startswith("mock") else 500)
        assert response.json()["data"] is None
        assert await db_session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("appid,secret", [("", "secret"), ("appid", "")])
async def test_partial_wechat_configuration_does_not_call_wechat(client, monkeypatch, appid, secret):
    monkeypatch.setattr(settings, "wechat_appid", appid)
    monkeypatch.setattr(settings, "wechat_secret", secret)
    lookup = AsyncMock()
    monkeypatch.setattr(user_service, "_wechat_openid", lookup)
    response = await client.post("/api/v1/users/login", json={"code": "real-code"})
    assert response.status_code == 500
    lookup.assert_not_awaited()


async def test_disabled_mock_is_rejected_even_when_wechat_is_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_mock_login", False)
    monkeypatch.setattr(settings, "wechat_appid", "appid")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    lookup = AsyncMock()
    monkeypatch.setattr(user_service, "_wechat_openid", lookup)
    response = await client.post("/api/v1/users/login", json={"code": "mock"})
    assert response.status_code == 400
    lookup.assert_not_awaited()


async def test_verified_wechat_login_still_works(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_mock_login", False)
    monkeypatch.setattr(settings, "wechat_appid", "appid")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    lookup = AsyncMock(return_value="verified-wechat-openid")
    monkeypatch.setattr(user_service, "_wechat_openid", lookup)
    response = await client.post("/api/v1/users/login", json={"code": "real-code"})
    assert response.status_code == 200
    lookup.assert_awaited_once_with("real-code")
    token = response.json()["data"]["token"]
    profile = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["data"]["openid"] == "verified-wechat-openid"


async def test_wechat_rejection_never_creates_mock_account(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "allow_mock_login", True)
    monkeypatch.setattr(settings, "wechat_appid", "appid")
    monkeypatch.setattr(settings, "wechat_secret", "secret")
    monkeypatch.setattr(user_service, "_wechat_openid", AsyncMock(side_effect=BadRequest("微信登录失败")))
    response = await client.post("/api/v1/users/login", json={"code": "rejected-code"})
    assert response.status_code == 400
    assert await db_session.scalar(select(func.count()).select_from(User)) == 0
