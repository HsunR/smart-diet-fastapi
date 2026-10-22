import json
from typing import TypedDict, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.ai import get_llm


class ChatState(TypedDict):
    message: str
    user_profile: Optional[dict]
    recent_diet: Optional[dict]
    history: list[dict]
    intent: Optional[str]
    reply: Optional[str]


INTENT_CLASSIFIER_PROMPT = """分析用户消息的意图，只返回以下其一：
- advice: 用户询问饮食建议、营养咨询
- query: 用户想查询饮食记录
- chat: 普通闲聊
- image: 用户想识别食物图片

消息: {message}
意图:"""

CHAT_PROMPT = """你是 AI 营养师助手。帮助用户记录饮食、提供建议、解答问题。

用户信息：{user_profile}
最近饮食：{recent_diet}

用温暖专业的语气回复，简洁明了。"""


async def classify_intent(state: ChatState) -> str:
    llm = get_llm()
    prompt = INTENT_CLASSIFIER_PROMPT.format(message=state["message"])
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()
    intent = intent if intent in ("advice", "query", "chat", "image") else "chat"
    return intent


async def handle_chat(state: ChatState) -> ChatState:
    llm = get_llm()
    prompt = CHAT_PROMPT.format(
        user_profile=json.dumps(state.get("user_profile", {}), ensure_ascii=False),
        recent_diet=json.dumps(state.get("recent_diet", {}), ensure_ascii=False),
    )
    messages = [SystemMessage(content=prompt)]
    for msg in (state.get("history") or []):
        messages.append(HumanMessage(content=msg.get("content", "")) if msg.get("role") == "user" else SystemMessage(content=msg.get("content", "")))
    messages.append(HumanMessage(content=state["message"]))
    response = await llm.ainvoke(messages)
    return {**state, "reply": response.content}


async def handle_query(state: ChatState) -> ChatState:
    return {**state, "reply": "请通过报告页面查看饮食记录"}


async def handle_image(state: ChatState) -> ChatState:
    return {**state, "reply": "请拍照上传以识别食物"}


async def run_chat(state: ChatState) -> ChatState:
    intent = await classify_intent(state)
    state = {**state, "intent": intent}
    if intent == "query":
        return await handle_query(state)
    if intent == "image":
        return await handle_image(state)
    return await handle_chat(state)
