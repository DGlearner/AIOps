from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from crossst.application.agents.diagnosis_graph import (
    DEFAULT_MAX_TOOL_CALLS,
    serialize_tool_kwargs,
    summarize_tool_result,
)
from crossst.application.agents.tools import (
    query_alerts_tool,
    query_events_tool,
    query_historical_incidents_tool,
    query_incidents_tool,
    query_recent_deployments_tool,
    query_runbooks_tool,
    query_service_dependencies_tool,
)


CONFIRMED_CONFIDENCE_THRESHOLD = 0.7
MAX_TOOL_RESULT_LIMIT = 100

TIME_SCOPED_TOOLS = {
    "query_events",
    "query_alerts",
    "query_incidents",
    "query_recent_deployments",
}

ALLOWED_TOOL_KWARGS = {
    "query_events": {
        "minutes",
        "source_type",
        "event_type",
        "host",
        "service",
        "component",
        "start_time",
        "end_time",
        "limit",
    },
    "query_alerts": {
        "minutes",
        "alert_type",
        "event_type",
        "severity",
        "source_type",
        "host",
        "service",
        "start_time",
        "end_time",
        "limit",
    },
    "query_incidents": {
        "minutes",
        "severity",
        "status",
        "aggregate_key",
        "host",
        "service",
        "event_type",
        "start_time",
        "end_time",
        "limit",
    },
    "query_service_dependencies": {
        "service",
        "dependency_service",
        "dependency_type",
        "direction",
        "active_only",
        "limit",
    },
    "query_recent_deployments": {
        "minutes",
        "service",
        "environment",
        "status",
        "start_time",
        "end_time",
        "limit",
    },
    "query_runbooks": {
        "query",
        "service",
        "component",
        "problem_type",
        "tag",
        "active_only",
        "limit",
    },
    "query_historical_incidents": {
        "query",
        "service",
        "component",
        "root_cause",
        "tag",
        "limit",
    },
}


class ChatInvestigationPlanner(Protocol):
    async def propose_next_step(
        self,
        *,
        question: str,
        incident: dict[str, Any] | None,
        diagnosis: dict[str, Any] | None,
        tool_calls: list[dict[str, Any]],
        evidence_chain: list[str],
        remaining_tool_calls: int,
        allowed_tools: list[str],
    ) -> dict[str, Any] | None:
        ...


class ChatInvestigationState(TypedDict, total=False):
    question: str
    incident: dict[str, Any] | None
    diagnosis: dict[str, Any] | None
    plan: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    evidence_chain: list[str]
    ruled_out_hypotheses: list[str]
    recommendations: list[str]
    current_step_index: int
    max_tool_calls: int
    tool_call_count: int
    status: Literal["running", "confirmed_investigation", "needs_human_review"]
    stop_reason: str | None
    confidence: float
    root_cause: str | None
    needs_human_review: bool
    fallback_report: dict[str, Any]
    planner_enabled: bool
    planner_provider: ChatInvestigationPlanner | None


def _text_blob(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).lower()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None


def _build_time_kwargs(
    incident: dict[str, Any] | None,
    *,
    padding_minutes: int = 5,
) -> dict[str, datetime]:
    incident = incident or {}
    start_time = _parse_datetime(incident.get("time_window_start"))
    end_time = _parse_datetime(incident.get("time_window_end"))
    if start_time is None or end_time is None:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=30)

    return {
        "start_time": start_time - timedelta(minutes=padding_minutes),
        "end_time": end_time + timedelta(minutes=padding_minutes),
    }


def _first_item(values: Any) -> Any:
    if isinstance(values, list) and values:
        return values[0]
    return None


def _append_plan_step(
    plan: list[dict[str, Any]],
    *,
    tool: str,
    reason: str,
    kwargs: dict[str, Any],
) -> None:
    key = (tool, tuple(sorted((key, str(value)) for key, value in kwargs.items())))
    existing_keys = {
        (
            step["tool"],
            tuple(sorted((key, str(value)) for key, value in step["kwargs"].items())),
        )
        for step in plan
    }
    if key not in existing_keys:
        plan.append({"tool": tool, "reason": reason, "kwargs": kwargs})


