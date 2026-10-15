from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from crossst.application.agents.diagnosis_reasoning import DEFAULT_REASONING, DiagnosisReasoning
from crossst.application.agents.diagnosis_state import DiagnosisState
from crossst.application.agents.tools import (
    query_alerts_tool,
    query_events_tool,
    query_historical_incidents_tool,
    query_incidents_tool,
    query_recent_deployments_tool,
    query_runbooks_tool,
    query_service_dependencies_tool,
)
from crossst.domain.schemas.diagnosis import DiagnosisReport
from crossst.infrastructure.storage.diagnoses import save_diagnosis
from crossst.infrastructure.storage.postgres import AsyncSessionLocal


CONFIDENCE_THRESHOLD = 0.7
DEFAULT_MAX_TOOL_CALLS = 5


def build_initial_state(
    *,
    incident: dict[str, Any],
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
) -> DiagnosisState:
    return {
        "incident_id": incident["incident_id"],
        "incident": incident,
        "trigger_summary": incident.get("summary", ""),
        "hypotheses": [],
        "current_hypothesis": None,
        "evidence_chain": [],
        "ruled_out_hypotheses": [],
        "tool_results": [],
        "tool_call_summary": [],
        "pending_tool_calls": [],
        "confidence": 0.0,
        "diagnosis_status": "running",
        "root_cause": None,
        "recommendations": [],
        "tool_call_count": 0,
        "max_tool_calls": max_tool_calls,
        "max_reasoning_steps": max_tool_calls,
        "stop_reason": None,
    }


def generate_hypotheses(state: DiagnosisState) -> DiagnosisState:
    return DEFAULT_REASONING.generate_hypotheses(state)


def parse_incident_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def build_incident_time_kwargs(
    incident: dict[str, Any],
    *,
    padding_minutes: int = 5,
) -> dict[str, datetime]:
    start_time = parse_incident_datetime(incident.get("time_window_start"))
    end_time = parse_incident_datetime(incident.get("time_window_end"))

    if start_time is None or end_time is None:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=30)
        end_time = now

    return {
        "start_time": start_time - timedelta(minutes=padding_minutes),
        "end_time": end_time + timedelta(minutes=padding_minutes),
    }


def select_next_tool(state: DiagnosisState) -> dict[str, Any]:
    incident = state["incident"]
    current = state.get("current_hypothesis")
    affected_hosts = incident.get("affected_hosts", [])
    affected_services = incident.get("affected_services", [])
    time_kwargs = build_incident_time_kwargs(incident)

    if current in {"mysql_unavailable", "database_dependency_unavailable"}:
        return {
            "tool": "query_events",
            "reason": "Check whether MySQL has availability errors near the incident window.",
            "kwargs": {
                "source_type": "mysql",
                "event_type": "mysql_connection_refused",
                "limit": 20,
                **time_kwargs,
            },
        }

    if current == "backend_dependency_failure_affecting_login":
        service = affected_services[0] if affected_services else "login-service"
        return {
            "tool": "query_events",
            "reason": "Check whether login service reported database connection errors.",
            "kwargs": {
                "service": service,
                "event_type": "app_db_connection_error",
                "limit": 20,
                **time_kwargs,
            },
        }

    if current == "credential_attack_or_bruteforce":
        host = affected_hosts[0] if affected_hosts else None
        return {
            "tool": "query_alerts",
            "reason": "Check login failure alerts and current attack-like signal strength.",
            "kwargs": {
                "event_type": "login_failed",
                "host": host,
                "limit": 20,
                **time_kwargs,
            },
        }

    if current == "service_level_failure":
        service = affected_services[0] if affected_services else None
        return {
            "tool": "query_service_dependencies",
            "reason": "Check declared dependencies for the affected service.",
            "kwargs": {
                "service": service,
                "active_only": True,
                "limit": 20,
            },
        }

    if current == "recent_deployment_or_config_change":
        service = affected_services[0] if affected_services else None
        return {
            "tool": "query_recent_deployments",
            "reason": "Check whether a recent deployment or config change overlaps the incident window.",
            "kwargs": {
                "service": service,
                "environment": "prod",
                "limit": 20,
                **time_kwargs,
            },
        }

    if current == "historical_similar_incident":
        service = affected_services[0] if affected_services else None
        return {
            "tool": "query_historical_incidents",
            "reason": "Check whether similar historical incidents exist for this service or symptom.",
            "kwargs": {
                "query": incident.get("summary", ""),
                "service": service,
                "limit": 10,
            },
        }

    if current == "runbook_available":
        service = affected_services[0] if affected_services else None
        component = None
        event_types = incident.get("event_types", [])
        if "mysql_connection_refused" in event_types:
            component = "mysql"
        return {
            "tool": "query_runbooks",
            "reason": "Check whether a runbook exists for this service or component symptom.",
            "kwargs": {
                "query": incident.get("summary", ""),
                "service": service,
                "component": component,
                "active_only": True,
                "limit": 10,
            },
        }

    return {
        "tool": "query_incidents",
        "reason": "Check related open incidents in the same recent time range.",
            "kwargs": {
                "status": "open",
                "limit": 20,
                **time_kwargs,
            },
    }


def serialize_tool_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in kwargs.items():
        if isinstance(value, datetime):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def summarize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tool": result.get("tool"),
        "count": result.get("count", 0),
    }
    for key in (
        "events",
        "alerts",
        "incidents",
        "dependencies",
        "deployments",
        "runbooks",
        "historical_incidents",
    ):
        items = result.get(key)
        if isinstance(items, list):
            summary[f"{key}_sample"] = items[:3]
    return summary


