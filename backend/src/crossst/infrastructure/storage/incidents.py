from datetime import datetime

from sqlalchemy import Select
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.incident import Incident, IncidentAlert
from crossst.domain.schemas.incidents import IncidentMessage


async def get_incident_by_id(
    session: AsyncSession,
    incident_id: str,
) -> Incident | None:
    result = await session.execute(
        select(Incident).where(Incident.incident_id == incident_id)
    )
    return result.scalar_one_or_none()


def build_get_incident_by_alert_id_statement(alert_id: str) -> Select[tuple[Incident]]:
    return (
        select(Incident)
        .join(IncidentAlert, Incident.incident_id == IncidentAlert.incident_id)
        .where(IncidentAlert.alert_id == alert_id)
        .order_by(Incident.created_at.desc())
        .limit(1)
    )


async def get_incident_by_alert_id(
    session: AsyncSession,
    alert_id: str,
) -> Incident | None:
    result = await session.execute(build_get_incident_by_alert_id_statement(alert_id))
    return result.scalar_one_or_none()


async def save_new_incident(
    session: AsyncSession,
    incident: IncidentMessage,
) -> None:
    session.add(
        Incident(
            incident_id=incident.incident_id,
            title=incident.title,
            severity=incident.severity,
            status=incident.status,
            aggregate_key=incident.aggregate_key,
            time_window_start=incident.time_window_start,
            time_window_end=incident.time_window_end,
            alert_count=incident.alert_count,
            affected_hosts=incident.affected_hosts,
            affected_services=incident.affected_services,
            event_types=incident.event_types,
            summary=incident.summary,
            fields=incident.fields,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
        )
    )

    for alert_id in incident.alert_ids:
        session.add(
            IncidentAlert(
                incident_id=incident.incident_id,
                alert_id=alert_id,
            )
        )

    await session.commit()


def build_query_incidents_statement(
    *,
    severity: str | None = None,
    status: str | None = None,
    aggregate_key: str | None = None,
    host: str | None = None,
    service: str | None = None,
    event_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> Select[tuple[Incident]]:
    statement = select(Incident).order_by(Incident.created_at.desc())

    if severity is not None:
        statement = statement.where(Incident.severity == severity)
    if status is not None:
        statement = statement.where(Incident.status == status)
    if aggregate_key is not None:
        statement = statement.where(Incident.aggregate_key == aggregate_key)
    if host is not None:
        statement = statement.where(Incident.affected_hosts.contains([host]))
    if service is not None:
        statement = statement.where(Incident.affected_services.contains([service]))
    if event_type is not None:
        statement = statement.where(Incident.event_types.contains([event_type]))
    if start_time is not None:
        statement = statement.where(Incident.created_at >= start_time)
    if end_time is not None:
        statement = statement.where(Incident.created_at <= end_time)

    return statement.limit(limit)


async def query_incidents(
    session: AsyncSession,
    *,
    severity: str | None = None,
    status: str | None = None,
    aggregate_key: str | None = None,
    host: str | None = None,
    service: str | None = None,
    event_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[Incident]:
    statement = build_query_incidents_statement(
        severity=severity,
        status=status,
        aggregate_key=aggregate_key,
        host=host,
        service=service,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def update_existing_incident(
    session: AsyncSession,
    existing: Incident,
    incident: IncidentMessage,
) -> None:
    existing.title = incident.title
    existing.severity = incident.severity
    existing.status = incident.status
    existing.time_window_end = incident.time_window_end
    existing.alert_count = incident.alert_count
    existing.affected_hosts = incident.affected_hosts
    existing.affected_services = incident.affected_services
    existing.event_types = incident.event_types
    existing.summary = incident.summary
    existing.fields = incident.fields
    existing.updated_at = incident.updated_at

    existing_alert_ids_result = await session.execute(
        select(IncidentAlert.alert_id).where(
            IncidentAlert.incident_id == existing.incident_id
        )
    )
    existing_alert_ids = set(existing_alert_ids_result.scalars().all())

    for alert_id in incident.alert_ids:
        if alert_id not in existing_alert_ids:
            session.add(
                IncidentAlert(
                    incident_id=existing.incident_id,
                    alert_id=alert_id,
                )
            )

    await session.commit()

