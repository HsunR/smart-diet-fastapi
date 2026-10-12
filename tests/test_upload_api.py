import pytest


class FakeStorage:
    def __init__(self):
        self.uploaded = None

    def upload_bytes(self, object_name, content, content_type):
        self.uploaded = (object_name, content, content_type)
        return f"https://objects.example.test/smartdiet/{object_name}"


@pytest.mark.asyncio
async def test_upload_stores_object_in_minio(auth_client, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr("app.api.upload.get_storage", lambda: storage)

    response = await auth_client.post(
        "/api/v1/upload",
        files={"file": ("meal.jpg", b"image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"].startswith("https://objects.example.test/smartdiet/")
    assert payload["filename"].endswith(".jpg")
    assert storage.uploaded == (payload["filename"], b"image-bytes", "image/jpeg")
