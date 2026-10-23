import base64
from io import BytesIO
from unittest.mock import Mock

import pytest

from app.core.config import settings
from app.services import vision_image
from app.services.storage import ObjectStorage
from app.services.vision_image import ImagePreparationError, prepare_image_data_url

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=")


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(settings, "minio_public_url", "https://photos.example.test/assets")
    instance = ObjectStorage.__new__(ObjectStorage)
    instance.bucket = "meals"
    instance.client = Mock()
    response = BytesIO(PNG)
    response.release_conn = Mock()
    response.read = Mock(wraps=response.read)
    instance.client.get_object.return_value = response
    monkeypatch.setattr(vision_image, "get_storage", lambda: instance)
    return instance, response


@pytest.mark.asyncio
async def test_uploaded_url_becomes_exact_inline_bytes_using_internal_storage(storage):
    instance, response = storage
    # Extension is intentionally misleading: actual image bytes determine MIME.
    url = instance.public_url("餐食 1.jpg")
    result = await prepare_image_data_url(url)
    assert result == "data:image/png;base64," + base64.b64encode(PNG).decode()
    instance.client.get_object.assert_called_once_with("meals", "餐食 1.jpg")
    response.read.assert_called_once_with(vision_image.MAX_IMAGE_BYTES + 1)
    assert response.closed
    response.release_conn.assert_called_once()


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/private", "https://photos.example.test.evil/assets/meals/a.png",
    "https://photos.example.test/assets/other/a.png", "file:///tmp/secret",
    "https://photos.example.test/assets/meals/%2e%2e/private", "https://photos.example.test/assets/meals/",
])
def test_only_configured_bucket_objects_can_be_read(storage, url):
    instance, _ = storage
    with pytest.raises(ValueError):
        instance.read_image_bytes(url, 1024)
    instance.client.get_object.assert_not_called()


@pytest.mark.asyncio
async def test_storage_connection_is_released_on_read_error(storage):
    instance, response = storage
    response.read.side_effect = OSError("storage failure containing private details")
    with pytest.raises(ImagePreparationError, match="无法读取餐食照片"):
        await prepare_image_data_url(instance.public_url("meal.png"))
    assert response.closed
    response.release_conn.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("content,mime", [
    (PNG, "image/png"), (b"\xff\xd8\xff\xe0jpeg", "image/jpeg"),
    (b"GIF89aimage", "image/gif"), (b"RIFF\x10\x00\x00\x00WEBPimage", "image/webp"),
])
async def test_existing_base64_is_not_double_encoded(monkeypatch, content, mime):
    get_storage = Mock()
    monkeypatch.setattr(vision_image, "get_storage", get_storage)
    value = f"data:{mime};base64,{base64.b64encode(content).decode()}"
    assert await prepare_image_data_url(value) == value
    get_storage.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "data:image/png;base64,%%%", "data:image/png;utf8,abc", "data:text/html;base64,YWJj",
    "data:image/png;base64,", "data:image/png;base64,PGh0bWw+",
])
async def test_malformed_empty_or_non_image_data_is_rejected(url):
    with pytest.raises(ImagePreparationError):
        await prepare_image_data_url(url)


@pytest.mark.asyncio
async def test_large_storage_objects_and_data_urls_are_rejected(storage, monkeypatch):
    instance, response = storage
    monkeypatch.setattr(vision_image, "MAX_IMAGE_BYTES", 8)
    with pytest.raises(ImagePreparationError, match="不能超过"):
        await prepare_image_data_url(instance.public_url("large.png"))
    response.read.assert_called_once_with(9)
    assert response.closed
    with pytest.raises(ImagePreparationError, match="不能超过"):
        await prepare_image_data_url("data:image/png;base64," + base64.b64encode(PNG).decode())
