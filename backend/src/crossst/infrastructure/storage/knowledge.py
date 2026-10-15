from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.knowledge import HistoricalIncident, Runbook


def build_query_runbooks_statement(
    *,
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    problem_type: str | None = None,
    tag: str | None = None,
    active_only: bool = True,
    limit: int = 100,
) -> Select[tuple[Runbook]]:
    statement = select(Runbook).order_by(Runbook.updated_at.desc())

    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                Runbook.title.ilike(pattern),
                Runbook.content.ilike(pattern),
            )
        )
    if service is not None:
        statement = statement.where(Runbook.service == service)
    if component is not None:
        statement = statement.where(Runbook.component == component)
    if problem_type is not None:
        statement = statement.where(Runbook.problem_types.contains([problem_type]))
    if tag is not None:
        statement = statement.where(Runbook.tags.contains([tag]))
    if active_only:
        statement = statement.where(Runbook.is_active.is_(True))

    return statement.limit(limit)


async def query_runbooks(
    session: AsyncSession,
    *,
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    problem_type: str | None = None,
    tag: str | None = None,
    active_only: bool = True,
    limit: int = 100,
) -> list[Runbook]:
    statement = build_query_runbooks_statement(
        query=query,
        service=service,
        component=component,
        problem_type=problem_type,
        tag=tag,
        active_only=active_only,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


def build_query_historical_incidents_statement(
    *,
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    root_cause: str | None = None,
    tag: str | None = None,
    limit: int = 100,
) -> Select[tuple[HistoricalIncident]]:
    statement = select(HistoricalIncident).order_by(
        HistoricalIncident.occurred_at.desc()
    )

    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                HistoricalIncident.title.ilike(pattern),
                HistoricalIncident.summary.ilike(pattern),
                HistoricalIncident.resolution.ilike(pattern),
            )
        )
    if service is not None:
        statement = statement.where(HistoricalIncident.service == service)
    if component is not None:
        statement = statement.where(HistoricalIncident.component == component)
    if root_cause is not None:
        statement = statement.where(HistoricalIncident.root_cause == root_cause)
    if tag is not None:
        statement = statement.where(HistoricalIncident.tags.contains([tag]))

    return statement.limit(limit)


async def query_historical_incidents(
    session: AsyncSession,
    *,
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    root_cause: str | None = None,
    tag: str | None = None,
    limit: int = 100,
) -> list[HistoricalIncident]:
    statement = build_query_historical_incidents_statement(
        query=query,
        service=service,
        component=component,
        root_cause=root_cause,
        tag=tag,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())

