import asyncio

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from crossst.services.llm.investigation_planner import (
    LangChainInvestigationPlannerProvider,
    build_investigation_planner_prompt_messages,
)


def test_build_investigation_planner_prompt_messages_includes_allowed_tools():
    messages = build_investigation_planner_prompt_messages(
        question="查一下多个 IP 登录失败是不是 MySQL 崩了导致的",
        incident={
            "incident_id": "incident-001",
            "summary": "Login failures increased and MySQL connection refused.",
            "event_types": ["login_failed", "mysql_connection_refused"],
        },
        diagnosis=None,
        tool_calls=[],
        evidence_chain=[],
        remaining_tool_calls=5,
        allowed_tools=["query_events", "query_alerts"],
    )

    rendered = "\n".join(message.content for message in messages)

    assert "query_events" in rendered
    assert "query_alerts" in rendered
    assert "remaining_tool_calls" in rendered
    assert "只输出 JSON" in rendered


def test_langchain_investigation_planner_provider_returns_json_step():
    model = FakeListChatModel(
        responses=[
            """
            {
              "tool": "query_events",
              "reason": "Check MySQL availability errors before attributing login failures.",
              "kwargs": {
                "source_type": "mysql",
                "event_type": "mysql_connection_refused",
                "limit": 20
              }
            }
            """
        ]
    )
    provider = LangChainInvestigationPlannerProvider(chat_model=model)

    step = asyncio.run(
        provider.propose_next_step(
            question="查一下多个 IP 登录失败是不是 MySQL 崩了导致的",
            incident={
                "incident_id": "incident-001",
                "summary": "Login failures increased and MySQL connection refused.",
                "event_types": ["login_failed", "mysql_connection_refused"],
            },
            diagnosis=None,
            tool_calls=[],
            evidence_chain=[],
            remaining_tool_calls=5,
            allowed_tools=["query_events", "query_alerts"],
        )
    )

    assert step == {
        "tool": "query_events",
        "reason": "Check MySQL availability errors before attributing login failures.",
        "kwargs": {
            "source_type": "mysql",
            "event_type": "mysql_connection_refused",
            "limit": 20,
        },
    }


def test_langchain_investigation_planner_provider_returns_none_for_invalid_json():
    model = FakeListChatModel(responses=["I would inspect MySQL logs first."])
    provider = LangChainInvestigationPlannerProvider(chat_model=model)

    step = asyncio.run(
        provider.propose_next_step(
            question="查一下 MySQL 错误",
            incident=None,
            diagnosis=None,
            tool_calls=[],
            evidence_chain=[],
            remaining_tool_calls=5,
            allowed_tools=["query_events"],
        )
    )

    assert step is None

