from datetime import datetime, date as Date
from uuid import UUID
from typing import Annotated, Optional
from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from app.schemas.base import CamelModel


class FoodItem(CamelModel):
    """单种食物的结构；可由用户填写或 AI 识别生成。"""
    name: str = Field(description="食物名称")
    category: str = Field(default="", description="食物分类")
    score: int = Field(default=60, description="健康评分")
    weight: float = Field(default=100, description="估算重量，单位：克")
    confidence: float = Field(default=0.8, description="识别置信度")
    tags: dict = Field(default_factory=dict, description="食物标签，通常按正向和警示分组")
    tag_reasons: dict = Field(default_factory=dict, description="标签出现的原因说明")
    advice: str = Field(default="", description="针对该食物的饮食建议")


class MealOverview(CamelModel):
    """一餐饮食的综合概览。"""
    overall_health_score: int = Field(default=60, description="这一餐的综合健康评分")
    health_tags: dict = Field(default_factory=dict, description="餐食级别的健康标签")
    tag_reasons: dict = Field(default_factory=dict, description="餐食标签的理由")
    summary: str = Field(default="", description="餐食总结")


PhotoUrl = Annotated[str, Field(min_length=1, max_length=512)]


class FoodRecordCreate(CamelModel):
    """新建饮食记录的请求 DTO。"""
    date: Date = Field(description="实际就餐日期")
    meal_type: str = Field(description="餐次类型")
    name: str = Field(default="", max_length=120, description="用户填写的饮食名称")
    description: str = Field(default="", max_length=1000, description="饮食描述，可选")
    positive_tags: list[str] = Field(default_factory=list, description="用户认为好的标签")
    negative_tags: list[str] = Field(default_factory=list, description="用户不喜欢的标签")
    price: Optional[float] = Field(default=None, ge=0, description="餐费金额，可选且不能为负")
    image_url: str = Field(default="", max_length=512, description="首张餐食图片 URL，兼容旧客户端")
    image_urls: list[PhotoUrl] = Field(default_factory=list, max_length=6, description="餐食图片 URL，最多 6 张")
    rating: int = Field(default=0, ge=0, le=5, description="用户星级评分，范围 0–5")


class FoodRecordUpdate(CamelModel):
    """更新饮食记录的请求 DTO；未传字段保持原值。"""
    date: Optional[Date] = Field(default=None, description="实际就餐日期")
    meal_type: Optional[str] = Field(default=None, description="餐次类型")
    name: Optional[str] = Field(default=None, max_length=120, description="饮食名称")
    description: Optional[str] = Field(default=None, max_length=1000, description="饮食描述")
    positive_tags: Optional[list[str]] = Field(default=None, description="用户认为好的标签")
    negative_tags: Optional[list[str]] = Field(default=None, description="用户不喜欢的标签")
    price: Optional[float] = Field(default=None, ge=0, description="餐费金额")
    image_url: Optional[str] = Field(default=None, max_length=512, description="餐食图片 URL")
    image_urls: Optional[list[PhotoUrl]] = Field(default=None, max_length=6, description="餐食图片 URL，最多 6 张")
    rating: Optional[int] = Field(default=None, ge=0, le=5, description="星级评分，范围 0–5")


class FoodRecordResponse(CamelModel):
    """返回给前端的饮食记录 VO。"""
    id: UUID = Field(description="饮食记录主键")
    user_id: UUID = Field(description="所属用户主键")
    date: Date = Field(description="实际就餐日期")
    meal_type: str = Field(description="餐次类型")
    name: str = Field(default="", description="饮食名称")
    description: str = Field(default="", description="饮食描述")
    positive_tags: list[str] = Field(default_factory=list, description="用户认为好的标签")
    negative_tags: list[str] = Field(default_factory=list, description="用户不喜欢的标签")
    price: Optional[float] = Field(default=None, description="餐费金额")
    image_url: str = Field(description="餐食图片 URL")
    image_urls: list[str] = Field(default_factory=list, description="餐食图片 URL 列表")
    rating: Optional[int] = Field(default=0, description="用户星级评分")
    created_at: datetime = Field(description="记录创建时间")

    @model_validator(mode="after")
    def include_legacy_photo(self):
        if not self.image_urls and self.image_url:
            self.image_urls = [self.image_url]
        return self


class FoodRecognitionRequest(CamelModel):
    """请求 AI 识别餐食图片的 DTO。"""
    image_url: str = Field(description="要识别的餐食图片 URL")
    user_feedback: str = Field(default="", description="用户对已有识别结果的补充或纠正")


class FoodRecognitionStreamRequest(CamelModel):
    """一次对话中联合识别整餐照片，兼容旧版单图请求。"""
    image_url: str = Field(default="", max_length=512)
    image_urls: list[PhotoUrl] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def require_photos(self):
        """将旧版单图字段补入列表，并拒绝空图片列表或空白地址。"""
        if not self.image_urls and self.image_url.strip():
            self.image_urls = [self.image_url.strip()]
        if not self.image_urls or any(not url.strip() for url in self.image_urls):
            raise PydanticCustomError("meal_photos", "请提供 1–6 张餐食照片")
        return self


class FoodRecognitionResponse(CamelModel):
    """AI 餐食识别结果 VO。"""
    foods: list[FoodItem] = Field(description="AI 识别到的食物明细")
    meal_overview: MealOverview = Field(description="AI 生成的餐食概览")
    dietary_advice: str = Field(default="", description="AI 给出的饮食建议")
