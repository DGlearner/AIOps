from datetime import datetime, timezone
from types import SimpleNamespace

from crossst.services.rag.chat_context import (
    build_chat_rag_query,
    build_chat_rag_context_payload,
)


def test_build_chat_rag_query_combines_question_incident_and_diagnosis():
    incident = SimpleNamespace(
        affected_services=["login-service"],
        affected_hosts=["app-prod-01", "db-prod-01"],
        event_types=["app_db_connection_error", "mysql_connection_refused"],
        summary="login-service login failures increased after database errors.",
    )
    diagnosis = {
        "root_cause": "mysql_or_database_dependency_unavailable",
        "hypotheses": ["mysql unavailable", "recent deployment issue"],
        "evidence_chain": ["query_events found mysql_connection_refused records."],
    }
    summary = SimpleNamespace(
        compressed_context="User is investigating login-service failed logins.",
        hypotheses=["database dependency outage"],
    )

    query = build_chat_rag_query(
        question="帮我综合分析一下这个问题",
        incident=incident,
        diagnosis=diagnosis,
        conversation_summary=summary,
    )

    assert "帮我综合分析一下这个问题" in query
    assert "login-service" in query
    assert "mysql_connection_refused" in query
    assert "mysql_or_database_dependency_unavailable" in query
    assert "database dependency outage" in query


def test_build_chat_rag_context_payload_collects_references():
    now = datetime.now(timezone.utc)
    runbook = SimpleNamespace(
        runbook_id="runbook-mysql-unavailable",
        title="MySQL unavailable affects login-service",
        service="login-service",
        component="mysql",
        problem_types=["mysql_connection_refused"],
        content="Check MySQL process status and login-service DB errors.",
        steps=["Check MySQL process.", "Review login-service DB errors."],
        tags=["mysql", "database"],
        updated_at=now,
    )
    historical_incident = SimpleNamespace(
        historical_incident_id="hist-login-mysql-outage",
        title="MySQL outage caused login failures",
        service="login-service",
        component="mysql",
        root_cause="mysql_or_database_dependency_unavailable",
        summary="MySQL refused connections while login failures increased.",
        resolution="Restarted MySQL.",
        evidence_chain=["mysql_connection_refused matched the incident window."],
        tags=["mysql", "login-service"],
        occurred_at=now,
    )
    diagnosis = {
        "diagnosis_id": "diag-001",
        "root_cause": "mysql_or_database_dependency_unavailable",
        "confidence": 0.82,
        "evidence_chain": ["query_events found mysql_connection_refused records."],
    }

    context = build_chat_rag_context_payload(
        query="login-service mysql failure",
        diagnosis=diagnosis,
        tool_calls=[
            {
                "tool_call_id": "tool-001",
                "tool_name": "query_events",
                "reason": "Check MySQL errors.",
                "result_count": 3,
            }
        ],
        runbooks=[runbook],
        historical_incidents=[historical_incident],
    )

    assert context["retrieval_mode"] == "postgres_text"
    assert context["document_count"] == 4
    assert {document["document_type"] for document in context["documents"]} == {
        "diagnosis",
        "tool_call",
        "runbook",
        "historical_incident",
    }
    assert context["references"][0]["source_id"] == "diag-001"
    assert context["milvus_ready"] is True

