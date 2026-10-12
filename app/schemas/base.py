import re
import warnings
from pydantic import BaseModel, ConfigDict

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
