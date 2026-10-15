from datetime import datetime, timedelta, timezone

from crossst.application.agents.tools import (
    resolve_time_window,
    serialize_historical_incident,
    serialize_recent_deployment,
    serialize_runbook,
    serialize_service_dependency,
)
from crossst.domain.models.context import RecentDeployment, ServiceDependency
from crossst.domain.models.knowledge import HistoricalIncident, Runbook
from crossst.infrastructure.storage.alerts import build_query_alerts_statement
from crossst.infrastructure.storage.incidents import build_query_incidents_statement


def test_resolve_time_window_defaults_start_from_minutes():
    end_time = datetime(2026, 6, 3, 14, 5, tzinfo=timezone.utc)

    start, end = resolve_time_window(minutes=5, end_time=end_time)

    assert end == end_time
    assert start == end_time - timedelta(minutes=5)


def test_build_query_alerts_statement_applies_filters():
    statement = build_query_alerts_statement(
        event_type="login_failed",
        severity="medium",
        host="app-prod-01",
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "alerts.event_type = 'login_failed'" in compiled
    assert "alerts.severity = 'medium'" in compiled
    assert "alerts.host = 'app-prod-01'" in compiled
    assert "LIMIT 10" in compiled


def test_build_query_incidents_statement_applies_filters():
    statement = build_query_incidents_statement(
        status="open",
        aggregate_key="host:app-prod-01",
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "incidents.status = 'open'" in compiled
    assert "incidents.aggregate_key = 'host:app-prod-01'" in compiled
    assert "LIMIT 10" in compiled


def test_serialize_service_dependency():
    dependency = ServiceDependency(
        dependency_id="dep-001",
        service="login-service",
        dependency_service="mysql",
        dependency_type="database",
        direction="outbound",
        description="login-service uses mysql for credentials.",
        is_active=True,
        extra={"critical": True},
        created_at=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 3, 14, 5, tzinfo=timezone.utc),
    )

    serialized = serialize_service_dependency(dependency)

    assert serialized["service"] == "login-service"
    assert serialized["dependency_service"] == "mysql"
    assert serialized["dependency_type"] == "database"
    assert serialized["metadata"] == {"critical": True}
    assert serialized["created_at"] == "2026-06-03T14:00:00+00:00"


def test_serialize_recent_deployment():
    deployment = RecentDeployment(
        deployment_id="deploy-001",
        service="login-service",
        environment="prod",
        version="2026.06.03.1",
        status="succeeded",
        actor="ci",
        summary="Deploy login-service.",
        extra={"commit": "abc123"},
        deployed_at=datetime(2026, 6, 3, 13, 55, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 3, 13, 56, tzinfo=timezone.utc),
    )

    serialized = serialize_recent_deployment(deployment)

    assert serialized["service"] == "login-service"
    assert serialized["environment"] == "prod"
    assert serialized["version"] == "2026.06.03.1"
    assert serialized["metadata"] == {"commit": "abc123"}
    assert serialized["deployed_at"] == "2026-06-03T13:55:00+00:00"


def test_serialize_runbook():
    runbook = Runbook(
        runbook_id="runbook-001",
        title="MySQL unavailable",
        service="login-service",
        component="mysql",
        problem_types=["mysql_connection_refused"],
        content="Check mysql process.",
        steps=["Check process", "Review error log"],
        tags=["database"],
        extra={"owner": "dba"},
        is_active=True,
        created_at=datetime(2026, 6, 3, 13, 55, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 3, 13, 56, tzinfo=timezone.utc),
    )

    serialized = serialize_runbook(runbook)

    assert serialized["runbook_id"] == "runbook-001"
    assert serialized["title"] == "MySQL unavailable"
    assert serialized["metadata"] == {"owner": "dba"}


def test_serialize_historical_incident():
    incident = HistoricalIncident(
        historical_incident_id="hist-001",
        title="MySQL outage affected login",
        service="login-service",
        component="mysql",
        root_cause="mysql_or_database_dependency_unavailable",
        summary="MySQL outage caused login errors.",
        resolution="Restarted mysql.",
        evidence_chain=["query_events returned mysql errors"],
        tags=["database"],
        extra={"severity": "high"},
        occurred_at=datetime(2026, 6, 3, 13, 55, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 3, 13, 56, tzinfo=timezone.utc),
    )

    serialized = serialize_historical_incident(incident)

    assert serialized["historical_incident_id"] == "hist-001"
    assert serialized["root_cause"] == "mysql_or_database_dependency_unavailable"
    assert serialized["metadata"] == {"severity": "high"}

