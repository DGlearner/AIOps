from crossst.services.chat.rules import build_rule_based_chat_reply


def test_rule_based_chat_reply_returns_diagnosis_summary():
    reply = build_rule_based_chat_reply(
        question="这个 incident 为什么触发？",
        diagnosis={
            "status": "confirmed_diagnosis",
            "root_cause": "mysql_or_database_dependency_unavailable",
            "confidence": 0.82,
            "trigger_summary": "MySQL connection refused.",
            "evidence_chain": ["mysql_unavailable: query_events returned 1 related record(s)."],
            "recommendations": ["Check MySQL process."],
        },
        tool_calls=[],
    )

    assert reply["intent"] == "diagnosis_summary"
    assert "mysql_or_database_dependency_unavailable" in reply["content"]


def test_rule_based_chat_reply_returns_tool_call_summary():
    reply = build_rule_based_chat_reply(
        question="Agent 查了什么？",
        diagnosis=None,
        tool_calls=[
            {
                "tool_name": "query_events",
                "reason": "Check MySQL errors.",
                "result_count": 1,
                "duration_ms": 12,
            }
        ],
    )

    assert reply["intent"] == "tool_call_summary"
    assert "query_events" in reply["content"]


def test_rule_based_chat_reply_returns_llm_placeholder_for_unknown_question():
    reply = build_rule_based_chat_reply(
        question="帮我综合分析一下这个问题",
        diagnosis=None,
        tool_calls=[],
    )

    assert reply["intent"] == "llm_not_configured"
    assert "尚未接入 LLM" in reply["content"]


def test_rule_based_chat_reply_returns_rag_context_for_open_question():
    reply = build_rule_based_chat_reply(
        question="帮我综合分析一下这个问题",
        diagnosis=None,
        tool_calls=[],
        rag_context={
            "document_count": 2,
            "references": [
                {
                    "document_type": "runbook",
                    "source_id": "runbook-mysql-unavailable",
                    "title": "MySQL unavailable affects login-service",
                },
                {
                    "document_type": "historical_incident",
                    "source_id": "hist-login-mysql-outage",
                    "title": "MySQL outage caused login failures",
                },
            ],
        },
    )

    assert reply["intent"] == "rag_context_ready"
    assert "检索到 2 条" in reply["content"]
    assert "runbook-mysql-unavailable" in reply["content"]
    assert reply["rag_context"]["document_count"] == 2


def test_rule_based_chat_reply_returns_investigation_result_summary():
    reply = build_rule_based_chat_reply(
        question="查一下多个 IP 登录失败是不是 MySQL 崩了导致的",
        diagnosis=None,
        tool_calls=[],
        investigation_result={
            "status": "confirmed_investigation",
            "root_cause": "database_dependency_unavailable",
            "confidence": 0.82,
            "needs_human_review": False,
            "evidence_chain": [
                "mysql_connection_refused: query_events returned 2 record(s).",
                "app_db_connection_error: query_events returned 1 record(s).",
            ],
            "recommendations": [
                "Check MySQL process, socket, and port listener on the database host.",
            ],
            "tool_calls": [
                {
                    "tool_name": "query_events",
                    "reason": "Check MySQL availability errors.",
                    "result_count": 2,
                    "duration_ms": 8,
                }
            ],
        },
    )

    assert reply["intent"] == "investigation_request"
    assert "database_dependency_unavailable" in reply["content"]
    assert "mysql_connection_refused" in reply["content"]
    assert "query_events" in reply["content"]
    assert reply["confidence"] == 0.82
    assert reply["needs_human_review"] is False
    assert reply["recommended_actions"] == [
        "Check MySQL process, socket, and port listener on the database host.",
    ]


def test_rule_based_chat_reply_returns_investigation_fallback_report():
    reply = build_rule_based_chat_reply(
        question="查一下最近 5 分钟未知错误日志",
        diagnosis=None,
        tool_calls=[],
        investigation_result={
            "status": "needs_human_review",
            "stop_reason": "max_tool_calls_reached",
            "confidence": 0.0,
            "root_cause": None,
            "needs_human_review": True,
            "tool_calls": [
                {
                    "tool_name": "query_events",
                    "reason": "Check recent normalized events.",
                    "result_count": 0,
                    "duration_ms": 5,
                }
            ],
            "fallback_report": {
                "initial_anomaly": "Unknown operational anomaly.",
                "original_question": "查一下最近 5 分钟未知错误日志",
                "checked_tools": [
                    {
                        "tool_name": "query_events",
                        "reason": "Check recent normalized events.",
                        "result_count": 0,
                    }
                ],
                "remaining_uncertainty": [
                    "No root cause crossed the confidence threshold.",
                ],
                "recommended_human_next_steps": [
                    "Inspect raw logs around the incident window.",
                ],
            },
        },
    )

    assert reply["intent"] == "investigation_request"
    assert "needs_human_review" in reply["content"]
    assert "Unknown operational anomaly" in reply["content"]
    assert "query_events" in reply["content"]
    assert "Inspect raw logs" in reply["content"]
    assert reply["needs_human_review"] is True

