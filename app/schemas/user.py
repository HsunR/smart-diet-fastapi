from datetime import datetime
from uuid import UUID
from decimal import Decimal
from typing import Optional
from pydantic import Field

from app.schemas.base import CamelModel


class UserCreate(CamelModel):
    """创建用户时的内部 DTO。"""
    openid: str = Field(description="微信或系统生成的唯一身份标识")
    nickname: str = Field(default="", description="展示昵称")
    avatar: str = Field(default="", description="头像 URL")
    gender: int = Field(default=0, description="性别编码")
    age: int = Field(default=25, description="年龄，单位：岁")
    height: Decimal = Field(default=Decimal("170"), description="身高，单位：厘米")
    weight: Decimal = Field(default=Decimal("65"), description="体重，单位：千克")
    activity_level: int = Field(default=3, description="日常活动等级")
    goal: str = Field(default="maintain", description="饮食目标")


class UserUpdate(CamelModel):
    """更新当前用户资料的请求 DTO；未传字段不会被更新。"""
    nickname: Optional[str] = Field(default=None, description="展示昵称")
    avatar: Optional[str] = Field(default=None, description="头像 URL")
    gender: Optional[int] = Field(default=None, description="性别编码")
    age: Optional[int] = Field(default=None, description="年龄，单位：岁")
    height: Optional[Decimal] = Field(default=None, description="身高，单位：厘米")
    weight: Optional[Decimal] = Field(default=None, description="体重，单位：千克")
    activity_level: Optional[int] = Field(default=None, description="日常活动等级")
    goal: Optional[str] = Field(default=None, description="饮食目标")
    preferences: Optional[list] = Field(default=None, description="饮食偏好标签")
    allergies: Optional[list] = Field(default=None, description="过敏原或忌口")


class UserResponse(CamelModel):
    """返回给前端的用户 VO，不包含账号密码等敏感字段。"""
    id: UUID = Field(description="用户主键")
    openid: str = Field(description="用户身份标识")
    nickname: str = Field(description="展示昵称")
    avatar: str = Field(description="头像 URL")
    gender: int = Field(description="性别编码")
    age: int = Field(description="年龄，单位：岁")
    height: Decimal = Field(description="身高，单位：厘米")
    weight: Decimal = Field(description="体重，单位：千克")
    activity_level: int = Field(description="日常活动等级")
    goal: str = Field(description="饮食目标")
    preferences: list = Field(description="饮食偏好标签")
    allergies: list = Field(description="过敏原或忌口")
    created_at: datetime = Field(description="注册时间")


class LoginRequest(CamelModel):
    """微信登录请求 DTO。"""
    code: str = Field(description="微信临时登录凭证")


class WebLoginRequest(CamelModel):
    """网页端账号密码登录 DTO。"""
    account: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$", description="登录账号")
    password: str = Field(min_length=8, max_length=72, description="明文密码，仅用于本次校验")


class WebRegisterRequest(WebLoginRequest):
    """网页端注册 DTO。"""
    nickname: str = Field(default="", max_length=64, description="注册后的展示昵称")


class LoginResponse(CamelModel):
    """登录成功响应 VO。"""
    token: str = Field(description="用于后续鉴权的 JWT")
    user: UserResponse = Field(description="当前登录用户资料")
    is_new: bool = Field(description="是否为本次登录新建的用户")
