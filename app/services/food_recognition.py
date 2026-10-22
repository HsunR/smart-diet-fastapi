import json
from typing import TypedDict, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.ai import get_vision_llm
from app.schemas.food import FoodItem, MealOverview

def _prepare_image_url(url: str) -> str:
    """MinIO uploads are returned as URLs accepted directly by the vision model."""
    if url.startswith(("http://", "https://", "data:")):
        return url
    return url


class FoodRecognitionState(TypedDict):
    image_url: str
    user_id: str
    user_profile: Optional[dict]
    user_feedback: str
    raw_response: Optional[str]
    foods: list[FoodItem]
    meal_overview: Optional[MealOverview]
    dietary_advice: str
    error: Optional[str]


FOOD_RECOGNITION_PROMPT = """### 角色
AI 营养师。分析图像，结合用户信息 ({user_profile}) 输出 JSON。
必须严格遵循下方 JSON 结构，无 Markdown 标记。
{user_feedback_section}
### JSON 结构示例
{{
   "success": true,
   "summary": {{
      "score": 65,
      "tags": {{"good": ["高蛋白"], "warn": ["高钠"]}},
      "tagReasons": {{"高蛋白": "鸡肉富含优质蛋白质", "高钠": "酱油和腌制调料含盐量高"}}
   }},
   "items": [
      {{
        "id": "food_001",
        "name": "宫保鸡丁",
        "category": "种类",
        "score": 75,
        "weight": {{"val": 135, "conf": 0.85}},
        "tags": {{"good": ["高蛋白"], "warn": ["高钠"]}},
        "tagReasons": {{"高蛋白": "鸡肉富含优质蛋白质", "高钠": "酱油和腌制调料含盐量高"}},
        "advice": "简短建议"
      }}
   ]
}}
错误返回：{{"success": false, "message": "原因"}}"""


FOOD_RECOGNITION_STREAM_PROMPT = """### 角色
AI 营养师。分析图像，结合用户信息 ({user_profile}) 逐行输出 JSON。

### 输出规则
严格逐行输出，每行一个完整 JSON 对象（一行内不含换行），无需 Markdown 标记，不要有空行。

第一行 — 餐食概览：
{{"type":"overview","score":65,"tags":{{"good":["高蛋白"],"warn":["高钠"]}},"tagReasons":{{"高蛋白":"鸡肉富含优质蛋白质","高钠":"酱油含盐量高"}},"summary":"识别到宫保鸡丁、米饭，整体评分65分"}}

后续每行 — 每种食物（逐行输出，不要放在数组里）：
{{"type":"food","id":"food_001","name":"宫保鸡丁","category":"肉类","score":75,"weight":{{"val":135,"conf":0.85}},"tags":{{"good":["高蛋白"],"warn":["高钠"]}},"tagReasons":{{"高蛋白":"鸡肉富含优质蛋白质","高钠":"酱油含盐量高"}},"advice":"少油更健康"}}

最后一行 — 整体建议：
{{"type":"done","dietaryAdvice":"整体建议：减少酱油用量，增加蔬菜比例"}}

若无法识别图片内容：
{{"type":"error","message":"无法识别图片中的食物"}}"""


