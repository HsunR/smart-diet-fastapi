from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+asyncpg://smartdiet:smartdiet@localhost:5432/smartdiet"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    wechat_appid: str = ""
    wechat_secret: str = ""
    allow_mock_login: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_api_key: str = ""
    llm_vision_model: str = ""
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "smartdiet"
    minio_secure: bool = False
    minio_public_url: str = "http://localhost:9000"
    minio_region: str = "us-east-1"
    image_url_expire_seconds: int = Field(default=900, ge=60, le=3600)

    redis_url: str = "redis://localhost:6379/0"
    redis_password: SecretStr = SecretStr("")


settings = Settings()
