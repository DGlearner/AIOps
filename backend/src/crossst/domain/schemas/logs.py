from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


SourceType = Literal["linux", "mysql", "app_service"]
Severity = Literal["info", "low", "medium", "high", "critical"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RawLogMessage(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    source_type: SourceType
    message: str
    host: str | None = None
    service: str | None = None
    source_name: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class NormalizedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    raw_log_id: str
    timestamp: datetime
    source_type: SourceType
    source_name: str | None = None
    host: str | None = None
    service: str | None = None
    component: str
    event_type: str
    message: str
    severity_hint: Severity
    fields: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
