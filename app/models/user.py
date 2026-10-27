import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, SmallInteger, Numeric, DateTime
from sqlalchemy import Uuid as UUID

from app.core.database import Base


class User(Base):
    """用户表：保存登录身份、个人资料与饮食偏好。"""
    __tablename__ = "users"
    __table_args__ = {"comment": "用户表：登录身份、个人资料与饮食偏好"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="用户主键")
    openid = Column(String(128), unique=True, nullable=True, index=True, comment="微信身份标识；网页账号为空")
    account = Column(String(32), unique=True, nullable=True, index=True, comment="网页端登录账号")
    password_hash = Column(String(128), nullable=True, comment="密码哈希，绝不保存明文密码")
    nickname = Column(String(64), default="", comment="用户展示昵称")
    avatar = Column(String(512), default="", comment="头像图片 URL")
    gender = Column(SmallInteger, default=0, comment="性别：0 未设置，其他值由前端约定")
    age = Column(SmallInteger, default=25, comment="年龄，单位：岁")
    height = Column(Numeric(5, 1), default=170, comment="身高，单位：厘米")
    weight = Column(Numeric(5, 1), default=65, comment="体重，单位：千克")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="创建时间，UTC")
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="最后更新时间，UTC")
