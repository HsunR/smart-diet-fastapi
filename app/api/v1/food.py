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
from app.schemas.base import ApiResponse
from app.schemas.food import FoodRecordCreate, FoodRecordUpdate, FoodRecordResponse, FoodRecognitionRequest, FoodRecognitionResponse, FoodRecognitionStreamRequest
from app.schemas.report import WeeklyReportResponse
from app.services import food as food_service
from app.services.food_recognition import recognize_food as run_food_recognition, FoodRecognitionState, recognize_food_stream
from app.services.images import owned_images, record_responses
from app.core.abuse_protection import guard_recognition

router = APIRouter(prefix="/records", tags=["food_records"])


@router.post("", response_model=ApiResponse[FoodRecordResponse], status_code=201)
async def create_record(data: FoodRecordCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    record = await food_service.create_record(db, current_user.id, data)
    return ApiResponse.success((await record_responses(db, current_user.id, [record]))[0])


@router.get("", response_model=ApiResponse[list[FoodRecordResponse]])
async def get_records(date: date = Query(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    records = await food_service.get_records_by_date(db, current_user.id, date)
    return ApiResponse.success(await record_responses(db, current_user.id, records))


@router.get("/history", response_model=ApiResponse[list[FoodRecordResponse]])
async def get_history(start: date = Query(...), end: date = Query(...), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    records = await food_service.get_history(db, current_user.id, start, end)
    return ApiResponse.success(await record_responses(db, current_user.id, records))


@router.delete("/{record_id}", status_code=204)
async def delete_record(record_id: UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    await food_service.delete_record(db, current_user.id, record_id)


@router.patch("/{record_id}", response_model=ApiResponse[FoodRecordResponse])
async def update_record(record_id: UUID, data: FoodRecordUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    record = await food_service.update_record(db, current_user.id, record_id, data)
    return ApiResponse.success((await record_responses(db, current_user.id, [record]))[0])


@router.post("/recognize", response_model=ApiResponse[FoodRecognitionResponse])
async def recognize_food(
    req: FoodRecognitionRequest,
    current_user: User = Depends(guard_recognition),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    image_url = (await owned_images(db, current_user.id, [req.image_url]))[0]
    initial_state: FoodRecognitionState = {
        "image_url": image_url,
        "user_id": str(current_user.id),
        "user_profile": {"age": current_user.age, "weight": float(current_user.weight)},
        "user_feedback": req.user_feedback or "",
        "raw_response": None,
        "foods": [],
        "meal_overview": None,
        "dietary_advice": "",
        "error": None,
    }
    result = await run_food_recognition(initial_state)
    if result.get("error"):
        raise BadRequest(result["error"])
    return ApiResponse.success(FoodRecognitionResponse(
        foods=result["foods"],
        meal_overview=result["meal_overview"],
        dietary_advice=result["dietary_advice"],
    ))


@router.post("/recognize/stream")
async def recognize_food_stream_endpoint(
    req: FoodRecognitionStreamRequest,
    current_user: User = Depends(guard_recognition),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user_profile = {"age": current_user.age, "weight": float(current_user.weight)}
    image_urls = await owned_images(db, current_user.id, req.image_urls)

    async def event_generator():
        async for event in recognize_food_stream(image_urls, user_profile):
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


@router.get("/report/weekly", response_model=ApiResponse[WeeklyReportResponse])
async def weekly_report(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    return ApiResponse.success(await food_service.get_weekly_report(db, current_user.id))
