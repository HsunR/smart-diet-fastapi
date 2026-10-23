import base64
import json
from types import SimpleNamespace

import pytest

from app.services import food_recognition


def photo_bytes(url):
    return b"\x89PNG\r\n\x1a\n" + url.encode()


def expected_data_url(url):
    return "data:image/png;base64," + base64.b64encode(photo_bytes(url)).decode()


@pytest.fixture(autouse=True)
def uploaded_photos(monkeypatch):
    from app.services import vision_image

    class Storage:
        def read_image_bytes(self, url, limit):
            return photo_bytes(url)

    monkeypatch.setattr(vision_image, "get_storage", lambda: Storage())


class FakeVisionModel:
    async def ainvoke(self, messages):
        assert len(messages) == 2
        assert messages[1].content[0]["image_url"]["url"] == expected_data_url("https://example.com/meal.jpg")
        return SimpleNamespace(content=json.dumps({
            "success": True,
            "summary": {"score": 82, "tags": {"good": ["高蛋白"], "warn": []}},
            "items": [{"name": "鸡蛋", "score": 82, "weight": {"val": 80, "conf": 0.9}}],
        }))


@pytest.mark.asyncio
async def test_recognition_service_maps_model_result(monkeypatch):
    monkeypatch.setattr(food_recognition, "get_vision_llm", lambda: FakeVisionModel())
    result = await food_recognition.recognize_food({
        "image_url": "https://example.com/meal.jpg",
        "user_id": "test-user",
        "user_profile": {},
        "user_feedback": "",
        "raw_response": None,
        "foods": [],
        "meal_overview": None,
        "dietary_advice": "",
        "error": None,
    })

    assert result["error"] is None
    assert result["foods"][0].name == "鸡蛋"
    assert result["meal_overview"].overall_health_score == 82


def mock_stream(monkeypatch, chunks):
    from app.services import ai

    class StreamingModel:
        async def astream(self, messages):
            # The model must see valid JSON examples, not escaped template braces.
            assert '{{"type"' not in messages[0].content
            for content in chunks:
                yield SimpleNamespace(content=content)

    monkeypatch.setattr(ai, "get_streaming_vision_llm", lambda: StreamingModel())


@pytest.mark.asyncio
async def test_suggestions_arrive_before_next_model_chunk(monkeypatch):
    from app.services import ai
    consumed = []

    class StreamingModel:
        async def astream(self, messages):
            consumed.append(1)
            yield SimpleNamespace(content='```json\n{"type":"suggestion","field":"name","value":"鸡蛋面"}')
            consumed.append(2)
            yield SimpleNamespace(content='\n{"type":"suggestion","field":"description","value":"面条配鸡蛋"}\n{"type":"done"}')

    monkeypatch.setattr(ai, "get_streaming_vision_llm", lambda: StreamingModel())
    stream = food_recognition.recognize_food_stream("https://example.test/meal.jpg", {})
    first = await anext(stream)
    assert first == {"type": "suggestion", "data": {"field": "name", "value": "鸡蛋面"}}
    assert consumed == [1]  # No need to wait for a newline or the complete answer.
    rest = [event async for event in stream]
    assert [event["type"] for event in rest] == ["suggestion", "done"]


@pytest.mark.asyncio
async def test_fragmented_json_deduplication_and_tail(monkeypatch):
    suggestion = json.dumps({"type": "suggestion", "field": "description", "value": '鸡蛋配"面条" {一碗}'}, ensure_ascii=False)
    text = '```json\n' + suggestion + '\n' + suggestion + '\n{"type":"done","dietaryAdvice":"清淡"}'
    mock_stream(monkeypatch, list(text))
    events = [event async for event in food_recognition.recognize_food_stream("image", {})]
    assert [event["type"] for event in events] == ["suggestion", "done"]
    assert events[0]["data"]["value"] == '鸡蛋配"面条" {一碗}'
    assert events[-1]["data"]["dietaryAdvice"] == "清淡"


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["nothing useful", '{"type":"suggestion","field":"name","value":"未完成', '{"type":"error","message":"无法识别"}'])
async def test_invalid_or_truncated_stream_is_an_error(monkeypatch, content):
    mock_stream(monkeypatch, [content])
    events = [event async for event in food_recognition.recognize_food_stream("image", {})]
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "done" for event in events)


@pytest.mark.asyncio
async def test_existing_food_events_and_final_overview_still_work(monkeypatch):
    mock_stream(monkeypatch, ['{"type":"overview","summary":"午餐"}\n{"type":"food","name":"鸡蛋"}\n{"type":"done"}'])
    events = [event async for event in food_recognition.recognize_food_stream("image", {})]
    assert [event["type"] for event in events] == ["overview", "food_item", "done"]
    assert events[-1]["data"]["foods"][0]["name"] == "鸡蛋"


@pytest.mark.asyncio
async def test_model_setup_failure_is_a_safe_stream_error(monkeypatch):
    from app.services import ai

    def fail():
        raise ValueError("internal configuration detail")

    monkeypatch.setattr(ai, "get_streaming_vision_llm", fail)
    events = [event async for event in food_recognition.recognize_food_stream("image", {})]
    assert events[-1]["type"] == "error"
    assert "internal" not in events[-1]["data"]["message"]


@pytest.mark.asyncio
async def test_multiple_photos_share_one_model_call_and_one_human_message(monkeypatch):
    from app.services import ai
    calls = []
    urls = ["https://example.test/beef.jpg", "https://example.test/rice.jpg"]

    class BatchModel:
        async def astream(self, messages):
            calls.append(messages)
            assert len(messages) == 2
            assert "同一餐" in messages[0].content
            images = [part["image_url"]["url"] for part in messages[1].content if part["type"] == "image_url"]
            assert images == [expected_data_url(url) for url in urls]
            yield SimpleNamespace(content='{"type":"suggestion","field":"name","value":"牛肉配米饭"}')
            yield SimpleNamespace(content='{"type":"done"}')

    monkeypatch.setattr(ai, "get_streaming_vision_llm", lambda: BatchModel())
    stream = food_recognition.recognize_food_stream(urls, {})
    assert (await anext(stream))["data"]["value"] == "牛肉配米饭"
    assert [event["type"] async for event in stream] == ["done"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_photo_read_failure_does_not_send_an_incomplete_meal_to_model(monkeypatch):
    from unittest.mock import Mock
    from app.services import ai, vision_image

    class Storage:
        def read_image_bytes(self, url, limit):
            if url.endswith("missing.jpg"):
                raise RuntimeError("private storage error")
            return photo_bytes(url)

    monkeypatch.setattr(vision_image, "get_storage", lambda: Storage())
    model_factory = Mock()
    monkeypatch.setattr(ai, "get_streaming_vision_llm", model_factory)
    events = [event async for event in food_recognition.recognize_food_stream([
        "https://example.test/meal.jpg", "https://example.test/missing.jpg",
    ], {})]
    assert events == [{"type": "error", "data": {"message": "无法读取餐食照片，请重新上传后再试"}}]
    model_factory.assert_not_called()


@pytest.mark.asyncio
async def test_single_photo_read_error_is_returned_in_state(monkeypatch):
    from unittest.mock import Mock
    from app.services import vision_image

    monkeypatch.setattr(vision_image, "get_storage", Mock(side_effect=RuntimeError("private details")))
    model_factory = Mock()
    monkeypatch.setattr(food_recognition, "get_vision_llm", model_factory)
    state = await food_recognition.recognize_food({"image_url": "missing"})
    assert state["error"] == "无法读取餐食照片，请重新上传后再试"
    model_factory.assert_not_called()
