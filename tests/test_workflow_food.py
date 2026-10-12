import pytest
from app.workflows.food_recognition import build_food_recognition_graph


@pytest.mark.asyncio
async def test_food_recognition_graph_structure():
    graph = build_food_recognition_graph()
    assert graph is not None
