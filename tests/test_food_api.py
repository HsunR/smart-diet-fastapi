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


@pytest.mark.asyncio
async def test_custom_feedback_tags_survive_save_and_read(auth_client):
    response = await auth_client.post("/api/v1/records", json={
        "date": str(date.today()), "mealType": "lunch", "name": "鸡蛋面",
        "description": "面条配鸡蛋", "positiveTags": ["面条很筋道", "好吃"],
        "negativeTags": ["汤可以再热一点"],
    })
    assert response.status_code == 201
    record_id = response.json()["data"]["id"]
    listed = await auth_client.get(f"/api/v1/records?date={date.today()}")
    saved = next(record for record in listed.json()["data"] if record["id"] == record_id)
    assert saved["positiveTags"] == ["面条很筋道", "好吃"]
    assert saved["negativeTags"] == ["汤可以再热一点"]


@pytest.mark.asyncio
async def test_batch_recognition_endpoint_and_legacy_single_photo(auth_client, monkeypatch):
    from app.api.v1 import food
    batches = []

    async def fake_stream(urls, profile):
        batches.append(urls)
        yield {"type": "suggestion", "data": {"field": "name", "value": "牛肉配米饭"}}
        yield {"type": "done", "data": {}}

    monkeypatch.setattr(food, "recognize_food_stream", fake_stream)
    urls = ["https://example.test/beef.jpg", "https://example.test/rice.jpg"]
    response = await auth_client.post("/api/v1/records/recognize/stream", json={"imageUrls": urls})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert '"type": "suggestion"' in response.text
    assert batches == [urls]
    legacy = await auth_client.post("/api/v1/records/recognize/stream", json={"imageUrl": urls[0]})
    assert legacy.status_code == 200
    assert batches[-1] == [urls[0]]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"imageUrls": []}, {"imageUrls": [""]}, {"imageUrls": [" "]}, {"imageUrls": ["https://example.test/a.jpg"] * 7}])
async def test_batch_recognition_requires_one_to_six_photos(auth_client, payload):
    response = await auth_client.post("/api/v1/records/recognize/stream", json=payload)
    assert response.status_code == 422
