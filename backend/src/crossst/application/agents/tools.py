from datetime import datetime, timedelta, timezone
from typing import Any

from crossst.domain.models.alert import Alert
from crossst.domain.models.context import RecentDeployment, ServiceDependency
from crossst.domain.models.event import NormalizedEventRecord
from crossst.domain.models.incident import Incident
from crossst.domain.models.knowledge import HistoricalIncident, Runbook
from crossst.infrastructure.storage.alerts import get_alert_lifecycle, query_alerts
from crossst.infrastructure.storage.context import query_recent_deployments, query_service_dependencies
from crossst.infrastructure.storage.events import query_events
from crossst.infrastructure.storage.incidents import query_incidents
from crossst.infrastructure.storage.knowledge import query_historical_incidents, query_runbooks
from crossst.infrastructure.storage.postgres import AsyncSessionLocal
from crossst.infrastructure.storage.redis import get_redis


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_time_window(
    *,
    minutes: int = 5,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[datetime, datetime]:
    resolved_end = end_time or utc_now()
    resolved_start = start_time or (resolved_end - timedelta(minutes=minutes))
    return resolved_start, resolved_end


def serialize_event(event: NormalizedEventRecord) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "raw_log_id": event.raw_log_id,
        "timestamp": event.timestamp.isoformat(),
        "source_type": event.source_type,
        "source_name": event.source_name,
        "host": event.host,
        "service": event.service,
        "component": event.component,
        "event_type": event.event_type,
        "severity_hint": event.severity_hint,
        "message": event.message,
        "fields": event.fields,
        "tags": event.tags,
    }


def serialize_alert(alert: Alert) -> dict[str, Any]:
    return {
        "alert_id": alert.alert_id,
        "event_id": alert.event_id,
        "raw_log_id": alert.raw_log_id,
        "alert_type": alert.alert_type,
        "event_type": alert.event_type,
        "severity": alert.severity,
        "source_type": alert.source_type,
        "component": alert.component,
        "host": alert.host,
        "service": alert.service,
        "summary": alert.summary,
        "count": alert.count,
        "window_seconds": alert.window_seconds,
        "fingerprint": alert.fingerprint,
        "fields": alert.fields,
        "lifecycle": get_alert_lifecycle(alert.fields),
        "tags": alert.tags,
        "created_at": alert.created_at.isoformat(),
    }


def serialize_incident(incident: Incident) -> dict[str, Any]:
    return {
        "incident_id": incident.incident_id,
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "aggregate_key": incident.aggregate_key,
        "time_window_start": incident.time_window_start.isoformat(),
        "time_window_end": incident.time_window_end.isoformat(),
        "alert_count": incident.alert_count,
        "affected_hosts": incident.affected_hosts,
        "affected_services": incident.affected_services,
        "event_types": incident.event_types,
        "summary": incident.summary,
        "fields": incident.fields,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }


def serialize_service_dependency(dependency: ServiceDependency) -> dict[str, Any]:
    return {
        "dependency_id": dependency.dependency_id,
        "service": dependency.service,
        "dependency_service": dependency.dependency_service,
        "dependency_type": dependency.dependency_type,
        "direction": dependency.direction,
        "description": dependency.description,
        "is_active": dependency.is_active,
        "metadata": dependency.extra,
        "created_at": dependency.created_at.isoformat(),
        "updated_at": dependency.updated_at.isoformat(),
    }


def serialize_recent_deployment(deployment: RecentDeployment) -> dict[str, Any]:
    return {
        "deployment_id": deployment.deployment_id,
        "service": deployment.service,
        "environment": deployment.environment,
        "version": deployment.version,
        "status": deployment.status,
        "actor": deployment.actor,
        "summary": deployment.summary,
        "metadata": deployment.extra,
        "deployed_at": deployment.deployed_at.isoformat(),
        "created_at": deployment.created_at.isoformat(),
    }


def serialize_runbook(runbook: Runbook) -> dict[str, Any]:
    return {
        "runbook_id": runbook.runbook_id,
        "title": runbook.title,
        "service": runbook.service,
        "component": runbook.component,
        "problem_types": runbook.problem_types,
        "content": runbook.content,
        "steps": runbook.steps,
        "tags": runbook.tags,
        "metadata": runbook.extra,
        "is_active": runbook.is_active,
        "created_at": runbook.created_at.isoformat(),
        "updated_at": runbook.updated_at.isoformat(),
    }


def serialize_historical_incident(incident: HistoricalIncident) -> dict[str, Any]:
    return {
        "historical_incident_id": incident.historical_incident_id,
        "title": incident.title,
        "service": incident.service,
        "component": incident.component,
        "root_cause": incident.root_cause,
        "summary": incident.summary,
        "resolution": incident.resolution,
        "evidence_chain": incident.evidence_chain,
        "tags": incident.tags,
        "metadata": incident.extra,
        "occurred_at": incident.occurred_at.isoformat(),
        "created_at": incident.created_at.isoformat(),
    }


