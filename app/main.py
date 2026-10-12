from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.database import engine, Base
from app.core.exceptions import AppException
from app.api.v1.user import router as user_router
from app.api.v1.food import router as food_router
from app.api.v1.chat import router as chat_router
from app.api.upload import router as upload_router
from app.services.storage import get_storage


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
        content={"code": exc.code, "message": exc.detail["message"]},
    )

app.include_router(user_router, prefix="/api/v1")
app.include_router(food_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(upload_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
