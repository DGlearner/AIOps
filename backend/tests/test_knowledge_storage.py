from crossst.infrastructure.storage.knowledge import (
    build_query_historical_incidents_statement,
    build_query_runbooks_statement,
)


def test_build_query_runbooks_statement_applies_filters():
    statement = build_query_runbooks_statement(
        query="mysql",
        service="login-service",
        component="mysql",
        active_only=True,
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "runbooks.service = 'login-service'" in compiled
    assert "runbooks.component = 'mysql'" in compiled
    assert "runbooks.is_active IS true" in compiled
    assert "LIMIT 10" in compiled


def test_build_query_runbooks_statement_filters_by_tag():
    statement = build_query_runbooks_statement(tag="database", limit=10)

    compiled = str(statement.compile())

    assert "runbooks.tags" in compiled


def test_build_query_historical_incidents_statement_applies_filters():
    statement = build_query_historical_incidents_statement(
        query="mysql",
        service="login-service",
        root_cause="mysql_or_database_dependency_unavailable",
        limit=10,
    )

    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "historical_incidents.service = 'login-service'" in compiled
    assert "historical_incidents.root_cause = 'mysql_or_database_dependency_unavailable'" in compiled
    assert "LIMIT 10" in compiled


def test_build_query_historical_incidents_statement_filters_by_tag():
    statement = build_query_historical_incidents_statement(tag="database", limit=10)

    compiled = str(statement.compile())

    assert "historical_incidents.tags" in compiled

