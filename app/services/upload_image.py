"""Validate actual raster image contents before writing to object storage."""

from io import BytesIO
from struct import error as StructError

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.core.upload_limits import MAX_IMAGE_PIXELS

IMAGE_TYPES = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "GIF": (".gif", "image/gif"),
    "WEBP": (".webp", "image/webp"),
}


def validate_image(content: bytes) -> tuple[str, str]:
    if not content:
        raise HTTPException(status_code=400, detail="照片不能为空")
    try:
        with Image.open(BytesIO(content), formats=list(IMAGE_TYPES)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="照片不能超过 4000 万像素，请缩小后重新上传")
            image_type = IMAGE_TYPES[image.format]
            image.verify()
        # Identification and verify() alone do not necessarily decode raster data.
        with Image.open(BytesIO(content), formats=list(IMAGE_TYPES)) as image:
            image.load()
    except Image.DecompressionBombError as exc:
        raise HTTPException(status_code=413, detail="照片像素尺寸过大，请缩小后重新上传") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError, OverflowError, StructError) as exc:
        raise HTTPException(status_code=400, detail="照片无效或已损坏，请上传 JPG、PNG、GIF 或 WebP 图片") from exc
    return image_type
