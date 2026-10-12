from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel

from app.schemas.base import CamelModel


class MessageCreate(CamelModel):
    """创建聊天消息的请求 DTO。"""
    conversation_id: Optional[UUID] = None  # 目标会话；为空时由服务端创建会话。
    content: str = ""  # 用户输入的文本内容。
    image_url: str = ""  # 可选的消息图片 URL。


class MessageResponse(CamelModel):
    """聊天消息响应 VO。"""
    id: UUID  # 消息主键。
    conversation_id: UUID  # 所属会话主键。
    role: str  # 消息角色，例如 user 或 assistant。
    content: str  # 消息正文。
    created_at: datetime  # 消息创建时间。


class ConversationResponse(CamelModel):
    """会话列表项响应 VO。"""
    id: UUID  # 会话主键。
    title: str  # 会话展示标题。
    created_at: datetime  # 创建时间。
    updated_at: datetime  # 最后更新时间。
