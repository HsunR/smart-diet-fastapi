import pytest


class FakeStorage:
    def __init__(self):
        self.uploaded = None
        self.all_uploaded = []

    def upload_bytes(self, object_name, content, content_type):
        self.uploaded = (object_name, content, content_type)
        self.all_uploaded.append(self.uploaded)
        return f"https://objects.example.test/smartdiet/{object_name}"


@pytest.mark.asyncio
async def test_upload_stores_object_in_minio(auth_client, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr("app.api.v1.upload.get_storage", lambda: storage)

    response = await auth_client.post(
        "/api/v1/upload",
        files={"file": ("meal.jpg", b"image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["url"].startswith("https://objects.example.test/smartdiet/")
    assert payload["filename"].endswith(".jpg")
    assert storage.uploaded == (payload["filename"], b"image-bytes", "image/jpeg")


@pytest.mark.asyncio
async def test_upload_multiple_images_preserves_order(auth_client, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr("app.api.v1.upload.get_storage", lambda: storage)
    response = await auth_client.post("/api/v1/upload/images", files=[
        ("files", ("first.jpg", b"first", "image/jpeg")),
        ("files", ("second.png", b"second", "image/png")),
    ])
    assert response.status_code == 200
    images = response.json()["data"]
    assert len(images) == 2
    assert images[0]["filename"].endswith(".jpg")
    assert images[1]["filename"].endswith(".png")
    assert [item[1] for item in storage.all_uploaded] == [b"first", b"second"]
