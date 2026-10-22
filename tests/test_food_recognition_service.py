import json
from types import SimpleNamespace

import pytest

from app.services import food_recognition


class FakeVisionModel:
    async def ainvoke(self, messages):
        assert len(messages) == 2
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
