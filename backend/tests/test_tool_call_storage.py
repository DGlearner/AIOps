import asyncio
from datetime import datetime, timezone

from crossst.domain.schemas.diagnosis import DiagnosisReport
from crossst.domain.schemas.tool_calls import ToolCallLog
from crossst.infrastructure.storage.diagnoses import save_diagnosis
from crossst.infrastructure.storage.tool_calls import build_query_tool_calls_statement


def test_build_query_tool_calls_statement_applies_filters():
    statement = build_query_tool_calls_statement(
        incident_id="incident-001",
        diagnosis_id="diagnosis-001",
        tool_name="query_events",
        start_time=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "tool_calls.incident_id = 'incident-001'" in compiled
    assert "tool_calls.diagnosis_id = 'diagnosis-001'" in compiled
    assert "tool_calls.tool_name = 'query_events'" in compiled
    assert "tool_calls.started_at >=" in compiled
    assert "tool_calls.started_at <=" in compiled
    assert "LIMIT 10" in compiled


def test_save_diagnosis_persists_tool_calls(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSession:
        def add(self, record):
            captured["diagnosis_record"] = record

        async def commit(self):
            captured["committed"] = True

    async def fake_save_tool_calls(session, tool_calls):
        captured["tool_calls"] = tool_calls

    monkeypatch.setattr(
        "crossst.infrastructure.storage.diagnoses.save_tool_calls",
        fake_save_tool_calls,
    )

    report = DiagnosisReport(
        incident_id="incident-001",
        status="confirmed_diagnosis",
        stop_reason="confidence_threshold_reached",
        confidence=0.82,
        trigger_summary="MySQL unavailable.",
        root_cause="mysql_or_database_dependency_unavailable",
        tool_calls=[
            ToolCallLog(
                incident_id="incident-001",
                tool_name="query_events",
                reason="Check MySQL errors.",
                kwargs={"event_type": "mysql_connection_refused"},
                result_count=1,
            ).model_dump()
        ],
    )

    asyncio.run(save_diagnosis(FakeSession(), report))

    assert captured["committed"] is True
    tool_calls = captured["tool_calls"]
    assert len(tool_calls) == 1
    assert tool_calls[0].diagnosis_id == report.diagnosis_id
    assert tool_calls[0].tool_name == "query_events"

