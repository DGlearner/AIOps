from datetime import datetime, timezone

from crossst.infrastructure.storage.context import (
    build_query_recent_deployments_statement,
    build_query_service_dependencies_statement,
)


def test_build_query_service_dependencies_statement_applies_filters():
    statement = build_query_service_dependencies_statement(
        service="login-service",
        dependency_type="database",
        active_only=True,
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "service_dependencies.service = 'login-service'" in compiled
    assert "service_dependencies.dependency_type = 'database'" in compiled
    assert "service_dependencies.is_active IS true" in compiled
    assert "LIMIT 10" in compiled


def test_build_query_recent_deployments_statement_applies_filters():
    statement = build_query_recent_deployments_statement(
        service="login-service",
        environment="prod",
        start_time=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "recent_deployments.service = 'login-service'" in compiled
    assert "recent_deployments.environment = 'prod'" in compiled
    assert "recent_deployments.deployed_at >=" in compiled
    assert "recent_deployments.deployed_at <=" in compiled
    assert "LIMIT 10" in compiled

