import asyncio

from crossst.domain.models.alert import Alert  # noqa: F401
from crossst.domain.models.base import Base
from crossst.domain.models.conversation import (  # noqa: F401
    ConversationMessage,
    ConversationSession,
    ConversationSummary,
)
from crossst.domain.models.context import RecentDeployment, ServiceDependency  # noqa: F401
from crossst.domain.models.diagnosis import IncidentDiagnosis  # noqa: F401
from crossst.domain.models.event import NormalizedEventRecord  # noqa: F401
from crossst.domain.models.incident import Incident, IncidentAlert  # noqa: F401
from crossst.domain.models.knowledge import HistoricalIncident, Runbook  # noqa: F401
from crossst.domain.models.tool_call import ToolCallRecord  # noqa: F401
from crossst.infrastructure.storage.postgres import engine


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> None:
    asyncio.run(init_db())


if __name__ == "__main__":
    main()

