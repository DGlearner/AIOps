import asyncio
import json

from crossst.application.agents.diagnosis_graph import (
    build_initial_state,
    generate_hypotheses,
    make_incident_context,
    run_diagnosis,
    select_next_tool,
    serialize_tool_kwargs,
    should_stop,
)


def test_generate_hypotheses_for_login_failed_incident():
    incident = make_incident_context(
        incident_id="incident-001",
        summary="Login failures increased.",
        event_types=["login_failed"],
        affected_hosts=["app-prod-01"],
        aggregate_key="host:app-prod-01",
    )
    state = build_initial_state(incident=incident)

    state = generate_hypotheses(state)

    assert "credential_attack_or_bruteforce" in state["hypotheses"]
    assert "backend_dependency_failure_affecting_login" in state["hypotheses"]


def test_should_stop_when_max_tool_calls_reached():
    incident = make_incident_context(
        incident_id="incident-001",
        summary="Unknown anomaly.",
        event_types=["unknown"],
    )
    state = build_initial_state(incident=incident, max_tool_calls=1)
    state["tool_call_count"] = 1

    assert should_stop(state) is True
    assert state["diagnosis_status"] == "needs_human_review"
    assert state["stop_reason"] == "max_tool_calls_reached"


def test_should_stop_when_confidence_threshold_reached():
    incident = make_incident_context(
        incident_id="incident-001",
        summary="MySQL unavailable.",
        event_types=["mysql_connection_refused"],
    )
    state = build_initial_state(incident=incident)
    state["confidence"] = 0.8

    assert should_stop(state) is True
    assert state["diagnosis_status"] == "confirmed_diagnosis"
    assert state["stop_reason"] == "confidence_threshold_reached"


def test_select_next_tool_uses_incident_time_window():
    incident = {
        "incident_id": "incident-001",
        "summary": "MySQL unavailable.",
        "event_types": ["mysql_connection_refused"],
        "affected_hosts": ["db-prod-01"],
        "affected_services": [],
        "aggregate_key": "host:db-prod-01",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }
    state = build_initial_state(incident=incident)
    state = generate_hypotheses(state)

    selected = select_next_tool(state)

    assert selected["tool"] == "query_events"
    assert selected["kwargs"]["start_time"].isoformat() == "2026-06-03T14:35:00+00:00"
    assert selected["kwargs"]["end_time"].isoformat() == "2026-06-03T14:50:00+00:00"


def test_select_next_tool_checks_service_dependencies_for_service_failure():
    incident = {
        "incident_id": "incident-001",
        "summary": "Service failure.",
        "event_types": ["app_db_connection_error"],
        "affected_hosts": ["app-prod-01"],
        "affected_services": ["login-service"],
        "aggregate_key": "service:login-service",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }
    state = build_initial_state(incident=incident)
    state["current_hypothesis"] = "service_level_failure"

    selected = select_next_tool(state)

    assert selected["tool"] == "query_service_dependencies"
    assert selected["kwargs"]["service"] == "login-service"
    assert selected["kwargs"]["active_only"] is True


def test_select_next_tool_checks_recent_deployments_for_deployment_hypothesis():
    incident = {
        "incident_id": "incident-001",
        "summary": "Service failure after deployment.",
        "event_types": ["app_db_connection_error"],
        "affected_hosts": ["app-prod-01"],
        "affected_services": ["login-service"],
        "aggregate_key": "service:login-service",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }
    state = build_initial_state(incident=incident)
    state["current_hypothesis"] = "recent_deployment_or_config_change"

    selected = select_next_tool(state)

    assert selected["tool"] == "query_recent_deployments"
    assert selected["kwargs"]["service"] == "login-service"
    assert selected["kwargs"]["environment"] == "prod"
    assert selected["kwargs"]["start_time"].isoformat() == "2026-06-03T14:35:00+00:00"
    assert selected["kwargs"]["end_time"].isoformat() == "2026-06-03T14:50:00+00:00"


def test_select_next_tool_checks_historical_incidents_for_history_hypothesis():
    incident = {
        "incident_id": "incident-001",
        "summary": "MySQL unavailable.",
        "event_types": ["mysql_connection_refused"],
        "affected_hosts": ["db-prod-01"],
        "affected_services": ["login-service"],
        "aggregate_key": "service:login-service",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }
    state = build_initial_state(incident=incident)
    state["current_hypothesis"] = "historical_similar_incident"

    selected = select_next_tool(state)

    assert selected["tool"] == "query_historical_incidents"
    assert selected["kwargs"]["service"] == "login-service"
    assert selected["kwargs"]["query"] == "MySQL unavailable."


