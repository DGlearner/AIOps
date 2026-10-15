from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from crossst.domain.models.base import Base


class Incident(Base):
    __tablename__ = "incidents"

    incident_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)

    aggregate_key: Mapped[str] = mapped_column(String(255), index=True)
    time_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    time_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    alert_count: Mapped[int] = mapped_column(Integer)
    affected_hosts: Mapped[list] = mapped_column(JSONB, default=list)
    affected_services: Mapped[list] = mapped_column(JSONB, default=list)
    event_types: Mapped[list] = mapped_column(JSONB, default=list)

    summary: Mapped[str] = mapped_column(Text)
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"
    __table_args__ = (
        UniqueConstraint("incident_id", "alert_id", name="uq_incident_alert"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("incidents.incident_id", ondelete="CASCADE"),
        index=True,
    )
    alert_id: Mapped[str] = mapped_column(String(36), index=True)

