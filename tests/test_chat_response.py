from types import SimpleNamespace

import pytest

from app.services import chat_response


class FakeChatModel:
    async def ainvoke(self, messages):
        assert len(messages) == 1
        return SimpleNamespace(content="query")


@pytest.mark.asyncio
async def test_query_intent_returns_report_guidance(monkeypatch):
    monkeypatch.setattr(chat_response, "get_llm", lambda: FakeChatModel())
    result = await chat_response.run_chat({
        "message": "查看我的饮食记录",
        "user_profile": {},
        "recent_diet": {},
        "history": [],
        "intent": None,
        "reply": None,
    })

    assert result["intent"] == "query"
    assert result["reply"] == "请通过报告页面查看饮食记录"
