from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from crossst.domain.models.base import Base


class NormalizedEventRecord(Base):
    __tablename__ = "normalized_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    raw_log_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    source_type: Mapped[str] = mapped_column(String(50), index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    service: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    component: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity_hint: Mapped[str] = mapped_column(String(20), index=True)

    message: Mapped[str] = mapped_column(Text)
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list] = mapped_column(JSONB, default=list)

