import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Conversation(Base):
    """会话表：归档一个用户与 AI 的对话上下文。"""
    __tablename__ = "conversations"
    __table_args__ = {"comment": "会话表：归档用户与 AI 的对话上下文"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="会话主键")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, comment="会话所属用户，关联 users.id")
    title = Column(String(128), default="新对话", comment="会话展示标题")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="创建时间，UTC")
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="最后更新时间，UTC")