async def query_events_tool(
    *,
    minutes: int = 5,
    source_type: str | None = None,
    event_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    component: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_start, resolved_end = resolve_time_window(
        minutes=minutes,
        start_time=start_time,
        end_time=end_time,
    )

    async with AsyncSessionLocal() as session:
        events = await query_events(
            session,
            source_type=source_type,
            event_type=event_type,
            host=host,
            service=service,
            component=component,
            start_time=resolved_start,
            end_time=resolved_end,
            limit=limit,
        )

    return {
        "tool": "query_events",
        "time_window": {
            "start": resolved_start.isoformat(),
            "end": resolved_end.isoformat(),
        },
        "filters": {
            "source_type": source_type,
            "event_type": event_type,
            "host": host,
            "service": service,
            "component": component,
        },
        "count": len(events),
        "events": [serialize_event(event) for event in events],
    }


async def query_alerts_tool(
    *,
    minutes: int = 5,
    alert_type: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_start, resolved_end = resolve_time_window(
        minutes=minutes,
        start_time=start_time,
        end_time=end_time,
    )

    async with AsyncSessionLocal() as session:
        alerts = await query_alerts(
            session,
            alert_type=alert_type,
            event_type=event_type,
            severity=severity,
            source_type=source_type,
            host=host,
            service=service,
            start_time=resolved_start,
            end_time=resolved_end,
            limit=limit,
        )

    return {
        "tool": "query_alerts",
        "time_window": {
            "start": resolved_start.isoformat(),
            "end": resolved_end.isoformat(),
        },
        "filters": {
            "alert_type": alert_type,
            "event_type": event_type,
            "severity": severity,
            "source_type": source_type,
            "host": host,
            "service": service,
        },
        "count": len(alerts),
        "alerts": [serialize_alert(alert) for alert in alerts],
    }


async def query_incidents_tool(
    *,
    minutes: int = 5,
    severity: str | None = None,
    status: str | None = None,
    aggregate_key: str | None = None,
    host: str | None = None,
    service: str | None = None,
    event_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_start, resolved_end = resolve_time_window(
        minutes=minutes,
        start_time=start_time,
        end_time=end_time,
    )

    async with AsyncSessionLocal() as session:
        incidents = await query_incidents(
            session,
            severity=severity,
            status=status,
            aggregate_key=aggregate_key,
            host=host,
            service=service,
            event_type=event_type,
            start_time=resolved_start,
            end_time=resolved_end,
            limit=limit,
        )

    return {
        "tool": "query_incidents",
        "time_window": {
            "start": resolved_start.isoformat(),
            "end": resolved_end.isoformat(),
        },
        "filters": {
            "severity": severity,
            "status": status,
            "aggregate_key": aggregate_key,
            "host": host,
            "service": service,
            "event_type": event_type,
        },
        "count": len(incidents),
        "incidents": [serialize_incident(incident) for incident in incidents],
    }


async def query_service_dependencies_tool(
    *,
    service: str | None = None,
    dependency_service: str | None = None,
    dependency_type: str | None = None,
    direction: str | None = None,
    active_only: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        dependencies = await query_service_dependencies(
            session,
            service=service,
            dependency_service=dependency_service,
            dependency_type=dependency_type,
            direction=direction,
            active_only=active_only,
            limit=limit,
        )

    return {
        "tool": "query_service_dependencies",
        "filters": {
            "service": service,
            "dependency_service": dependency_service,
            "dependency_type": dependency_type,
            "direction": direction,
            "active_only": active_only,
        },
        "count": len(dependencies),
        "dependencies": [
            serialize_service_dependency(dependency) for dependency in dependencies
        ],
    }


async def query_recent_deployments_tool(
    *,
    minutes: int = 60,
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    resolved_start, resolved_end = resolve_time_window(
        minutes=minutes,
        start_time=start_time,
        end_time=end_time,
    )

    async with AsyncSessionLocal() as session:
        deployments = await query_recent_deployments(
            session,
            service=service,
            environment=environment,
            status=status,
            start_time=resolved_start,
            end_time=resolved_end,
            limit=limit,
        )

    return {
        "tool": "query_recent_deployments",
        "time_window": {
            "start": resolved_start.isoformat(),
            "end": resolved_end.isoformat(),
        },
        "filters": {
            "service": service,
            "environment": environment,
            "status": status,
        },
        "count": len(deployments),
        "deployments": [
            serialize_recent_deployment(deployment) for deployment in deployments
        ],
    }


async def query_runbooks_tool(
    *,
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    problem_type: str | None = None,
    tag: str | None = None,
    active_only: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        runbooks = await query_runbooks(
            session,
            query=query,
            service=service,
            component=component,
            problem_type=problem_type,
            tag=tag,
            active_only=active_only,
            limit=limit,
        )

    return {
        "tool": "query_runbooks",
        "filters": {
            "query": query,
            "service": service,
            "component": component,
            "problem_type": problem_type,
            "tag": tag,
            "active_only": active_only,
        },
        "count": len(runbooks),
        "runbooks": [serialize_runbook(runbook) for runbook in runbooks],
    }


async def query_historical_incidents_tool(
    *,
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    root_cause: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        incidents = await query_historical_incidents(
            session,
            query=query,
            service=service,
            component=component,
            root_cause=root_cause,
            tag=tag,
            limit=limit,
        )

    return {
        "tool": "query_historical_incidents",
        "filters": {
            "query": query,
            "service": service,
            "component": component,
            "root_cause": root_cause,
            "tag": tag,
        },
        "count": len(incidents),
        "historical_incidents": [
            serialize_historical_incident(incident) for incident in incidents
        ],
    }


async def query_redis_counters_tool(
    *,
    pattern: str = "counter:*",
    limit: int = 50,
) -> dict[str, Any]:
    redis = await get_redis()
    keys: list[str] = []
    cursor = 0

    while len(keys) < limit:
        cursor, batch = await redis.scan(cursor=cursor, match=pattern, count=limit)
        keys.extend(batch)
        if cursor == 0:
            break

    keys = keys[:limit]
    values: dict[str, str | None] = {}
    for key in keys:
        values[key] = await redis.get(key)

    return {
        "tool": "query_redis_counters",
        "pattern": pattern,
        "count": len(values),
        "counters": values,
    }

