from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


IncidentSeverity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["open", "investigating", "resolved"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentMessage(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    severity: IncidentSeverity
    status: IncidentStatus = "open"

    aggregate_key: str
    time_window_start: datetime
    time_window_end: datetime

    alert_ids: list[str] = Field(default_factory=list)
    alert_count: int = 0
    affected_hosts: list[str] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(default_factory=list)

    summary: str
    fields: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

