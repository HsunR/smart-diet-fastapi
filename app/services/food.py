from uuid import UUID
from datetime import date, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.models.food_record import FoodRecord
from app.schemas.food import FoodRecordCreate, FoodRecordUpdate
from app.schemas.report import WeeklyReportResponse


async def create_record(db: AsyncSession, user_id: UUID, data: FoodRecordCreate) -> FoodRecord:
    image_urls = data.image_urls if "image_urls" in data.model_fields_set else ([data.image_url] if data.image_url else [])
    record = FoodRecord(
        user_id=user_id,
        date=data.date,
        meal_type=data.meal_type,
        name=data.name,
        description=data.description,
        positive_tags=data.positive_tags,
        negative_tags=data.negative_tags,
        price=data.price,
        image_url=image_urls[0] if image_urls else "",
        image_urls=image_urls,
        rating=data.rating,
    )
    db.add(record)
    await db.flush()
    return record


async def get_records_by_date(db: AsyncSession, user_id: UUID, query_date: date) -> list[FoodRecord]:
    result = await db.execute(
        select(FoodRecord)
        .where(and_(FoodRecord.user_id == user_id, FoodRecord.date == query_date))
        .order_by(FoodRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def get_history(db: AsyncSession, user_id: UUID, start: date, end: date) -> list[FoodRecord]:
    result = await db.execute(
        select(FoodRecord)
        .where(and_(FoodRecord.user_id == user_id, FoodRecord.date >= start, FoodRecord.date <= end))
        .order_by(FoodRecord.date.desc(), FoodRecord.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())


async def delete_record(db: AsyncSession, user_id: UUID, record_id: UUID) -> None:
    result = await db.execute(
        select(FoodRecord).where(and_(FoodRecord.id == record_id, FoodRecord.user_id == user_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFound("记录不存在")
    await db.delete(record)
    await db.flush()


async def update_record(db: AsyncSession, user_id: UUID, record_id: UUID, data: FoodRecordUpdate) -> FoodRecord:
    result = await db.execute(
        select(FoodRecord).where(and_(FoodRecord.id == record_id, FoodRecord.user_id == user_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFound("记录不存在")
    update_data = data.model_dump(exclude_unset=True)
    if "image_urls" in update_data:
        update_data["image_urls"] = update_data["image_urls"] or []
        update_data["image_url"] = update_data["image_urls"][0] if update_data["image_urls"] else ""
    elif "image_url" in update_data:
        update_data["image_url"] = update_data["image_url"] or ""
        update_data["image_urls"] = [update_data["image_url"]] if update_data["image_url"] else []
    for field, value in update_data.items():
        setattr(record, field, value)
    await db.flush()
    return record


async def get_weekly_report(db: AsyncSession, user_id: UUID) -> WeeklyReportResponse:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    records = await get_history(db, user_id, week_start, week_end)

    scores = []
    score_trend = []
    for r in records:
        score = r.rating or 0
        scores.append(score)
        score_trend.append({"date": str(r.date), "score": score})

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    return WeeklyReportResponse(
        week_start=week_start,
        week_end=week_end,
        total_meals=len(records),
        avg_score=avg_score,
        score_trend=score_trend,
        report=f"本周共记录 {len(records)} 餐，平均星级评分 {avg_score}",
    )
