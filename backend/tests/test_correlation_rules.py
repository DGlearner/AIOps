from crossst.domain.schemas.alerts import AlertMessage
from crossst.services.correlation.rules import (
    build_aggregate_key,
    build_incident_from_alerts,
)


def test_build_aggregate_key_prefers_service():
    alert = AlertMessage(
        event_id="evt-001",
        raw_log_id="raw-001",
        alert_type="app_db_connection_error_threshold",
        event_type="app_db_connection_error",
        severity="medium",
        source_type="app_service",
        component="application",
        host="app-prod-01",
        service="login-service",
        message="DB connection refused",
        summary="login-service DB error",
        count=2,
        window_seconds=300,
        fingerprint="app_db_connection_error:login-service:app-prod-01",
    )

    assert build_aggregate_key(alert) == "service:login-service"


def test_build_incident_from_alerts_uses_highest_severity():
    alerts = [
        AlertMessage(
            alert_id="alert-001",
            event_id="evt-001",
            raw_log_id="raw-001",
            alert_type="ssh_login_failed_threshold",
            event_type="login_failed",
            severity="medium",
            source_type="linux",
            component="ssh",
            host="app-prod-01",
            service=None,
            message="Failed password",
            summary="SSH login failed",
            count=3,
            window_seconds=300,
            fingerprint="login_failed:app-prod-01:8.8.8.8",
        ),
        AlertMessage(
            alert_id="alert-002",
            event_id="evt-002",
            raw_log_id="raw-002",
            alert_type="mysql_connection_refused",
            event_type="mysql_connection_refused",
            severity="high",
            source_type="mysql",
            component="mysql",
            host="app-prod-01",
            service=None,
            message="Can't connect",
            summary="MySQL connection refused",
            count=1,
            window_seconds=300,
            fingerprint="mysql_connection_refused:app-prod-01",
        ),
    ]

    incident = build_incident_from_alerts(
        incident_id="incident-001",
        aggregate_key="host:app-prod-01",
        alerts=alerts,
    )

    assert incident.severity == "high"
    assert incident.alert_count == 2
    assert incident.affected_hosts == ["app-prod-01"]
    assert incident.event_types == ["login_failed", "mysql_connection_refused"]

