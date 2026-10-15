from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from crossst.domain.models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), index=True)
    raw_log_id: Mapped[str] = mapped_column(String(36), index=True)

    alert_type: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)

    source_type: Mapped[str] = mapped_column(String(50), index=True)
    component: Mapped[str] = mapped_column(String(100), index=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    message: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)

    count: Mapped[int] = mapped_column(Integer)
    window_seconds: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(255), index=True)

    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
