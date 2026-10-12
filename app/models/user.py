import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, SmallInteger, Numeric, DateTime
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class User(Base):
    """用户表：保存登录身份、个人资料与饮食偏好。"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 用户主键。
    openid = Column(String(128), unique=True, nullable=False, index=True)  # 微信身份标识；网页用户使用系统生成的兼容值。
    account = Column(String(32), unique=True, nullable=True, index=True)  # 网页端登录账号。
    password_hash = Column(String(128), nullable=True)  # 密码哈希，绝不保存明文密码。
    nickname = Column(String(64), default="")  # 用户展示昵称。
    avatar = Column(String(512), default="")  # 头像图片 URL。
    gender = Column(SmallInteger, default=0)  # 性别：0 未设置，其他值由前端约定。
    age = Column(SmallInteger, default=25)  # 年龄（岁）。
    height = Column(Numeric(5, 1), default=170)  # 身高（厘米）。
    weight = Column(Numeric(5, 1), default=65)  # 体重（千克）。
    activity_level = Column(SmallInteger, default=3)  # 日常活动等级。
    goal = Column(String(16), default="maintain")  # 饮食目标：减脂、保持或增肌。
    preferences = Column(JSON, default=list)  # 饮食偏好标签列表。
    allergies = Column(JSON, default=list)  # 过敏原或忌口列表。
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))  # 创建时间（UTC）。
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))  # 最后更新时间（UTC）。
