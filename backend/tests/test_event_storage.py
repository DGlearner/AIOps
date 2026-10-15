from datetime import datetime, timezone

from crossst.infrastructure.storage.events import build_query_events_statement


def test_build_query_events_statement_applies_filters():
    statement = build_query_events_statement(
        source_type="mysql",
        event_type="mysql_connection_refused",
        host="db-prod-01",
        start_time=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 3, 14, 5, tzinfo=timezone.utc),
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "normalized_events.source_type = 'mysql'" in compiled
    assert "normalized_events.event_type = 'mysql_connection_refused'" in compiled
    assert "normalized_events.host = 'db-prod-01'" in compiled
    assert "LIMIT 10" in compiled

