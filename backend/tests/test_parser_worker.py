from crossst.workers.parser_worker import normalize_raw_log_payload


def test_normalize_raw_log_payload_outputs_normalized_event():
    payload = {
        "log_id": "raw-001",
        "source_type": "linux",
        "source_name": "auth.log",
        "message": (
            "Jun  3 14:03:12 app-prod-01 sshd[2311]: "
            "Failed password for root from 1.2.3.4 port 52231 ssh2"
        ),
        "host": None,
        "service": None,
        "timestamp": "2026-06-03T13:23:50.032158Z",
    }

    event = normalize_raw_log_payload(payload)

    assert event.raw_log_id == "raw-001"
    assert event.source_type == "linux"
    assert event.event_type == "login_failed"
    assert event.host == "app-prod-01"
    assert event.fields["src_ip"] == "1.2.3.4"
