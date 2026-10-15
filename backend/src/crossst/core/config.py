from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# 统一管理项目配置

class Settings(BaseSettings):
    app_name: str = "CrossST Agent"
    app_env: str = "dev"

    postgres_dsn: str = (
        "postgresql+asyncpg://crossst:crossst@localhost:5432/crossst"
    )

    redis_url: str = "redis://localhost:6379/0"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_logs_topic: str = "raw_logs"
    kafka_normalized_events_topic: str = "normalized_events"
    kafka_alerts_topic: str = "alerts"
    kafka_incidents_topic: str = "incidents"
    kafka_agent_tasks_topic: str = "agent_tasks"

    llm_enabled: bool = False
    llm_provider: str = "openai"
    llm_model: str = ""
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1200
    llm_timeout_seconds: int = 30
    diagnosis_llm_enabled: bool = False
    chat_investigation_llm_planner_enabled: bool = False

    chat_memory_window_size: int = 12
    chat_memory_query_limit: int = 200
    chat_memory_max_summary_chars: int = 4000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
