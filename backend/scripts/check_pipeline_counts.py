import argparse
import asyncio
import json

from sqlalchemy import func, select

from crossst.domain.models.alert import Alert
from crossst.domain.models.context import RecentDeployment, ServiceDependency
from crossst.domain.models.conversation import (
    ConversationMessage,
    ConversationSession,
    ConversationSummary,
)
from crossst.domain.models.diagnosis import IncidentDiagnosis
from crossst.domain.models.event import NormalizedEventRecord
from crossst.domain.models.incident import Incident
from crossst.domain.models.knowledge import HistoricalIncident, Runbook
from crossst.domain.models.tool_call import ToolCallRecord
from crossst.application.agents.tools import query_redis_counters_tool
from crossst.infrastructure.storage.kafka import create_kafka_consumer
from crossst.infrastructure.storage.postgres import AsyncSessionLocal


TOPICS = ["raw_logs", "normalized_events", "alerts", "incidents"]
DATABASE_COUNT_MODELS = {
    "events": NormalizedEventRecord,
    "alerts": Alert,
    "incidents": Incident,
    "diagnoses": IncidentDiagnosis,
    "tool_calls": ToolCallRecord,
    "conversation_sessions": ConversationSession,
    "conversation_messages": ConversationMessage,
    "conversation_summaries": ConversationSummary,
    "runbooks": Runbook,
    "historical_incidents": HistoricalIncident,
    "service_dependencies": ServiceDependency,
    "recent_deployments": RecentDeployment,
}


async def get_topic_offsets(topic: str) -> int:
    consumer = await create_kafka_consumer(
        topic=topic,
        group_id=f"count-checker-{topic}",
    )
    try:
        partitions = consumer.assignment()
        if not partitions:
            await consumer.seek_to_beginning()
            partitions = consumer.assignment()
        end_offsets = await consumer.end_offsets(partitions)
        return sum(end_offsets.values())
    finally:
        await consumer.stop()


async def get_database_counts() -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        counts = {}
        for name, model in DATABASE_COUNT_MODELS.items():
            count = await session.scalar(select(func.count()).select_from(model))
            counts[name] = int(count or 0)
    return counts


async def get_redis_counter_snapshot() -> dict[str, object]:
    return await query_redis_counters_tool(pattern="counter:*", limit=500)


async def collect_counts() -> dict[str, object]:
    topic_offsets: dict[str, int | None] = {}
    for topic in TOPICS:
        try:
            topic_offsets[topic] = await get_topic_offsets(topic)
        except Exception:
            topic_offsets[topic] = None

    return {
        "kafka_offsets": topic_offsets,
        "redis": await get_redis_counter_snapshot(),
        "postgres": await get_database_counts(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check MVP pipeline counts.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    args = parser.parse_args()

    counts = asyncio.run(collect_counts())
    print(json.dumps(counts, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()

