from datetime import datetime
from uuid import UUID
from decimal import Decimal
from typing import Optional
from pydantic import Field

from app.schemas.base import CamelModel


class UserCreate(CamelModel):
    """创建用户时的内部 DTO。"""
    openid: str  # 微信或系统生成的唯一身份标识。
    nickname: str = ""  # 展示昵称。
    avatar: str = ""  # 头像 URL。
    gender: int = 0  # 性别编码。
    age: int = 25  # 年龄（岁）。
    height: Decimal = Decimal("170")  # 身高（厘米）。
    weight: Decimal = Decimal("65")  # 体重（千克）。
    activity_level: int = 3  # 活动等级。
    goal: str = "maintain"  # 饮食目标。


class UserUpdate(CamelModel):
    """更新当前用户资料的请求 DTO；未传字段不会被更新。"""
    nickname: Optional[str] = None  # 展示昵称。
    avatar: Optional[str] = None  # 头像 URL。
    gender: Optional[int] = None  # 性别编码。
    age: Optional[int] = None  # 年龄（岁）。
    height: Optional[Decimal] = None  # 身高（厘米）。
    weight: Optional[Decimal] = None  # 体重（千克）。
    activity_level: Optional[int] = None  # 活动等级。
    goal: Optional[str] = None  # 饮食目标。
    preferences: Optional[list] = None  # 饮食偏好标签。
    allergies: Optional[list] = None  # 过敏原或忌口。


class UserResponse(CamelModel):
    """返回给前端的用户 VO，不包含账号密码等敏感字段。"""
    id: UUID  # 用户主键。
    openid: str  # 用户身份标识。
    nickname: str  # 展示昵称。
    avatar: str  # 头像 URL。
    gender: int  # 性别编码。
    age: int  # 年龄（岁）。
    height: Decimal  # 身高（厘米）。
    weight: Decimal  # 体重（千克）。
    activity_level: int  # 活动等级。
    goal: str  # 饮食目标。
    preferences: list  # 饮食偏好标签。
    allergies: list  # 过敏原或忌口。
    created_at: datetime  # 注册时间。


class LoginRequest(CamelModel):
    """微信登录请求 DTO。"""
    code: str  # 微信临时登录凭证。


class WebLoginRequest(CamelModel):
    """网页端账号密码登录 DTO。"""
    account: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")  # 登录账号。
    password: str = Field(min_length=8, max_length=72)  # 明文密码，仅用于本次校验。


class WebRegisterRequest(WebLoginRequest):
    """网页端注册 DTO。"""
    nickname: str = Field(default="", max_length=64)  # 注册后的展示昵称。


class LoginResponse(CamelModel):
    """登录成功响应 VO。"""
    token: str  # 用于后续鉴权的 JWT。
    user: UserResponse  # 当前登录用户资料。
    is_new: bool  # 是否为本次登录新建的用户。