def _sanitize_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 20
    return max(1, min(limit, MAX_TOOL_RESULT_LIMIT))


def sanitize_planner_step(
    step: dict[str, Any] | None,
    *,
    incident: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(step, dict):
        return None

    tool = step.get("tool")
    if tool not in ALLOWED_TOOL_KWARGS:
        return None

    raw_kwargs = step.get("kwargs") or {}
    if not isinstance(raw_kwargs, dict):
        return None

    allowed_keys = ALLOWED_TOOL_KWARGS[tool]
    kwargs = {
        key: value
        for key, value in raw_kwargs.items()
        if key in allowed_keys and value is not None
    }
    kwargs["limit"] = _sanitize_limit(kwargs.get("limit", 20))

    if tool in TIME_SCOPED_TOOLS:
        time_kwargs = _build_time_kwargs(incident)
        kwargs["start_time"] = time_kwargs["start_time"]
        kwargs["end_time"] = time_kwargs["end_time"]

    reason = str(step.get("reason") or "Planner selected this investigation tool.")
    return {
        "tool": tool,
        "reason": reason[:500],
        "kwargs": kwargs,
    }


def build_investigation_plan(
    *,
    question: str,
    incident: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
) -> list[dict[str, Any]]:
    incident = incident or {}
    diagnosis = diagnosis or {}
    event_types = incident.get("event_types") or []
    affected_hosts = incident.get("affected_hosts") or []
    affected_services = incident.get("affected_services") or []
    service = _first_item(affected_services)
    host = _first_item(affected_hosts)
    text = _text_blob(
        question,
        incident.get("summary"),
        " ".join(event_types),
        diagnosis.get("root_cause"),
    )
    time_kwargs = _build_time_kwargs(incident)
    plan: list[dict[str, Any]] = []

    has_mysql_signal = _contains_any(
        text,
        ("mysql", "database", "db", "connection refused", "socket"),
    )
    has_login_signal = _contains_any(
        text,
        ("login", "登录", "登陆", "ssh", "failed password", "login_failed"),
    )

    if has_mysql_signal or "mysql_connection_refused" in event_types:
        _append_plan_step(
            plan,
            tool="query_events",
            reason="Check MySQL availability errors near the chat investigation window.",
            kwargs={
                "source_type": "mysql",
                "event_type": "mysql_connection_refused",
                "limit": 20,
                **time_kwargs,
            },
        )

    if service and (has_mysql_signal or has_login_signal or "app_db_connection_error" in event_types):
        _append_plan_step(
            plan,
            tool="query_events",
            reason="Check whether the affected service reported database connection errors.",
            kwargs={
                "service": service,
                "event_type": "app_db_connection_error",
                "limit": 20,
                **time_kwargs,
            },
        )

    if has_login_signal or "login_failed" in event_types:
        _append_plan_step(
            plan,
            tool="query_alerts",
            reason="Check login failure alert strength and affected host scope.",
            kwargs={
                "event_type": "login_failed",
                "host": host,
                "limit": 20,
                **time_kwargs,
            },
        )

    if service:
        _append_plan_step(
            plan,
            tool="query_service_dependencies",
            reason="Check declared dependencies for the affected service.",
            kwargs={
                "service": service,
                "active_only": True,
                "limit": 20,
            },
        )
        _append_plan_step(
            plan,
            tool="query_recent_deployments",
            reason="Check recent deployments or config changes for the affected service.",
            kwargs={
                "service": service,
                "environment": "prod",
                "limit": 20,
                **time_kwargs,
            },
        )

    _append_plan_step(
        plan,
        tool="query_events",
        reason="Check recent normalized events matching the initial anomaly.",
        kwargs={
            "host": host,
            "service": service,
            "event_type": _first_item(event_types),
            "limit": 20,
            **time_kwargs,
        },
    )
    _append_plan_step(
        plan,
        tool="query_alerts",
        reason="Check related alerts in the same time window.",
        kwargs={
            "host": host,
            "service": service,
            "limit": 20,
            **time_kwargs,
        },
    )
    _append_plan_step(
        plan,
        tool="query_incidents",
        reason="Check related open incidents that may explain the current symptom.",
        kwargs={
            "status": "open",
            "host": host,
            "service": service,
            "limit": 20,
            **time_kwargs,
        },
    )

    if service or has_mysql_signal:
        _append_plan_step(
            plan,
            tool="query_runbooks",
            reason="Check whether a runbook covers this component or symptom.",
            kwargs={
                "query": incident.get("summary") or question,
                "service": service,
                "component": "mysql" if has_mysql_signal else None,
                "active_only": True,
                "limit": 10,
            },
        )
        _append_plan_step(
            plan,
            tool="query_historical_incidents",
            reason="Check similar historical incidents for this service or symptom.",
            kwargs={
                "query": incident.get("summary") or question,
                "service": service,
                "limit": 10,
            },
        )

    return plan[:max_tool_calls]


def initialize_node(state: ChatInvestigationState) -> ChatInvestigationState:
    plan = build_investigation_plan(
        question=state["question"],
        incident=state.get("incident"),
        diagnosis=state.get("diagnosis"),
        max_tool_calls=state.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS),
    )
    return {
        **state,
        "plan": plan,
        "tool_results": [],
        "tool_calls": [],
        "evidence_chain": [],
        "ruled_out_hypotheses": [],
        "recommendations": [],
        "current_step_index": 0,
        "tool_call_count": 0,
        "status": "running",
        "stop_reason": None,
        "confidence": 0.0,
        "root_cause": None,
        "needs_human_review": True,
    }


