from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, UserResponse, UserUpdate, WebLoginRequest, WebRegisterRequest
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user, token, is_new = await user_service.login(db, req.code)
    return LoginResponse(token=token, user=UserResponse.model_validate(user), is_new=is_new)


@router.post("/web/register", response_model=LoginResponse, status_code=201)
async def register_web_account(req: WebRegisterRequest, db: AsyncSession = Depends(get_db)):
    user, token, is_new = await user_service.register_web_account(db, req.account, req.password, req.nickname)
    return LoginResponse(token=token, user=UserResponse.model_validate(user), is_new=is_new)


@router.post("/web/login", response_model=LoginResponse)
async def login_web_account(req: WebLoginRequest, db: AsyncSession = Depends(get_db)):
    user, token, is_new = await user_service.login_web_account(db, req.account, req.password)
    return LoginResponse(token=token, user=UserResponse.model_validate(user), is_new=is_new)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(data: UserUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user = await user_service.update_user(db, current_user.id, data)
    return UserResponse.model_validate(user)
