from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.diagnosis import IncidentDiagnosis
from crossst.domain.schemas.diagnosis import DiagnosisReport
from crossst.domain.schemas.tool_calls import ToolCallLog
from crossst.infrastructure.storage.tool_calls import save_tool_calls


async def save_diagnosis(
    session: AsyncSession,
    report: DiagnosisReport,
) -> None:
    session.add(
        IncidentDiagnosis(
            diagnosis_id=report.diagnosis_id,
            incident_id=report.incident_id,
            status=report.status,
            stop_reason=report.stop_reason,
            confidence=report.confidence,
            trigger_summary=report.trigger_summary,
            root_cause=report.root_cause,
            hypotheses=report.hypotheses,
            evidence_chain=report.evidence_chain,
            ruled_out_hypotheses=report.ruled_out_hypotheses,
            tool_call_summary=report.tool_call_summary,
            recommendations=report.recommendations,
            created_at=report.created_at,
        )
    )
    tool_calls = [
        ToolCallLog.model_validate(
            {
                **tool_call,
                "diagnosis_id": report.diagnosis_id,
            }
        )
        for tool_call in report.tool_calls
    ]
    await save_tool_calls(session, tool_calls)
    await session.commit()


async def get_latest_diagnosis_for_incident(
    session: AsyncSession,
    incident_id: str,
) -> IncidentDiagnosis | None:
    result = await session.execute(
        select(IncidentDiagnosis)
        .where(IncidentDiagnosis.incident_id == incident_id)
        .order_by(IncidentDiagnosis.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def query_diagnoses(
    session: AsyncSession,
    *,
    incident_id: str | None = None,
    status: str | None = None,
    root_cause: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[IncidentDiagnosis]:
    statement = select(IncidentDiagnosis).order_by(IncidentDiagnosis.created_at.desc())

    if incident_id is not None:
        statement = statement.where(IncidentDiagnosis.incident_id == incident_id)
    if status is not None:
        statement = statement.where(IncidentDiagnosis.status == status)
    if root_cause is not None:
        statement = statement.where(IncidentDiagnosis.root_cause == root_cause)
    if start_time is not None:
        statement = statement.where(IncidentDiagnosis.created_at >= start_time)
    if end_time is not None:
        statement = statement.where(IncidentDiagnosis.created_at <= end_time)

    result = await session.execute(statement.limit(limit))
    return list(result.scalars().all())