async def _execute_tool(tool_name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "query_events":
        return await query_events_tool(**kwargs)
    if tool_name == "query_alerts":
        return await query_alerts_tool(**kwargs)
    if tool_name == "query_incidents":
        return await query_incidents_tool(**kwargs)
    if tool_name == "query_service_dependencies":
        return await query_service_dependencies_tool(**kwargs)
    if tool_name == "query_recent_deployments":
        return await query_recent_deployments_tool(**kwargs)
    if tool_name == "query_runbooks":
        return await query_runbooks_tool(**kwargs)
    if tool_name == "query_historical_incidents":
        return await query_historical_incidents_tool(**kwargs)
    raise ValueError(f"Unsupported investigation tool: {tool_name}")


def _result_count_for(
    tool_results: list[dict[str, Any]],
    *,
    tool: str | None = None,
    event_type: str | None = None,
    source_type: str | None = None,
) -> int:
    total = 0
    for result in tool_results:
        if tool is not None and result.get("tool") != tool:
            continue
        filters = result.get("filters") or {}
        if event_type is not None and filters.get("event_type") != event_type:
            items = (result.get("events") or []) + (result.get("alerts") or [])
            matching_items = [
                item
                for item in items
                if item.get("event_type") == event_type
            ]
            if not matching_items:
                continue
            total += len(matching_items)
            continue
        if source_type is not None and filters.get("source_type") != source_type:
            continue
        total += int(result.get("count", 0) or 0)
    return total


def evaluate_evidence(state: ChatInvestigationState) -> ChatInvestigationState:
    tool_results = state.get("tool_results", [])
    mysql_errors = _result_count_for(
        tool_results,
        tool="query_events",
        event_type="mysql_connection_refused",
    )
    app_db_errors = _result_count_for(
        tool_results,
        tool="query_events",
        event_type="app_db_connection_error",
    )
    login_alerts = _result_count_for(
        tool_results,
        tool="query_alerts",
        event_type="login_failed",
    )

    evidence_chain = state.setdefault("evidence_chain", [])
    ruled_out = state.setdefault("ruled_out_hypotheses", [])

    if mysql_errors > 0 and (
        app_db_errors > 0
        or login_alerts > 0
        or "login_failed" in (state.get("incident") or {}).get("event_types", [])
    ):
        if not any("mysql_connection_refused" in item for item in evidence_chain):
            evidence_chain.append(
                f"mysql_connection_refused: query_events returned {mysql_errors} record(s)."
            )
        if app_db_errors > 0:
            evidence_chain.append(
                f"app_db_connection_error: query_events returned {app_db_errors} record(s)."
            )
        if login_alerts > 0:
            evidence_chain.append(
                f"login_failed: query_alerts returned {login_alerts} alert(s)."
            )
        state["root_cause"] = "database_dependency_unavailable"
        state["confidence"] = 0.82 if app_db_errors > 0 else 0.74
        state["status"] = "confirmed_investigation"
        state["stop_reason"] = "confidence_threshold_reached"
        state["needs_human_review"] = False
        state["recommendations"] = [
            "Check MySQL process, socket, and port listener on the database host.",
            "Confirm login-service database connectivity recovers after MySQL is restored.",
            "Keep login failure alerts open until failed-login volume returns to baseline.",
        ]
        return state

    if login_alerts >= 3 and mysql_errors == 0 and app_db_errors == 0:
        if "database_dependency_unavailable" not in ruled_out:
            ruled_out.append("database_dependency_unavailable")
        evidence_chain.append(
            f"login_failed: query_alerts returned {login_alerts} alert(s), but database evidence is not present yet."
        )
        state["root_cause"] = "credential_attack_or_bruteforce"
        state["confidence"] = 0.7
        state["status"] = "confirmed_investigation"
        state["stop_reason"] = "confidence_threshold_reached"
        state["needs_human_review"] = False
        state["recommendations"] = [
            "Review source IP distribution and affected accounts.",
            "Check whether rate limiting or account lockout policies triggered.",
        ]
        return state

    return state


def should_stop(state: ChatInvestigationState) -> bool:
    if state.get("status") != "running":
        return True
    if state.get("confidence", 0.0) >= CONFIRMED_CONFIDENCE_THRESHOLD:
        state["status"] = "confirmed_investigation"
        state["stop_reason"] = "confidence_threshold_reached"
        state["needs_human_review"] = False
        return True
    if state.get("tool_call_count", 0) >= state.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS):
        state["status"] = "needs_human_review"
        state["stop_reason"] = "max_tool_calls_reached"
        state["needs_human_review"] = True
        return True
    if (
        state.get("planner_provider") is None
        and state.get("current_step_index", 0) >= len(state.get("plan", []))
    ):
        state["status"] = "needs_human_review"
        state["stop_reason"] = "no_more_investigation_steps"
        state["needs_human_review"] = True
        return True
    return False


