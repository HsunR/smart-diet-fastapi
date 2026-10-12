import pytest
from datetime import date


@pytest.mark.asyncio
async def test_create_food_record(auth_client):
    resp = await auth_client.post("/api/v1/records", json={
        "date": str(date.today()),
        "mealType": "lunch",
        "name": "番茄鸡蛋面",
        "description": "午餐，味道清淡",
        "positiveTags": ["好吃", "饱腹感强"],
        "negativeTags": ["价格偏高"],
        "price": 18.5,
        "rating": 4,
    })
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["code"] == 0
    data = payload["data"]
    assert data["date"] == str(date.today())
    assert data["mealType"] == "lunch"
    assert data["name"] == "番茄鸡蛋面"
    assert data["positiveTags"] == ["好吃", "饱腹感强"]
    assert data["price"] == 18.5
    assert "foods" not in data
    assert "mealOverview" not in data


@pytest.mark.asyncio
async def test_get_records_by_date(auth_client):
    resp = await auth_client.get(f"/api/v1/records?date={date.today()}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["code"] == 0
    assert isinstance(payload["data"], list)
