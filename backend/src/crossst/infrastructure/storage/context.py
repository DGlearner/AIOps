from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.context import RecentDeployment, ServiceDependency


def build_query_service_dependencies_statement(
    *,
    service: str | None = None,
    dependency_service: str | None = None,
    dependency_type: str | None = None,
    direction: str | None = None,
    active_only: bool = True,
    limit: int = 100,
) -> Select[tuple[ServiceDependency]]:
    statement = select(ServiceDependency).order_by(ServiceDependency.updated_at.desc())

    if service is not None:
        statement = statement.where(ServiceDependency.service == service)
    if dependency_service is not None:
        statement = statement.where(ServiceDependency.dependency_service == dependency_service)
    if dependency_type is not None:
        statement = statement.where(ServiceDependency.dependency_type == dependency_type)
    if direction is not None:
        statement = statement.where(ServiceDependency.direction == direction)
    if active_only:
        statement = statement.where(ServiceDependency.is_active.is_(True))

    return statement.limit(limit)


async def query_service_dependencies(
    session: AsyncSession,
    *,
    service: str | None = None,
    dependency_service: str | None = None,
    dependency_type: str | None = None,
    direction: str | None = None,
    active_only: bool = True,
    limit: int = 100,
) -> list[ServiceDependency]:
    statement = build_query_service_dependencies_statement(
        service=service,
        dependency_service=dependency_service,
        dependency_type=dependency_type,
        direction=direction,
        active_only=active_only,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


def build_query_recent_deployments_statement(
    *,
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> Select[tuple[RecentDeployment]]:
    statement = select(RecentDeployment).order_by(RecentDeployment.deployed_at.desc())

    if service is not None:
        statement = statement.where(RecentDeployment.service == service)
    if environment is not None:
        statement = statement.where(RecentDeployment.environment == environment)
    if status is not None:
        statement = statement.where(RecentDeployment.status == status)
    if start_time is not None:
        statement = statement.where(RecentDeployment.deployed_at >= start_time)
    if end_time is not None:
        statement = statement.where(RecentDeployment.deployed_at <= end_time)

    return statement.limit(limit)


async def query_recent_deployments(
    session: AsyncSession,
    *,
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[RecentDeployment]:
    statement = build_query_recent_deployments_statement(
        service=service,
        environment=environment,
        status=status,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())

