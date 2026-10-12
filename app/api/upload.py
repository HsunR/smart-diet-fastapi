import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.storage import get_storage

router = APIRouter(tags=["upload"])


@router.post("/api/v1/upload")
async def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    ext = Path(file.filename or ".jpg").suffix.lower() or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    content = await file.read()
    url = await run_in_threadpool(
        get_storage().upload_bytes,
        filename,
        content,
        file.content_type,
    )
    return JSONResponse({"url": url, "filename": filename})
