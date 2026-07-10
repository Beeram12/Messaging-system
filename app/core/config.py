from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://notif_user:notif_pass@localhost:5432/notifications"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "notifications.exchange"

    rate_limit_per_hour: int = 100
    max_retries: int = 3
    retry_base_delay_seconds: int = 5

    log_level: str = "INFO"
    api_key: str = "dev-local-api-key"


@lru_cache
def get_settings() -> Settings:
    return Settings()
