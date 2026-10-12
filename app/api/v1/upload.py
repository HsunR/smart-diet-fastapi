"""饮食图片上传接口（API v1）。"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.base import ApiResponse
from app.services.storage import get_storage

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=ApiResponse[dict[str, str]])
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """上传用户选择的饮食图片；该操作不触发 AI 识别。"""
    ext = Path(file.filename or ".jpg").suffix.lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    url = await run_in_threadpool(
        get_storage().upload_bytes,
        filename,
        content,
        file.content_type,
    )
    return ApiResponse.success({"url": url, "filename": filename})
