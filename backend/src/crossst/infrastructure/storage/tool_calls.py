from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.tool_call import ToolCallRecord
from crossst.domain.schemas.tool_calls import ToolCallLog


async def save_tool_calls(
    session: AsyncSession,
    tool_calls: list[ToolCallLog],
) -> None:
    for tool_call in tool_calls:
        session.add(
            ToolCallRecord(
                tool_call_id=tool_call.tool_call_id,
                incident_id=tool_call.incident_id,
                diagnosis_id=tool_call.diagnosis_id,
                tool_name=tool_call.tool_name,
                reason=tool_call.reason,
                kwargs=tool_call.kwargs,
                result_count=tool_call.result_count,
                result_summary=tool_call.result_summary,
                started_at=tool_call.started_at,
                finished_at=tool_call.finished_at,
                duration_ms=tool_call.duration_ms,
            )
        )


def build_query_tool_calls_statement(
    *,
    incident_id: str | None = None,
    diagnosis_id: str | None = None,
    tool_name: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> Select[tuple[ToolCallRecord]]:
    statement = select(ToolCallRecord).order_by(ToolCallRecord.started_at.desc())

    if incident_id is not None:
        statement = statement.where(ToolCallRecord.incident_id == incident_id)
    if diagnosis_id is not None:
        statement = statement.where(ToolCallRecord.diagnosis_id == diagnosis_id)
    if tool_name is not None:
        statement = statement.where(ToolCallRecord.tool_name == tool_name)
    if start_time is not None:
        statement = statement.where(ToolCallRecord.started_at >= start_time)
    if end_time is not None:
        statement = statement.where(ToolCallRecord.started_at <= end_time)

    return statement.limit(limit)


async def query_tool_calls(
    session: AsyncSession,
    *,
    incident_id: str | None = None,
    diagnosis_id: str | None = None,
    tool_name: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
) -> list[ToolCallRecord]:
    statement = build_query_tool_calls_statement(
        incident_id=incident_id,
        diagnosis_id=diagnosis_id,
        tool_name=tool_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())

