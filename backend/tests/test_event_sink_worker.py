from crossst.workers.event_sink_worker import parse_normalized_event_payload


def test_parse_normalized_event_payload():
    payload = {
        "event_id": "evt-001",
        "raw_log_id": "raw-001",
        "timestamp": "2026-06-03T14:01:59.364803Z",
        "source_type": "mysql",
        "source_name": "mysql-error.log",
        "host": "db-prod-01",
        "service": None,
        "component": "mysql",
        "event_type": "mysql_connection_refused",
        "message": "Can't connect to local MySQL server through socket",
        "severity_hint": "high",
        "fields": {"reason": "connection_refused"},
        "tags": ["mysql", "database", "availability"],
    }

    event = parse_normalized_event_payload(payload)

    assert event.event_id == "evt-001"
    assert event.source_type == "mysql"
    assert event.event_type == "mysql_connection_refused"

