import asyncio
from datetime import datetime, timezone

from fastapi.routing import APIRoute

from crossst.api.routes import chat as chat_routes
from crossst.api.app import app
from crossst.api.routes.chat import (
    build_assistant_message_metadata,
    create_chat_session,
    build_user_message_metadata,
    ensure_conversation_access,
    serialize_conversation_session,
)
from crossst.domain.schemas.conversations import ConversationSessionCreate


def test_serialize_conversation_session_includes_team_id_from_metadata():
    class Record:
        session_id = "session-001"
        user_id = "ops-user"
        current_incident_id = "incident-001"
        title = "Incident chat"
        status = "open"
        extra = {"team_id": "sre-team", "environment": "prod"}
        created_at = datetime(2026, 6, 4, tzinfo=timezone.utc)
        updated_at = datetime(2026, 6, 4, tzinfo=timezone.utc)

    payload = serialize_conversation_session(Record())

    assert payload["user_id"] == "ops-user"
    assert payload["team_id"] == "sre-team"


def test_chat_messages_route_defaults_to_recent_paginated_messages():
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == "/chat/sessions/{session_id}/messages"
        and "GET" in route.methods
    )
    dependant = route.dependant
    params = {param.name: param.default for param in dependant.query_params}

    assert params["limit"] == 50
    assert params["newest_first"] is True
    assert params["before_created_at"] is None


def test_chat_session_detail_routes_accept_optional_access_filters():
    route_specs = [
        ("/chat/sessions/{session_id}", "PATCH"),
        ("/chat/sessions/{session_id}/messages", "GET"),
        ("/chat/sessions/{session_id}/messages", "POST"),
        ("/chat/sessions/{session_id}/context", "GET"),
        ("/chat/sessions/{session_id}/rag-context", "GET"),
    ]

    for path, method in route_specs:
        route = next(
            route
            for route in app.routes
            if isinstance(route, APIRoute)
            and route.path == path
            and method in route.methods
        )
        params = {param.name: param.default for param in route.dependant.query_params}

        assert params["user_id"] is None
        assert params["team_id"] is None


def test_create_chat_session_does_not_write_summary_in_mvp(monkeypatch):
    calls = {"session": 0, "summary": 0}

    class FakeAsyncSessionLocal:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    async def fake_save_conversation_session(session, conversation):
        calls["session"] += 1

    async def fake_save_conversation_summary(session, summary):
        calls["summary"] += 1

    monkeypatch.setattr(chat_routes, "AsyncSessionLocal", FakeAsyncSessionLocal)
    monkeypatch.setattr(
        chat_routes,
        "save_conversation_session",
        fake_save_conversation_session,
    )
    monkeypatch.setattr(
        chat_routes,
        "save_conversation_summary",
        fake_save_conversation_summary,
        raising=False,
    )

    response = asyncio.run(
        create_chat_session(
            ConversationSessionCreate(
                user_id="ops-user",
                team_id="sre-team",
                current_incident_id="incident-001",
            )
        )
    )

    assert response["user_id"] == "ops-user"
    assert calls == {"session": 1, "summary": 0}


def test_build_user_message_metadata_adds_detected_intent():
    metadata = build_user_message_metadata(
        payload_metadata={"client": "web"},
        detected_intent="diagnosis_summary",
    )

    assert metadata == {
        "client": "web",
        "detected_intent": "diagnosis_summary",
    }


def test_ensure_conversation_access_allows_matching_user_or_team():
    class Record:
        user_id = "ops-user"
        extra = {"team_id": "sre-team"}

    ensure_conversation_access(Record(), user_id="ops-user")
    ensure_conversation_access(Record(), team_id="sre-team")
    ensure_conversation_access(Record(), user_id="ops-user", team_id="sre-team")


def test_ensure_conversation_access_rejects_mismatched_user_or_team():
    class Record:
        user_id = "ops-user"
        extra = {"team_id": "sre-team"}

    try:
        ensure_conversation_access(Record(), user_id="other-user")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("Expected user mismatch to be rejected")

    try:
        ensure_conversation_access(Record(), team_id="other-team")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("Expected team mismatch to be rejected")


