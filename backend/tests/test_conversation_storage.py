from datetime import datetime, timezone

from crossst.domain.schemas.conversations import ConversationSessionRecord
from crossst.infrastructure.storage.conversations import (
    build_conversation_session_extra,
    build_query_conversation_messages_statement,
    build_query_conversation_sessions_statement,
    build_update_conversation_session_values,
    build_update_conversation_summary_values,
    get_conversation_team_id,
)


def test_build_query_conversation_sessions_statement_applies_filters():
    statement = build_query_conversation_sessions_statement(
        user_id="ops-user",
        incident_id="incident-001",
        status="open",
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "conversation_sessions.user_id = 'ops-user'" in compiled
    assert "conversation_sessions.current_incident_id = 'incident-001'" in compiled
    assert "conversation_sessions.status = 'open'" in compiled
    assert "LIMIT 10" in compiled


def test_build_query_conversation_sessions_statement_filters_by_team_id():
    statement = build_query_conversation_sessions_statement(
        team_id="sre-team",
        limit=10,
    )

    compiled_statement = statement.compile()
    compiled = str(compiled_statement)

    assert "conversation_sessions.metadata" in compiled
    assert "sre-team" in str(compiled_statement.params.values())


def test_build_conversation_session_extra_stores_team_id_in_metadata():
    conversation = ConversationSessionRecord(
        user_id="ops-user",
        team_id="sre-team",
        title="Incident chat",
        metadata={"environment": "prod"},
    )

    extra = build_conversation_session_extra(conversation)

    assert extra["team_id"] == "sre-team"
    assert extra["environment"] == "prod"


def test_get_conversation_team_id_reads_metadata_team_id():
    class Record:
        extra = {"team_id": "sre-team"}

    assert get_conversation_team_id(Record()) == "sre-team"


def test_build_update_conversation_session_values_updates_title_and_timestamp():
    updated_at = datetime(2026, 6, 5, 11, 0, tzinfo=timezone.utc)

    values = build_update_conversation_session_values(
        title="自定义会话名",
        status=None,
        updated_at=updated_at,
    )

    assert values == {
        "title": "自定义会话名",
        "updated_at": updated_at,
    }


def test_build_query_conversation_messages_statement_filters_by_session():
    statement = build_query_conversation_messages_statement(
        session_id="session-001",
        limit=20,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "conversation_messages.session_id = 'session-001'" in compiled
    assert "LIMIT 20" in compiled


def test_build_query_conversation_messages_statement_supports_latest_page():
    before = datetime(2026, 6, 4, 10, 30, tzinfo=timezone.utc)
    statement = build_query_conversation_messages_statement(
        session_id="session-001",
        before_created_at=before,
        newest_first=True,
        limit=20,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "conversation_messages.created_at <" in compiled
    assert "ORDER BY conversation_messages.created_at DESC" in compiled
    assert "LIMIT 20" in compiled


def test_build_update_conversation_summary_values_maps_record_fields():
    class Existing:
        summary_id = "summary-001"

    class Record:
        known_facts = ["mysql failed"]
        checked_tools = ["query_events"]
        hypotheses = ["mysql unavailable"]
        pending_actions = ["check process"]
        compressed_context = "older context"
        message_count = 5
        updated_at = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)

    values = build_update_conversation_summary_values(Existing(), Record())

    assert values["known_facts"] == ["mysql failed"]
    assert values["checked_tools"] == ["query_events"]
    assert values["hypotheses"] == ["mysql unavailable"]
    assert values["pending_actions"] == ["check process"]
    assert values["compressed_context"] == "older context"
    assert values["message_count"] == 5

