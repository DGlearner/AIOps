from crossst.domain.schemas.logs import NormalizedEvent
from crossst.services.detection.rules import build_detection_context, evaluate_event


def make_login_failed_event() -> NormalizedEvent:
    return NormalizedEvent(
        raw_log_id="raw-001",
        event_id="evt-001",
        timestamp="2026-06-03T14:01:59.364803Z",
        source_type="linux",
        source_name="auth.log",
        host="app-prod-01",
        service=None,
        component="ssh",
        event_type="login_failed",
        message="Failed password for root from 8.8.8.8 port 52231 ssh2",
        severity_hint="low",
        fields={"user": "root", "src_ip": "8.8.8.8", "port": 52231},
        tags=["linux", "auth", "ssh", "security"],
    )


def test_login_failed_below_threshold_does_not_alert():
    event = make_login_failed_event()

    context = build_detection_context(event)
    alert = evaluate_event(event, count=2, window_seconds=context.window_seconds)

    assert alert is None


def test_login_failed_at_threshold_alerts():
    event = make_login_failed_event()

    context = build_detection_context(event)
    alert = evaluate_event(event, count=3, window_seconds=context.window_seconds)

    assert alert is not None
    assert alert.alert_type == "ssh_login_failed_threshold"
    assert alert.severity == "medium"
    assert alert.fingerprint == "login_failed:app-prod-01:8.8.8.8"


def test_mysql_connection_refused_alerts_immediately():
    event = NormalizedEvent(
        raw_log_id="raw-002",
        event_id="evt-002",
        timestamp="2026-06-03T14:01:59.364803Z",
        source_type="mysql",
        source_name="mysql-error.log",
        host="db-prod-01",
        service=None,
        component="mysql",
        event_type="mysql_connection_refused",
        message="Can't connect to local MySQL server through socket",
        severity_hint="high",
        fields={"reason": "connection_refused"},
        tags=["mysql", "database", "availability"],
    )

    context = build_detection_context(event)
    alert = evaluate_event(event, count=1, window_seconds=context.window_seconds)

    assert alert is not None
    assert alert.alert_type == "mysql_connection_refused"
    assert alert.severity == "high"
    assert alert.fingerprint == "mysql_connection_refused:db-prod-01"
