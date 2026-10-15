import asyncio

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from crossst.services.llm.chat import (
    LangChainChatProvider,
    build_allowed_evidence_refs,
    build_chat_prompt_messages,
    build_configured_langchain_chat_provider,
    build_llm_chat_reply,
)
from crossst.services.llm.schemas import LLMChatOutput, validate_llm_chat_output
from crossst.services.chat.reply import build_chat_reply


def test_validate_llm_chat_output_rejects_confident_answer_without_evidence():
    output = LLMChatOutput(
        intent="incident_analysis",
        answer="MySQL is the confirmed root cause.",
        evidence_refs=[],
        confidence=0.91,
        needs_human_review=False,
    )

    validated = validate_llm_chat_output(output)

    assert validated.needs_human_review is True
    assert validated.confidence <= 0.5
    assert "缺少证据引用" in validated.answer


def test_validate_llm_chat_output_filters_unsupported_evidence_refs():
    output = LLMChatOutput(
        intent="incident_analysis",
        answer="MySQL is the confirmed root cause.",
        evidence_refs=[
            "runbook:runbook-mysql-unavailable",
            "event:hallucinated-log",
        ],
        confidence=0.86,
        needs_human_review=False,
    )

    validated = validate_llm_chat_output(
        output,
        allowed_evidence_refs={"runbook:runbook-mysql-unavailable"},
    )

    assert validated.evidence_refs == ["runbook:runbook-mysql-unavailable"]
    assert validated.needs_human_review is True
    assert validated.confidence <= 0.5
    assert "未授权证据引用" in validated.answer


def test_validate_llm_chat_output_overrides_unexpected_intent():
    output = LLMChatOutput(
        intent="made_up_intent",
        answer="Here is the answer.",
        evidence_refs=[],
        confidence=0.3,
        needs_human_review=False,
    )

    validated = validate_llm_chat_output(
        output,
        detected_intent="recommendations",
    )

    assert validated.intent == "recommendations"


def test_llm_chat_output_normalizes_structured_recommended_actions():
    output = LLMChatOutput.model_validate(
        {
            "intent": "recommendations",
            "answer": "按阶段处理。",
            "evidence_refs": ["runbook:runbook-mysql-unavailable"],
            "confidence": 0.76,
            "needs_human_review": False,
            "recommended_actions": [
                {
                    "phase": "立即验证",
                    "actions": [
                        "检查 MySQL 进程状态。",
                        "检查端口监听。",
                    ],
                },
                {
                    "phase": "恢复后观察",
                    "actions": ["观察登录失败是否下降。"],
                },
            ],
        }
    )

    assert output.recommended_actions == [
        "立即验证: 检查 MySQL 进程状态。",
        "立即验证: 检查端口监听。",
        "恢复后观察: 观察登录失败是否下降。",
    ]
    assert output.action_plan == [
        {
            "phase": "立即验证",
            "actions": ["检查 MySQL 进程状态。", "检查端口监听。"],
        },
        {
            "phase": "恢复后观察",
            "actions": ["观察登录失败是否下降。"],
        },
    ]


def test_build_allowed_evidence_refs_includes_diagnosis_tools_and_rag():
    refs = build_allowed_evidence_refs(
        diagnosis={
            "diagnosis_id": "diagnosis-001",
            "incident_id": "incident-001",
        },
        tool_calls=[
            {
                "tool_call_id": "tool-call-001",
                "tool_name": "query_events",
            }
        ],
        rag_context={
            "references": [
                {
                    "document_type": "runbook",
                    "source_id": "runbook-mysql-unavailable",
                }
            ]
        },
    )

    assert "diagnosis:diagnosis-001" in refs
    assert "incident:incident-001" in refs
    assert "tool_call:tool-call-001" in refs
    assert "tool:query_events" in refs
    assert "runbook:runbook-mysql-unavailable" in refs


