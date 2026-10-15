import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from crossst.domain.models.context import RecentDeployment, ServiceDependency
from crossst.infrastructure.storage.postgres import AsyncSessionLocal


def build_seed_records(now: datetime | None = None) -> tuple[ServiceDependency, RecentDeployment]:
    now = now or datetime.now(timezone.utc)
    return (
        ServiceDependency(
            dependency_id="dep-login-service-mysql",
            service="login-service",
            dependency_service="mysql",
            dependency_type="database",
            direction="outbound",
            description="login-service depends on mysql for credential and session data.",
            is_active=True,
            extra={"critical": True, "environment": "prod"},
            created_at=now,
            updated_at=now,
        ),
        RecentDeployment(
            deployment_id=str(uuid4()),
            service="login-service",
            environment="prod",
            version="mvp-demo",
            status="succeeded",
            actor="seed-script",
            summary="Seed deployment record for diagnosis tool smoke tests.",
            extra={"source": "seed_context_data.py"},
            deployed_at=now - timedelta(minutes=10),
            created_at=now,
        ),
    )


async def seed_context_data() -> dict[str, str]:
    dependency, deployment = build_seed_records()
    async with AsyncSessionLocal() as session:
        existing_dependency = await session.scalar(
            select(ServiceDependency).where(
                ServiceDependency.dependency_id == dependency.dependency_id
            )
        )
        if existing_dependency is None:
            session.add(dependency)
        else:
            existing_dependency.dependency_service = dependency.dependency_service
            existing_dependency.dependency_type = dependency.dependency_type
            existing_dependency.direction = dependency.direction
            existing_dependency.description = dependency.description
            existing_dependency.is_active = dependency.is_active
            existing_dependency.extra = dependency.extra
            existing_dependency.updated_at = dependency.updated_at

        session.add(deployment)
        await session.commit()

    return {
        "dependency_id": dependency.dependency_id,
        "deployment_id": deployment.deployment_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed service context data for MVP diagnosis.")
    parser.parse_args()

    result = asyncio.run(seed_context_data())
    print(result)


if __name__ == "__main__":
    main()

