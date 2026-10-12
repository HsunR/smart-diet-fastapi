import warnings
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Suppress Pydantic v2 alias generator warnings
warnings.filterwarnings("ignore", message=".*alias.*Field.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*validation_alias.*Field.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*serialization_alias.*Field.*", category=UserWarning)


def to_camel(snake_str: str) -> str:
    parts = snake_str.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class CamelModel(BaseModel):
    """API 基类：Python 使用 snake_case，JSON 请求与响应自动使用 camelCase。"""
    model_config = ConfigDict(
        alias_generator=to_camel,  # 将 user_id 序列化为 userId。
        populate_by_name=True,  # 同时允许 snake_case 与 camelCase 输入。
        from_attributes=True,  # 支持从 SQLAlchemy ORM 对象构建响应。
    )


ResponseDataT = TypeVar("ResponseDataT")


class ApiResponse(CamelModel, Generic[ResponseDataT]):
    """统一 HTTP API 响应外层；实际业务数据始终放在 data 中。"""

    code: int = Field(default=0, description="业务状态码；0 表示成功，其余值与 HTTP 错误语义对应")
    message: str = Field(default="success", description="面向调用方的响应说明")
    data: ResponseDataT | None = Field(default=None, description="实际业务响应数据")

    @classmethod
    def success(cls, data: ResponseDataT | None = None, message: str = "success") -> "ApiResponse[ResponseDataT]":
        """创建统一的成功响应。"""
        return cls(code=0, message=message, data=data)
