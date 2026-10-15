from typing import TypedDict

from langgraph.graph import END, StateGraph

from crossst.services.chat.intent import classify_chat_intent


class ChatRouterState(TypedDict, total=False):
    question: str
    detected_intent: str
    chat_route: str
    route_reason: str
    requires_tool_investigation: bool


CHAT_ROUTE_BY_INTENT = {
    "diagnosis_summary": "answer_with_context",
    "tool_call_summary": "answer_with_tool_summary",
    "recommendations": "answer_with_recommendations",
    "incident_report": "generate_incident_report",
    "knowledge_query": "answer_with_rag",
    "investigation_request": "investigate_with_tools",
    "general_question": "answer_with_context",
}

CHAT_ROUTE_REASONS = {
    "answer_with_context": "Use current diagnosis, memory, tool summaries, and RAG context to answer directly.",
    "answer_with_tool_summary": "Summarize existing audited tool calls without running new tools.",
    "answer_with_recommendations": "Generate operational recommendations from current evidence.",
    "generate_incident_report": "Prepare an incident report from the current session context.",
    "answer_with_rag": "Use runbooks, historical incidents, and knowledge context.",
    "investigate_with_tools": "Route to a future ReAct-style tool investigation chain.",
}


def route_chat_intent(detected_intent: str | None) -> str:
    return CHAT_ROUTE_BY_INTENT.get(
        detected_intent or "general_question",
        "answer_with_context",
    )


def build_route_reason(chat_route: str) -> str:
    return CHAT_ROUTE_REASONS.get(chat_route, CHAT_ROUTE_REASONS["answer_with_context"])


def route_node(state: ChatRouterState) -> ChatRouterState:
    detected_intent = state.get("detected_intent") or classify_chat_intent(
        state.get("question", "")
    )
    chat_route = route_chat_intent(detected_intent)
    return {
        **state,
        "detected_intent": detected_intent,
        "chat_route": chat_route,
        "route_reason": build_route_reason(chat_route),
        "requires_tool_investigation": chat_route == "investigate_with_tools",
    }


def build_chat_router_app():
    graph = StateGraph(ChatRouterState)
    graph.add_node("route", route_node)
    graph.set_entry_point("route")
    graph.add_edge("route", END)
    return graph.compile()


async def run_chat_router(
    *,
    question: str,
    detected_intent: str | None = None,
) -> ChatRouterState:
    app = build_chat_router_app()
    return await app.ainvoke(
        {
            "question": question,
            "detected_intent": detected_intent or classify_chat_intent(question),
        }
    )

