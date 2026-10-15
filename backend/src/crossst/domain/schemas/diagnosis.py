from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


DiagnosisStatus = Literal["running", "confirmed_diagnosis", "needs_human_review"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DiagnosisReport(BaseModel):
    diagnosis_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_id: str
    status: DiagnosisStatus
    stop_reason: str
    confidence: float

    trigger_summary: str
    root_cause: str | None = None
    hypotheses: list[str] = Field(default_factory=list)
    evidence_chain: list[str] = Field(default_factory=list)
    ruled_out_hypotheses: list[str] = Field(default_factory=list)
    tool_call_summary: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=utc_now)

