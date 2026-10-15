from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


MessageRole = Literal["user", "assistant", "system"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationSessionCreate(BaseModel):
    user_id: str | None = None
    team_id: str | None = None
    current_incident_id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationSessionUpdate(BaseModel):
    title: str | None = None
    status: str | None = None


class ConversationSessionRecord(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    team_id: str | None = None
    current_incident_id: str | None = None
    title: str
    status: str = "open"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ConversationMessageCreate(BaseModel):
    role: MessageRole = "user"
    content: str
    incident_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationMessageRecord(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    incident_id: str | None = None
    role: MessageRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ConversationSummaryRecord(BaseModel):
    summary_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    current_incident_id: str | None = None
    known_facts: list[str] = Field(default_factory=list)
    checked_tools: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    pending_actions: list[str] = Field(default_factory=list)
    compressed_context: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    message_count: int = 0

