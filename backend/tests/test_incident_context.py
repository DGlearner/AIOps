from datetime import datetime, timezone

from crossst.application.agents.incident_context import build_incident_context_from_record
from crossst.infrastructure.storage.incidents import build_get_incident_by_alert_id_statement


class FakeIncident:
    incident_id = "incident-001"
    summary = "MySQL connection refused incident."
    event_types = ["mysql_connection_refused"]
    affected_hosts = ["db-prod-01"]
    affected_services = []
    aggregate_key = "host:db-prod-01"
    time_window_start = datetime(2026, 6, 3, 14, 40, tzinfo=timezone.utc)
    time_window_end = datetime(2026, 6, 3, 14, 45, tzinfo=timezone.utc)


def test_build_incident_context_from_record():
    context = build_incident_context_from_record(FakeIncident())

    assert context["incident_id"] == "incident-001"
    assert context["event_types"] == ["mysql_connection_refused"]
    assert context["time_window_start"] == "2026-06-03T14:40:00+00:00"


def test_build_get_incident_by_alert_id_statement_joins_incident_alerts():
    statement = build_get_incident_by_alert_id_statement("alert-001")

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "JOIN incident_alerts" in compiled
    assert "incident_alerts.alert_id = 'alert-001'" in compiled

