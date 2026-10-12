from uuid import UUID
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models.conversation import Conversation
from app.models.message import Message


async def create_conversation(db: AsyncSession, user_id: UUID) -> Conversation:
    conv = Conversation(user_id=user_id)
    db.add(conv)
    await db.flush()
    return conv


async def list_conversations(db: AsyncSession, user_id: UUID) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_conversation(db: AsyncSession, user_id: UUID, conv_id: UUID) -> Conversation:
    result = await db.execute(
        select(Conversation).where(and_(Conversation.id == conv_id, Conversation.user_id == user_id))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFound("对话不存在")
    return conv


async def delete_conversation(db: AsyncSession, user_id: UUID, conv_id: UUID) -> None:
    conv = await get_conversation(db, user_id, conv_id)
    await db.delete(conv)
    await db.flush()


async def add_message(db: AsyncSession, conv_id: UUID, role: str, content: str, metadata: dict = None) -> Message:
    msg = Message(conversation_id=conv_id, role=role, content=content, metadata_=metadata or {})
    db.add(msg)
    await db.flush()
    return msg


async def get_history(db: AsyncSession, conv_id: UUID, limit: int = 50) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())