def test_build_assistant_message_metadata_persists_reply_audit_fields():
    metadata = build_assistant_message_metadata(
        reply={
            "intent": "recommendations",
            "evidence_refs": ["diagnosis:diag-001", "runbook:runbook-001"],
            "confidence": 0.76,
            "needs_human_review": False,
            "recommended_actions": ["检查 MySQL 进程状态。"],
            "action_plan": [
                {
                    "phase": "立即验证",
                    "actions": ["检查 MySQL 进程状态。"],
                }
            ],
            "metadata": {
                "provider": "langchain",
                "detected_intent": "recommendations",
                "llm_intent": "recommendations",
            },
        },
        detected_intent="recommendations",
        rag_context={
            "references": [
                {"document_type": "runbook", "source_id": "runbook-001"},
                {"document_type": "historical_incident", "source_id": "hist-001"},
            ]
        },
        route_result={
            "chat_route": "answer_with_recommendations",
            "route_reason": "Generate operational recommendations from current evidence.",
            "requires_tool_investigation": False,
        },
    )

    assert metadata["intent"] == "recommendations"
    assert metadata["detected_intent"] == "recommendations"
    assert metadata["chat_route"] == "answer_with_recommendations"
    assert metadata["route_reason"] == "Generate operational recommendations from current evidence."
    assert metadata["requires_tool_investigation"] is False
    assert metadata["llm_intent"] == "recommendations"
    assert metadata["provider"] == "langchain"
    assert metadata["evidence_refs"] == ["diagnosis:diag-001", "runbook:runbook-001"]
    assert metadata["confidence"] == 0.76
    assert metadata["needs_human_review"] is False
    assert metadata["recommended_actions"] == ["检查 MySQL 进程状态。"]
    assert metadata["action_plan"][0]["phase"] == "立即验证"
    assert metadata["rag_reference_count"] == 2


def test_build_assistant_message_metadata_persists_investigation_summary():
    metadata = build_assistant_message_metadata(
        reply={
            "intent": "investigation_request",
            "evidence_refs": [],
            "confidence": 0.82,
            "needs_human_review": False,
            "recommended_actions": ["检查 MySQL 进程状态。"],
            "metadata": {"provider": "rules"},
        },
        detected_intent="investigation_request",
        rag_context=None,
        route_result={
            "chat_route": "investigate_with_tools",
            "route_reason": "Route to a future ReAct-style tool investigation chain.",
            "requires_tool_investigation": True,
        },
        investigation_result={
            "status": "confirmed_investigation",
            "stop_reason": "confidence_threshold_reached",
            "confidence": 0.82,
            "root_cause": "database_dependency_unavailable",
            "needs_human_review": False,
            "planner_provider": "langchain",
            "planner_fallback_reason": None,
            "tool_call_count": 2,
            "tool_calls": [
                {
                    "tool_name": "query_events",
                    "reason": "Check MySQL availability errors.",
                    "result_count": 2,
                }
            ],
            "fallback_report": {
                "initial_anomaly": "Login failures increased.",
                "remaining_uncertainty": [],
            },
        },
    )

    assert metadata["requires_tool_investigation"] is True
    assert metadata["investigation_status"] == "confirmed_investigation"
    assert metadata["investigation_root_cause"] == "database_dependency_unavailable"
    assert metadata["investigation_planner_provider"] == "langchain"
    assert metadata["investigation_planner_fallback_reason"] is None
    assert metadata["investigation_tool_call_count"] == 2
    assert metadata["investigation_checked_tools"] == [
        {
            "tool_name": "query_events",
            "reason": "Check MySQL availability errors.",
            "result_count": 2,
        }
    ]
    assert metadata["investigation_fallback_report"]["initial_anomaly"] == (
        "Login failures increased."
    )

