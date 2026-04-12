from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    service_version: str = "0.1.0"

    database_url: str = "postgresql+asyncpg://app:app@postgres:5432/app"

    # JWT config (used in WP-006-BE)
    jwt_secret: str = "change-me-in-production"

    # External services
    inventory_service_url: str = "http://inventory-service:8001"
    notification_service_url: str = "http://notification-service:8002"


settings = Settings()
