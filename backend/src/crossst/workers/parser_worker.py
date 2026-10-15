"""
Parser Worker

职责：
- 持续消费 Kafka topic: raw_logs。
- 将原始日志按 source_type 分发给对应 parser，例如 regex_linux、regex_mysql、regex_app。
- 把解析后的日志转换为统一的 NormalizedEvent 结构。
- 将标准化事件写入 Kafka topic: normalized_events。

边界：
- 只负责日志解析和结构化。
- 不做异常判断、不做计数、不生成告警。
"""

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from crossst.core.config import get_settings
from crossst.parsers.parsers_route import parse_raw_log
from crossst.domain.schemas.logs import NormalizedEvent, RawLogMessage
from crossst.infrastructure.storage.kafka import (
    create_kafka_consumer,
    create_kafka_producer,
    send_json_message,
)


logger = logging.getLogger(__name__)
settings = get_settings()


def normalize_raw_log_payload(payload: dict[str, Any]) -> NormalizedEvent:
    raw_log = RawLogMessage.model_validate(payload)
    return parse_raw_log(raw_log)


async def run_parser_worker() -> None:
    consumer = await create_kafka_consumer(
        topic=settings.kafka_raw_logs_topic,
        group_id="parser-worker",
    )
    producer = await create_kafka_producer()

    logger.info(
        "Parser worker started: %s -> %s",
        settings.kafka_raw_logs_topic,
        settings.kafka_normalized_events_topic,
    )

    try:
        async for message in consumer:
            try:
                event = normalize_raw_log_payload(message.value)
                await send_json_message(
                    producer,
                    topic=settings.kafka_normalized_events_topic,
                    key=event.event_id,
                    value=event.model_dump(mode="json"),
                )
                logger.info(
                    "Normalized raw_log_id=%s event_type=%s",
                    event.raw_log_id,
                    event.event_type,
                )
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Skip invalid raw log payload: %s", exc)
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_parser_worker())


if __name__ == "__main__":
    main()
