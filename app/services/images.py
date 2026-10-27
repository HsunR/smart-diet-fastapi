"""图片归属校验，以及不向数据库写入签名 URL 的响应转换。"""

from sqlalchemy import select

from app.core.exceptions import NotFound
from app.models.uploaded_image import UploadedImage
from app.schemas.food import FoodRecordResponse
from app.schemas.user import UserResponse
from app.services.storage import get_storage


async def owned_images(db, user_id, references: list[str]) -> list[str]:
    if not references:
        return []
    storage = get_storage()
    try:
        names = [storage.object_name(url) for url in references]
    except ValueError as exc:
        raise NotFound("图片不存在或无权访问，请重新上传") from exc
    owned = set((await db.scalars(select(UploadedImage.object_name).where(
        UploadedImage.user_id == user_id, UploadedImage.object_name.in_(set(names)),
    ))).all())
    if any(name not in owned for name in names):
        raise NotFound("图片不存在或无权访问，请重新上传")
    return [storage.reference_url(name) for name in names]


async def image_access(db, user_id, references: list[str]) -> list[str]:
    storage = get_storage()
    return [storage.signed_url(storage.object_name(url)) for url in await owned_images(db, user_id, references)]


async def record_responses(db, user_id, records) -> list[FoodRecordResponse]:
    """批量校验归属并签名；数据库仅含当前数据结构。"""
    responses = [FoodRecordResponse.model_validate(record) for record in records]
    references = list(dict.fromkeys(url for record in responses for url in record.image_urls))
    access = await image_access(db, user_id, references)
    signed = dict(zip(references, access))
    for record in responses:
        record.image_urls = [signed[url] for url in record.image_urls]
    return responses


async def user_response(db, user) -> UserResponse:
    response = UserResponse.model_validate(user)
    if response.avatar:
        response.avatar = (await image_access(db, user.id, [response.avatar]))[0]
    return response
