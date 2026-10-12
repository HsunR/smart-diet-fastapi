import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Message(Base):
    """消息表：保存单个会话中的用户或 AI 消息。"""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 消息主键。
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)  # 所属会话，关联 conversations.id。
    role = Column(String(16), nullable=False)  # 消息角色，例如 user 或 assistant。
    content = Column(Text, default="")  # 消息正文。
    metadata_ = Column("metadata", JSON, default=dict)  # 消息附加元数据；Python 属性名避开 SQLAlchemy 保留字。
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))  # 创建时间（UTC）。
