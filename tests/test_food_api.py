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
        "foods": [{"name": "测试食物", "score": 80}],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["date"] == str(date.today())
    assert data["mealType"] == "lunch"
    assert data["name"] == "番茄鸡蛋面"
    assert data["positiveTags"] == ["好吃", "饱腹感强"]
    assert data["price"] == 18.5


@pytest.mark.asyncio
async def test_get_records_by_date(auth_client):
    resp = await auth_client.get(f"/api/v1/records?date={date.today()}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
