from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


AlertSeverity = Literal["low", "medium", "high", "critical"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AlertMessage(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str
    raw_log_id: str
    alert_type: str
    event_type: str
    severity: AlertSeverity
    source_type: str
    component: str
    host: str | None = None
    service: str | None = None
    message: str
    summary: str
    count: int
    window_seconds: int
    fingerprint: str
    fields: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