def test_build_chat_prompt_messages_includes_rag_references():
    messages = build_chat_prompt_messages(
        question="帮我分析这个故障",
        diagnosis={
            "diagnosis_id": "diagnosis-001",
            "root_cause": "mysql_or_database_dependency_unavailable",
        },
        tool_calls=[
            {
                "tool_call_id": "tool-call-001",
                "tool_name": "query_events",
            }
        ],
        rag_context={
            "references": [
                {
                    "document_type": "runbook",
                    "source_id": "runbook-mysql-unavailable",
                    "title": "MySQL unavailable affects login-service",
                }
            ],
            "documents": [
                {
                    "document_type": "runbook",
                    "source_id": "runbook-mysql-unavailable",
                    "title": "MySQL unavailable affects login-service",
                    "content": "Check MySQL process and DB connection errors.",
                }
            ],
        },
        detected_intent="diagnosis_summary",
    )

    rendered = "\n".join(message.content for message in messages)

    assert "帮我分析这个故障" in rendered
    assert "系统识别意图：diagnosis_summary" in rendered
    assert "diagnosis:diagnosis-001" in rendered
    assert "tool_call:tool-call-001" in rendered
    assert "runbook:runbook-mysql-unavailable" in rendered
    assert "mysql_or_database_dependency_unavailable" in rendered


def test_build_chat_prompt_messages_includes_investigation_result():
    messages = build_chat_prompt_messages(
        question="查一下多个 IP 登录失败是不是 MySQL 崩了导致的",
        diagnosis=None,
        tool_calls=[],
        rag_context=None,
        detected_intent="investigation_request",
        investigation_result={
            "status": "confirmed_investigation",
            "root_cause": "database_dependency_unavailable",
            "confidence": 0.82,
            "needs_human_review": False,
            "evidence_chain": [
                "mysql_connection_refused: query_events returned 2 record(s).",
            ],
            "fallback_report": {
                "initial_anomaly": "Login failures increased.",
                "checked_tools": [
                    {
                        "tool_name": "query_events",
                        "result_count": 2,
                    }
                ],
            },
        },
    )

    rendered = "\n".join(message.content for message in messages)

    assert "本轮工具调查" in rendered
    assert "confirmed_investigation" in rendered
    assert "database_dependency_unavailable" in rendered
    assert "mysql_connection_refused" in rendered
    assert "Login failures increased" in rendered


def test_langchain_chat_provider_returns_validated_json_reply():
    model = FakeListChatModel(
        responses=[
            """
            {
              "intent": "incident_analysis",
              "answer": "更可能是 MySQL 不可用导致 login-service 登录失败。",
              "evidence_refs": ["runbook:runbook-mysql-unavailable"],
              "confidence": 0.78,
              "needs_human_review": false,
              "recommended_actions": ["检查 MySQL 进程状态"]
            }
            """
        ]
    )
    provider = LangChainChatProvider(chat_model=model)

    reply = asyncio.run(
        provider.generate_chat_reply(
            question="帮我分析这个故障",
            diagnosis={"root_cause": "mysql_or_database_dependency_unavailable"},
            tool_calls=[],
            rag_context={
                "references": [
                    {
                        "document_type": "runbook",
                        "source_id": "runbook-mysql-unavailable",
                        "title": "MySQL unavailable affects login-service",
                    }
                ],
                "documents": [],
            },
            detected_intent="diagnosis_summary",
        )
    )

    assert reply["intent"] == "diagnosis_summary"
    assert "MySQL" in reply["content"]
    assert reply["evidence_refs"] == ["runbook:runbook-mysql-unavailable"]
    assert reply["metadata"]["provider"] == "langchain"
    assert reply["metadata"]["detected_intent"] == "diagnosis_summary"
    assert reply["metadata"]["llm_intent"] == "incident_analysis"


