from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.alert import Alert
from crossst.domain.schemas.alerts import AlertMessage


ALERT_LIFECYCLE_KEY = "_lifecycle"
ALERT_LIFECYCLE_STATUSES = {
    "open",
    "acknowledged",
    "resolved",
    "silenced",
    "false_positive",
}


def build_alert_lifecycle(
    *,
    status: str = "open",
    owner: str | None = None,
    updated_by: str | None = None,
    note: str | None = None,
    updated_at: datetime | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if status not in ALERT_LIFECYCLE_STATUSES:
        raise ValueError(f"Unsupported alert lifecycle status: {status}")

    timestamp = updated_at.isoformat() if updated_at is not None else None
    lifecycle = {
        "status": status,
        "owner": owner,
        "updated_by": updated_by,
        "note": note,
        "updated_at": timestamp,
        "history": list(history or []),
    }
    if updated_by is not None or note is not None or updated_at is not None:
        lifecycle["history"].append(
            {
                "status": status,
                "owner": owner,
                "updated_by": updated_by,
                "note": note,
                "updated_at": timestamp,
            }
        )
    return lifecycle


def get_alert_lifecycle(fields: dict[str, Any] | None) -> dict[str, Any]:
    fields = fields or {}
    lifecycle = fields.get(ALERT_LIFECYCLE_KEY)
    if not isinstance(lifecycle, dict):
        return build_alert_lifecycle()

    status = str(lifecycle.get("status") or "open")
    if status not in ALERT_LIFECYCLE_STATUSES:
        status = "open"

    history = lifecycle.get("history")
    return {
        "status": status,
        "owner": lifecycle.get("owner"),
        "updated_by": lifecycle.get("updated_by"),
        "note": lifecycle.get("note"),
        "updated_at": lifecycle.get("updated_at"),
        "history": history if isinstance(history, list) else [],
    }


def build_alert_lifecycle_update(
    fields: dict[str, Any] | None,
    *,
    status: str,
    owner: str | None = None,
    updated_by: str | None = None,
    note: str | None = None,
    updated_at: datetime,
) -> dict[str, Any]:
    updated_fields = dict(fields or {})
    current = get_alert_lifecycle(updated_fields)
    updated_fields[ALERT_LIFECYCLE_KEY] = build_alert_lifecycle(
        status=status,
        owner=owner if owner is not None else current.get("owner"),
        updated_by=updated_by,
        note=note,
        updated_at=updated_at,
        history=current.get("history", []),
    )
    return updated_fields


def summarize_alert_lifecycles(alerts: list[Alert]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for alert in alerts:
        lifecycle = get_alert_lifecycle(alert.fields)
        status = str(lifecycle["status"])
        severity = str(alert.severity)
        by_status[status] = by_status.get(status, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1

    return {
        "total": len(alerts),
        "by_status": by_status,
        "by_severity": by_severity,
    }


async def save_alert(session: AsyncSession, alert: AlertMessage) -> None:
    session.add(
        Alert(
            alert_id=alert.alert_id,
            event_id=alert.event_id,
            raw_log_id=alert.raw_log_id,
            alert_type=alert.alert_type,
            event_type=alert.event_type,
            severity=alert.severity,
            source_type=alert.source_type,
            component=alert.component,
            host=alert.host,
            service=alert.service,
            message=alert.message,
            summary=alert.summary,
            count=alert.count,
            window_seconds=alert.window_seconds,
            fingerprint=alert.fingerprint,
            fields=alert.fields,
            tags=alert.tags,
            created_at=alert.created_at,
        )
    )
    await session.commit()


async def get_alert_by_id(
    session: AsyncSession,
    alert_id: str,
) -> Alert | None:
    result = await session.execute(select(Alert).where(Alert.alert_id == alert_id))
    return result.scalar_one_or_none()


async def update_alert_lifecycle(
    session: AsyncSession,
    alert: Alert,
    *,
    status: str,
    owner: str | None = None,
    updated_by: str | None = None,
    note: str | None = None,
    updated_at: datetime,
) -> Alert:
    alert.fields = build_alert_lifecycle_update(
        alert.fields,
        status=status,
        owner=owner,
        updated_by=updated_by,
        note=note,
        updated_at=updated_at,
    )
    await session.commit()
    await session.refresh(alert)
    return alert


def build_query_alerts_statement(
    *,
    alert_type: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> Select[tuple[Alert]]:
    statement = select(Alert).order_by(Alert.created_at.desc())

    if alert_type is not None:
        statement = statement.where(Alert.alert_type == alert_type)
    if event_type is not None:
        statement = statement.where(Alert.event_type == event_type)
    if severity is not None:
        statement = statement.where(Alert.severity == severity)
    if source_type is not None:
        statement = statement.where(Alert.source_type == source_type)
    if host is not None:
        statement = statement.where(Alert.host == host)
    if service is not None:
        statement = statement.where(Alert.service == service)
    if start_time is not None:
        statement = statement.where(Alert.created_at >= start_time)
    if end_time is not None:
        statement = statement.where(Alert.created_at <= end_time)

    return statement.limit(limit)


async def query_alerts(
    session: AsyncSession,
    *,
    alert_type: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[Alert]:
    statement = build_query_alerts_statement(
        alert_type=alert_type,
        event_type=event_type,
        severity=severity,
        source_type=source_type,
        host=host,
        service=service,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())

