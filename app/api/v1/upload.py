"""饮食图片上传接口（API v1）。"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.core.upload_limits import MAX_IMAGE_BYTES, MAX_UPLOAD_IMAGES
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.storage import get_storage
from app.services.upload_image import validate_image

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=ApiResponse[dict[str, str]])
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """上传用户选择的饮食图片；该操作不触发 AI 识别。"""
    return ApiResponse.success(await _store_image(file))


@router.post("/images", response_model=ApiResponse[list[dict[str, str]]])
async def upload_images(files: list[UploadFile] = File(...), current_user: User = Depends(get_current_user)):
    """按上传顺序保存最多六张饮食照片。"""
    if len(files) > MAX_UPLOAD_IMAGES:
        raise HTTPException(status_code=400, detail="最多上传 6 张照片")
    # Validate the entire batch before storing any files.
    images = [await _read_image(file) for file in files]
    return ApiResponse.success([await _save_image(*image) for image in images])


async def _store_image(file: UploadFile) -> dict[str, str]:
    return await _save_image(*await _read_image(file))


async def _read_image(file: UploadFile) -> tuple[bytes, str, str]:
    if file.size is not None and file.size > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张上传照片不能超过 10 MiB")
    content = bytearray()
    while True:
        chunk = await file.read(min(64 * 1024, MAX_IMAGE_BYTES + 1 - len(content)))
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="单张上传照片不能超过 10 MiB")
    image_bytes = bytes(content)
    ext, content_type = await run_in_threadpool(validate_image, image_bytes)
    return image_bytes, ext, content_type


async def _save_image(content: bytes, ext: str, content_type: str) -> dict[str, str]:
    filename = f"{uuid.uuid4().hex}{ext}"
    url = await run_in_threadpool(
        get_storage().upload_bytes,
        filename,
        content,
        content_type,
    )
    return {"url": url, "filename": filename}