async def recognize_food(state: FoodRecognitionState) -> FoodRecognitionState:
    llm = get_vision_llm()
    user_feedback = state.get("user_feedback", "")
    feedback_section = ""
    if user_feedback:
        feedback_section = f"### 用户反馈\n用户对上次识别结果提出以下修正意见：{user_feedback}\n请结合图片和用户反馈重新分析，优先采纳用户的合理意见。\n"
    prompt = FOOD_RECOGNITION_PROMPT.replace("{user_profile}", json.dumps(state.get("user_profile", {}), ensure_ascii=False)).replace("{user_feedback_section}", feedback_section)
    image_url = _prepare_image_url(state["image_url"])
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=[{"type": "image_url", "image_url": {"url": image_url}}]),
    ]
    try:
        response = await llm.ainvoke(messages)
        content = response.content.strip()
        result = json.loads(content)
        if not result.get("success"):
            return {**state, "error": result.get("message", "识别失败")}

        foods = []
        for item in result.get("items", []):
            foods.append(FoodItem(
                name=item.get("name", "未知食物"),
                category=item.get("category", ""),
                score=item.get("score", 60),
                weight=item.get("weight", {}).get("val", 100),
                confidence=item.get("weight", {}).get("conf", 0.8),
                tags={"positive": item.get("tags", {}).get("good", []), "warning": item.get("tags", {}).get("warn", [])},
                tag_reasons=item.get("tagReasons", {}),
                advice=item.get("advice", ""),
            ))

        summary = result.get("summary", {})
        overview = MealOverview(
            overall_health_score=summary.get("score", 60),
            health_tags={"positive": summary.get("tags", {}).get("good", []), "warning": summary.get("tags", {}).get("warn", [])},
            tag_reasons=summary.get("tagReasons", {}),
            summary=f"识别到: {', '.join(f.name for f in foods)}" if foods else "识别成功",
        )

        advices = [f.advice for f in foods if f.advice]
        dietary_advice = "; ".join(advices)

        return {**state, "foods": foods, "meal_overview": overview, "dietary_advice": dietary_advice}
    except Exception as e:
        return {**state, "error": str(e)}


async def recognize_food_stream(image_url: str, user_profile: dict):
    from app.services.ai import get_streaming_vision_llm

    llm = get_streaming_vision_llm()
    prompt = FOOD_RECOGNITION_STREAM_PROMPT.replace(
        "{user_profile}", json.dumps(user_profile, ensure_ascii=False)
    )
    prepared_url = _prepare_image_url(image_url)
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=[{"type": "image_url", "image_url": {"url": prepared_url}}]),
    ]

    buffer = ""
    foods = []
    overview = None
    dietary_advice = ""
    has_error = False

    try:
        async for chunk in llm.astream(messages):
            content = chunk.content
            if not content:
                continue
            buffer += content

            if "\n" not in buffer:
                continue

            lines = buffer.split("\n")
            buffer = lines.pop()

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type")
                if event_type == "error":
                    has_error = True
                    yield {"type": "error", "data": {"message": data.get("message", "识别失败")}}
                    return
                elif event_type == "overview":
                    overview = {
                        "overallHealthScore": data.get("score", 60),
                        "healthTags": {
                            "positive": data.get("tags", {}).get("good", []),
                            "warning": data.get("tags", {}).get("warn", []),
                        },
                        "tagReasons": data.get("tagReasons", {}),
                        "summary": data.get("summary", ""),
                    }
                    yield {"type": "overview", "data": overview}
                elif event_type == "food":
                    food_item = {
                        "id": data.get("id", f"food_{len(foods) + 1}"),
                        "name": data.get("name", "未知食物"),
                        "category": data.get("category", ""),
                        "score": data.get("score", 60),
                        "weight": data.get("weight", {}).get("val", 100),
                        "tags": {
                            "positive": data.get("tags", {}).get("good", []),
                            "warning": data.get("tags", {}).get("warn", []),
                        },
                        "tagReasons": data.get("tagReasons", {}),
                        "advice": data.get("advice", ""),
                    }
                    foods.append(food_item)
                    yield {"type": "food_item", "data": food_item}
                elif event_type == "done":
                    dietary_advice = data.get("dietaryAdvice", "")
                    break

        if has_error:
            return

        advices = [f.get("advice", "") for f in foods if f.get("advice")]
        if not dietary_advice and advices:
            dietary_advice = "; ".join(advices)

        yield {"type": "done", "data": {"dietaryAdvice": dietary_advice, "foods": foods, "mealOverview": overview}}

    except Exception as e:
        yield {"type": "error", "data": {"message": str(e)}}