def test_select_next_tool_checks_runbooks_for_runbook_hypothesis():
    incident = {
        "incident_id": "incident-001",
        "summary": "MySQL unavailable.",
        "event_types": ["mysql_connection_refused"],
        "affected_hosts": ["db-prod-01"],
        "affected_services": ["login-service"],
        "aggregate_key": "service:login-service",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }
    state = build_initial_state(incident=incident)
    state["current_hypothesis"] = "runbook_available"

    selected = select_next_tool(state)

    assert selected["tool"] == "query_runbooks"
    assert selected["kwargs"]["service"] == "login-service"
    assert selected["kwargs"]["query"] == "MySQL unavailable."


def test_serialize_tool_kwargs_converts_datetimes_to_json_safe_strings():
    selected = {
        "start_time": "2026-06-03T14:35:00+00:00",
        "limit": 20,
    }
    incident = {
        "incident_id": "incident-001",
        "summary": "MySQL unavailable.",
        "event_types": ["mysql_connection_refused"],
        "affected_hosts": ["db-prod-01"],
        "affected_services": [],
        "aggregate_key": "host:db-prod-01",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }
    state = generate_hypotheses(build_initial_state(incident=incident))
    tool = select_next_tool(state)

    serialized = serialize_tool_kwargs(tool["kwargs"])

    assert serialized["start_time"] == selected["start_time"]
    assert serialized["limit"] == selected["limit"]
    json.dumps(serialized)


def test_run_diagnosis_falls_back_without_matching_evidence(monkeypatch):
    async def fake_query_incidents_tool(**kwargs):
        return {
            "tool": "query_incidents",
            "count": 0,
            "filters": kwargs,
            "incidents": [],
        }

    monkeypatch.setattr(
        "crossst.application.agents.diagnosis_graph.query_incidents_tool",
        fake_query_incidents_tool,
    )

    incident = make_incident_context(
        incident_id="incident-no-evidence",
        summary="Unknown operational anomaly.",
        event_types=["unknown"],
    )

    report = asyncio.run(
        run_diagnosis(
            incident=incident,
            max_tool_calls=1,
            persist=False,
        )
    )

    assert report.status == "needs_human_review"
    assert report.stop_reason in {"max_tool_calls_reached", "no_more_hypotheses"}
    assert report.recommendations
    assert report.tool_calls
    assert report.tool_calls[0]["tool_name"] == "query_incidents"
    assert report.tool_calls[0]["incident_id"] == "incident-no-evidence"
    assert report.tool_calls[0]["result_count"] >= 0


def test_run_diagnosis_accepts_custom_reasoning_provider(monkeypatch):
    class FakeReasoning:
        def generate_hypotheses(self, state):
            state["hypotheses"] = ["custom_dependency_failure"]
            state["current_hypothesis"] = "custom_dependency_failure"
            return state

        def update_evidence(self, state):
            state["confidence"] = 0.91
            state["root_cause"] = "custom_root_cause"
            state.setdefault("evidence_chain", []).append("custom evidence")
            return state

        def generate_recommendations(self, state):
            state["recommendations"] = ["custom recommendation"]
            return state

    async def fake_execute_selected_tool(state, selected_tool):
        state["tool_call_count"] = state.get("tool_call_count", 0) + 1
        state.setdefault("tool_results", []).append(
            {
                "tool": selected_tool["tool"],
                "count": 1,
                "items": [],
            }
        )
        return state

    monkeypatch.setattr(
        "crossst.application.agents.diagnosis_graph.execute_selected_tool",
        fake_execute_selected_tool,
    )

    incident = make_incident_context(
        incident_id="incident-custom-reasoning",
        summary="Custom anomaly.",
        event_types=["unknown"],
    )

    report = asyncio.run(
        run_diagnosis(
            incident=incident,
            max_tool_calls=1,
            persist=False,
            reasoning=FakeReasoning(),
        )
    )

    assert report.status == "confirmed_diagnosis"
    assert report.root_cause == "custom_root_cause"
    assert report.evidence_chain == ["custom evidence"]
    assert report.recommendations == ["custom recommendation"]

