import json
from uuid import UUID
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.base import ApiResponse
from app.schemas.chat import MessageCreate, MessageResponse, ConversationResponse
from app.services import chat as chat_service
from app.services.ai import get_streaming_llm
from app.workflows.chat import build_chat_graph, ChatState, CHAT_PROMPT
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/conversations", response_model=ApiResponse[ConversationResponse], status_code=201)
async def create_conversation(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    conv = await chat_service.create_conversation(db, current_user.id)
    return ApiResponse.success(ConversationResponse.model_validate(conv))


@router.get("/conversations", response_model=ApiResponse[list[ConversationResponse]])
async def list_conversations(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    convs = await chat_service.list_conversations(db, current_user.id)
    return ApiResponse.success([ConversationResponse.model_validate(c) for c in convs])


@router.get("/conversations/{conv_id}/messages", response_model=ApiResponse[list[MessageResponse]])
async def get_history(conv_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await chat_service.get_conversation(db, current_user.id, conv_id)
    messages = await chat_service.get_history(db, conv_id)
    return ApiResponse.success([MessageResponse.model_validate(m) for m in messages])


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(conv_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await chat_service.delete_conversation(db, current_user.id, conv_id)


@router.post("/messages", response_model=ApiResponse[MessageResponse])
async def send_message(
    req: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_id = req.conversation_id
    if not conv_id:
        conv = await chat_service.create_conversation(db, current_user.id)
        conv_id = conv.id
    else:
        await chat_service.get_conversation(db, current_user.id, conv_id)

    # 先读取历史，再保存本条用户消息，避免把当前消息重复注入模型上下文。
    history_messages = await chat_service.get_history(db, conv_id, 20)
    history = [{"role": m.role, "content": m.content} for m in history_messages[-10:]]
    await chat_service.add_message(db, conv_id, "user", req.content)

    graph = build_chat_graph()
    state: ChatState = {
        "message": req.content,
        "user_profile": {"age": current_user.age, "weight": float(current_user.weight)},
        "recent_diet": {},
        "history": history,
        "intent": None,
        "reply": None,
    }
    result = await graph.ainvoke(state)
    reply = result.get("reply", "抱歉，暂时无法回复")

    msg = await chat_service.add_message(db, conv_id, "assistant", reply, {"intent": result.get("intent")})
    return ApiResponse.success(MessageResponse.model_validate(msg))


@router.post("/messages/stream")
async def send_message_stream(
    req: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_id = req.conversation_id
    if not conv_id:
        conv = await chat_service.create_conversation(db, current_user.id)
        conv_id = conv.id
    else:
        await chat_service.get_conversation(db, current_user.id, conv_id)

    # 只把此前消息作为 history，当前消息在末尾追加一次。
    history_messages = await chat_service.get_history(db, conv_id, 20)
    history = [{"role": m.role, "content": m.content} for m in history_messages[-10:]]
    await chat_service.add_message(db, conv_id, "user", req.content)

    # 构建消息列表
    prompt = CHAT_PROMPT.format(
        user_profile=json.dumps({"age": current_user.age, "weight": float(current_user.weight)}, ensure_ascii=False),
        recent_diet=json.dumps({}, ensure_ascii=False),
    )
    messages = [SystemMessage(content=prompt)]
    for msg in history:
        messages.append(HumanMessage(content=msg.get("content", "")) if msg.get("role") == "user" else AIMessage(content=msg.get("content", "")))
    messages.append(HumanMessage(content=req.content))

    async def event_generator():
        full_reply = ""
        llm = get_streaming_llm()
        async for chunk in llm.astream(messages):
            content = chunk.content
            if content:
                full_reply += content
                yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"
        
        # 保存完整的AI回复到数据库
        await chat_service.add_message(db, conv_id, "assistant", full_reply)
        yield f"data: {json.dumps({'content': '', 'done': True, 'conversationId': str(conv_id)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