async def execute_selected_tool(
    state: DiagnosisState,
    selected_tool: dict[str, Any],
) -> DiagnosisState:
    tool_name = selected_tool["tool"]
    kwargs = selected_tool["kwargs"]
    started_at = datetime.now(timezone.utc)

    if tool_name == "query_events":
        result = await query_events_tool(**kwargs)
    elif tool_name == "query_alerts":
        result = await query_alerts_tool(**kwargs)
    elif tool_name == "query_incidents":
        result = await query_incidents_tool(**kwargs)
    elif tool_name == "query_historical_incidents":
        result = await query_historical_incidents_tool(**kwargs)
    elif tool_name == "query_runbooks":
        result = await query_runbooks_tool(**kwargs)
    elif tool_name == "query_service_dependencies":
        result = await query_service_dependencies_tool(**kwargs)
    elif tool_name == "query_recent_deployments":
        result = await query_recent_deployments_tool(**kwargs)
    else:
        raise ValueError(f"Unsupported tool: {tool_name}")

    finished_at = datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    serialized_kwargs = serialize_tool_kwargs(kwargs)
    state["tool_call_count"] = state.get("tool_call_count", 0) + 1
    state.setdefault("tool_results", []).append(result)
    state.setdefault("tool_call_summary", []).append(
        {
            "tool": tool_name,
            "reason": selected_tool["reason"],
            "kwargs": serialized_kwargs,
            "result_count": result.get("count", 0),
        }
    )
    state.setdefault("pending_tool_calls", []).append(
        {
            "tool_call_id": str(uuid4()),
            "incident_id": state["incident_id"],
            "tool_name": tool_name,
            "reason": selected_tool["reason"],
            "kwargs": serialized_kwargs,
            "result_count": result.get("count", 0),
            "result_summary": summarize_tool_result(result),
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
        }
    )
    return state


def update_evidence(state: DiagnosisState) -> DiagnosisState:
    return DEFAULT_REASONING.update_evidence(state)


def move_to_next_hypothesis(state: DiagnosisState) -> DiagnosisState:
    hypotheses = state.get("hypotheses", [])
    current = state.get("current_hypothesis")
    if current not in hypotheses:
        state["current_hypothesis"] = hypotheses[0] if hypotheses else None
        return state

    next_index = hypotheses.index(current) + 1
    state["current_hypothesis"] = (
        hypotheses[next_index] if next_index < len(hypotheses) else None
    )
    return state


def should_stop(state: DiagnosisState) -> bool:
    if state.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD:
        state["diagnosis_status"] = "confirmed_diagnosis"
        state["stop_reason"] = "confidence_threshold_reached"
        return True

    if state.get("tool_call_count", 0) >= state.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS):
        state["diagnosis_status"] = "needs_human_review"
        state["stop_reason"] = "max_tool_calls_reached"
        return True

    if state.get("current_hypothesis") is None:
        state["diagnosis_status"] = "needs_human_review"
        state["stop_reason"] = "no_more_hypotheses"
        return True

    return False


def generate_recommendations(state: DiagnosisState) -> DiagnosisState:
    return DEFAULT_REASONING.generate_recommendations(state)


def build_diagnosis_report(state: DiagnosisState) -> DiagnosisReport:
    return DiagnosisReport(
        incident_id=state["incident_id"],
        status=state.get("diagnosis_status", "needs_human_review"),
        stop_reason=state.get("stop_reason") or "unknown",
        confidence=state.get("confidence", 0.0),
        trigger_summary=state.get("trigger_summary", ""),
        root_cause=state.get("root_cause"),
        hypotheses=state.get("hypotheses", []),
        evidence_chain=state.get("evidence_chain", []),
        ruled_out_hypotheses=state.get("ruled_out_hypotheses", []),
        tool_call_summary=state.get("tool_call_summary", []),
        tool_calls=state.get("pending_tool_calls", []),
        recommendations=state.get("recommendations", []),
    )


async def run_diagnosis(
    *,
    incident: dict[str, Any],
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    persist: bool = True,
    reasoning: DiagnosisReasoning | None = None,
) -> DiagnosisReport:
    reasoning = reasoning or DEFAULT_REASONING
    state = build_initial_state(incident=incident, max_tool_calls=max_tool_calls)
    state = reasoning.generate_hypotheses(state)

    while not should_stop(state):
        selected_tool = select_next_tool(state)
        state = await execute_selected_tool(state, selected_tool)
        state = reasoning.update_evidence(state)
        if should_stop(state):
            break
        state = move_to_next_hypothesis(state)

    state = reasoning.generate_recommendations(state)
    report = build_diagnosis_report(state)

    if persist:
        async with AsyncSessionLocal() as session:
            await save_diagnosis(session, report)

    return report


def make_incident_context(
    *,
    incident_id: str,
    summary: str,
    event_types: list[str],
    affected_hosts: list[str] | None = None,
    affected_services: list[str] | None = None,
    aggregate_key: str = "unknown",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "incident_id": incident_id,
        "summary": summary,
        "event_types": event_types,
        "affected_hosts": affected_hosts or [],
        "affected_services": affected_services or [],
        "aggregate_key": aggregate_key,
        "time_window_start": now.isoformat(),
        "time_window_end": now.isoformat(),
    }

