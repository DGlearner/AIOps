from crossst.workers.diagnosis_worker import build_incident_context_from_payload


def test_build_incident_context_from_payload():
    payload = {
        "incident_id": "incident-001",
        "title": "HIGH incident on host:db-prod-01",
        "severity": "high",
        "status": "open",
        "aggregate_key": "host:db-prod-01",
        "time_window_start": "2026-06-03T14:40:00Z",
        "time_window_end": "2026-06-03T14:45:00Z",
        "alert_ids": ["alert-001"],
        "alert_count": 1,
        "affected_hosts": ["db-prod-01"],
        "affected_services": [],
        "event_types": ["mysql_connection_refused"],
        "summary": "MySQL connection refused incident.",
        "fields": {},
        "created_at": "2026-06-03T14:45:01Z",
        "updated_at": "2026-06-03T14:45:01Z",
    }

    context = build_incident_context_from_payload(payload)

    assert context["incident_id"] == "incident-001"
    assert context["event_types"] == ["mysql_connection_refused"]
    assert context["affected_hosts"] == ["db-prod-01"]
    assert context["time_window_start"] == "2026-06-03T14:40:00+00:00"

