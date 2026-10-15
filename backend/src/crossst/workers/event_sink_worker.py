"""
Event Sink Worker

职责：
- 持续消费 Kafka topic: normalized_events。
- 将标准化事件持久化到 PostgreSQL。
- 为后续查询、回放、Agent 工具调用和人工排查提供事件数据。

边界：
- 只负责事件落库。
- 不改变事件含义，不生成告警。
"""


import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from crossst.core.config import get_settings
from crossst.domain.schemas.logs import NormalizedEvent
from crossst.infrastructure.storage.events import save_normalized_event
from crossst.infrastructure.storage.kafka import create_kafka_consumer
from crossst.infrastructure.storage.postgres import AsyncSessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()


def parse_normalized_event_payload(payload: dict[str, Any]) -> NormalizedEvent:
    return NormalizedEvent.model_validate(payload)


async def persist_normalized_event_payload(payload: dict[str, Any]) -> NormalizedEvent:
    event = parse_normalized_event_payload(payload)
    async with AsyncSessionLocal() as session:
        await save_normalized_event(session, event)
    return event


async def run_event_sink_worker() -> None:
    consumer = await create_kafka_consumer(
        topic=settings.kafka_normalized_events_topic,
        group_id="event-sink-worker",
    )

    logger.info(
        "Event sink worker started: %s -> PostgreSQL normalized_events",
        settings.kafka_normalized_events_topic,
    )

    try:
        async for message in consumer:
            try:
                event = await persist_normalized_event_payload(message.value)
                logger.info(
                    "Persisted normalized event event_id=%s event_type=%s",
                    event.event_id,
                    event.event_type,
                )
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Skip invalid normalized event payload: %s", exc)
    finally:
        await consumer.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_event_sink_worker())


if __name__ == "__main__":
    main()

