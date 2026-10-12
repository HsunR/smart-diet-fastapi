import json
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import BadRequest
from app.models.user import User
from app.schemas.food import FoodRecordCreate, FoodRecordUpdate, FoodRecordResponse, FoodRecognitionRequest, FoodRecognitionResponse
from app.schemas.report import WeeklyReportResponse
from app.services import food as food_service
from app.workflows.food_recognition import build_food_recognition_graph, FoodRecognitionState, recognize_food_stream

router = APIRouter(prefix="/records", tags=["food_records"])


@router.post("", response_model=FoodRecordResponse, status_code=201)
async def create_record(data: FoodRecordCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    record = await food_service.create_record(db, current_user.id, data)
    return FoodRecordResponse.model_validate(record)


@router.get("", response_model=list[FoodRecordResponse])
async def get_records(date: date = Query(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    records = await food_service.get_records_by_date(db, current_user.id, date)
    return [FoodRecordResponse.model_validate(r) for r in records]


@router.get("/history", response_model=list[FoodRecordResponse])
async def get_history(start: date = Query(...), end: date = Query(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    records = await food_service.get_history(db, current_user.id, start, end)
    return [FoodRecordResponse.model_validate(r) for r in records]


@router.delete("/{record_id}", status_code=204)
async def delete_record(record_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await food_service.delete_record(db, current_user.id, record_id)


@router.patch("/{record_id}", response_model=FoodRecordResponse)
async def update_record(record_id: UUID, data: FoodRecordUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    record = await food_service.update_record(db, current_user.id, record_id, data)
    return FoodRecordResponse.model_validate(record)


@router.post("/recognize", response_model=FoodRecognitionResponse)
async def recognize_food(
    req: FoodRecognitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    graph = build_food_recognition_graph()
    initial_state: FoodRecognitionState = {
        "image_url": req.image_url,
        "user_id": str(current_user.id),
        "user_profile": {"age": current_user.age, "weight": float(current_user.weight), "goal": current_user.goal},
        "user_feedback": req.user_feedback or "",
        "raw_response": None,
        "foods": [],
        "meal_overview": None,
        "dietary_advice": "",
        "error": None,
    }
    result = await graph.ainvoke(initial_state)
    if result.get("error"):
        raise BadRequest(result["error"])
    return FoodRecognitionResponse(
        foods=result["foods"],
        meal_overview=result["meal_overview"],
        dietary_advice=result["dietary_advice"],
    )


@router.post("/recognize/stream")
async def recognize_food_stream_endpoint(
    req: FoodRecognitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_profile = {"age": current_user.age, "weight": float(current_user.weight), "goal": current_user.goal}

    async def event_generator():
        async for event in recognize_food_stream(req.image_url, user_profile):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/report/weekly", response_model=WeeklyReportResponse)
async def weekly_report(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await food_service.get_weekly_report(db, current_user.id)
