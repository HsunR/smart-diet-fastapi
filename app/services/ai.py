from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


def _make_llm(model: str, temperature: float, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        model=model,
        api_key=settings.llm_api_key,
        temperature=temperature,
        streaming=streaming,
    )


def get_llm() -> BaseChatModel:
    return _make_llm(settings.llm_model, 0.7)


def get_streaming_llm() -> BaseChatModel:
    return _make_llm(settings.llm_model, 0.7, streaming=True)


def get_vision_llm() -> BaseChatModel:
    model = settings.llm_vision_model or settings.llm_model
    return _make_llm(model, 0.3)


def get_streaming_vision_llm() -> BaseChatModel:
    model = settings.llm_vision_model or settings.llm_model
    return _make_llm(model, 0.3, streaming=True)
