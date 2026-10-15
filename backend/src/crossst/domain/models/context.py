from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from crossst.domain.models.base import Base


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"

    dependency_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    dependency_service: Mapped[str] = mapped_column(String(255), index=True)
    dependency_type: Mapped[str] = mapped_column(String(50), index=True)
    direction: Mapped[str] = mapped_column(String(30), default="outbound", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    extra: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RecentDeployment(Base):
    __tablename__ = "recent_deployments"

    deployment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), index=True)
    environment: Mapped[str] = mapped_column(String(50), index=True)
    version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), index=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

