from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from crossst.domain.models.base import Base


class IncidentDiagnosis(Base):
    __tablename__ = "incident_diagnoses"

    diagnosis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    stop_reason: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)

    trigger_summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    hypotheses: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_chain: Mapped[list] = mapped_column(JSONB, default=list)
    ruled_out_hypotheses: Mapped[list] = mapped_column(JSONB, default=list)
    tool_call_summary: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

