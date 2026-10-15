from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CrossST Log Ingest"
    app_env: str = "dev"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_logs_topic: str = "raw_logs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
