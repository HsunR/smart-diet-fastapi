"""饮食图片上传接口（API v1）。"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import Field

from app.core.dependencies import get_current_user
from app.core.upload_limits import MAX_IMAGE_BYTES, MAX_UPLOAD_IMAGES
from app.models.user import User
from app.models.uploaded_image import UploadedImage
from app.core.database import get_db
from app.schemas.base import ApiResponse, CamelModel
from app.schemas.food import PhotoUrl
from app.services.images import image_access
from app.services.storage import get_storage
from app.services.upload_image import validate_image

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=ApiResponse[dict[str, str]])
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    """上传用户选择的饮食图片；该操作不触发 AI 识别。"""
    return ApiResponse.success(await _save_image(db, current_user.id, *await _read_image(file)))


@router.post("/images", response_model=ApiResponse[list[dict[str, str]]])
async def upload_images(files: list[UploadFile] = File(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    """按上传顺序保存最多六张饮食照片。"""
    if len(files) > MAX_UPLOAD_IMAGES:
        raise HTTPException(status_code=400, detail="最多上传 6 张照片")
    # Validate the entire batch before storing any files.
    images = [await _read_image(file) for file in files]
    return ApiResponse.success([await _save_image(db, current_user.id, *image) for image in images])


class ImageAccessRequest(CamelModel):
    image_urls: list[PhotoUrl] = Field(min_length=1, max_length=6)


@router.post("/access", response_model=ApiResponse[list[str]])
async def refresh_image_access(req: ImageAccessRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    """刷新本人图片的短时访问地址，旧签名即使过期也必须重新通过登录与归属校验。"""
    return ApiResponse.success(await image_access(db, current_user.id, req.image_urls))


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


async def _save_image(db: AsyncSession, user_id, content: bytes, ext: str, content_type: str) -> dict[str, str]:
    filename = f"{uuid.uuid4().hex}{ext}"
    object_name = f"users/{user_id}/{filename}"
    storage = get_storage()
    await run_in_threadpool(
        storage.upload_bytes,
        object_name,
        content,
        content_type,
    )
    db.add(UploadedImage(user_id=user_id, object_name=object_name))
    await db.flush()
    return {"url": storage.signed_url(object_name), "filename": filename}
