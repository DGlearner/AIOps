from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from crossst.domain.models.base import Base


class Runbook(Base):
    __tablename__ = "runbooks"

    runbook_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    component: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    problem_types: Mapped[list] = mapped_column(JSONB, default=list)
    content: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    extra: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class HistoricalIncident(Base):
    __tablename__ = "historical_incidents"

    historical_incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    component: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    root_cause: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_chain: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    extra: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

