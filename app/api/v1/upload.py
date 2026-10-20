"""饮食图片上传接口（API v1）。"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.storage import get_storage

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=ApiResponse[dict[str, str]])
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """上传用户选择的饮食图片；该操作不触发 AI 识别。"""
    return ApiResponse.success(await _store_image(file))


@router.post("/images", response_model=ApiResponse[list[dict[str, str]]])
async def upload_images(files: list[UploadFile] = File(...), current_user: User = Depends(get_current_user)):
    """按上传顺序保存最多六张饮食照片。"""
    if len(files) > 6:
        raise HTTPException(status_code=400, detail="最多上传 6 张照片")
    return ApiResponse.success([await _store_image(file) for file in files])


async def _store_image(file: UploadFile) -> dict[str, str]:
    ext = Path(file.filename or ".jpg").suffix.lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    url = await run_in_threadpool(
        get_storage().upload_bytes,
        filename,
        content,
        file.content_type,
    )
    return {"url": url, "filename": filename}
