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

    rate_limit_enabled: bool = True
    rate_limit_prefix: str = Field(default="smartdiet:ratelimit:v1", min_length=1, pattern=r"^[A-Za-z0-9:_-]+$")
    rate_limit_ip_per_minute: int = Field(default=300, ge=1)
    rate_limit_user_per_minute: int = Field(default=120, ge=1)
    rate_limit_login_per_minute: int = Field(default=20, ge=1)
    rate_limit_account_per_minute: int = Field(default=10, ge=1)
    rate_limit_register_per_hour: int = Field(default=5, ge=1)
    rate_limit_upload_images_per_minute: int = Field(default=30, ge=6)
    rate_limit_ai_per_minute: int = Field(default=6, ge=1)


settings = Settings()
