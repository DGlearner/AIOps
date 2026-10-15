from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.event import NormalizedEventRecord
from crossst.domain.schemas.logs import NormalizedEvent


async def save_normalized_event(
    session: AsyncSession,
    event: NormalizedEvent,
) -> None:
    existing = await session.get(NormalizedEventRecord, event.event_id)
    if existing is not None:
        return

    session.add(
        NormalizedEventRecord(
            event_id=event.event_id,
            raw_log_id=event.raw_log_id,
            timestamp=event.timestamp,
            source_type=event.source_type,
            source_name=event.source_name,
            host=event.host,
            service=event.service,
            component=event.component,
            event_type=event.event_type,
            severity_hint=event.severity_hint,
            message=event.message,
            fields=event.fields,
            tags=event.tags,
        )
    )
    await session.commit()


def build_query_events_statement(
    *,
    source_type: str | None = None,
    event_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    component: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> Select[tuple[NormalizedEventRecord]]:
    statement = select(NormalizedEventRecord).order_by(NormalizedEventRecord.timestamp.desc())

    if source_type is not None:
        statement = statement.where(NormalizedEventRecord.source_type == source_type)
    if event_type is not None:
        statement = statement.where(NormalizedEventRecord.event_type == event_type)
    if host is not None:
        statement = statement.where(NormalizedEventRecord.host == host)
    if service is not None:
        statement = statement.where(NormalizedEventRecord.service == service)
    if component is not None:
        statement = statement.where(NormalizedEventRecord.component == component)
    if start_time is not None:
        statement = statement.where(NormalizedEventRecord.timestamp >= start_time)
    if end_time is not None:
        statement = statement.where(NormalizedEventRecord.timestamp <= end_time)

    return statement.limit(limit)


async def query_events(
    session: AsyncSession,
    *,
    source_type: str | None = None,
    event_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    component: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[NormalizedEventRecord]:
    statement = build_query_events_statement(
        source_type=source_type,
        event_type=event_type,
        host=host,
        service=service,
        component=component,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())

