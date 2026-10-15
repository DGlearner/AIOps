import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from crossst.domain.models.knowledge import HistoricalIncident, Runbook
from crossst.infrastructure.storage.postgres import AsyncSessionLocal


def build_seed_records(now: datetime | None = None) -> tuple[Runbook, HistoricalIncident]:
    now = now or datetime.now(timezone.utc)
    return (
        Runbook(
            runbook_id="runbook-mysql-unavailable",
            title="MySQL unavailable affects login-service",
            service="login-service",
            component="mysql",
            problem_types=["mysql_connection_refused", "app_db_connection_error"],
            content=(
                "Use this runbook when login-service reports database connection "
                "errors and MySQL logs show connection refused or shutdown symptoms."
            ),
            steps=[
                "Check MySQL process status on the database host.",
                "Review MySQL error logs around the incident window.",
                "Verify login-service database connection pool and credentials.",
                "Confirm recovery by watching login-service DB error rate.",
            ],
            tags=["database", "mysql", "login-service"],
            extra={"owner": "dba", "environment": "prod"},
            is_active=True,
            created_at=now,
            updated_at=now,
        ),
        HistoricalIncident(
            historical_incident_id="hist-login-mysql-outage",
            title="MySQL outage caused login-service failures",
            service="login-service",
            component="mysql",
            root_cause="mysql_or_database_dependency_unavailable",
            summary=(
                "login-service produced DB connection errors while MySQL returned "
                "connection refused. User login failures increased during the same window."
            ),
            resolution="Restarted MySQL and verified login-service connection pool recovery.",
            evidence_chain=[
                "query_events found mysql_connection_refused records.",
                "query_events found app_db_connection_error records for login-service.",
                "Login failures dropped after MySQL recovered.",
            ],
            tags=["database", "mysql", "login-service"],
            extra={"severity": "high", "environment": "prod"},
            occurred_at=now - timedelta(days=14),
            created_at=now,
        ),
    )


async def seed_knowledge_data() -> dict[str, str]:
    runbook, historical_incident = build_seed_records()
    async with AsyncSessionLocal() as session:
        existing_runbook = await session.scalar(
            select(Runbook).where(Runbook.runbook_id == runbook.runbook_id)
        )
        if existing_runbook is None:
            session.add(runbook)
        else:
            existing_runbook.title = runbook.title
            existing_runbook.service = runbook.service
            existing_runbook.component = runbook.component
            existing_runbook.problem_types = runbook.problem_types
            existing_runbook.content = runbook.content
            existing_runbook.steps = runbook.steps
            existing_runbook.tags = runbook.tags
            existing_runbook.extra = runbook.extra
            existing_runbook.is_active = runbook.is_active
            existing_runbook.updated_at = runbook.updated_at

        existing_incident = await session.scalar(
            select(HistoricalIncident).where(
                HistoricalIncident.historical_incident_id
                == historical_incident.historical_incident_id
            )
        )
        if existing_incident is None:
            session.add(historical_incident)
        else:
            existing_incident.title = historical_incident.title
            existing_incident.service = historical_incident.service
            existing_incident.component = historical_incident.component
            existing_incident.root_cause = historical_incident.root_cause
            existing_incident.summary = historical_incident.summary
            existing_incident.resolution = historical_incident.resolution
            existing_incident.evidence_chain = historical_incident.evidence_chain
            existing_incident.tags = historical_incident.tags
            existing_incident.extra = historical_incident.extra
            existing_incident.occurred_at = historical_incident.occurred_at

        await session.commit()

    return {
        "runbook_id": runbook.runbook_id,
        "historical_incident_id": historical_incident.historical_incident_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed runbook and historical incident data.")
    parser.parse_args()

    result = asyncio.run(seed_knowledge_data())
    print(result)


if __name__ == "__main__":
    main()

