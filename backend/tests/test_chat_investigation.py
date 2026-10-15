import asyncio

from crossst.application.agents.chat_investigation import (
    build_chat_investigation_app,
    build_investigation_plan,
    sanitize_planner_step,
    run_chat_investigation,
)


def test_build_chat_investigation_app():
    app = build_chat_investigation_app()

    assert app is not None


def test_build_investigation_plan_prefers_incident_signals():
    incident = {
        "incident_id": "incident-001",
        "summary": "Login failures increased and MySQL connection refused.",
        "event_types": ["login_failed", "mysql_connection_refused"],
        "affected_hosts": ["app-prod-01"],
        "affected_services": ["login-service"],
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }

    plan = build_investigation_plan(
        question="查一下多个 IP 登录失败是不是 MySQL 崩了导致的",
        incident=incident,
        diagnosis=None,
        max_tool_calls=5,
    )

    assert [step["tool"] for step in plan][:3] == [
        "query_events",
        "query_events",
        "query_alerts",
    ]
    assert plan[0]["kwargs"]["source_type"] == "mysql"
    assert plan[1]["kwargs"]["event_type"] == "app_db_connection_error"
    assert plan[2]["kwargs"]["event_type"] == "login_failed"


def test_sanitize_planner_step_rejects_unsupported_tool():
    step = sanitize_planner_step(
        {
            "tool": "restart_mysql",
            "reason": "Try to fix the outage.",
            "kwargs": {"host": "db-prod-01"},
        },
        incident=None,
    )

    assert step is None


def test_sanitize_planner_step_filters_kwargs_and_adds_incident_window():
    step = sanitize_planner_step(
        {
            "tool": "query_events",
            "reason": "Check MySQL errors.",
            "kwargs": {
                "source_type": "mysql",
                "event_type": "mysql_connection_refused",
                "limit": 9999,
                "raw_sql": "drop table alerts",
            },
        },
        incident={
            "time_window_start": "2026-06-03T14:40:00Z",
            "time_window_end": "2026-06-03T14:45:00Z",
        },
    )

    assert step is not None
    assert step["tool"] == "query_events"
    assert step["kwargs"]["source_type"] == "mysql"
    assert step["kwargs"]["event_type"] == "mysql_connection_refused"
    assert step["kwargs"]["limit"] == 100
    assert "raw_sql" not in step["kwargs"]
    assert step["kwargs"]["start_time"].isoformat() == "2026-06-03T14:35:00+00:00"
    assert step["kwargs"]["end_time"].isoformat() == "2026-06-03T14:50:00+00:00"


def test_run_chat_investigation_uses_valid_planner_step(monkeypatch):
    calls = []

    class FakePlanner:
        async def propose_next_step(self, **kwargs):
            return {
                "tool": "query_alerts",
                "reason": "LLM wants to check login failure alerts first.",
                "kwargs": {
                    "event_type": "login_failed",
                    "limit": 3,
                },
            }

    async def fake_query_alerts_tool(**kwargs):
        calls.append(("query_alerts", kwargs))
        return {
            "tool": "query_alerts",
            "filters": kwargs,
            "count": 3,
            "alerts": [
                {
                    "alert_id": "alert-login-001",
                    "event_type": "login_failed",
                    "summary": "Multiple login failures.",
                }
            ],
        }

    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_alerts_tool",
        fake_query_alerts_tool,
    )

    result = asyncio.run(
        run_chat_investigation(
            question="查一下最近登录失败",
            incident={
                "incident_id": "incident-login",
                "summary": "Login failures increased.",
                "event_types": ["login_failed"],
                "affected_hosts": ["app-prod-01"],
                "affected_services": [],
                "time_window_start": "2026-06-03T14:40:00Z",
                "time_window_end": "2026-06-03T14:45:00Z",
            },
            diagnosis=None,
            max_tool_calls=1,
            planner_provider=FakePlanner(),
        )
    )

    assert calls[0][0] == "query_alerts"
    assert calls[0][1]["event_type"] == "login_failed"
    assert "planner_provider" not in result
    assert result["tool_calls"][0]["reason"] == (
        "LLM wants to check login failure alerts first."
    )


def test_run_chat_investigation_falls_back_when_planner_step_invalid(monkeypatch):
    calls = []

    class FakePlanner:
        async def propose_next_step(self, **kwargs):
            return {
                "tool": "delete_events",
                "reason": "Unsupported destructive action.",
                "kwargs": {"limit": 1},
            }

    async def fake_query_events_tool(**kwargs):
        calls.append(("query_events", kwargs))
        return {
            "tool": "query_events",
            "filters": kwargs,
            "count": 0,
            "events": [],
        }

    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_events_tool",
        fake_query_events_tool,
    )

    result = asyncio.run(
        run_chat_investigation(
            question="查一下最近未知错误",
            incident={
                "incident_id": "incident-unknown",
                "summary": "Unknown operational anomaly.",
                "event_types": ["unknown"],
                "affected_hosts": ["app-prod-01"],
                "affected_services": [],
                "time_window_start": "2026-06-03T14:40:00Z",
                "time_window_end": "2026-06-03T14:45:00Z",
            },
            diagnosis=None,
            max_tool_calls=1,
            planner_provider=FakePlanner(),
        )
    )

    assert calls[0][0] == "query_events"
    assert result["tool_calls"][0]["tool_name"] == "query_events"
    assert result["tool_calls"][0]["reason"] == (
        "Check recent normalized events matching the initial anomaly."
    )


