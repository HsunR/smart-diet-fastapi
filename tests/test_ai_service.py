import os
os.environ["LLM_API_KEY"] = "test-key"

from app.core.config import settings
settings.llm_api_key = "test-key"
settings.llm_base_url = "https://api.openai.com/v1"
settings.llm_model = "gpt-4o"

from app.services.ai import get_llm, get_vision_llm


def test_get_llm_returns_chat_model():
    llm = get_llm()
    assert llm is not None


def test_get_vision_llm_returns_chat_model():
    llm = get_vision_llm()
    assert llm is not None
