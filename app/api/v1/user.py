from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.user import LoginRequest, LoginResponse, UserResponse, UserUpdate, WebLoginRequest, WebRegisterRequest
from app.services import user as user_service
from app.services.images import user_response

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db, scope="function")):
    user, token, is_new = await user_service.login(db, req.code)
    return ApiResponse.success(LoginResponse(token=token, user=await user_response(db, user), is_new=is_new))


@router.post("/web/register", response_model=ApiResponse[LoginResponse], status_code=201)
async def register_web_account(req: WebRegisterRequest, db: AsyncSession = Depends(get_db, scope="function")):
    user, token, is_new = await user_service.register_web_account(db, req.account, req.password, req.nickname)
    return ApiResponse.success(LoginResponse(token=token, user=await user_response(db, user), is_new=is_new))


@router.post("/web/login", response_model=ApiResponse[LoginResponse])
async def login_web_account(req: WebLoginRequest, db: AsyncSession = Depends(get_db, scope="function")):
    user, token, is_new = await user_service.login_web_account(db, req.account, req.password)
    return ApiResponse.success(LoginResponse(token=token, user=await user_response(db, user), is_new=is_new))


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    return ApiResponse.success(await user_response(db, current_user))


@router.patch("/me", response_model=ApiResponse[UserResponse])
async def update_me(data: UserUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    user = await user_service.update_user(db, current_user.id, data)
    return ApiResponse.success(await user_response(db, user))
