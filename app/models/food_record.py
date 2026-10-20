import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Date, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class FoodRecord(Base):
    """饮食记录表：保存用户对每一餐的图片、主观评价及辅助明细。"""
    __tablename__ = "food_records"
    __table_args__ = {"comment": "饮食记录表：餐食图片、用户评价与食物明细"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="饮食记录主键")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True, comment="所属用户，关联 users.id")
    date = Column(Date, nullable=False, comment="实际就餐日期")
    meal_type = Column(String(16), nullable=False, comment="餐次类型：早餐、午餐、晚餐或其他")
    name = Column(String(120), nullable=False, default="", comment="用户填写的饮食名称")
    description = Column(Text, nullable=False, default="", comment="用户填写的饮食描述，可为空")
    positive_tags = Column(JSON, default=list, comment="用户认为这餐好的标签列表")
    negative_tags = Column(JSON, default=list, comment="用户不喜欢这餐的标签列表")
    price = Column(Numeric(10, 2), nullable=True, comment="餐费金额，可为空")
    image_url = Column(String(512), default="", comment="上传餐食图片的 MinIO 访问地址")
    image_urls = Column(JSON, nullable=False, default=list, comment="餐食图片地址列表，第一张为封面")
    rating = Column(Integer, default=0, comment="用户星级评分，0 表示尚未评分")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="创建时间，UTC")
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), comment="最后更新时间，UTC")
