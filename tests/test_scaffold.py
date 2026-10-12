import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"code": 0, "message": "success", "data": {"status": "ok"}}


@pytest.mark.asyncio
async def test_validation_error_uses_standard_response(client):
    resp = await client.post("/api/v1/users/web/login", json={"account": "a", "password": "short"})

    assert resp.status_code == 422
    payload = resp.json()
    assert payload["code"] == 422
    assert payload["message"] == "请求参数校验失败"
    assert isinstance(payload["data"], list)
