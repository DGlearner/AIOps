from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


SourceType = Literal["linux", "mysql", "app_service"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IngestLogsRequest(BaseModel):
    source_type: SourceType
    logs: list[str] = Field(min_length=1)
    host: str | None = None
    service: str | None = None
    source_name: str | None = None


class IngestLogsResponse(BaseModel):
    status: str
    topic: str
    accepted: int
    log_ids: list[str]


class RawLogMessage(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    source_type: SourceType
    message: str
    host: str | None = None
    service: str | None = None
    source_name: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class StreamSourceConfig(BaseModel):
    name: str | None = None
    enabled: bool = True
    source_type: SourceType
    source_name: str | None = None
    host: str | None = None
    service: str | None = None
    file: str
    batch_size: int | None = None
    rate_per_second: float | None = None


class StreamSimulationConfig(BaseModel):
    batch_size: int = 10
    rate_per_second: float = 10
    sources: list[StreamSourceConfig] = Field(min_length=1)


def stream_source_to_payload(source: dict[str, Any], logs: list[str]) -> dict[str, Any]:
    payload = {
        "source_type": source["source_type"],
        "source_name": source.get("source_name"),
        "host": source.get("host"),
        "service": source.get("service"),
        "logs": logs,
    }
    return {key: value for key, value in payload.items() if value is not None}
