import json
from typing import TypedDict, Optional, Literal
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

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


async def classify_intent(state: ChatState) -> Command[Literal["handle_advice", "handle_query", "handle_chat", "handle_image"]]:
    llm = get_llm()
    prompt = INTENT_CLASSIFIER_PROMPT.format(message=state["message"])
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    intent = response.content.strip().lower()
    intent = intent if intent in ("advice", "query", "chat", "image") else "chat"
    state["intent"] = intent
    goto_map = {
        "advice": "handle_advice",
        "query": "handle_query",
        "chat": "handle_chat",
        "image": "handle_image",
    }
    return Command(goto=goto_map[intent], update={"intent": intent})


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


async def handle_advice(state: ChatState) -> ChatState:
    return await handle_chat(state)


async def handle_query(state: ChatState) -> ChatState:
    return {**state, "reply": "请通过报告页面查看饮食记录"}


async def handle_image(state: ChatState) -> ChatState:
    return {**state, "reply": "请拍照上传以识别食物"}


def build_chat_graph() -> StateGraph:
    builder = StateGraph(ChatState)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("handle_advice", handle_advice)
    builder.add_node("handle_query", handle_query)
    builder.add_node("handle_chat", handle_chat)
    builder.add_node("handle_image", handle_image)
    builder.add_edge(START, "classify_intent")
    builder.add_edge("handle_advice", END)
    builder.add_edge("handle_query", END)
    builder.add_edge("handle_chat", END)
    builder.add_edge("handle_image", END)
    return builder.compile()
