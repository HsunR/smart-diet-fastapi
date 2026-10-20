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


@pytest.mark.asyncio
async def test_multiple_photos_create_read_update_and_legacy_cover(auth_client):
    photo_a = "https://objects.example.test/a.jpg"
    photo_b = "https://objects.example.test/b.jpg"
    created = await auth_client.post("/api/v1/records", json={
        "date": str(date.today()), "mealType": "lunch", "name": "午餐",
        "imageUrls": [photo_a, photo_b],
    })
    assert created.status_code == 201
    record = created.json()["data"]
    assert record["imageUrls"] == [photo_a, photo_b]
    assert record["imageUrl"] == photo_a

    listed = await auth_client.get(f"/api/v1/records?date={date.today()}")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["imageUrls"] == [photo_a, photo_b]

    updated = await auth_client.patch(f"/api/v1/records/{record['id']}", json={"imageUrls": [photo_b]})
    assert updated.status_code == 200
    assert updated.json()["data"]["imageUrl"] == photo_b

    cleared = await auth_client.patch(f"/api/v1/records/{record['id']}", json={"imageUrls": []})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["imageUrls"] == []
    assert cleared.json()["data"]["imageUrl"] == ""

    legacy = await auth_client.patch(f"/api/v1/records/{record['id']}", json={"imageUrl": photo_a})
    assert legacy.status_code == 200
    assert legacy.json()["data"]["imageUrls"] == [photo_a]


@pytest.mark.asyncio
async def test_photo_limit_is_validated(auth_client):
    response = await auth_client.post("/api/v1/records", json={
        "date": str(date.today()), "mealType": "lunch", "name": "午餐",
        "imageUrls": [f"https://objects.example.test/{index}.jpg" for index in range(7)],
    })
    assert response.status_code == 422
