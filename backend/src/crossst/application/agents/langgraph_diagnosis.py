from typing import Any, Literal

from langgraph.graph import END, StateGraph

from crossst.application.agents.diagnosis_reasoning import (
    DEFAULT_REASONING,
    DiagnosisReasoning,
    build_configured_diagnosis_reasoning,
)
from crossst.application.agents.diagnosis_graph import (
    DEFAULT_MAX_TOOL_CALLS,
    build_diagnosis_report,
    build_initial_state,
    execute_selected_tool,
    move_to_next_hypothesis,
    run_diagnosis,
    select_next_tool,
    should_stop,
)
from crossst.application.agents.diagnosis_state import DiagnosisState
from crossst.domain.schemas.diagnosis import DiagnosisReport
from crossst.infrastructure.storage.diagnoses import save_diagnosis
from crossst.infrastructure.storage.postgres import AsyncSessionLocal


def initialize_state_node(
    state: DiagnosisState,
    reasoning: DiagnosisReasoning = DEFAULT_REASONING,
) -> DiagnosisState:
    return reasoning.generate_hypotheses(state)


async def tool_step_node(
    state: DiagnosisState,
    reasoning: DiagnosisReasoning = DEFAULT_REASONING,
) -> DiagnosisState:
    if should_stop(state):
        return state

    selected_tool = select_next_tool(state)
    state = await execute_selected_tool(state, selected_tool)
    state = reasoning.update_evidence(state)
    if should_stop(state):
        return state

    state = move_to_next_hypothesis(state)
    should_stop(state)
    return state


def route_after_tool(state: DiagnosisState) -> Literal["finish", "continue"]:
    if state.get("diagnosis_status") != "running":
        return "finish"
    return "continue"


def finish_node(
    state: DiagnosisState,
    reasoning: DiagnosisReasoning = DEFAULT_REASONING,
) -> DiagnosisState:
    state = reasoning.generate_recommendations(state)
    return state


def build_langgraph_app(reasoning: DiagnosisReasoning | None = None):
    reasoning = reasoning or DEFAULT_REASONING

    def initialize_with_reasoning(state: DiagnosisState) -> DiagnosisState:
        return initialize_state_node(state, reasoning)

    async def tool_step_with_reasoning(state: DiagnosisState) -> DiagnosisState:
        return await tool_step_node(state, reasoning)

    def finish_with_reasoning(state: DiagnosisState) -> DiagnosisState:
        return finish_node(state, reasoning)

    graph = StateGraph(DiagnosisState)
    graph.add_node("initialize", initialize_with_reasoning)
    graph.add_node("tool_step", tool_step_with_reasoning)
    graph.add_node("finish", finish_with_reasoning)

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


async def run_langgraph_diagnosis(
    *,
    incident: dict[str, Any],
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    persist: bool = True,
    reasoning: DiagnosisReasoning | None = None,
) -> DiagnosisReport:
    reasoning = reasoning or build_configured_diagnosis_reasoning()
    app = build_langgraph_app(reasoning)
    initial_state = build_initial_state(
        incident=incident,
        max_tool_calls=max_tool_calls,
    )
    final_state = await app.ainvoke(initial_state)
    report = build_diagnosis_report(final_state)

    if persist:
        async with AsyncSessionLocal() as session:
            await save_diagnosis(session, report)

    return report

