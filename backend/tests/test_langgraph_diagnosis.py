import asyncio
import subprocess
import sys
from pathlib import Path

from crossst.application.agents.diagnosis_graph import make_incident_context


def test_langgraph_modules_import_without_pending_deprecation_warning():
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import crossst.application.agents.langgraph_diagnosis; "
                "import crossst.application.agents.chat_router; "
                "import crossst.application.agents.chat_investigation"
            ),
        ],
        cwd=backend_dir,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "allowed_objects" not in result.stderr


def test_build_langgraph_app():
    from crossst.application.agents.langgraph_diagnosis import build_langgraph_app

    app = build_langgraph_app()

    assert app is not None


def test_run_langgraph_diagnosis_falls_back_to_human_review_without_evidence(monkeypatch):
    from crossst.application.agents.langgraph_diagnosis import run_langgraph_diagnosis

    async def fake_execute_selected_tool(state, selected_tool):
        state["tool_call_count"] = state.get("tool_call_count", 0) + 1
        state.setdefault("tool_results", []).append(
            {
                "tool": selected_tool["tool"],
                "count": 0,
                "items": [],
            }
        )
        state.setdefault("tool_call_summary", []).append(
            {
                "tool": selected_tool["tool"],
                "reason": selected_tool["reason"],
                "kwargs": {},
                "result_count": 0,
            }
        )
        return state

    monkeypatch.setattr(
        "crossst.application.agents.langgraph_diagnosis.execute_selected_tool",
        fake_execute_selected_tool,
    )

    incident = make_incident_context(
        incident_id="incident-langgraph-no-evidence",
        summary="Unknown operational anomaly.",
        event_types=["unknown"],
    )

    report = asyncio.run(
        run_langgraph_diagnosis(
            incident=incident,
            max_tool_calls=1,
            persist=False,
        )
    )

    assert report.status == "needs_human_review"
    assert report.recommendations


def test_run_langgraph_diagnosis_accepts_custom_reasoning_provider(monkeypatch):
    from crossst.application.agents.langgraph_diagnosis import run_langgraph_diagnosis

    class FakeReasoning:
        def generate_hypotheses(self, state):
            state["hypotheses"] = ["custom_langgraph_hypothesis"]
            state["current_hypothesis"] = "custom_langgraph_hypothesis"
            return state

        def update_evidence(self, state):
            state["confidence"] = 0.93
            state["root_cause"] = "custom_langgraph_root_cause"
            state.setdefault("evidence_chain", []).append("custom langgraph evidence")
            return state

        def generate_recommendations(self, state):
            state["recommendations"] = ["custom langgraph recommendation"]
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
        state.setdefault("tool_call_summary", []).append(
            {
                "tool": selected_tool["tool"],
                "reason": selected_tool["reason"],
                "kwargs": {},
                "result_count": 1,
            }
        )
        return state

    monkeypatch.setattr(
        "crossst.application.agents.langgraph_diagnosis.execute_selected_tool",
        fake_execute_selected_tool,
    )

    incident = make_incident_context(
        incident_id="incident-langgraph-custom-reasoning",
        summary="Custom LangGraph anomaly.",
        event_types=["unknown"],
    )

    report = asyncio.run(
        run_langgraph_diagnosis(
            incident=incident,
            max_tool_calls=1,
            persist=False,
            reasoning=FakeReasoning(),
        )
    )

    assert report.status == "confirmed_diagnosis"
    assert report.root_cause == "custom_langgraph_root_cause"
    assert report.evidence_chain == ["custom langgraph evidence"]
    assert report.recommendations == ["custom langgraph recommendation"]

