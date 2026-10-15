from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from crossst.application.agents.tools import (
    query_alerts_tool,
    query_events_tool,
    query_historical_incidents_tool,
    query_incidents_tool,
    query_redis_counters_tool,
    query_recent_deployments_tool,
    query_runbooks_tool,
    query_service_dependencies_tool,
)
from crossst.application.agents.incident_context import build_incident_context_from_record
from crossst.application.agents.langgraph_diagnosis import run_langgraph_diagnosis
from crossst.domain.models.alert import Alert
from crossst.domain.models.diagnosis import IncidentDiagnosis
from crossst.domain.models.event import NormalizedEventRecord
from crossst.domain.models.incident import Incident
from crossst.domain.models.tool_call import ToolCallRecord
from crossst.infrastructure.storage.diagnoses import query_diagnoses
from crossst.infrastructure.storage.alerts import (
    get_alert_by_id,
    get_alert_lifecycle,
    query_alerts,
    summarize_alert_lifecycles,
    update_alert_lifecycle,
)
from crossst.infrastructure.storage.postgres import AsyncSessionLocal
from crossst.infrastructure.storage.incidents import get_incident_by_alert_id
from crossst.infrastructure.storage.tool_calls import query_tool_calls

router = APIRouter(prefix="/ops", tags=["ops"])


class AlertLifecycleUpdateRequest(BaseModel):
    status: str
    owner: str | None = None
    updated_by: str | None = None
    note: str | None = None


def resolve_ops_window(minutes: int) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    return start, end


def build_ops_overview_payload(
    *,
    start: datetime,
    end: datetime,
    counts: dict[str, int],
    alert_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "time_window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "pipeline_counts": counts,
        "alert_lifecycle": alert_summary,
        "next_actions": [
            "Review open high/critical alerts first.",
            "Check incidents without confirmed diagnosis.",
            "Use tool call audit for unresolved investigations.",
        ],
    }


def serialize_ops_alert(record: Alert) -> dict[str, Any]:
    return {
        "alert_id": record.alert_id,
        "event_id": record.event_id,
        "raw_log_id": record.raw_log_id,
        "alert_type": record.alert_type,
        "event_type": record.event_type,
        "severity": record.severity,
        "source_type": record.source_type,
        "component": record.component,
        "host": record.host,
        "service": record.service,
        "message": record.message,
        "summary": record.summary,
        "count": record.count,
        "window_seconds": record.window_seconds,
        "fingerprint": record.fingerprint,
        "fields": record.fields,
        "lifecycle": get_alert_lifecycle(record.fields),
        "tags": record.tags,
        "created_at": record.created_at.isoformat(),
    }


def serialize_diagnosis(record) -> dict[str, Any]:
    return {
        "diagnosis_id": record.diagnosis_id,
        "incident_id": record.incident_id,
        "status": record.status,
        "stop_reason": record.stop_reason,
        "confidence": record.confidence,
        "trigger_summary": record.trigger_summary,
        "root_cause": record.root_cause,
        "hypotheses": record.hypotheses,
        "evidence_chain": record.evidence_chain,
        "ruled_out_hypotheses": record.ruled_out_hypotheses,
        "tool_call_summary": record.tool_call_summary,
        "recommendations": record.recommendations,
        "created_at": record.created_at.isoformat(),
    }


def serialize_tool_call(record) -> dict[str, Any]:
    return {
        "tool_call_id": record.tool_call_id,
        "incident_id": record.incident_id,
        "diagnosis_id": record.diagnosis_id,
        "tool_name": record.tool_name,
        "reason": record.reason,
        "kwargs": record.kwargs,
        "result_count": record.result_count,
        "result_summary": record.result_summary,
        "started_at": record.started_at.isoformat(),
        "finished_at": record.finished_at.isoformat(),
        "duration_ms": record.duration_ms,
    }


async def count_ops_records(
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        events = await session.scalar(
            select(func.count())
            .select_from(NormalizedEventRecord)
            .where(NormalizedEventRecord.timestamp >= start)
            .where(NormalizedEventRecord.timestamp <= end)
        )
        alerts = await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.created_at >= start)
            .where(Alert.created_at <= end)
        )
        incidents = await session.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.created_at >= start)
            .where(Incident.created_at <= end)
        )
        diagnoses = await session.scalar(
            select(func.count())
            .select_from(IncidentDiagnosis)
            .where(IncidentDiagnosis.created_at >= start)
            .where(IncidentDiagnosis.created_at <= end)
        )
        tool_calls = await session.scalar(
            select(func.count())
            .select_from(ToolCallRecord)
            .where(ToolCallRecord.started_at >= start)
            .where(ToolCallRecord.started_at <= end)
        )

    return {
        "events": int(events or 0),
        "alerts": int(alerts or 0),
        "incidents": int(incidents or 0),
        "diagnoses": int(diagnoses or 0),
        "tool_calls": int(tool_calls or 0),
    }


@router.get("/overview")
async def get_ops_overview(
    minutes: int = Query(default=1440, ge=1, le=10080),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)
    counts = await count_ops_records(start=start, end=end)
    async with AsyncSessionLocal() as session:
        alerts = await query_alerts(
            session,
            start_time=start,
            end_time=end,
            limit=1000,
        )

    return build_ops_overview_payload(
        start=start,
        end=end,
        counts=counts,
        alert_summary=summarize_alert_lifecycles(alerts),
    )