async def select_step_node_input(
    state: ChatInvestigationState,
) -> dict[str, Any] | None:
    planner_provider = state.get("planner_provider")
    if planner_provider is not None:
        try:
            proposed_step = await planner_provider.propose_next_step(
                question=state["question"],
                incident=state.get("incident"),
                diagnosis=state.get("diagnosis"),
                tool_calls=state.get("tool_calls", []),
                evidence_chain=state.get("evidence_chain", []),
                remaining_tool_calls=(
                    state.get("max_tool_calls", DEFAULT_MAX_TOOL_CALLS)
                    - state.get("tool_call_count", 0)
                ),
                allowed_tools=sorted(ALLOWED_TOOL_KWARGS),
            )
        except Exception:
            proposed_step = None

        sanitized_step = sanitize_planner_step(
            proposed_step,
            incident=state.get("incident"),
        )
        if sanitized_step is not None:
            return sanitized_step

    plan = state.get("plan", [])
    step_index = state.get("current_step_index", 0)
    if step_index >= len(plan):
        return None
    return plan[step_index]


async def tool_step_node(state: ChatInvestigationState) -> ChatInvestigationState:
    if should_stop(state):
        return state

    step = await select_step_node_input(state)
    if step is None:
        state["status"] = "needs_human_review"
        state["stop_reason"] = "no_more_investigation_steps"
        state["needs_human_review"] = True
        return state

    started_at = datetime.now(timezone.utc)
    result = await _execute_tool(step["tool"], step["kwargs"])
    finished_at = datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    serialized_kwargs = serialize_tool_kwargs(step["kwargs"])
    result_summary = summarize_tool_result(result)
    tool_call = {
        "tool_call_id": str(uuid4()),
        "incident_id": (state.get("incident") or {}).get("incident_id", "chat-investigation"),
        "diagnosis_id": None,
        "tool_name": step["tool"],
        "reason": step["reason"],
        "kwargs": serialized_kwargs,
        "result_count": int(result.get("count", 0) or 0),
        "result_summary": result_summary,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": duration_ms,
    }
    state.setdefault("tool_results", []).append(result)
    state.setdefault("tool_calls", []).append(tool_call)
    state["current_step_index"] = state.get("current_step_index", 0) + 1
    state["tool_call_count"] = state.get("tool_call_count", 0) + 1
    state = evaluate_evidence(state)
    should_stop(state)
    return state


