from typing import Any, Literal, TypedDict


DiagnosisStatus = Literal["running", "confirmed_diagnosis", "needs_human_review"]


class DiagnosisState(TypedDict, total=False):
    incident_id: str
    incident: dict[str, Any]
    trigger_summary: str

    hypotheses: list[str]
    current_hypothesis: str | None
    evidence_chain: list[str]
    ruled_out_hypotheses: list[str]
    tool_results: list[dict[str, Any]]
    tool_call_summary: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]

    confidence: float
    diagnosis_status: DiagnosisStatus
    root_cause: str | None
    recommendations: list[str]

    tool_call_count: int
    max_tool_calls: int
    max_reasoning_steps: int
    stop_reason: str | None

