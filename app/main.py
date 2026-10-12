from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.database import engine, Base
from app.core.exceptions import AppException
from app.schemas.base import ApiResponse
from app.api.v1.user import router as user_router
from app.api.v1.food import router as food_router
from app.api.v1.chat import router as chat_router
from app.api.upload import router as upload_router
from app.services.storage import get_storage


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    get_storage().ensure_bucket()
    yield
    await engine.dispose()


app = FastAPI(title="SmartDiet API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.detail["message"], "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """将 FastAPI 自动生成的 422 参数校验错误也收敛为统一结构。"""
    return JSONResponse(
        status_code=422,
        content={"code": 422, "message": "请求参数校验失败", "data": exc.errors()},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": message, "data": None},
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled API exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "data": None},
    )

app.include_router(user_router, prefix="/api/v1")
app.include_router(food_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(upload_router)


@app.get("/health", response_model=ApiResponse[dict[str, str]])
async def health():
    return ApiResponse.success({"status": "ok"})
