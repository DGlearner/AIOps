from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolCallLog(BaseModel):
    tool_call_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    diagnosis_id: str | None = None
    tool_name: str
    reason: str
    kwargs: dict[str, Any] = Field(default_factory=dict)
    result_count: int = 0
    result_summary: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = 0