def test_langchain_chat_provider_filters_hallucinated_evidence_refs():
    model = FakeListChatModel(
        responses=[
            """
            {
              "intent": "incident_analysis",
              "answer": "更可能是 MySQL 不可用导致 login-service 登录失败。",
              "evidence_refs": [
                "runbook:runbook-mysql-unavailable",
                "event:fake-log"
              ],
              "confidence": 0.82,
              "needs_human_review": false,
              "recommended_actions": ["检查 MySQL 进程状态"]
            }
            """
        ]
    )
    provider = LangChainChatProvider(chat_model=model)

    reply = asyncio.run(
        provider.generate_chat_reply(
            question="帮我分析这个故障",
            diagnosis=None,
            tool_calls=[],
            rag_context={
                "references": [
                    {
                        "document_type": "runbook",
                        "source_id": "runbook-mysql-unavailable",
                    }
                ],
                "documents": [],
            },
        )
    )

    assert reply["evidence_refs"] == ["runbook:runbook-mysql-unavailable"]
    assert reply["needs_human_review"] is True
    assert reply["confidence"] <= 0.5
    assert "未授权证据引用" in reply["content"]


def test_langchain_chat_provider_returns_action_plan_for_structured_actions():
    model = FakeListChatModel(
        responses=[
            """
            {
              "intent": "recommendations",
              "answer": "按阶段处理。",
              "evidence_refs": ["runbook:runbook-mysql-unavailable"],
              "confidence": 0.76,
              "needs_human_review": false,
              "recommended_actions": [
                {
                  "phase": "立即验证",
                  "actions": ["检查 MySQL 进程状态。"]
                },
                {
                  "phase": "恢复后观察",
                  "actions": ["观察登录失败是否下降。"]
                }
              ]
            }
            """
        ]
    )
    provider = LangChainChatProvider(chat_model=model)

    reply = asyncio.run(
        provider.generate_chat_reply(
            question="下一步怎么处理？",
            diagnosis=None,
            tool_calls=[],
            rag_context={
                "references": [
                    {
                        "document_type": "runbook",
                        "source_id": "runbook-mysql-unavailable",
                    }
                ],
                "documents": [],
            },
            detected_intent="recommendations",
        )
    )

    assert reply["recommended_actions"] == [
        "立即验证: 检查 MySQL 进程状态。",
        "恢复后观察: 观察登录失败是否下降。",
    ]
    assert reply["action_plan"] == [
        {"phase": "立即验证", "actions": ["检查 MySQL 进程状态。"]},
        {"phase": "恢复后观察", "actions": ["观察登录失败是否下降。"]},
    ]


def test_build_llm_chat_reply_falls_back_when_provider_is_none():
    reply = asyncio.run(
        build_llm_chat_reply(
            provider=None,
            question="帮我分析这个故障",
            diagnosis=None,
            tool_calls=[],
            rag_context=None,
        )
    )

    assert reply is None


def test_build_chat_reply_uses_rules_when_provider_is_none():
    reply = asyncio.run(
        build_chat_reply(
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
            rag_context=None,
            llm_provider=None,
        )
    )

    assert reply["intent"] == "tool_call_summary"
    assert reply["metadata"]["provider"] == "rules"


def test_build_chat_reply_falls_back_to_rules_when_llm_errors():
    class BrokenProvider:
        async def generate_chat_reply(self, **kwargs):
            raise ValueError("bad model output")

    reply = asyncio.run(
        build_chat_reply(
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
            rag_context=None,
            llm_provider=BrokenProvider(),
        )
    )

    assert reply["intent"] == "tool_call_summary"
    assert reply["metadata"]["provider"] == "rules"
    assert reply["metadata"]["llm_fallback_reason"] == "ValueError"


def test_build_chat_reply_records_provider_build_error():
    reply = asyncio.run(
        build_chat_reply(
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
            rag_context=None,
            llm_provider=None,
            llm_fallback_reason="ImportError",
        )
    )

    assert reply["intent"] == "tool_call_summary"
    assert reply["metadata"]["provider"] == "rules"
    assert reply["metadata"]["llm_fallback_reason"] == "ImportError"


def test_build_configured_langchain_chat_provider_returns_error_on_bad_config():
    class BadSettings:
        llm_enabled = True
        llm_model = "missing-model"
        llm_provider = "missing-provider"
        llm_temperature = 0.1
        llm_max_tokens = 1200
        llm_timeout_seconds = 30
        llm_api_key = None
        llm_base_url = None

    provider, error = build_configured_langchain_chat_provider(BadSettings())

    assert provider is None
    assert error is not None

