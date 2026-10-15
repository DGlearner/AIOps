"""
Detection Worker

职责：
- 持续消费 Kafka topic: normalized_events。
- 根据 detection rules 判断事件是否命中异常规则。
- 使用 Redis 做滑动窗口计数、阈值判断、去重和抑制。
- 当规则满足告警条件时，生成 Alert 并写入 Kafka topic: alerts。

边界：
- 只负责确定性规则检测和告警生成。
- 不调用 LLM，不做跨组件根因分析。
"""


import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from crossst.core.config import get_settings
from crossst.domain.schemas.alerts import AlertMessage
from crossst.domain.schemas.logs import NormalizedEvent
from crossst.services.detection.redis_window import (
    increment_window_counter,
    mark_alert_dedup,
)
from crossst.services.detection.rules import build_detection_context, evaluate_event
from crossst.infrastructure.storage.alerts import save_alert
from crossst.infrastructure.storage.kafka import (
    create_kafka_consumer,
    create_kafka_producer,
    send_json_message,
)
from crossst.infrastructure.storage.postgres import AsyncSessionLocal
from crossst.infrastructure.storage.redis import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()


async def detect_normalized_event(payload: dict[str, Any]) -> AlertMessage | None:
    event = NormalizedEvent.model_validate(payload)
    context = build_detection_context(event)

    if context is None:
        return None

    redis = await get_redis()
    count = await increment_window_counter(
        redis,
        key=context.counter_key,
        window_seconds=context.window_seconds,
    )

    alert = evaluate_event(
        event,
        count=count,
        window_seconds=context.window_seconds,
    )

    if alert is None:
        return None

    should_emit = await mark_alert_dedup(
        redis,
        fingerprint=alert.fingerprint,
        ttl_seconds=context.window_seconds,
    )

    if not should_emit:
        logger.info("Deduplicated alert fingerprint=%s", alert.fingerprint)
        return None

    return alert


async def persist_and_publish_alert(
    alert: AlertMessage,
    producer,
) -> None:
    async with AsyncSessionLocal() as session:
        await save_alert(session, alert)

    await send_json_message(
        producer,
        topic=settings.kafka_alerts_topic,
        key=alert.alert_id,
        value=alert.model_dump(mode="json"),
    )


async def run_detection_worker() -> None:
    consumer = await create_kafka_consumer(
        topic=settings.kafka_normalized_events_topic,
        group_id="detection-worker",
    )
    producer = await create_kafka_producer()

    logger.info(
        "Detection worker started: %s -> %s",
        settings.kafka_normalized_events_topic,
        settings.kafka_alerts_topic,
    )

    try:
        async for message in consumer:
            try:
                alert = await detect_normalized_event(message.value)
                if alert is None:
                    continue

                await persist_and_publish_alert(alert, producer)
                logger.info(
                    "Alert emitted alert_id=%s alert_type=%s severity=%s",
                    alert.alert_id,
                    alert.alert_type,
                    alert.severity,
                )
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Skip invalid normalized event payload: %s", exc)
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_detection_worker())


if __name__ == "__main__":
    main()