def test_run_chat_investigation_planner_can_continue_beyond_static_plan(monkeypatch):
    calls = []

    class FakePlanner:
        async def propose_next_step(self, **kwargs):
            return {
                "tool": "query_alerts",
                "reason": "Continue checking alert evidence while budget remains.",
                "kwargs": {"limit": 1},
            }

    async def fake_query_alerts_tool(**kwargs):
        calls.append(("query_alerts", kwargs))
        return {
            "tool": "query_alerts",
            "filters": kwargs,
            "count": 0,
            "alerts": [],
        }

    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_alerts_tool",
        fake_query_alerts_tool,
    )

    result = asyncio.run(
        run_chat_investigation(
            question="查一下最近未知错误",
            incident={
                "incident_id": "incident-unknown",
                "summary": "Unknown operational anomaly.",
                "event_types": ["unknown"],
                "affected_hosts": [],
                "affected_services": [],
                "time_window_start": "2026-06-03T14:40:00Z",
                "time_window_end": "2026-06-03T14:45:00Z",
            },
            diagnosis=None,
            max_tool_calls=4,
            planner_provider=FakePlanner(),
        )
    )

    assert len(calls) == 4
    assert result["tool_call_count"] == 4
    assert result["stop_reason"] == "max_tool_calls_reached"


def test_run_chat_investigation_confirms_database_dependency(monkeypatch):
    calls = []

    async def fake_query_events_tool(**kwargs):
        calls.append(("query_events", kwargs))
        if kwargs.get("source_type") == "mysql":
            return {
                "tool": "query_events",
                "count": 2,
                "events": [
                    {
                        "event_id": "event-mysql-001",
                        "event_type": "mysql_connection_refused",
                        "message": "Can't connect to local MySQL server through socket",
                    }
                ],
            }
        if kwargs.get("event_type") == "app_db_connection_error":
            return {
                "tool": "query_events",
                "count": 1,
                "events": [
                    {
                        "event_id": "event-app-001",
                        "event_type": "app_db_connection_error",
                        "message": "login-service database connection refused",
                    }
                ],
            }
        return {"tool": "query_events", "count": 0, "events": []}

    async def fake_query_alerts_tool(**kwargs):
        calls.append(("query_alerts", kwargs))
        return {
            "tool": "query_alerts",
            "count": 5,
            "alerts": [
                {
                    "alert_id": "alert-login-001",
                    "event_type": "login_failed",
                    "summary": "Multiple login failures from different IPs.",
                }
            ],
        }

    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_events_tool",
        fake_query_events_tool,
    )
    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_alerts_tool",
        fake_query_alerts_tool,
    )

    incident = {
        "incident_id": "incident-001",
        "summary": "Multiple login failures and MySQL connection refused.",
        "event_types": ["login_failed", "mysql_connection_refused"],
        "affected_hosts": ["app-prod-01"],
        "affected_services": ["login-service"],
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
    }

    result = asyncio.run(
        run_chat_investigation(
            question="查一下多个 IP 登录失败是不是 MySQL 崩了导致的",
            incident=incident,
            diagnosis=None,
            max_tool_calls=5,
        )
    )

    assert result["status"] == "confirmed_investigation"
    assert result["root_cause"] == "database_dependency_unavailable"
    assert result["confidence"] >= 0.7
    assert result["needs_human_review"] is False
    assert result["tool_call_count"] <= 5
    assert calls[0][0] == "query_events"
    assert result["fallback_report"]["initial_anomaly"] == incident["summary"]
    assert result["fallback_report"]["checked_tools"]


def test_run_chat_investigation_falls_back_after_bounded_checks(monkeypatch):
    async def fake_empty_tool(**kwargs):
        return {
            "tool": "fake_empty",
            "count": 0,
        }

    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_events_tool",
        fake_empty_tool,
    )
    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_alerts_tool",
        fake_empty_tool,
    )
    monkeypatch.setattr(
        "crossst.application.agents.chat_investigation.query_incidents_tool",
        fake_empty_tool,
    )

    result = asyncio.run(
        run_chat_investigation(
            question="查一下最近 5 分钟未知错误日志",
            incident={
                "incident_id": "incident-unknown",
                "summary": "Unknown operational anomaly.",
                "event_types": ["unknown"],
                "affected_hosts": [],
                "affected_services": [],
            },
            diagnosis=None,
            max_tool_calls=2,
        )
    )

    assert result["status"] == "needs_human_review"
    assert result["stop_reason"] == "max_tool_calls_reached"
    assert result["needs_human_review"] is True
    assert result["tool_call_count"] == 2
    assert result["fallback_report"]["original_question"] == "查一下最近 5 分钟未知错误日志"
    assert result["fallback_report"]["remaining_uncertainty"]

