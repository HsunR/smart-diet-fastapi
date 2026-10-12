"""数据库 ORM 模型包。

这里的类由 SQLAlchemy 映射到数据库表，负责定义字段类型、主键、外键和表关系。
它们只描述数据如何持久化，不应直接作为 API 的请求或响应结构返回给前端。
"""

from app.models.user import User
from app.models.food_record import FoodRecord
from app.models.conversation import Conversation
from app.models.message import Message

__all__ = ["User", "FoodRecord", "Conversation", "Message"]
