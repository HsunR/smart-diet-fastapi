from datetime import datetime, date
from uuid import UUID
from typing import Optional
from pydantic import Field

from app.schemas.base import CamelModel


class FoodItem(CamelModel):
    """单种食物的结构；可由用户填写或 AI 识别生成。"""
    name: str  # 食物名称。
    category: str = ""  # 食物分类。
    score: int = 60  # 健康评分。
    weight: float = 100  # 估算重量（克）。
    confidence: float = 0.8  # 识别置信度。
    tags: dict = {}  # 食物标签，通常按正向/警示分组。
    tag_reasons: dict = {}  # 标签出现的原因说明。
    advice: str = ""  # 针对该食物的饮食建议。


class MealOverview(CamelModel):
    """一餐饮食的综合概览。"""
    overall_health_score: int = 60  # 这一餐的综合健康评分。
    health_tags: dict = {}  # 餐食级别的健康标签。
    tag_reasons: dict = {}  # 餐食标签的理由。
    summary: str = ""  # 餐食总结。


class FoodRecordCreate(CamelModel):
    """新建饮食记录的请求 DTO。"""
    date: date  # 实际就餐日期。
    meal_type: str  # 餐次类型。
    name: str = Field(default="", max_length=120)  # 用户填写的饮食名称。
    description: str = Field(default="", max_length=1000)  # 饮食描述，可选。
    positive_tags: list[str] = Field(default_factory=list)  # 用户认为好的标签。
    negative_tags: list[str] = Field(default_factory=list)  # 用户不喜欢的标签。
    price: Optional[float] = Field(default=None, ge=0)  # 餐费金额，可选且不能为负。
    foods: list[FoodItem] = []  # 食物明细。
    meal_overview: MealOverview = MealOverview()  # 餐食综合信息。
    image_url: str = ""  # 餐食图片 URL。
    rating: int = 0  # 用户星级评分。


class FoodRecordUpdate(CamelModel):
    """更新饮食记录的请求 DTO；未传字段保持原值。"""
    date: Optional[date] = None  # 实际就餐日期。
    meal_type: Optional[str] = None  # 餐次类型。
    name: Optional[str] = Field(default=None, max_length=120)  # 饮食名称。
    description: Optional[str] = Field(default=None, max_length=1000)  # 饮食描述。
    positive_tags: Optional[list[str]] = None  # 用户认为好的标签。
    negative_tags: Optional[list[str]] = None  # 用户不喜欢的标签。
    price: Optional[float] = Field(default=None, ge=0)  # 餐费金额。
    image_url: Optional[str] = Field(default=None, max_length=512)  # 餐食图片 URL。
    rating: Optional[int] = Field(default=None, ge=0, le=5)  # 星级评分，范围 0–5。
    foods: Optional[list[FoodItem]] = None  # 食物明细。
    meal_overview: Optional[MealOverview] = None  # 餐食综合信息。


class FoodRecordResponse(CamelModel):
    """返回给前端的饮食记录 VO。"""
    id: UUID  # 饮食记录主键。
    user_id: UUID  # 所属用户主键。
    date: date  # 实际就餐日期。
    meal_type: str  # 餐次类型。
    name: str = ""  # 饮食名称。
    description: str = ""  # 饮食描述。
    positive_tags: list[str] = Field(default_factory=list)  # 用户认为好的标签。
    negative_tags: list[str] = Field(default_factory=list)  # 用户不喜欢的标签。
    price: Optional[float] = None  # 餐费金额。
    foods: list[FoodItem]  # 食物明细。
    meal_overview: MealOverview  # 餐食综合信息。
    image_url: str  # 餐食图片 URL。
    rating: Optional[int] = 0  # 用户星级评分。
    created_at: datetime  # 记录创建时间。


class FoodRecognitionRequest(CamelModel):
    """请求 AI 识别餐食图片的 DTO。"""
    image_url: str  # 要识别的餐食图片 URL。
    user_feedback: str = ""  # 用户对已有识别结果的补充或纠正。


class FoodRecognitionResponse(CamelModel):
    """AI 餐食识别结果 VO。"""
    foods: list[FoodItem]  # AI 识别到的食物明细。
    meal_overview: MealOverview  # AI 生成的餐食概览。
    dietary_advice: str = ""  # AI 给出的饮食建议。
