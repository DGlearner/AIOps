from fastapi import APIRouter, HTTPException

from crossst.application.agents.incident_context import build_incident_context_from_record
from crossst.application.agents.langgraph_diagnosis import run_langgraph_diagnosis
from crossst.api.routes.ops import serialize_tool_call
from crossst.infrastructure.storage.diagnoses import get_latest_diagnosis_for_incident
from crossst.infrastructure.storage.incidents import get_incident_by_id
from crossst.infrastructure.storage.postgres import AsyncSessionLocal
from crossst.infrastructure.storage.tool_calls import query_tool_calls

router = APIRouter(prefix="/incidents", tags=["diagnosis"])


def serialize_diagnosis_record(record) -> dict:
    return {
        "diagnosis_id": record.diagnosis_id,
        "incident_id": record.incident_id,
        "status": record.status,
        "stop_reason": record.stop_reason,
        "confidence": record.confidence,
        "trigger_summary": record.trigger_summary,
        "root_cause": record.root_cause,
        "hypotheses": record.hypotheses,
        "evidence_chain": record.evidence_chain,
        "ruled_out_hypotheses": record.ruled_out_hypotheses,
        "tool_call_summary": record.tool_call_summary,
        "recommendations": record.recommendations,
        "created_at": record.created_at.isoformat(),
    }


@router.get("/ /diagnosis/latest")
async def get_latest_incident_diagnosis(incident_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        diagnosis = await get_latest_diagnosis_for_incident(session, incident_id)

    if diagnosis is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    return serialize_diagnosis_record(diagnosis)


@router.post("/{incident_id}/diagnose")
async def diagnose_incident(incident_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        incident = await get_incident_by_id(session, incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    context = build_incident_context_from_record(incident)
    report = await run_langgraph_diagnosis(
        incident=context,
        max_tool_calls=5,
        persist=True,
    )
    return report.model_dump(mode="json")


@router.get("/{incident_id}/tool-calls")
async def get_incident_tool_calls(
    incident_id: str,
    limit: int = 100,
) -> dict:
    async with AsyncSessionLocal() as session:
        tool_calls = await query_tool_calls(
            session,
            incident_id=incident_id,
            limit=limit,
        )

    return {
        "incident_id": incident_id,
        "count": len(tool_calls),
        "tool_calls": [serialize_tool_call(tool_call) for tool_call in tool_calls],
    }

