import asyncio

from crossst.application.agents.chat_router import (
    build_chat_router_app,
    route_chat_intent,
    run_chat_router,
)


def test_route_chat_intent_maps_known_intents_to_routes():
    assert route_chat_intent("diagnosis_summary") == "answer_with_context"
    assert route_chat_intent("tool_call_summary") == "answer_with_tool_summary"
    assert route_chat_intent("recommendations") == "answer_with_recommendations"
    assert route_chat_intent("knowledge_query") == "answer_with_rag"
    assert route_chat_intent("incident_report") == "generate_incident_report"
    assert route_chat_intent("investigation_request") == "investigate_with_tools"
    assert route_chat_intent("general_question") == "answer_with_context"
    assert route_chat_intent("unknown") == "answer_with_context"


def test_build_chat_router_app():
    app = build_chat_router_app()

    assert app is not None


def test_run_chat_router_returns_route_decision():
    result = asyncio.run(
        run_chat_router(
            question="查一下最近 5 分钟 MySQL 错误日志",
            detected_intent="investigation_request",
        )
    )

    assert result["question"] == "查一下最近 5 分钟 MySQL 错误日志"
    assert result["detected_intent"] == "investigation_request"
    assert result["chat_route"] == "investigate_with_tools"
    assert result["route_reason"]

