"""API 数据结构包（DTO / 响应 VO）。

这里的 Pydantic 模型定义接口的请求参数、响应内容与校验规则：
- *Create / *Update：请求 DTO；
- *Response：响应 DTO / VO；
- 领域辅助结构：嵌套字段的类型与校验。

Schema 与 models 分离，避免暴露数据库字段，并让 API 文档与输入校验保持一致。
"""

from app.schemas.user import UserCreate, UserUpdate, UserResponse, LoginRequest, LoginResponse
from app.schemas.food import FoodItem, MealOverview, FoodRecordCreate, FoodRecordUpdate, FoodRecordResponse, FoodRecognitionRequest, FoodRecognitionResponse
from app.schemas.chat import MessageCreate, MessageResponse, ConversationResponse
from app.schemas.report import WeeklyReportResponse

__all__ = [
    "UserCreate", "UserUpdate", "UserResponse", "LoginRequest", "LoginResponse",
    "FoodItem", "MealOverview", "FoodRecordCreate", "FoodRecordUpdate", "FoodRecordResponse",
    "FoodRecognitionRequest", "FoodRecognitionResponse",
    "MessageCreate", "MessageResponse", "ConversationResponse",
    "WeeklyReportResponse",
]
