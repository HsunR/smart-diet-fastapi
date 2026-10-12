import pytest


@pytest.mark.asyncio
async def test_register_and_login_web_account(client):
    registration = await client.post("/api/v1/users/web/register", json={
        "account": "diet.user",
        "password": "strong-password-123",
        "nickname": "网页用户",
    })
    assert registration.status_code == 201
    created = registration.json()["data"]
    assert created["isNew"] is True
    assert created["user"]["nickname"] == "网页用户"
    assert created["user"]["openid"].startswith("web_")

    login = await client.post("/api/v1/users/web/login", json={
        "account": "DIET.USER",
        "password": "strong-password-123",
    })
    assert login.status_code == 200
    assert login.json()["code"] == 0
    assert login.json()["data"]["isNew"] is False
    assert login.json()["data"]["token"]


@pytest.mark.asyncio
async def test_web_account_rejects_duplicate_account_and_bad_password(client):
    payload = {"account": "web-user", "password": "strong-password-123"}
    assert (await client.post("/api/v1/users/web/register", json=payload)).status_code == 201
    assert (await client.post("/api/v1/users/web/register", json=payload)).status_code == 400
    assert (await client.post("/api/v1/users/web/login", json={**payload, "password": "incorrect-password"})).status_code == 400
