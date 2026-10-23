from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.api.v1 import upload
from app.core import upload_middleware
from app.services import upload_image


def image_bytes(format="PNG"):
    buffer = BytesIO()
    with Image.new("RGB", (2, 2), "red") as image:
        image.save(buffer, format=format)
    return buffer.getvalue()


class FakeStorage:
    def __init__(self):
        self.all_uploaded = []

    def upload_bytes(self, object_name, content, content_type):
        self.all_uploaded.append((object_name, content, content_type))
        return f"https://objects.example.test/smartdiet/{object_name}"


@pytest.fixture
def storage(monkeypatch):
    instance = FakeStorage()
    monkeypatch.setattr(upload, "get_storage", lambda: instance)
    return instance


@pytest.mark.parametrize("format,extension,mime", [
    ("JPEG", ".jpg", "image/jpeg"), ("PNG", ".png", "image/png"),
    ("GIF", ".gif", "image/gif"), ("WEBP", ".webp", "image/webp"),
])
async def test_upload_uses_actual_format_not_client_metadata(auth_client, storage, format, extension, mime):
    content = image_bytes(format)
    response = await auth_client.post(
        "/api/v1/upload", files={"file": ("untrusted.html", content, "text/html")},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["url"].startswith("https://objects.example.test/smartdiet/")
    assert payload["filename"].endswith(extension)
    assert storage.all_uploaded == [(payload["filename"], content, mime)]


async def test_upload_multiple_images_preserves_order(auth_client, storage):
    first, second = image_bytes("JPEG"), image_bytes("PNG")
    response = await auth_client.post("/api/v1/upload/images", files=[
        ("files", ("first.jpg", first, "image/jpeg")),
        ("files", ("second.png", second, "image/png")),
    ])
    assert response.status_code == 200
    images = response.json()["data"]
    assert len(images) == 2
    assert images[0]["filename"].endswith(".jpg")
    assert images[1]["filename"].endswith(".png")
    assert [item[1] for item in storage.all_uploaded] == [first, second]


@pytest.mark.parametrize("content", [
    b"", b"<html>not an image</html>", b"\x89PNG\r\n\x1a\ntruncated",
    image_bytes("BMP"), image_bytes("PNG")[:45], image_bytes("JPEG")[:-20],
])
async def test_invalid_or_unsupported_images_are_never_stored(auth_client, storage, content):
    response = await auth_client.post(
        "/api/v1/upload", files={"file": ("meal.jpg", content, "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == 400
    assert storage.all_uploaded == []


async def test_image_byte_limit_includes_boundary(auth_client, storage, monkeypatch):
    content = image_bytes()
    monkeypatch.setattr(upload, "MAX_IMAGE_BYTES", len(content))
    assert (await auth_client.post("/api/v1/upload", files={"file": ("meal.png", content)})).status_code == 200
    storage.all_uploaded.clear()
    response = await auth_client.post("/api/v1/upload", files={"file": ("meal.png", content + b"x")})
    assert response.status_code == 413
    assert storage.all_uploaded == []


async def test_file_without_size_metadata_still_has_a_byte_limit(monkeypatch):
    monkeypatch.setattr(upload, "MAX_IMAGE_BYTES", 8)
    file = UploadFile(BytesIO(b"x" * 9))
    try:
        with pytest.raises(HTTPException) as exc:
            await upload._read_image(file)
        assert exc.value.status_code == 413
    finally:
        await file.close()


async def test_pixel_limit_prevents_decoding_oversized_image(auth_client, storage, monkeypatch):
    monkeypatch.setattr(upload_image, "MAX_IMAGE_PIXELS", 3)
    response = await auth_client.post("/api/v1/upload", files={"file": ("meal.png", image_bytes())})
    assert response.status_code == 413
    assert storage.all_uploaded == []


async def test_invalid_batch_does_not_store_earlier_valid_photos(auth_client, storage):
    response = await auth_client.post("/api/v1/upload/images", files=[
        ("files", ("valid.png", image_bytes(), "image/png")),
        ("files", ("invalid.jpg", b"not-an-image", "image/jpeg")),
    ])
    assert response.status_code == 400
    assert storage.all_uploaded == []


@pytest.mark.parametrize("count,status", [(6, 200), (7, 400)])
async def test_batch_count_limit(auth_client, storage, count, status):
    response = await auth_client.post("/api/v1/upload/images", files=[
        ("files", (f"{index}.png", image_bytes(), "image/png")) for index in range(count)
    ])
    assert response.status_code == status
    assert len(storage.all_uploaded) == (count if status == 200 else 0)


@pytest.mark.parametrize("path", ["/api/v1/upload", "/api/v1/upload/images"])
async def test_declared_oversized_body_rejected_before_parsing(client, path):
    response = await client.post(path, content=b"", headers={"Content-Length": str(100 * 1024 * 1024)})
    assert response.status_code == 413
    assert response.json()["code"] == 413


@pytest.mark.parametrize("content_length", [None, "1"])
@pytest.mark.parametrize("path,field", [("/api/v1/upload", "file"), ("/api/v1/upload/images", "files")])
async def test_streamed_body_limit_ignores_missing_or_forged_length_and_closes_tempfiles(
    auth_client, storage, monkeypatch, content_length, path, field,
):
    import starlette.formparsers

    monkeypatch.setattr(upload_middleware, "MAX_IMAGE_BYTES", 256)
    monkeypatch.setattr(upload_middleware, "MULTIPART_OVERHEAD_BYTES", 256)
    temporary_files = []
    factory = starlette.formparsers.SpooledTemporaryFile

    def track_file(*args, **kwargs):
        file = factory(*args, **kwargs)
        temporary_files.append(file)
        return file

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", track_file)
    body = (
        f'--boundary\r\nContent-Disposition: form-data; name="{field}"; filename="meal.png"\r\n'.encode()
        +
        b'Content-Type: image/png\r\n\r\n' + b"x" * 2048 + b"\r\n--boundary--\r\n"
    )
    consumed = 0

    async def chunks():
        nonlocal consumed
        for start in range(0, len(body), 64):
            consumed += 64
            yield body[start:start + 64]

    headers = {"Content-Type": "multipart/form-data; boundary=boundary"}
    if content_length is not None:
        headers["Content-Length"] = content_length
    response = await auth_client.post(path, content=chunks(), headers=headers)
    assert response.status_code == 413
    assert response.json()["code"] == 413
    assert consumed < len(body)
    assert temporary_files and all(file.closed for file in temporary_files)
    assert storage.all_uploaded == []


async def test_body_limit_applies_behind_a_proxy_root_path():
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    transport = ASGITransport(app=app, root_path="/diet")
    async with AsyncClient(transport=transport, base_url="http://test/diet") as client:
        response = await client.post(
            "/api/v1/upload", content=b"", headers={"Content-Length": str(100 * 1024 * 1024)},
        )
    assert response.status_code == 413