def route_after_tool(state: ChatInvestigationState) -> Literal["finish", "continue"]:
    if state.get("status") != "running":
        return "finish"
    return "continue"


def _build_findings_summary(state: ChatInvestigationState) -> list[str]:
    findings: list[str] = []
    for tool_call in state.get("tool_calls", []):
        findings.append(
            (
                f"{tool_call.get('tool_name')} checked "
                f"{tool_call.get('kwargs')} and returned "
                f"{tool_call.get('result_count', 0)} result(s)."
            )
        )
    return findings


def build_fallback_report(state: ChatInvestigationState) -> dict[str, Any]:
    incident = state.get("incident") or {}
    checked_tools = [
        {
            "tool_name": tool_call.get("tool_name"),
            "reason": tool_call.get("reason"),
            "result_count": tool_call.get("result_count", 0),
        }
        for tool_call in state.get("tool_calls", [])
    ]
    remaining_uncertainty = []
    if state.get("status") == "needs_human_review":
        remaining_uncertainty.append(
            "The bounded investigation did not collect enough correlated evidence to confirm a root cause."
        )
    if not state.get("root_cause"):
        remaining_uncertainty.append(
            "No root cause crossed the confidence threshold within the allowed tool-call budget."
        )

    return {
        "initial_anomaly": incident.get("summary") or state.get("question", ""),
        "original_question": state.get("question", ""),
        "checked_tools": checked_tools,
        "findings_summary": _build_findings_summary(state),
        "evidence_chain": state.get("evidence_chain", []),
        "ruled_out_hypotheses": state.get("ruled_out_hypotheses", []),
        "remaining_uncertainty": remaining_uncertainty,
        "recommended_human_next_steps": [
            "Inspect raw logs around the incident window for components not covered by current parsers.",
            "Validate infrastructure health and dependency status from monitoring dashboards.",
            "Escalate to the service owner if symptoms continue after the checked causes are ruled out.",
        ],
    }


def finish_node(state: ChatInvestigationState) -> ChatInvestigationState:
    if state.get("status") == "running":
        state["status"] = "needs_human_review"
        state["stop_reason"] = "no_more_investigation_steps"
        state["needs_human_review"] = True
    if not state.get("recommendations"):
        state["recommendations"] = [
            "Use the fallback report to continue manual triage.",
            "Add parser or correlation rules if this pattern repeats.",
        ]
    state["fallback_report"] = build_fallback_report(state)
    return state


def build_chat_investigation_app():
    graph = StateGraph(ChatInvestigationState)
    graph.add_node("initialize", initialize_node)
    graph.add_node("tool_step", tool_step_node)
    graph.add_node("finish", finish_node)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "tool_step")
    graph.add_conditional_edges(
        "tool_step",
        route_after_tool,
        {
            "continue": "tool_step",
            "finish": "finish",
        },
    )
    graph.add_edge("finish", END)
    return graph.compile()


async def run_chat_investigation(
    *,
    question: str,
    incident: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    planner_provider: ChatInvestigationPlanner | None = None,
) -> ChatInvestigationState:
    app = build_chat_investigation_app()
    initial_state: ChatInvestigationState = {
        "question": question,
        "incident": incident,
        "diagnosis": diagnosis,
        "max_tool_calls": max_tool_calls,
        "planner_enabled": planner_provider is not None,
        "planner_provider": planner_provider,
    }
    final_state = await app.ainvoke(initial_state)
    final_state.pop("planner_provider", None)
    return final_state