@router.patch("/alerts/{alert_id}/lifecycle")
async def patch_alert_lifecycle(
    alert_id: str,
    payload: AlertLifecycleUpdateRequest,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        alert = await get_alert_by_id(session, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        updated = await update_alert_lifecycle(
            session,
            alert,
            status=payload.status,
            owner=payload.owner,
            updated_by=payload.updated_by,
            note=payload.note,
            updated_at=datetime.now(timezone.utc),
        )

    return serialize_ops_alert(updated)


@router.post("/alerts/{alert_id}/diagnose")
async def diagnose_alert(alert_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        alert = await get_alert_by_id(session, alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        incident = await get_incident_by_alert_id(session, alert_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="No correlated incident found for alert",
        )

    context = build_incident_context_from_record(incident)
    report = await run_langgraph_diagnosis(
        incident=context,
        max_tool_calls=5,
        persist=True,
    )
    payload = report.model_dump(mode="json")
    payload["alert_id"] = alert_id
    payload["incident_id"] = incident.incident_id
    return payload


@router.get("/events")
async def list_events(
    minutes: int = Query(default=1440, ge=1, le=10080),
    source_type: str | None = None,
    event_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    component: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)
    return await query_events_tool(
        source_type=source_type,
        event_type=event_type,
        host=host,
        service=service,
        component=component,
        start_time=start,
        end_time=end,
        limit=limit,
    )


@router.get("/alerts")
async def list_alerts(
    minutes: int = Query(default=1440, ge=1, le=10080),
    alert_type: str | None = None,
    event_type: str | None = None,
    severity: str | None = None,
    source_type: str | None = None,
    host: str | None = None,
    service: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)
    return await query_alerts_tool(
        alert_type=alert_type,
        event_type=event_type,
        severity=severity,
        source_type=source_type,
        host=host,
        service=service,
        start_time=start,
        end_time=end,
        limit=limit,
    )


@router.get("/incidents")
async def list_incidents(
    minutes: int = Query(default=1440, ge=1, le=10080),
    severity: str | None = None,
    status: str | None = None,
    aggregate_key: str | None = None,
    host: str | None = None,
    service: str | None = None,
    event_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)
    return await query_incidents_tool(
        severity=severity,
        status=status,
        aggregate_key=aggregate_key,
        host=host,
        service=service,
        event_type=event_type,
        start_time=start,
        end_time=end,
        limit=limit,
    )


@router.get("/diagnoses")
async def list_diagnoses(
    minutes: int = Query(default=1440, ge=1, le=10080),
    incident_id: str | None = None,
    status: str | None = None,
    root_cause: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)

    async with AsyncSessionLocal() as session:
        diagnoses = await query_diagnoses(
            session,
            incident_id=incident_id,
            status=status,
            root_cause=root_cause,
            start_time=start,
            end_time=end,
            limit=limit,
        )

    return {
        "tool": "query_diagnoses",
        "time_window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "filters": {
            "incident_id": incident_id,
            "status": status,
            "root_cause": root_cause,
        },
        "count": len(diagnoses),
        "diagnoses": [serialize_diagnosis(diagnosis) for diagnosis in diagnoses],
    }


@router.get("/service-dependencies")
async def list_service_dependencies(
    service: str | None = None,
    dependency_service: str | None = None,
    dependency_type: str | None = None,
    direction: str | None = None,
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return await query_service_dependencies_tool(
        service=service,
        dependency_service=dependency_service,
        dependency_type=dependency_type,
        direction=direction,
        active_only=active_only,
        limit=limit,
    )


@router.get("/recent-deployments")
async def list_recent_deployments(
    minutes: int = Query(default=1440, ge=1, le=10080),
    service: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)
    return await query_recent_deployments_tool(
        service=service,
        environment=environment,
        status=status,
        start_time=start,
        end_time=end,
        limit=limit,
    )


@router.get("/runbooks")
async def list_runbooks(
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    problem_type: str | None = None,
    tag: str | None = None,
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return await query_runbooks_tool(
        query=query,
        service=service,
        component=component,
        problem_type=problem_type,
        tag=tag,
        active_only=active_only,
        limit=limit,
    )


@router.get("/historical-incidents")
async def list_historical_incidents(
    query: str | None = None,
    service: str | None = None,
    component: str | None = None,
    root_cause: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return await query_historical_incidents_tool(
        query=query,
        service=service,
        component=component,
        root_cause=root_cause,
        tag=tag,
        limit=limit,
    )


@router.get("/tool-calls")
async def list_tool_calls(
    minutes: int = Query(default=1440, ge=1, le=10080),
    incident_id: str | None = None,
    diagnosis_id: str | None = None,
    tool_name: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    start, end = resolve_ops_window(minutes)
    async with AsyncSessionLocal() as session:
        tool_calls = await query_tool_calls(
            session,
            incident_id=incident_id,
            diagnosis_id=diagnosis_id,
            tool_name=tool_name,
            start_time=start,
            end_time=end,
            limit=limit,
        )

    return {
        "tool": "query_tool_calls",
        "time_window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "filters": {
            "incident_id": incident_id,
            "diagnosis_id": diagnosis_id,
            "tool_name": tool_name,
        },
        "count": len(tool_calls),
        "tool_calls": [serialize_tool_call(tool_call) for tool_call in tool_calls],
    }


@router.get("/redis-counters")
async def list_redis_counters(
    pattern: str = "counter:*",
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    return await query_redis_counters_tool(pattern=pattern, limit=limit)

